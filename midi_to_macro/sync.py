"""Play together: host a room or join one; host's Play triggers synced playback for all."""

import base64
import json
import logging
import socket
import threading
import time
from typing import Callable

log = logging.getLogger("midi_to_macro.sync")

DEFAULT_PORT = 38472
START_DELAY_SEC = 3.0  # longer delay so clients have time to receive and clocks align better


def get_lan_ip() -> str:
    """Return this machine's LAN IP (e.g. 192.168.1.x) for others to connect to. Avoids 127.0.0.1 on Windows."""
    try:
        # Connect to an external address to see which local interface would be used (no data sent).
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(('8.8.8.8', 1))
            return s.getsockname()[0]
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return '?'


class Room:
    """Host or client for synced play. All callbacks are invoked from the reader thread; app must schedule GUI updates."""

    def __init__(self):
        self._host_socket: socket.socket | None = None
        self._host_thread: threading.Thread | None = None
        self._clients: list[socket.socket] = []
        self._client_socket: socket.socket | None = None
        self._client_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._running = False

        self.on_play_file: Callable[..., None] | None = None
        self.on_play_os: Callable[..., None] | None = None
        self.on_stop: Callable[[], None] | None = None
        self.on_clients_changed: Callable[[int], None] | None = None
        self.on_connected: Callable[[], None] | None = None
        self.on_disconnected: Callable[[], None] | None = None
        self.on_room_playing: Callable[[list[tuple[str, str]]], None] | None = None  # [(who, label), ...]

        self._host_playing_label = ""
        self._client_labels: dict[int, str] = {}  # id(client) -> label

    def is_host(self) -> bool:
        return self._host_socket is not None

    def is_client(self) -> bool:
        return self._client_socket is not None

    def is_connected(self) -> bool:
        return self.is_host() or self.is_client()

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def start_host(self, port: int = DEFAULT_PORT) -> int:
        """Start hosting on port. Returns actual port or 0 on failure."""
        if self.is_connected():
            log.warning("start_host: already connected")
            return 0
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
            sock.listen(4)
            if port == 0:
                port = sock.getsockname()[1]
        except OSError as e:
            log.warning("start_host bind failed port=%s: %s", port, e)
            return 0
        self._host_socket = sock
        self._running = True
        self._host_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._host_thread.start()
        log.info("Host listening on port %s", port)
        return port

    def _accept_loop(self):
        assert self._host_socket is not None
        while self._running and self._host_socket:
            try:
                self._host_socket.settimeout(0.5)
                client, _ = self._host_socket.accept()
            except (socket.timeout, OSError):
                continue
            with self._lock:
                self._clients.append(client)
            log.info("Client connected (peer %s); total %s", client.getpeername(), len(self._clients))
            if self.on_clients_changed:
                self.on_clients_changed(self.client_count())
            threading.Thread(target=self._serve_client, args=(client,), daemon=True).start()

    def _serve_client(self, client: socket.socket):
        buf = b''
        try:
            client.settimeout(300.0)
            while self._running:
                data = client.recv(4096)
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode('utf-8'))
                        if msg.get('cmd') == 'report_playing':
                            label = str(msg.get('label', ''))[:200]
                            self._client_labels[id(client)] = label
                            self._broadcast_room_playing()
                    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                        pass
        except (OSError, ConnectionResetError) as e:
            log.debug("Client connection closed: %s", e)
        finally:
            self._client_labels.pop(id(client), None)
            self._broadcast_room_playing()
            with self._lock:
                if client in self._clients:
                    self._clients.remove(client)
                    log.info("Client disconnected; %s participant(s) left", len(self._clients))
            try:
                client.close()
            except OSError:
                pass
            if self.on_clients_changed:
                self.on_clients_changed(self.client_count())

    def _broadcast_room_playing(self):
        """Build players list and send to all clients; notify host UI via callback."""
        players = [('host', self._host_playing_label)]
        with self._lock:
            for c in self._clients:
                players.append(('client', self._client_labels.get(id(c), '')))
        payload = {'cmd': 'room_playing', 'players': players}
        line = (json.dumps(payload) + '\n').encode('utf-8')
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(line)
                except OSError:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
        if self.on_room_playing:
            self.on_room_playing(players)

    def stop_host(self):
        log.info("Stop host")
        self._running = False
        self._host_playing_label = ""
        self._client_labels.clear()
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._host_socket:
            try:
                self._host_socket.close()
            except OSError:
                pass
            self._host_socket = None
        if self.on_clients_changed:
            self.on_clients_changed(0)

    def connect(self, host: str, port: int) -> bool:
        """Connect to host. Returns True on success."""
        if self.is_connected():
            log.warning("connect: already connected")
            return False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((host, port))
            sock.settimeout(1.0)  # short timeout so recv loop checks _running often
        except (OSError, socket.gaierror) as e:
            log.warning("connect failed %s:%s: %s", host, port, e)
            return False
        self._client_socket = sock
        self._running = True
        log.info("Connected to %s:%s", host, port)
        if self.on_connected:
            self.on_connected()
        self._client_thread = threading.Thread(target=self._client_recv_loop, daemon=True)
        self._client_thread.start()
        return True

    def _client_recv_loop(self):
        buf = b''
        assert self._client_socket is not None
        try:
            while self._running and self._client_socket:
                try:
                    data = self._client_socket.recv(4096)
                except socket.timeout:
                    # Idle: no data from host yet; keep waiting
                    continue
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode('utf-8'))
                        self._handle_message(msg)
                    except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
                        pass
        except (OSError, ConnectionResetError) as e:
            log.info("Disconnected from host: %s", e)
        finally:
            self._client_socket = None
            self._running = False
            if self.on_disconnected:
                self.on_disconnected()

    def _handle_message(self, msg: dict):
        cmd = msg.get('cmd')
        host_send_time = msg.get('host_send_time')  # host's time.time() when sending (for reference)
        host_playing_label = str(msg.get('host_playing_label', ''))
        client_recv_time = time.time()  # client uses this for sync so start is ~start_in_sec after receive
        if cmd == 'play_file' and self.on_play_file:
            try:
                start_in = float(msg.get('start_in_sec', START_DELAY_SEC))
                b64 = msg.get('midi_base64', '')
                midi_bytes = base64.b64decode(b64)
                tempo = float(msg.get('tempo', 1.0))
                transpose = int(msg.get('transpose', 0))
                self.on_play_file(start_in, midi_bytes, tempo, transpose, host_send_time, host_playing_label, client_recv_time)
            except (TypeError, ValueError):
                pass
        elif cmd == 'play_os' and self.on_play_os:
            try:
                start_in = float(msg.get('start_in_sec', START_DELAY_SEC))
                sid = str(msg.get('sid', ''))
                tempo = float(msg.get('tempo', 1.0))
                transpose = int(msg.get('transpose', 0))
                self.on_play_os(start_in, sid, tempo, transpose, host_send_time, host_playing_label, client_recv_time)
            except (TypeError, ValueError):
                pass
        elif cmd == 'stop' and self.on_stop:
            self.on_stop()
        elif cmd == 'room_playing' and self.on_room_playing:
            try:
                players = list(msg.get('players', []))
                self.on_room_playing([(str(w), str(l)) for w, l in players])
            except (TypeError, ValueError):
                pass

    def disconnect(self):
        """Leave the room (client only). Wakes the recv thread and updates UI."""
        log.info("Client disconnecting")
        self._running = False
        if self._client_socket:
            try:
                self._client_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._client_socket.close()
            except OSError:
                pass
            self._client_socket = None
        if self.on_disconnected:
            self.on_disconnected()

    def send_report_playing(self, label: str):
        """Client only: tell host what we're playing (for room_playing display)."""
        if not self.is_client() or not self._client_socket:
            return
        payload = {'cmd': 'report_playing', 'label': label[:200]}
        line = (json.dumps(payload) + '\n').encode('utf-8')
        try:
            self._client_socket.sendall(line)
        except OSError:
            pass

    def host_report_playing(self, label: str):
        """Host only: set host's playing label and broadcast room_playing to all clients."""
        if not self.is_host():
            return
        self._host_playing_label = label[:200]
        self._broadcast_room_playing()

    def send_play_file(self, start_in_sec: float, midi_bytes: bytes, tempo: float, transpose: int, host_playing_label: str = ''):
        """Host only: broadcast play file to all clients."""
        if not self.is_host():
            return
        host_send_time = time.time()
        payload = {
            'cmd': 'play_file',
            'start_in_sec': start_in_sec,
            'host_send_time': host_send_time,
            'midi_base64': base64.b64encode(midi_bytes).decode('ascii'),
            'tempo': tempo,
            'transpose': transpose,
            'host_playing_label': host_playing_label,
        }
        line = (json.dumps(payload) + '\n').encode('utf-8')
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(line)
                except OSError:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
        if dead and self.on_clients_changed:
            self.on_clients_changed(self.client_count())

    def send_play_os(self, start_in_sec: float, sid: str, tempo: float, transpose: int, host_playing_label: str = ''):
        """Host only: broadcast play OS sequence to all clients."""
        if not self.is_host():
            return
        host_send_time = time.time()
        payload = {
            'cmd': 'play_os',
            'start_in_sec': start_in_sec,
            'host_send_time': host_send_time,
            'sid': sid,
            'tempo': tempo,
            'transpose': transpose,
            'host_playing_label': host_playing_label,
        }
        line = (json.dumps(payload) + '\n').encode('utf-8')
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(line)
                except OSError:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
        if dead and self.on_clients_changed:
            self.on_clients_changed(self.client_count())

    def send_stop(self):
        """Host only: broadcast stop to all clients so they stop playback too."""
        if not self.is_host():
            return
        payload = {'cmd': 'stop'}
        line = (json.dumps(payload) + '\n').encode('utf-8')
        with self._lock:
            dead = []
            for c in self._clients:
                try:
                    c.sendall(line)
                except OSError:
                    dead.append(c)
            for c in dead:
                self._clients.remove(c)
        if dead and self.on_clients_changed:
            self.on_clients_changed(self.client_count())
