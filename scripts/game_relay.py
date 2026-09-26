"""把游戏的 TCP 8195 改道到本机，再原样转发。

和 RocoMITMServer 一样用 WinDivert 站在连接中间，因此从第一个字节起能看到
0x1002 里的会话密钥。这里只观察和解密，不改写、不注入游戏报文。
需要管理员权限，以及 pydivert、psutil。
"""

from __future__ import annotations

import ctypes
import os
import socket
import threading
import time
from pathlib import Path

from Crypto.Cipher import AES

from scripts.rocom_capture import FileKeyStore

GAME_PORT = 8195
PROXY_PORT = 18197
GAME_PROCESS = "NRC-Win64-Shipping.exe"
IV = bytes(range(16))
ACK_KEY_OFFSET = 0x17
INTERNAL_HEADER_LEN = 30
PROJECT_ROOT = Path(__file__).resolve().parents[1]
KEY_DIR = PROJECT_ROOT / "captures" / "keys"
_active_stop: threading.Event | None = None


def stop_relay() -> bool:
    """请求结束当前改道。没有正在进行的改道时返回 False。"""
    event = _active_stop
    if event is None:
        return False
    event.set()
    return True


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def local_ipv4() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def pop_packet(buf: bytearray) -> bytes | None:
    """从字节流切出一个 GCP 包。魔数错开时向前找，不把连接拆掉。"""
    while True:
        if len(buf) < 21:
            return None
        if buf[0:2] != b"\x33\x66":
            nxt = buf.find(b"\x33\x66", 1)
            if nxt < 0:
                del buf[:-1]
                return None
            del buf[:nxt]
            continue
        head_len = int.from_bytes(buf[13:17], "big")
        body_len = int.from_bytes(buf[17:21], "big")
        if head_len < 21 or head_len > 4096 or body_len > 8 * 1024 * 1024:
            del buf[:2]
            continue
        total = head_len + body_len
        if len(buf) < total:
            return None
        pkt = bytes(buf[:total])
        del buf[:total]
        return pkt


def ack_key(pkt: bytes) -> bytes | None:
    """0x1002 整包偏移 0x17 起的 16 字节，和 RocoMITM 的取法相同。"""
    if len(pkt) < ACK_KEY_OFFSET + 16:
        return None
    if int.from_bytes(pkt[6:8], "big") != 0x1002:
        return None
    return pkt[ACK_KEY_OFFSET : ACK_KEY_OFFSET + 16]


def _strip_trailer(plain: bytes) -> bytes | None:
    if len(plain) < 6:
        return None
    trailer_len = plain[-1]
    if not (6 <= trailer_len <= len(plain)):
        return None
    trailer = plain[-trailer_len:]
    if trailer[-6:-1] != b"tsf4g":
        return None
    return plain[:-trailer_len]


def _payload_without_trailer(payload: bytes) -> bytes:
    stripped = _strip_trailer(payload)
    return payload if stripped is None else stripped


def _read_internal(view: bytes, direction: str) -> tuple[int, bytes] | None:
    """30 字节内部头：偏移 4 是 55 aa，下行 opcode 在会话号的低 16 位。"""
    if len(view) < INTERNAL_HEADER_LEN or view[4:6] != b"\x55\xaa":
        return None
    if direction == "c2s":
        opcode = int.from_bytes(view[22:24], "big")
    else:
        opcode = int.from_bytes(view[16:20], "big") & 0xFFFF
    if not opcode:
        return None
    return opcode, view[INTERNAL_HEADER_LEN:]


def _read_live_s2c(view: bytes) -> tuple[int, bytes] | None:
    """16 字节信封之后的下行头：前 4 字节是 opcode，紧接着是 55 aa，载荷从偏移 10 开始。"""
    if len(view) < 10 or view[4:6] != b"\x55\xaa":
        return None
    opcode = int.from_bytes(view[0:4], "big")
    if opcode <= 0 or opcode > 0xFFFF:
        return None
    return opcode, _payload_without_trailer(view[10:])


def open_data(key: bytes, body: bytes, direction: str) -> tuple[int, bytes] | None:
    """固定 IV 解密并去掉 tsf4g。下行内部头有时在 16 字节信封之后。"""
    if len(key) != 16 or len(body) < 16 or len(body) % 16 != 0:
        return None
    plain = AES.new(key, AES.MODE_CBC, IV).decrypt(body)
    stripped = _strip_trailer(plain)
    if stripped is None:
        return None
    if direction == "s2c" and len(stripped) >= 26 and stripped[20:22] == b"\x55\xaa":
        opened = _read_live_s2c(stripped[16:])
        if opened is not None:
            return opened
    return _read_internal(stripped, direction)


def open_s2c(key: bytes, body: bytes) -> tuple[int, bytes] | None:
    return open_data(key, body, "s2c")


