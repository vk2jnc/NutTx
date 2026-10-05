"""UDP socket listener for NutTx (ESP32 WiFi mode)."""

import socket
import threading


class UDPInput:
    """Listens for UDP datagrams with single-char sound triggers.

    Used with the ESP32 in WiFi mode. Each button press sends a 1-byte
    UDP packet to this listener.
    """

    def __init__(self, port: int, on_key: callable, bind: str = "0.0.0.0"):
        self.port = port
        self.on_key = on_key
        self.bind = bind
        self._running = False
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()

    def _listen(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(0.5)
        self._sock.bind((self.bind, self.port))
        print(f"[udp] Listening on {self.bind}:{self.port}")

        while self._running:
            try:
                data, addr = self._sock.recvfrom(16)
                if data:
                    ch = data.decode("ascii", errors="ignore")
                    if ch:
                        self.on_key(ch)
            except socket.timeout:
                continue
            except OSError:
                break

        print("[udp] Stopped")
