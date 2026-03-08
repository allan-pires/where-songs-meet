"""Tests for lib.sync: Room, get_lan_ip, payload format."""

import base64
import time

import pytest

from lib.sync import (
    DEFAULT_PORT,
    START_DELAY_SEC,
    Room,
    get_lan_ip,
)


class TestGetLanIp:
    """Test get_lan_ip returns a string."""

    def test_returns_string(self):
        ip = get_lan_ip()
        assert isinstance(ip, str)
        assert len(ip) >= 1

    def test_not_empty_when_success(self):
        ip = get_lan_ip()
        # Either a valid-looking IP or '?' on failure
        assert ip == '?' or (ip.count('.') == 3 and all(s.isdigit() for s in ip.split('.')))


class TestRoom:
    """Test Room host/client state and message handling."""

    def test_init_not_connected(self):
        r = Room()
        assert not r.is_host()
        assert not r.is_client()
        assert not r.is_connected()
        assert r.client_count() == 0

    def test_start_host_on_port_zero_binds_any(self):
        r = Room()
        port = r.start_host(port=0)
        try:
            assert port != 0
            assert r.is_host()
            assert r.is_connected()
        finally:
            r.stop_host()

    def test_start_host_twice_returns_zero_second_time(self):
        r = Room()
        p1 = r.start_host(port=0)
        try:
            assert p1 != 0
            p2 = r.start_host(port=0)
            assert p2 == 0
        finally:
            r.stop_host()

    def test_stop_host_clears_state(self):
        r = Room()
        r.start_host(port=0)
        r.stop_host()
        assert not r.is_host()
        assert not r.is_connected()

    def test_send_play_file_no_clients_does_not_raise(self):
        r = Room()
        r.start_host(port=0)
        try:
            r.send_play_file(2.0, b'\x00\x00', 1.0, 0)
        finally:
            r.stop_host()

    def test_handle_message_play_file_invokes_callback(self):
        r = Room()
        received = []
        def on_play(start_in, midi_bytes, tempo, transpose, *rest):
            received.append(('play_file', start_in, len(midi_bytes), tempo, transpose, rest[0] if rest else None))
        r.on_play_file = on_play
        payload = {
            'cmd': 'play_file',
            'start_in_sec': 2.5,
            'host_send_time': time.time(),
            'midi_base64': base64.b64encode(b'MThd').decode('ascii'),
            'tempo': 1.0,
            'transpose': 0,
        }
        r._handle_message(payload)
        assert len(received) == 1
        assert received[0][0] == 'play_file'
        assert received[0][1] == 2.5
        assert received[0][3] == 1.0
        assert received[0][4] == 0
        assert received[0][5] is not None

    def test_handle_message_play_os_invokes_callback(self):
        r = Room()
        received = []
        def on_play(start_in, sid, tempo, transpose, *rest):
            received.append(('play_os', start_in, sid, tempo, transpose, rest[0] if rest else None))
        r.on_play_os = on_play
        payload = {
            'cmd': 'play_os',
            'start_in_sec': 3.0,
            'host_send_time': 12345.67,
            'sid': '999',
            'tempo': 1.2,
            'transpose': 2,
        }
        r._handle_message(payload)
        assert len(received) == 1
        assert received[0][0] == 'play_os'
        assert received[0][1] == 3.0
        assert received[0][2] == '999'
        assert received[0][3] == 1.2
        assert received[0][4] == 2
        assert received[0][5] == 12345.67

    def test_handle_message_unknown_cmd_ignored(self):
        r = Room()
        r.on_play_file = lambda *a, **k: None
        r._handle_message({'cmd': 'unknown'})
        # no raise

    def test_connect_refuses_when_already_host(self):
        r = Room()
        r.start_host(port=0)
        try:
            ok = r.connect('127.0.0.1', 9999)
            assert ok is False
        finally:
            r.stop_host()
