"""把 TCP 8195 收成 GCP 消息。

会话怎么对上、密钥怎么共享，跟 rocom-parse 的 capture 包一样：
同一条连接的上下行共用 0x1002 里的密钥，s2c 明文必须带 0x55aa。
实时抓包在 Windows 上用 Scapy 读本机网卡；rocom 自己的 afpacket 只能在 Linux 网关用。
"""

from __future__ import annotations

from pathlib import Path

from scripts.rocom_gcp import (
    CMD_ACK,
    CMD_DATA,
    C2S,
    S2C,
    app_body,
    app_opcode,
    decrypt_matching,
    deframe,
    extract_key,
    valid_plain,
)


def parse_key_text(text: str) -> bytes | None:
    """接受 32 位 hex、16 字节 ASCII，以及 RKPP 的 key_hex= / key_ascii= 文件。"""
    raw = text.strip()
    if not raw:
        return None

    def _pack(value: str) -> bytes | None:
        value = value.strip()
        hex_cand = "".join(char for char in value if char in "0123456789abcdefABCDEF")
        if len(value) == 16:
            try:
                key = value.encode("ascii")
            except UnicodeEncodeError:
                return None
        elif len(hex_cand) == 32 and len(value) == 32:
            key = bytes.fromhex(hex_cand)
        else:
            return None
        return key if len(key) == 16 else None

    first = raw.splitlines()[0].strip()
    if "=" not in first:
        return _pack(first)
    for line in raw.splitlines():
        if line.startswith("key_hex=") or line.startswith("key_ascii="):
            key = _pack(line.split("=", 1)[1])
            if key is not None and not (line.startswith("key_ascii=") and "<non-ascii>" in line):
                return key
    return None


