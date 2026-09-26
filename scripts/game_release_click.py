"""在游戏窗口里按盒子顺序点击建议放生的格子。不向游戏连接写入数据。"""

from __future__ import annotations

import ctypes
import json
import threading
import time
from ctypes import wintypes
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PATH = PROJECT_ROOT / "captures" / "click_calibration.json"
WINDOW_TITLE = "洛克王国"
COLS = 6
ROWS = 5
MAX_CLICKS = 90
STEPS = ("first", "last", "selected", "release", "next")
STEP_LABELS = {
    "first": "请点击格子左上角第一只精灵的中心",
    "last": "请点击格子右下角最后一只精灵的中心",
    "selected": "请点击「已选」旁边的数字",
    "release": "请点击「放生」按钮",
    "next": "请点击下一盒的右箭头",
    "confirm": "请点击放生确认按钮；如果没有确认框，在页面上跳过",
}

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

_state_lock = threading.Lock()
_calibration = {
    "listening": False,
    "step": "",
    "points": {},
    "client": None,
}
_stop = threading.Event()
_hook_thread: threading.Thread | None = None


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def find_game_window() -> int:
    found = []

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if WINDOW_TITLE in buffer.value:
            found.append(hwnd)
        return True

    prototype = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(prototype(visit), 0)
    return found[0] if found else 0


def client_size(hwnd: int) -> tuple[int, int]:
    rect = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def _client_point(hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int]:
    point = POINT(screen_x, screen_y)
    user32.ScreenToClient(hwnd, ctypes.byref(point))
    return point.x, point.y


def click_client(hwnd: int, x: float, y: float) -> None:
    point = POINT(int(x), int(y))
    user32.ClientToScreen(hwnd, ctypes.byref(point))
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.08)
    user32.SetCursorPos(point.x, point.y)
    time.sleep(0.04)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.12)


def load_calibration() -> dict | None:
    if not CALIBRATION_PATH.is_file():
        return None
    return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))


def calibration_status() -> dict:
    with _state_lock:
        listening = _calibration["listening"]
        step = _calibration["step"]
        points = dict(_calibration["points"])
    saved = load_calibration()
    return {
        "listening": listening,
        "step": step,
        "prompt": STEP_LABELS.get(step, ""),
        "captured": list(points),
        "ready": bool(saved and all(name in saved.get("points", {}) for name in STEPS)),
    }


def _remember_click(x: int, y: int) -> None:
    hwnd = find_game_window()
    if not hwnd or user32.GetForegroundWindow() != hwnd:
        return
    cx, cy = _client_point(hwnd, x, y)
    width, height = client_size(hwnd)
    with _state_lock:
        if not _calibration["listening"]:
            return
        step = _calibration["step"]
        _calibration["points"][step] = {"x": cx, "y": cy}
        if step == "confirm":
            _finish_calibration(width, height)
            return
        index = STEPS.index(step) + 1 if step in STEPS else len(STEPS)
        if index >= len(STEPS):
            _calibration["step"] = "confirm"
        else:
            _calibration["step"] = STEPS[index]


def _finish_calibration(width: int, height: int) -> None:
    payload = {
        "client": {"width": width, "height": height},
        "points": _calibration["points"],
    }
    CALIBRATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _calibration["listening"] = False
    _calibration["step"] = ""


def skip_confirm() -> None:
    hwnd = find_game_window()
    if not hwnd:
        raise RuntimeError("没有找到游戏窗口")
    width, height = client_size(hwnd)
    with _state_lock:
        if _calibration["step"] != "confirm":
            raise RuntimeError("还没到确认按钮这一步")
        _finish_calibration(width, height)


def start_calibration() -> None:
    global _hook_thread
    hwnd = find_game_window()
    if not hwnd:
        raise RuntimeError("没有找到游戏窗口。请先打开精灵仓库。")
    with _state_lock:
        _calibration["listening"] = True
        _calibration["step"] = STEPS[0]
        _calibration["points"] = {}
        _calibration["client"] = client_size(hwnd)
    if _hook_thread is None or not _hook_thread.is_alive():
        _hook_thread = threading.Thread(target=_hook_loop, daemon=True)
        _hook_thread.start()


def _hook_loop() -> None:
    prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    holder = {"hook": None}

    def handler(code, wparam, lparam):
        if code >= 0 and wparam == 0x0201:
            point = ctypes.cast(lparam, ctypes.POINTER(POINT)).contents
            _remember_click(point.x, point.y)
        return user32.CallNextHookEx(holder["hook"], code, wparam, lparam)

    callback = prototype(handler)
    holder["hook"] = user32.SetWindowsHookExW(14, callback, None, 0)
    message = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))
    if holder["hook"]:
        user32.UnhookWindowsHookEx(holder["hook"])
    del callback


