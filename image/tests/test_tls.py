"""Tests for tls.parse_sans() — IP vs. DNS-SAN separation."""

import sys
import os
import ipaddress

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from core.tls import parse_sans


class TestParseSans:
    def test_single_ip(self):
        dns, ips = parse_sans("127.0.0.1")
        assert ips == [ipaddress.ip_address("127.0.0.1")]
        assert dns == []

    def test_single_hostname(self):
        dns, ips = parse_sans("myserver.local")
        assert dns == ["myserver.local"]
        assert ips == []

    def test_mixed_comma_separated(self):
        dns, ips = parse_sans("localhost, 127.0.0.1, 192.168.1.10, myserver.local")
        assert "localhost" in dns
        assert "myserver.local" in dns
        assert ipaddress.ip_address("127.0.0.1") in ips
        assert ipaddress.ip_address("192.168.1.10") in ips

    def test_ipv6(self):
        dns, ips = parse_sans("::1")
        assert ipaddress.ip_address("::1") in ips
        assert dns == []

    def test_empty_string(self):
        dns, ips = parse_sans("")
        assert dns == []
        assert ips == []

    def test_whitespace_and_empty_entries_ignored(self):
        dns, ips = parse_sans("  localhost  ,  ,  127.0.0.1  ")
        assert dns == ["localhost"]
        assert len(ips) == 1

    def test_newline_separated(self):
        dns, ips = parse_sans("localhost\n127.0.0.1")
        assert "localhost" in dns
        assert ipaddress.ip_address("127.0.0.1") in ips
