"""Serial input listener for NutTx (ESP32 USB CDC mode)."""

import threading
import select
import sys


class SerialInput:
    """Reads single-char commands from a USB serial device.

    Used with the ESP32 in USB CDC serial mode.
    """

    def __init__(self, port: str, on_key: callable):
        self.port = port
        self.on_key = on_key
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _listen(self) -> None:
        try:
            fd = open(self.port, "rb", buffering=0)
        except OSError as e:
            print(f"[serial] Cannot open {self.port}: {e}")
            return

        print(f"[serial] Listening on {self.port}")
        try:
            while self._running:
                ready, _, _ = select.select([fd], [], [], 0.1)
                if ready:
                    data = fd.read(1)
                    if data:
                        ch = data.decode("ascii", errors="ignore")
                        if ch:
                            self.on_key(ch)
        finally:
            fd.close()
            print("[serial] Disconnected")
