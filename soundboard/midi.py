"""MIDI input support for NutTx.

Map MIDI note-on events to sound triggers.
Requires: pip install python-rtmidi
"""

import threading

try:
    from rtmidi import MidiIn
    HAS_MIDI = True
except ImportError:
    HAS_MIDI = False


class MidiInput:
    """Listens for MIDI note-on messages and triggers sounds.

    Mapping: MIDI note number -> key character
    By default: C4(60)='1', C#4(61)='2', D4(62)='3', ... A4(69)='0',
    C5(72)='m' (mute)
    """

    # Default mapping: note -> key
    DEFAULT_MAP = {
        60: '1', 61: '2', 62: '3', 63: '4', 64: '5',
        65: '6', 66: '7', 67: '8', 68: '9', 69: '0',
        72: 'm', 73: 'p',  # mute, panic
    }

    def __init__(self, on_key: callable, device: str = "default", note_map: dict | None = None):
        if not HAS_MIDI:
            raise ImportError("python-rtmidi not installed. Run: pip install python-rtmidi")
        self.on_key = on_key
        self.device = device
        self.note_map = note_map or self.DEFAULT_MAP
        self._running = False
        self._port = None
        self._thread = None

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._port:
            self._port.close_port()

    def _listen(self) -> None:
        try:
            if self.device == "default":
                port = 0
            elif self.device.isdigit():
                port = int(self.device)
            else:
                port = self._find_port(self.device)
                if port is None:
                    print("[midi] No matching MIDI device found")
                    return

            self._port = MidiIn()
            self._port.open_port(port)
            self._port.set_message_callback(self._on_message)
            name = self._port.get_port_name()
            print(f"[midi] Opened: {name}")

            while self._running:
                import time
                time.sleep(0.5)

        except Exception as e:
            print(f"[midi] Error: {e}")

    def _find_port(self, name: str) -> int | None:
        from rtmidi import MidiIn
        probe = MidiIn()
        count = probe.get_port_count()
        for i in range(count):
            if name.lower() in probe.get_port_name(i).lower():
                return i
        probe.close_port() if probe.is_port_open() else None
        return None

    def _on_message(self, msg) -> None:
        if len(msg) < 3:
            return
        status = msg[0] & 0xF0
        note = msg[1]
        velocity = msg[2]
        # Note-on with velocity > 0
        if status == 0x90 and velocity > 0:
            key = self.note_map.get(note)
            if key:
                self.on_key(key)
