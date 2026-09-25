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
    decrypt_data,
    deframe,
    extract_key,
    valid_plain,
)


class FileKeyStore:
    """按连接把 16 字节密钥落在本地，进程重启后还能解还没断开的会话。"""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, conn_id: str) -> Path:
        safe = conn_id.replace(":", "_").replace("|", "__").replace("/", "_")
        return self.directory / f"{safe}.key"

    def load_key(self, conn_id: str) -> bytes | None:
        path = self._path(conn_id)
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
        try:
            key = bytes.fromhex(text)
        except ValueError:
            return None
        return key if len(key) == 16 else None

    def save_key(self, conn_id: str, key: bytes) -> None:
        self._path(conn_id).write_text(key.hex(), encoding="utf-8")


class _Direction:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.next_seq: int | None = None
        self.pending: dict[int, bytes] = {}

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

    def feed(self, packet) -> None:
        parsed = _packet_endpoints(packet)
        if parsed is None:
            return
        self.feed_segment(*parsed)

    def feed_segment(self, src: str, sport: int, dst: str, dport: int, seq: int, payload: bytes, syn: bool = False) -> None:
        if sport != self.port and dport != self.port:
            return
        if dport == self.port:
            direction = C2S
            client, client_port = src, sport
            server, server_port = dst, dport
        else:
            direction = S2C
            client, client_port = dst, dport
            server, server_port = src, sport
        conn_id = f"{server}:{server_port}|{client}:{client_port}"
        key = (server, server_port, client, client_port)
        flow = self.flows.get(key)
        if flow is None:
            session = _Session()
            if self.keys is not None:
                cached = self.keys.load_key(conn_id)
                if cached:
                    session.load_cached(cached)
                    self.log(f"从缓存恢复会话密钥 [{conn_id}]")
            flow = _Flow(conn_id, session)
            self.flows[key] = flow
            self.log(f"检测到新连接: 客户端 {client}:{client_port} → 服务器 {server}:{server_port}")
        side = flow.c2s if direction == C2S else flow.s2c
        side.push(seq, payload, syn)
        packets, rest = deframe(bytes(side.buf))
        side.buf = bytearray(rest)
        for item in packets:
            self._on_gcp(flow, direction, item)

    def _on_gcp(self, flow: _Flow, direction: str, packet) -> None:
        if packet.command == CMD_ACK:
            key = extract_key(packet.header_extra)
            if key is None:
                return
            if flow.session.key is None:
                self.log(f"会话密钥就绪 [{flow.conn_id}]")
            flow.session.set_key(key)
            if self.keys is not None:
                self.keys.save_key(flow.conn_id, key)
            return
        if packet.command != CMD_DATA:
            return
        key = flow.session.key
        if key is None:
            self.no_key += 1
            return
        plain = decrypt_data(key, packet.body)
        if plain is None:
            return
        if not valid_plain(direction, plain):
            self.bad_key += 1
            if flow.session.from_cache:
                self.log(f"缓存密钥校验失败，已清除 [{flow.conn_id}]")
                flow.session.clear_key()
            return
        opcode = app_opcode(direction, plain)
        if opcode is None:
            return
        message = Message(direction, opcode, flow.conn_id, plain, app_body(direction, plain))
        if self.on_message is not None:
            self.on_message(message)


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
