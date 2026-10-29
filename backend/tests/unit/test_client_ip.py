"""
Unit tests for resolve_client_ip.

This is the address rate limiting keys on, so the property that matters is that a client
cannot choose it. Most of these tests are an attacker forging X-Forwarded-For in some way.
"""

import pytest
import structlog
from starlette.requests import Request

from src.api import client_ip
from src.api.client_ip import UNKNOWN_CLIENT, check_proxy_configuration, resolve_client_ip

PEER = "10.0.0.5"  # the proxy nearest the API, as the socket sees it


def make_request(
    *forwarded: str,
    peer: str | None = PEER,
) -> Request:
    """A request from `peer` carrying one X-Forwarded-For header line per argument."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"x-forwarded-for", line.encode()) for line in forwarded],
        "client": (peer, 40000) if peer is not None else None,
    }
    return Request(scope)


class TestHeaderIgnored:
    def test_the_socket_peer_is_used_when_no_proxies_are_trusted(self) -> None:
        assert resolve_client_ip(make_request("203.0.113.9"), 0) == PEER

    def test_a_forged_header_is_ignored_when_no_proxies_are_trusted(self) -> None:
        forged = make_request("1.1.1.1, 2.2.2.2, 3.3.3.3")

        assert resolve_client_ip(forged, 0) == PEER

    def test_rotating_the_header_cannot_change_the_answer(self) -> None:
        answers = {
            resolve_client_ip(make_request(f"198.51.100.{n}"), 0) for n in range(1, 50)
        }

        assert answers == {PEER}


class TestCountingFromTheRight:
    def test_one_proxy_the_last_entry_is_the_client(self) -> None:
        assert resolve_client_ip(make_request("203.0.113.9"), 1) == "203.0.113.9"

    def test_one_proxy_entries_the_client_sent_itself_are_ignored(self) -> None:
        """The client prepends whatever it likes; our proxy appends the truth after it."""
        request = make_request("6.6.6.6, 7.7.7.7, 203.0.113.9")

        assert resolve_client_ip(request, 1) == "203.0.113.9"

    def test_two_proxies_the_client_is_second_from_the_right(self) -> None:
        # forged..., client, router    (the socket peer is nginx)
        request = make_request("6.6.6.6, 203.0.113.9, 10.1.1.1")

        assert resolve_client_ip(request, 2) == "203.0.113.9"

    def test_two_proxies_a_forged_left_hand_side_does_not_leak_through(self) -> None:
        answers = {
            resolve_client_ip(make_request(f"9.9.9.{n}, 203.0.113.9, 10.1.1.1"), 2)
            for n in range(1, 50)
        }

        assert answers == {"203.0.113.9"}

    def test_several_header_lines_are_read_as_one_chain_in_order(self) -> None:
        request = make_request("6.6.6.6", "203.0.113.9", "10.1.1.1")

        assert resolve_client_ip(request, 2) == "203.0.113.9"

    def test_whitespace_and_empty_entries_are_tolerated(self) -> None:
        request = make_request(" 6.6.6.6 ,, 203.0.113.9 ")

        assert resolve_client_ip(request, 1) == "203.0.113.9"


class TestChainShorterThanExpected:
    def test_the_header_is_not_trusted_and_the_peer_is_used(self) -> None:
        """A request that skipped a proxy: nothing in the header can be believed."""
        request = make_request("203.0.113.9")

        assert resolve_client_ip(request, 2) == PEER

    def test_a_missing_header_falls_back_to_the_peer(self) -> None:
        assert resolve_client_ip(make_request(), 1) == PEER

    def test_a_garbage_entry_falls_back_to_the_peer(self) -> None:
        assert resolve_client_ip(make_request("not-an-ip"), 1) == PEER

    @pytest.mark.parametrize("junk", ["", "unknown", "999.1.1.1", "1.2.3", "'; DROP TABLE x;--"])
    def test_junk_values_never_become_the_answer(self, junk: str) -> None:
        assert resolve_client_ip(make_request(junk), 1) == PEER


class TestAddressForms:
    def test_a_port_on_an_ipv4_entry_is_dropped(self) -> None:
        assert resolve_client_ip(make_request("203.0.113.9:51234"), 1) == "203.0.113.9"

    def test_a_bracketed_ipv6_entry_with_a_port_is_understood(self) -> None:
        request = make_request("[2001:db8:1:2:3:4:5:6]:443")

        assert resolve_client_ip(request, 1) == "2001:db8:1:2::/64"

    def test_an_ipv4_mapped_ipv6_address_is_treated_as_ipv4(self) -> None:
        assert resolve_client_ip(make_request("::ffff:203.0.113.9"), 1) == "203.0.113.9"

    def test_ipv6_clients_are_bucketed_by_their_64(self) -> None:
        """One subscriber is handed a whole /64; keying on the full address would give an
        attacker 2**64 fresh budgets."""
        first = resolve_client_ip(make_request("2001:db8:1:2:aaaa:bbbb:cccc:dddd"), 1)
        second = resolve_client_ip(make_request("2001:db8:1:2:1111:2222:3333:4444"), 1)
        other_subscriber = resolve_client_ip(make_request("2001:db8:1:3::1"), 1)

        assert first == second == "2001:db8:1:2::/64"
        assert other_subscriber == "2001:db8:1:3::/64"

    def test_an_ipv6_peer_is_bucketed_too(self) -> None:
        request = make_request(peer="2001:db8:9:9:1:2:3:4")

        assert resolve_client_ip(request, 0) == "2001:db8:9:9::/64"

    def test_an_interface_scope_cannot_split_a_bucket(self) -> None:
        plain = resolve_client_ip(make_request("fe80::1"), 1)
        scoped = resolve_client_ip(make_request("fe80::1%eth0"), 1)

        assert plain == scoped


class TestNoPeer:
    def test_no_peer_and_no_header_is_one_shared_bucket_not_a_crash(self) -> None:
        assert resolve_client_ip(make_request(peer=None), 0) == UNKNOWN_CLIENT

    def test_no_peer_still_honours_a_valid_forwarded_chain(self) -> None:
        request = make_request("203.0.113.9", peer=None)

        assert resolve_client_ip(request, 1) == "203.0.113.9"


def _warnings(request: Request, hops: int) -> list[str]:
    with structlog.testing.capture_logs() as logs:
        check_proxy_configuration(request, hops)
    return [str(entry["event"]) for entry in logs]


class TestMisconfigurationWarnings:
    """
    The requests are the only thing that can tell an operator TRUSTED_PROXY_HOPS is wrong.

    A wrong value does not fail: it silently changes what the per-IP limits mean. Behind a
    proxy with the setting at 0, every user shares the proxy's address.
    """

    @pytest.fixture(autouse=True)
    def fresh_process(self) -> None:
        client_ip._reported.clear()

    @pytest.mark.parametrize("header", ["x-forwarded-for", "forwarded", "x-real-ip"])
    def test_a_forwarding_header_while_the_setting_is_zero_is_called_out(
        self, header: str
    ) -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [(header.encode(), b"203.0.113.9")],
                "client": (PEER, 40000),
            }
        )

        assert _warnings(request, 0) == ["trusted_proxy_hops_too_low"]

    def test_the_warning_names_the_proxy_address_the_api_is_seeing(self) -> None:
        with structlog.testing.capture_logs() as logs:
            check_proxy_configuration(make_request("203.0.113.9"), 0)

        assert logs[0]["peer"] == PEER
        assert logs[0]["log_level"] == "warning"
        assert "TRUSTED_PROXY_HOPS" in str(logs[0]["detail"])

    def test_a_request_with_no_forwarding_header_is_not_a_warning(self) -> None:
        assert _warnings(make_request(), 0) == []

    def test_each_condition_is_reported_once_per_process(self) -> None:
        """A probe sending the header a million times must not fill the log."""
        first = _warnings(make_request("203.0.113.9"), 0)
        again = [_warnings(make_request(f"198.51.100.{n}"), 0) for n in range(1, 50)]

        assert first == ["trusted_proxy_hops_too_low"]
        assert again == [[]] * 49

    def test_a_chain_shorter_than_the_setting_is_called_out(self) -> None:
        assert _warnings(make_request("203.0.113.9"), 2) == [
            "trusted_proxy_chain_shorter_than_hops"
        ]

    def test_a_chain_as_long_as_the_setting_is_fine(self) -> None:
        assert _warnings(make_request("203.0.113.9, 10.1.1.1"), 2) == []

    def test_a_correctly_configured_proxy_never_warns(self) -> None:
        assert _warnings(make_request("203.0.113.9"), 1) == []

    def test_checking_never_changes_the_answer(self) -> None:
        request = make_request("203.0.113.9")
        before = resolve_client_ip(request, 0)

        check_proxy_configuration(request, 0)

        assert resolve_client_ip(request, 0) == before == PEER