def describe_decrypt(key: bytes, body: bytes) -> str:
    """第一包解不开时写进日志，不包含密钥。"""
    if len(body) < 16 or len(body) % 16 != 0:
        return f"0x4013 包体长度 {len(body)} 不能按 AES 块解密"
    plain = AES.new(key, AES.MODE_CBC, IV).decrypt(body)
    mark = plain[4:6].hex() if len(plain) >= 6 else ""
    mark20 = plain[20:22].hex() if len(plain) >= 22 else ""
    tail = plain[-8:].hex() if len(plain) >= 8 else plain.hex()
    trailer = "有" if _strip_trailer(plain) is not None else "无"
    return f"0x4013 解密后对不上明文。偏移4={mark} 偏移20={mark20} trailer={trailer} 尾部={tail}"


class _ConnMap:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, int], tuple[str, int]] = {}

    def remember(self, cli_ip: str, cli_port: int, orig_ip: str, orig_port: int) -> None:
        with self._lock:
            self._rows[(cli_ip, cli_port)] = (orig_ip, orig_port)

    def lookup(self, cli_ip: str, cli_port: int) -> tuple[str, int] | None:
        with self._lock:
            return self._rows.get((cli_ip, cli_port))


def _find_pid(name: str) -> int | None:
    import psutil

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] == name:
                return int(proc.info["pid"])
        except (psutil.Error, TypeError, ValueError):
            continue
    return None


def _owner_pid(target_pid: int | None, cache: dict[tuple[str, int], tuple[int, float]], addr: str, port: int) -> int | None:
    now = time.time()
    cached = cache.get((addr, port))
    if cached and now - cached[1] < 1.0:
        return cached[0]
    if target_pid is None:
        return None
    import psutil

    try:
        conns = psutil.Process(target_pid).net_connections(kind="tcp")
    except (psutil.Error, OSError):
        return None
    found = None
    for conn in conns:
        if not conn.laddr:
            continue
        cache[(conn.laddr.ip, conn.laddr.port)] = (target_pid, now)
        if conn.laddr.ip == addr and conn.laddr.port == port:
            found = target_pid
    return found


