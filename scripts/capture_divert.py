"""本机 WinDivert 改道抓包。

收齐仓库分页后写入本机库。配置了 ROCO_CLOUD_URL 时，同一份快照会推到云端。
不打开网页。需要管理员权限，以及 uv sync --extra capture。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    if sys.platform != "win32":
        print("改道抓包只在 Windows 上运行。云端只浏览仓库，数据由本机推送。")
        return 1
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from scripts.game_relay import stop_relay
    from scripts.packet_store import record_divert

    def progress(message, current=0, total=0):
        del current, total
        print(message, flush=True)

    try:
        result = record_divert(progress=progress)
    except KeyboardInterrupt:
        stop_relay()
        print("已停止改道记录")
        return 130
    push = (result.get("sync") or {}).get("push") or {}
    if push and not push.get("ok") and not push.get("skipped"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
