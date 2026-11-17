"""
Client address resolution for security decisions.

Used for rate limiting, where a wrong answer has teeth: believe a forged header and an
attacker gets a fresh budget with every request. So this is stricter than the left-most
`X-Forwarded-For` hop that the audit code reads, which the client controls.

How `X-Forwarded-For` is built: each proxy appends the address it saw the request come
from. Entries on the right were added by our own infrastructure and can be trusted; entries
on the left may have been sent by the client. With `trusted_proxy_hops = N` the client is the
Nth entry counting from the right.

    client -> router -> nginx -> api          X-Forwarded-For: <forged...>, <client>, <router>
                                              (the socket peer is nginx)
    trusted_proxy_hops = 2  ->  <client>

0 (the default) ignores the header altogether and uses the socket peer. That cannot be
forged, but behind a reverse proxy it is the proxy's own address, so every user shares one.
Set it to the number of proxies in front of the API. If the chain is shorter than expected
(a request that skipped a proxy), the header is not trusted and the peer is used instead.

This only holds when the API is reachable solely through that chain. A request sent to it
directly can carry any header it likes, so keep the API off the public network.

IPv6 clients are bucketed by /64. A single subscriber is routinely handed a whole /64, so
keying on the full address would give an attacker 2**64 fresh budgets.
"""

import ipaddress
from typing import Final

import structlog
from starlette.requests import Request

__all__ = ["UNKNOWN_CLIENT", "check_proxy_configuration", "resolve_client_ip"]

logger = structlog.get_logger(__name__)

UNKNOWN_CLIENT: Final = "unknown"
_IPV6_BUCKET_PREFIX: Final = 64
_FORWARDING_HEADERS: Final = ("x-forwarded-for", "forwarded", "x-real-ip")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Which misconfiguration warnings this process has already given. Each is worth saying once.
_reported: set[str] = set()


def resolve_client_ip(request: Request, trusted_proxy_hops: int) -> str:
    """The address to rate-limit this request under; never raises, never empty."""
    if trusted_proxy_hops > 0:
        chain = _forwarded_chain(request)
        if len(chain) >= trusted_proxy_hops:
            claimed = _parse(chain[-trusted_proxy_hops])
            if claimed is not None:
                return _bucket(claimed)
    peer = _parse(request.client.host) if request.client else None
    return _bucket(peer) if peer is not None else UNKNOWN_CLIENT


def check_proxy_configuration(request: Request, trusted_proxy_hops: int) -> None:
    """
    Warn, once each, when the requests themselves show `trusted_proxy_hops` is wrong.

    Nothing else tells an operator. A wrong value does not fail, it quietly changes what the
    per-IP limits mean: too low and everyone behind the proxy shares one address, so a few
    failed logins block them all together. The requests give it away, though. A forwarding
    header arriving while the setting is 0 means a proxy exists; a chain shorter than the
    setting means the count is too high (or a request skipped the proxy).

    Never changes the answer `resolve_client_ip` gives, and logs at most once per condition
    per process, so a probe cannot use it to fill the log.
    """
    peer = request.client.host if request.client else UNKNOWN_CLIENT
    if trusted_proxy_hops == 0:
        present = [name for name in _FORWARDING_HEADERS if name in request.headers]
        if present:
            _warn_once(
                "hops_too_low",
                "trusted_proxy_hops_too_low",
                peer=peer,
                forwarding_headers=present,
                detail=(
                    "A request carried a forwarding header while TRUSTED_PROXY_HOPS is 0, "
                    "so the API sees the proxy's address as the client. Every user behind "
                    "it shares one rate-limit address. Set TRUSTED_PROXY_HOPS to the "
                    "number of proxies in front of the API."
                ),
            )
    elif len(_forwarded_chain(request)) < trusted_proxy_hops:
        _warn_once(
            "chain_too_short",
            "trusted_proxy_chain_shorter_than_hops",
            peer=peer,
            trusted_proxy_hops=trusted_proxy_hops,
            forwarded_entries=len(_forwarded_chain(request)),
            detail=(
                "X-Forwarded-For has fewer entries than TRUSTED_PROXY_HOPS, so it was not "
                "trusted and the socket peer is used instead. Either the setting is higher "
                "than the real number of proxies, or a request reached the API without "
                "passing through them."
            ),
        )


def _warn_once(key: str, event: str, **fields: object) -> None:
    if key in _reported:
        return
    _reported.add(key)
    logger.warning(event, **fields)


def _forwarded_chain(request: Request) -> list[str]:
    """Every `X-Forwarded-For` entry in order. Proxies may send several header lines."""
    entries: list[str] = []
    for line in request.headers.getlist("x-forwarded-for"):
        entries.extend(part.strip() for part in line.split(",") if part.strip())
    return entries


def _parse(text: str) -> IPAddress | None:
    """An IP from a header or socket value, tolerating a port and brackets; else None."""
    candidate = text.strip()
    if candidate.startswith("["):  # [v6]:port
        closing = candidate.find("]")
        if closing == -1:
            return None
        candidate = candidate[1:closing]
    elif candidate.count(":") == 1:  # v4:port (a bare v6 address has several colons)
        candidate = candidate.split(":", 1)[0]
    try:
        address: IPAddress = ipaddress.ip_address(candidate)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _bucket(address: IPAddress) -> str:
    if isinstance(address, ipaddress.IPv4Address):
        return str(address)
    # Rebuilt from the integer so an interface scope (fe80::1%eth0) cannot split a bucket.
    network = ipaddress.IPv6Network((int(address), _IPV6_BUCKET_PREFIX), strict=False)
    return str(network)
