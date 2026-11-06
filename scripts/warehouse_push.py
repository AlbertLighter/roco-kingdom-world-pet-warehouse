"""把收齐的仓库快照推到云端。

本机改道在分页收齐时调用这里。失败可以再执行本文件重试，不必打开网页。
云端地址和令牌来自 ROCO_CLOUD_URL、ROCO_SYNC_TOKEN。没配地址就只留在本机。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = PROJECT_ROOT / "captures" / "warehouse_snapshot.json"
IMPORT_PATH = "/api/sync/warehouse"
_sync_logger = logging.getLogger("sync")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def cloud_settings(environ: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if environ is None else environ
    url = str(env.get("ROCO_CLOUD_URL") or "").strip()
    token = str(env.get("ROCO_SYNC_TOKEN") or "").strip()
    return url, token


def import_endpoint(base: str) -> str:
    text = base.strip().rstrip("/")
    if text.endswith(IMPORT_PATH):
        return text
    return text + IMPORT_PATH


def save_warehouse_snapshot(records: list[dict], path: Path | None = None) -> Path:
    """原子写下最近一次收齐的仓库，供失败后重试。"""
    target = path or SNAPSHOT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "complete": True,
        "pets": records,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)
    return target


def load_warehouse_snapshot(path: Path | None = None) -> dict:
    target = path or SNAPSHOT_PATH
    if not target.is_file():
        raise FileNotFoundError(
            f"没有仓库快照 {target}。先在 Windows 上收齐一次仓库分页，再重试推送。"
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"complete": True, "pets": data}
    if not isinstance(data, dict):
        raise ValueError(f"仓库快照不是对象：{target}")
    return data


def describe_push(result: dict, count: int) -> str:
    if result.get("skipped"):
        return (
            "未配置 ROCO_CLOUD_URL，完整仓库只写在本机。"
            "配置后可执行 python scripts/warehouse_push.py 再推一次。"
        )
    if result.get("ok"):
        remote = result.get("result") if isinstance(result.get("result"), dict) else {}
        return (
            f"已把 {count} 只精灵推到云端："
            f"新增 {remote.get('new', 0)}，更新 {remote.get('updated', 0)}，"
            f"标记放生 {remote.get('released', 0)}"
        )
    reason = result.get("reason") or "未知错误"
    return f"推送云端失败：{reason}。可执行 python scripts/warehouse_push.py 重试。"


def _retryable_status(status: int) -> bool:
    return status in {408, 429} or status >= 500


def _response_detail(response) -> str:
    body: object
    try:
        body = response.json()
    except Exception:
        body = None
    if isinstance(body, dict) and body.get("detail"):
        return str(body["detail"])[:300]
    text = getattr(response, "text", "") or ""
    return text[:300]


def push_warehouse_snapshot(
    records: list[dict],
    *,
    complete: bool = True,
    environ: Mapping[str, str] | None = None,
    attempts: int = 3,
    poster: Callable | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict:
    """POST 到云端 /api/sync/warehouse。网络错误和 5xx 会重试，认证失败不重试。"""
    url, token = cloud_settings(environ)
    if not url:
        _sync_logger.info("未配置 ROCO_CLOUD_URL，跳过仓库推送")
        return {"ok": False, "skipped": True, "reason": "未配置 ROCO_CLOUD_URL"}
    if not token:
        _sync_logger.error("已配置 ROCO_CLOUD_URL，但缺少 ROCO_SYNC_TOKEN，无法推送")
        return {"ok": False, "skipped": False, "reason": "缺少 ROCO_SYNC_TOKEN"}

    endpoint = import_endpoint(url)
    payload = {"pets": records, "complete": bool(complete)}
    send = poster or _post
    tries = max(1, int(attempts))
    reason = "未知错误"
    for attempt in range(1, tries + 1):
        try:
            response = send(endpoint, payload, token)
        except (requests.RequestException, OSError) as exc:
            reason = str(exc)
            _sync_logger.warning("仓库推送失败（第 %s/%s 次）：%s", attempt, tries, reason)
            if attempt < tries:
                _pause(attempt, sleep)
            continue
        status = int(getattr(response, "status_code", 0) or 0)
        if status < 400:
            body: object
            try:
                body = response.json()
            except Exception:
                body = {"raw": _response_detail(response)}
            _sync_logger.info("仓库已推送到 %s，共 %s 只", endpoint, len(records))
            return {"ok": True, "skipped": False, "status": status, "result": body}
        reason = f"HTTP {status} {_response_detail(response)}".strip()
        _sync_logger.warning("仓库推送失败（第 %s/%s 次）：%s", attempt, tries, reason)
        if not _retryable_status(status) or attempt >= tries:
            break
        _pause(attempt, sleep)
    return {"ok": False, "skipped": False, "reason": reason}


def start_warehouse_push(
    records: list[dict],
    *,
    emit=None,
    environ: Mapping[str, str] | None = None,
    attempts: int = 3,
    poster: Callable | None = None,
    sleep: Callable[[float], None] | None = None,
    snapshot_path: Path | None = None,
) -> threading.Thread:
    """先写下快照，再在后台推送，避免挡住改道转发。"""
    frozen = json.loads(json.dumps(records, ensure_ascii=False))
    holder: dict = {"result": None}
    snapshot = ""
    try:
        snapshot = str(save_warehouse_snapshot(frozen, snapshot_path))
    except OSError as exc:
        _sync_logger.error("无法写下仓库快照：%s", exc)

    def run() -> None:
        result = push_warehouse_snapshot(
            frozen,
            complete=True,
            environ=environ,
            attempts=attempts,
            poster=poster,
            sleep=sleep,
        )
        result["snapshot"] = snapshot
        message = describe_push(result, len(frozen))
        if emit is not None:
            emit(message)
        else:
            _sync_logger.info("%s", message)
        holder["result"] = result

    thread = threading.Thread(target=run, name="warehouse-push", daemon=True)
    thread.push_result = holder  # type: ignore[attr-defined]
    thread.start()
    return thread


def _post(endpoint: str, payload: dict, token: str):
    return requests.post(
        endpoint,
        json=payload,
        headers={"X-Roco-Token": token},
        timeout=20,
    )


def _pause(attempt: int, sleep: Callable[[float], None] | None) -> None:
    delay = min(2 ** (attempt - 1), 8)
    if sleep is None:
        time.sleep(delay)
    else:
        sleep(delay)


def _load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def main() -> int:
    _load_project_env()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        payload = load_warehouse_snapshot()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(exc)
        return 1
    pets = payload.get("pets")
    if not isinstance(pets, list):
        print("快照里没有 pets 数组")
        return 1
    result = push_warehouse_snapshot(pets, complete=bool(payload.get("complete", True)))
    print(describe_push(result, len(pets)))
    if result.get("ok"):
        return 0
    if result.get("skipped"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
