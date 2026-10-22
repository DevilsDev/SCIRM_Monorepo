"""
Outbound requests to addresses a tenant typed in (an SAP system, a webhook URL).

Outside development (strict mode) the host is resolved once, every address must be public,
and the request is sent to the checked address with the original name used for the Host
header and TLS (SNI and certificate checks), so a DNS answer that changes between the
check and the request (DNS rebinding) cannot reach an internal address. Redirects must
never be followed by the caller: a redirect would skip this check.
"""

import ipaddress
import socket
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlsplit


class OutboundError(Exception):
    """kind: "dns" (the host could not be resolved) or "private" (not a public address)."""

    def __init__(self, kind: str, host: str):
        super().__init__(f"{kind}: {host}")
        self.kind, self.host = kind, host


def system_resolve(host: str, port: int) -> List[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def pin(url: str, strict: bool, resolve: Callable[[str, int], List[str]] = system_resolve) -> Tuple[str, Optional[str]]:
    """(URL to send the request to, name for Host/SNI or None). In strict mode the URL names
    the checked public address; otherwise it is returned unchanged."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not strict:
        return url, None
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = [host] if is_ip(host) else resolve(host, port)
    except (OSError, UnicodeError):
        raise OutboundError("dns", host)
    if not addresses:
        raise OutboundError("dns", host)
    if not all(is_public(a) for a in addresses):
        raise OutboundError("private", host)
    ip = addresses[0]
    literal = f"[{ip}]" if ":" in ip else ip
    rest = parts.path + (f"?{parts.query}" if parts.query else "")
    return f"{parts.scheme}://{literal}:{port}{rest}", host
