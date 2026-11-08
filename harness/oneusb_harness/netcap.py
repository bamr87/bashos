"""pcap assertions without third-party deps: DNS queries/answers and TCP SYNs.

QEMU's filter-dump writes classic libpcap files with Ethernet framing.
"""
from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Capture:
    dns_queries: list[str] = field(default_factory=list)
    dns_answers: dict[str, set[str]] = field(default_factory=dict)   # qname → A/AAAA addresses
    tcp_syns: list[tuple[str, int]] = field(default_factory=list)     # (dst ip, dst port)
    packets: int = 0

    def resolved(self, name: str) -> set[str]:
        return self.dns_answers.get(name.rstrip(".").lower(), set())

    def connected_to(self, name: str, ports: tuple[int, ...] = (80, 443)) -> bool:
        ips = self.resolved(name)
        return any(ip in ips and port in ports for ip, port in self.tcp_syns)


def read(path: Path) -> Capture:
    cap = Capture()
    data = path.read_bytes() if path.exists() else b""
    if len(data) < 24:
        return cap
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        endian = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        endian = ">"
    else:
        raise ValueError(f"{path}: not a pcap file")
    off = 24
    while off + 16 <= len(data):
        _, _, incl, _ = struct.unpack(endian + "IIII", data[off:off + 16])
        frame = data[off + 16: off + 16 + incl]
        off += 16 + incl
        cap.packets += 1
        try:
            _frame(frame, cap)
        except (struct.error, IndexError, ValueError):
            continue
    return cap


def _frame(f: bytes, cap: Capture) -> None:
    ethertype = struct.unpack("!H", f[12:14])[0]
    p = f[14:]
    if ethertype == 0x8100:  # VLAN
        ethertype = struct.unpack("!H", f[16:18])[0]
        p = f[18:]
    if ethertype == 0x0800:
        ihl = (p[0] & 0x0F) * 4
        proto, dst = p[9], str(ipaddress.IPv4Address(p[16:20]))
        _l4(proto, p[ihl:], dst, cap)
    elif ethertype == 0x86DD:
        proto, dst = p[6], str(ipaddress.IPv6Address(p[24:40]))
        _l4(proto, p[40:], dst, cap)


def _l4(proto: int, seg: bytes, dst: str, cap: Capture) -> None:
    if proto == 6:
        sport, dport = struct.unpack("!HH", seg[:4])
        flags = seg[13]
        if flags & 0x02 and not flags & 0x10:  # SYN without ACK
            cap.tcp_syns.append((dst, dport))
    elif proto == 17:
        sport, dport = struct.unpack("!HH", seg[:4])
        if 53 in (sport, dport):
            _dns(seg[8:], cap)


def _name(msg: bytes, off: int) -> tuple[str, int]:
    labels, jumped, end = [], False, off
    for _ in range(128):
        n = msg[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", msg[off:off + 2])[0] & 0x3FFF
            if not jumped:
                end = off + 2
            jumped, off = True, ptr
            continue
        labels.append(msg[off + 1: off + 1 + n].decode("ascii", "replace"))
        off += 1 + n
    return ".".join(labels).lower(), (end if jumped else off)


def _dns(msg: bytes, cap: Capture) -> None:
    _, flags, qd, an, _, _ = struct.unpack("!HHHHHH", msg[:12])
    off, qnames = 12, []
    for _ in range(qd):
        name, off = _name(msg, off)
        off += 4
        qnames.append(name)
    if not flags & 0x8000:
        cap.dns_queries.extend(qnames)
        return
    for _ in range(an):
        _, off = _name(msg, off)
        rtype, _, _, rdlen = struct.unpack("!HHIH", msg[off:off + 10])
        rdata = msg[off + 10: off + 10 + rdlen]
        off += 10 + rdlen
        addr = None
        if rtype == 1 and rdlen == 4:
            addr = str(ipaddress.IPv4Address(rdata))
        elif rtype == 28 and rdlen == 16:
            addr = str(ipaddress.IPv6Address(rdata))
        if addr:
            # Attribute every address in the response to the question (follows CNAME chains).
            for q in qnames:
                cap.dns_answers.setdefault(q, set()).add(addr)