def run_relay(seconds: int | None, on_s2c, progress=None, stop_when=None, on_frame=None) -> dict:
    """改道并转发，直到调用 stop_relay 或 stop_when() 为真。seconds 为空则不限时。"""
    global _active_stop
    if not is_admin():
        raise RuntimeError("改道同步需要管理员权限。请用管理员身份重新启动仓库服务。")
    try:
        import psutil  # noqa: F401
        import pydivert
    except ImportError as exc:
        raise RuntimeError("改道同步需要 pydivert 和 psutil。在项目根目录执行 uv sync --extra capture") from exc

    deadline = None if seconds is None else time.time() + max(10, min(int(seconds), 600))
    host = local_ipv4()
    conns = _ConnMap()
    stop = threading.Event()
    _active_stop = stop
    stats = {"key": False, "s2c": 0, "pets": 0, "failed": 0, "flows": 0, "error": "", "fail_reason": ""}
    key_box: dict[str, bytes | None] = {"key": None}
    sockets: list[socket.socket] = []
    sockets_lock = threading.Lock()
    listen_box: dict[str, socket.socket | None] = {"sock": None}
    divert_box: dict[str, object] = {"wd": None}

    def report(message: str, current: int = 0, total: int = 0) -> None:
        if progress:
            progress(message, current, total)

    def track(sock: socket.socket) -> None:
        with sockets_lock:
            sockets.append(sock)

    def emit_frame(direction: str, command: int, opcode: int | None, payload: bytes, note: str) -> None:
        if on_frame is None:
            return
        on_frame(direction, command, opcode, payload, note)

    def observe(pkt: bytes, direction: str) -> None:
        command = int.from_bytes(pkt[6:8], "big") if len(pkt) >= 8 else 0
        if direction == "s2c":
            found = ack_key(pkt)
            if found is not None:
                key_box["key"] = found
                stats["key"] = True
                FileKeyStore(KEY_DIR).save_key("divert", found)
                report("已从 0x1002 拿到会话密钥，并写入 latest.key")
                emit_frame(direction, 0x1002, None, b"", "会话密钥")
                return
        if command != 0x4013:
            if command:
                emit_frame(direction, command, None, b"", "")
            return
        key = key_box["key"]
        if key is None:
            emit_frame(direction, command, None, b"", "还没有密钥")
            return
        head_len = int.from_bytes(pkt[13:17], "big")
        body_len = int.from_bytes(pkt[17:21], "big")
        body = pkt[head_len : head_len + body_len]
        opened = open_data(key, body, direction)
        if opened is None:
            stats["failed"] += 1
            if not stats["fail_reason"]:
                stats["fail_reason"] = describe_decrypt(key, body)
                report(stats["fail_reason"])
            emit_frame(direction, command, None, b"", "解密失败")
            return
        opcode, payload = opened
        stats["s2c"] += 1
        if opcode == 0x1346:
            stats["pets"] += 1
        emit_frame(direction, command, opcode, payload, "")
        on_s2c(opcode, payload)
        if stop_when is not None and stop_when():
            report("精灵列表已齐，结束改道。当前这局游戏连接会断开。")
            shutdown()

    def pump(src: socket.socket, dst: socket.socket, direction: str) -> None:
        buf = bytearray()
        try:
            while not stop.is_set():
                data = src.recv(65536)
                if not data:
                    break
                dst.sendall(data)
                buf.extend(data)
                while True:
                    pkt = pop_packet(buf)
                    if pkt is None:
                        break
                    observe(pkt, direction)
        except OSError:
            return
        finally:
            for sock in (src, dst):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def handle(client: socket.socket, addr: tuple) -> None:
        orig = None
        for _ in range(20):
            orig = conns.lookup(addr[0], addr[1])
            if orig:
                break
            time.sleep(0.05)
        if orig is None:
            report(f"没有找到 {addr[0]}:{addr[1]} 的原服务器，已断开")
            client.close()
            return
        upstream = socket.create_connection(orig, timeout=10)
        track(client)
        track(upstream)
        stats["flows"] += 1
        report(f"已改道 {addr[0]}:{addr[1]} → {orig[0]}:{orig[1]}")
        left = threading.Thread(target=pump, args=(client, upstream, "c2s"), daemon=True)
        right = threading.Thread(target=pump, args=(upstream, client, "s2c"), daemon=True)
        left.start()
        right.start()
        left.join()
        right.join()

    def serve() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", PROXY_PORT))
        except OSError as exc:
            stats["error"] = f"本机端口 {PROXY_PORT} 绑定失败: {exc}"
            report(stats["error"])
            stop.set()
            return
        sock.listen(8)
        sock.settimeout(0.5)
        listen_box["sock"] = sock
        report(f"本机代理已在 {host}:{PROXY_PORT} 等待。现在进游戏，并打开宠物仓库翻页。")
        while not stop.is_set():
            try:
                client, addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=handle, args=(client, addr), daemon=True).start()

    def shutdown() -> None:
        if stop.is_set():
            return
        stop.set()
        wd = divert_box.get("wd")
        if wd is not None:
            try:
                wd.close()
            except Exception:
                pass
        listen = listen_box.get("sock")
        if listen is not None:
            try:
                listen.close()
            except OSError:
                pass
        with sockets_lock:
            for sock in sockets:
                try:
                    sock.close()
                except OSError:
                    pass

    def divert() -> None:
        import pydivert

        filt = (
            f"tcp and ((outbound and tcp.DstPort == {GAME_PORT}) or "
            f"(outbound and tcp.SrcPort == {PROXY_PORT}))"
        )
        cache: dict[tuple[str, int], tuple[int, float]] = {}
        target_pid: int | None = None
        refreshed = 0.0
        self_pid = os.getpid()
        wd = pydivert.WinDivert(filt)
        wd.open()
        divert_box["wd"] = wd
        report(f"WinDivert 已开始，只改道 {GAME_PROCESS} 的 TCP {GAME_PORT}")
        try:
            while not stop.is_set():
                pkt = wd.recv()
                now = time.time()
                if target_pid is None or now - refreshed > 2:
                    target_pid = _find_pid(GAME_PROCESS)
                    refreshed = now
                if pkt.dst_port == GAME_PORT:
                    owner = _owner_pid(target_pid, cache, pkt.src_addr, pkt.src_port)
                    if owner == self_pid or owner != target_pid or target_pid is None:
                        wd.send(pkt)
                        continue
                    conns.remember(pkt.src_addr, pkt.src_port, pkt.dst_addr, pkt.dst_port)
                    pkt.dst_addr = host
                    pkt.dst_port = PROXY_PORT
                    pkt.recalculate_checksums()
                    wd.send(pkt)
                elif pkt.src_port == PROXY_PORT:
                    orig = conns.lookup(pkt.dst_addr, pkt.dst_port)
                    if orig:
                        pkt.src_addr = orig[0]
                        pkt.src_port = orig[1]
                        pkt.recalculate_checksums()
                    wd.send(pkt)
                else:
                    wd.send(pkt)
        except OSError:
            return
        finally:
            try:
                wd.close()
            except Exception:
                pass

    threading.Thread(target=serve, daemon=True).start()
    for _ in range(20):
        if listen_box["sock"] is not None or stop.is_set():
            break
        time.sleep(0.05)
    if stats["error"]:
        shutdown()
        _active_stop = None
        raise RuntimeError(stats["error"])
    threading.Thread(target=divert, daemon=True).start()
    try:
        while not stop.is_set():
            if deadline is not None and time.time() >= deadline:
                break
            time.sleep(0.5)
    finally:
        shutdown()
        _active_stop = None
    if stats["error"]:
        raise RuntimeError(stats["error"])
    return stats