class FileKeyStore:
    """按连接保存密钥，并额外写一份 latest.key，下一条连接也能先拿来试。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, conn_id: str) -> Path:
        safe = conn_id.replace(":", "_").replace("|", "__").replace("/", "_")
        return self.directory / f"{safe}.key"

    def latest_path(self) -> Path:
        return self.directory / "latest.key"

    def _read(self, path: Path) -> bytes | None:
        if not path.is_file():
            return None
        return parse_key_text(path.read_text(encoding="utf-8", errors="ignore"))

    def load_key(self, conn_id: str) -> bytes | None:
        return self._read(self._path(conn_id))

    def load_latest(self) -> bytes | None:
        return self._read(self.latest_path())

    def save_key(self, conn_id: str, key: bytes) -> None:
        self._path(conn_id).write_text(key.hex(), encoding="utf-8")
        ascii_key = key.decode("ascii") if all(32 <= byte < 127 for byte in key) else "<non-ascii>"
        self.latest_path().write_text(
            f"key_hex={key.hex()}\nkey_ascii={ascii_key}\nflow={conn_id}\n",
            encoding="utf-8",
        )


class _Direction:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.next_seq: int | None = None
        self.pending: dict[int, bytes] = {}
        self.isolated: list[bytes] = []

    def push(self, seq: int, payload: bytes, syn: bool = False) -> None:
        if syn and self.next_seq is None:
            self.next_seq = (seq + 1) & 0xFFFFFFFF
        if not payload:
            return
        if self.next_seq is None:
            self.next_seq = seq
        if _seq_before(seq, self.next_seq):
            skip = (self.next_seq - seq) & 0xFFFFFFFF
            if skip >= len(payload):
                self.isolated.append(payload)
                return
            payload = payload[skip:]
            seq = self.next_seq
        if seq != self.next_seq:
            if len(self.pending) < 64:
                self.pending[seq] = payload
            return
        self.buf.extend(payload)
        self.next_seq = (self.next_seq + len(payload)) & 0xFFFFFFFF
        while self.next_seq in self.pending:
            chunk = self.pending.pop(self.next_seq)
            self.buf.extend(chunk)
            self.next_seq = (self.next_seq + len(chunk)) & 0xFFFFFFFF


def _seq_before(left: int, right: int) -> bool:
    return ((left - right) & 0xFFFFFFFF) > 0x80000000


class _Session:
    def __init__(self) -> None:
        self.key: bytes | None = None
        self.from_cache = False

    def set_key(self, key: bytes) -> None:
        self.key = key
        self.from_cache = False

    def load_cached(self, key: bytes) -> None:
        self.key = key
        self.from_cache = True

    def clear_key(self) -> None:
        self.key = None
        self.from_cache = False


class Message:
    def __init__(self, direction: str, opcode: int, session: str, plain: bytes, app_body_bytes: bytes) -> None:
        self.direction = direction
        self.opcode = opcode
        self.session = session
        self.plain = plain
        self.app_body = app_body_bytes


class _Flow:
    def __init__(self, conn_id: str, session: _Session) -> None:
        self.conn_id = conn_id
        self.session = session
        self.c2s = _Direction()
        self.s2c = _Direction()


class Engine:
    def __init__(self, port: int = 8195, keys: FileKeyStore | None = None, on_message=None, log=None) -> None:
        self.port = port
        self.keys = keys
        self.on_message = on_message
        self.log = log or (lambda _message: None)
        self.flows: dict[tuple, _Flow] = {}
        self.no_key = 0
        self.bad_key = 0
        self.tcp_segments = 0
        self.tcp_payload_bytes = 0
        self.gcp_frames = 0
        self.key_frames = 0
        self.key_extract_failed = 0
        self.decrypt_failed = 0
        self.decoded = 0
        self.commands: dict[int, int] = {}
        self.opcodes: dict[int, int] = {}
        self.servers: set[str] = set()
        self._logged_commands: set[int] = set()
        self._seen_gcp: set[tuple[str, int, int]] = set()

    def feed(self, packet) -> None:
        parsed = _packet_endpoints(packet)
        if parsed is None:
            return
        self.feed_segment(*parsed)

    def feed_segment(self, src: str, sport: int, dst: str, dport: int, seq: int, payload: bytes, syn: bool = False) -> None:
        if sport != self.port and dport != self.port:
            return
        self.tcp_segments += 1
        self.tcp_payload_bytes += len(payload)
        if dport == self.port:
            direction = C2S
            client, client_port = src, sport
            server, server_port = dst, dport
        else:
            direction = S2C
            client, client_port = dst, dport
            server, server_port = src, sport
        conn_id = f"{server}:{server_port}|{client}:{client_port}"
        self.servers.add(f"{server}:{server_port}")
        key = (server, server_port, client, client_port)
        flow = self.flows.get(key)
        if flow is None:
            session = _Session()
            if self.keys is not None:
                cached = self.keys.load_key(conn_id)
                origin = "这条连接的缓存"
                if cached is None:
                    cached = self.keys.load_latest()
                    origin = "latest.key"
                if cached:
                    session.load_cached(cached)
                    self.log(f"从{origin}恢复会话密钥 [{conn_id}]")
            flow = _Flow(conn_id, session)
            self.flows[key] = flow
            self.log(f"检测到新连接: 客户端 {client}:{client_port} → 服务器 {server}:{server_port}")
        side = flow.c2s if direction == C2S else flow.s2c
        side.push(seq, payload, syn)
        for blob in side.isolated:
            lone, _rest = deframe(blob)
            for item in lone:
                self._on_gcp(flow, direction, item)
        side.isolated.clear()
        packets, rest = deframe(bytes(side.buf))
        side.buf = bytearray(rest)
        for item in packets:
            self._on_gcp(flow, direction, item)

    def _on_gcp(self, flow: _Flow, direction: str, packet) -> None:
        ident = (direction, packet.command, packet.sequence)
        if ident in self._seen_gcp:
            return
        self._seen_gcp.add(ident)
        self.gcp_frames += 1
        self.commands[packet.command] = self.commands.get(packet.command, 0) + 1
        if packet.command == CMD_ACK:
            self.key_frames += 1
            key = extract_key(packet.header_extra)
            if key is None:
                self.key_extract_failed += 1
                self.log(f"密钥帧里没有 16 字节密钥 [{flow.conn_id}]")
                return
            if flow.session.key is None or flow.session.from_cache:
                self.log(f"会话密钥就绪，已写入 latest.key [{flow.conn_id}]")
            flow.session.set_key(key)
            if self.keys is not None:
                self.keys.save_key(flow.conn_id, key)
            return
        if packet.command != CMD_DATA:
            if packet.command not in self._logged_commands:
                self._logged_commands.add(packet.command)
                self.log(f"忽略 GCP 命令 0x{packet.command:04X} [{flow.conn_id}]")
            return
        key = flow.session.key
        if key is None:
            self.no_key += 1
            return
        plain = decrypt_matching(key, packet.body, direction)
        if plain is None:
            if flow.session.from_cache and len(packet.body) >= 32:
                self.bad_key += 1
                self.log(f"缓存密钥校验失败，已清除 [{flow.conn_id}]")
                flow.session.clear_key()
            else:
                self.decrypt_failed += 1
            return
        opcode = app_opcode(direction, plain)
        if opcode is None:
            return
        self.decoded += 1
        self.opcodes[opcode] = self.opcodes.get(opcode, 0) + 1
        message = Message(direction, opcode, flow.conn_id, plain, app_body(direction, plain))
        if self.on_message is not None:
            self.on_message(message)

    def summary(self) -> str:
        commands = ", ".join(f"0x{cmd:04X}×{count}" for cmd, count in sorted(self.commands.items())) or "无"
        opcodes = ", ".join(f"0x{opcode:04X}×{count}" for opcode, count in sorted(self.opcodes.items())) or "无"
        peers = sorted(self.servers)
        shown = ", ".join(peers[:4]) or "无"
        if len(peers) > 4:
            shown += f" 等{len(peers)}个"
        return (
            f"TCP段 {self.tcp_segments}，载荷 {self.tcp_payload_bytes} 字节，"
            f"连接 {len(self.flows)}，对端 {shown}；"
            f"GCP帧 {self.gcp_frames}（{commands}），密钥帧 {self.key_frames}；"
            f"解密成功 {self.decoded}（{opcodes}）；"
            f"无密钥 {self.no_key}，解密失败 {self.decrypt_failed}，"
            f"密钥不符 {self.bad_key}，密钥提取失败 {self.key_extract_failed}"
        )

    def failure_hint(self) -> str:
        """抓包结束仍没有可用明文时，说明卡在哪一步。"""
        if self.tcp_segments == 0:
            return "这块网卡上没有 TCP 8195。确认游戏已经连上，并且选的是游戏流量经过的网卡。"
        if self.key_frames == 0 and self.no_key:
            return (
                "看到了数据包，但没有会话密钥帧 0x1002。"
                "进游戏前就要开始抓；captures/keys/latest.key 里若有上一局密钥，新连接会先拿来试。"
            )
        if self.key_frames and self.key_extract_failed and self.decoded == 0:
            return "看到了密钥帧，但扩展头里没有 16 字节密钥。"
        if self.bad_key and self.decoded == 0:
            return "缓存的会话密钥对不上，重新登录后再抓一次。"
        if self.decoded == 0:
            return "有 GCP 帧，但没有解出应用层消息。"
        return ""


def _packet_endpoints(packet):
    try:
        from scapy.layers.inet import IP, TCP
        from scapy.layers.inet6 import IPv6
    except ImportError as exc:
        raise RuntimeError("回放和实时抓包需要 scapy") from exc
    if not packet.haslayer(TCP):
        return None
    tcp = packet[TCP]
    if packet.haslayer(IP):
        ip = packet[IP]
    elif packet.haslayer(IPv6):
        ip = packet[IPv6]
    else:
        return None
    syn = bool(int(tcp.flags) & 0x02)
    return ip.src, int(tcp.sport), ip.dst, int(tcp.dport), int(tcp.seq), bytes(tcp.payload), syn


def read_pcap(path: Path):
    try:
        from scapy.all import PcapReader
    except ImportError as exc:
        raise RuntimeError("回放 pcap 需要 scapy") from exc
    reader = PcapReader(str(path))
    try:
        yield from reader
    finally:
        reader.close()