def cell_point(calib: dict, slot: int) -> tuple[float, float]:
    first = calib["points"]["first"]
    last = calib["points"]["last"]
    column = slot % COLS
    row = slot // COLS
    x = first["x"] + (last["x"] - first["x"]) * column / (COLS - 1)
    y = first["y"] + (last["y"] - first["y"]) * row / (ROWS - 1)
    return x, y


def request_stop() -> None:
    _stop.set()


def running() -> bool:
    return not _stop.is_set() and _stop is not None


def read_selected_count(hwnd: int, calib: dict) -> int | None:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageChops
    except ImportError as exc:
        raise RuntimeError("核对已选数量需要 Pillow。请执行 uv sync --extra capture") from exc
    point = calib["points"]["selected"]
    image = _capture_client(hwnd, int(point["x"]) - 28, int(point["y"]) - 16, 56, 32)
    binary = image.convert("L").point(lambda value: 255 if value > 170 else 0)
    bbox = binary.getbbox()
    if not bbox:
        return None
    crop = binary.crop(bbox)
    best_text = ""
    best_score = 10**9
    font_path = Path(r"C:\Windows\Fonts\arialbd.ttf")
    if not font_path.is_file():
        font_path = Path(r"C:\Windows\Fonts\arial.ttf")
    for size in (16, 18, 20, 22):
        font = ImageFont.truetype(str(font_path), size)
        for number in range(0, 31):
            canvas = Image.new("L", crop.size, 0)
            draw = ImageDraw.Draw(canvas)
            draw.text((0, 0), str(number), fill=255, font=font)
            diff = ImageChops.difference(crop, canvas.resize(crop.size))
            score = sum(diff.getdata())
            if score < best_score:
                best_score = score
                best_text = str(number)
    if best_score > crop.size[0] * crop.size[1] * 80:
        return None
    return int(best_text) if best_text else None


def _capture_client(hwnd: int, x: int, y: int, width: int, height: int):
    from PIL import Image

    origin = POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    desktop = user32.GetDC(0)
    memory = gdi32.CreateCompatibleDC(desktop)
    bitmap = gdi32.CreateCompatibleBitmap(desktop, width, height)
    gdi32.SelectObject(memory, bitmap)
    gdi32.BitBlt(memory, 0, 0, width, height, desktop, origin.x, origin.y, 0x00CC0020)
    info = _bitmap_info(width, height)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(info), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory)
    user32.ReleaseDC(0, desktop)
    image = Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, -1)
    return image


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _bitmap_info(width: int, height: int) -> BITMAPINFOHEADER:
    info = BITMAPINFOHEADER()
    info.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    info.biWidth = width
    info.biHeight = -height
    info.biPlanes = 1
    info.biBitCount = 32
    return info


def run_release(groups: list[tuple[int, list[int]]], progress=None) -> dict:
    """groups 是 (盒子编号, 格位列表)，按盒子编号排序。格位是 0 到 29。"""
    calib = load_calibration()
    if not calib or any(name not in calib.get("points", {}) for name in STEPS):
        raise RuntimeError("还没有完成点击校准")
    hwnd = find_game_window()
    if not hwnd:
        raise RuntimeError("没有找到游戏窗口")
    width, height = client_size(hwnd)
    saved = calib.get("client") or {}
    if saved.get("width") != width or saved.get("height") != height:
        raise RuntimeError("游戏窗口大小和校准时不一致，请重新校准")
    _stop.clear()
    clicked = 0
    if groups:
        progress and progress(f"请先打开 {groups[0][0]} 号精灵盒子，并处于勾选模式", 0, 0)
        time.sleep(1.5)
    for box_id, slots in groups:
        if _stop.is_set() or clicked >= MAX_CLICKS:
            break
        take = slots[: MAX_CLICKS - clicked]
        progress and progress(f"{box_id} 号盒子要点 {len(take)} 格", clicked, MAX_CLICKS)
        for slot in take:
            if _stop.is_set():
                break
            x, y = cell_point(calib, slot)
            click_client(hwnd, x, y)
            clicked += 1
        seen = read_selected_count(hwnd, calib)
        if seen != len(take):
            raise RuntimeError(f"{box_id} 号盒子已选 {seen}，实际点击 {len(take)}，已停止，没有点放生")
        release = calib["points"]["release"]
        click_client(hwnd, release["x"], release["y"])
        confirm = calib["points"].get("confirm")
        if confirm:
            time.sleep(0.4)
            click_client(hwnd, confirm["x"], confirm["y"])
        progress and progress(f"{box_id} 号盒子已点击放生 {len(take)} 只", clicked, MAX_CLICKS)
        nxt = calib["points"]["next"]
        click_client(hwnd, nxt["x"], nxt["y"])
        time.sleep(0.4)
    return {"clicked": clicked, "stopped": _stop.is_set()}
