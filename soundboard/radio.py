"""Radio control via the rigctld text protocol (FLRig / hamlib rigctld).

Minimal stdlib-socket client -- no new dependencies. FLRig (Windows) and
``rigctld`` (Linux/hamlib) both speak this protocol on TCP port 4532 by
default, so one client covers both.

Protocol commands used:
    P1 / P0   key / release PTT
    P         query PTT state ("0"/"1")
    F         query frequency (Hz)
    M         query mode (single letter)
    I         rig info string
    V         version string

A single background thread owns the connection: it (re)connects with
backoff, polls PTT state for the live UI indicator, and refreshes
frequency/mode. All command sends are lock-protected so playback threads
can key PTT safely.
"""

import socket
import threading
import time

MODE_NAMES = {
    "U": "USB", "L": "LSB", "F": "FM", "W": "CW", "A": "AM",
    "D": "Data", "N": "None", "S": "RTTY", "B": "PSK31",
}

# Name -> rigctld mode letter (for setting)
MODE_CHARS = {
    "FM": "F", "USB": "U", "LSB": "L", "CW": "W", "AM": "A", "DATA": "D",
}


def parse_freq(value) -> int | None:
    """Parse a frequency given as MHz ("145.500", "7.0740") or Hz ("145500000").

    Returns integer Hz, or None if unparseable.
    """
    s = str(value).strip()
    try:
        if "." in s:
            return int(float(s) * 1_000_000)
        v = int(s)
        return v if v >= 100_000 else v * 1_000_000
    except ValueError:
        return None


def _fmt_freq(hz) -> str | None:
    if hz is None:
        return None
    try:
        hz = float(hz)
    except (TypeError, ValueError):
        return str(hz)
    if hz >= 1_000_000:
        return f"{hz / 1_000_000:.3f} MHz"
    return f"{hz / 1000:.1f} kHz"


def _fmt_mode(m) -> str | None:
    if not m:
        return None
    m = m.strip()
    return MODE_NAMES.get(m[0].upper(), m)


class RigClient:
    """Threaded rigctld client with PTT reference counting."""

    def __init__(self, cfg: dict, on_ptt_change=None):
        r = cfg.get("radio", {}) or {}
        self.host = str(r.get("host", "127.0.0.1"))
        self.port = int(r.get("port", 4532))
        self.enabled = bool(r.get("enabled", False))
        self.ptt_on_play = bool(r.get("ptt_on_play", True))
        self.ptt_pre_ms = int(r.get("ptt_pre_ms", 50))
        self.ptt_post_ms = int(r.get("ptt_post_ms", 150))
        self.ptt_trigger_sound = r.get("ptt_trigger_sound", "") or ""
        self.on_ptt_change = on_ptt_change  # callback(ptt: bool)

        self._sock: socket.socket | None = None
        self._buf = b""
        self._lock = threading.Lock()
        self._ptt_refs = 0        # sounds currently holding PTT
        self._manual_ptt = False  # manual PTT (UI button / key)
        self._ext_ptt = False     # PTT held externally (user keyed the radio)
        self._ptt_state = False   # last PTT state read from the radio
        self._info = ""
        self._freq: str | None = None
        self._mode: str | None = None
        self._last_error = ""
        self._running = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread is not None:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="rig")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._send("P0")  # never leave the radio keyed
        with self._lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def reconfigure(self, **kw) -> None:
        """Update settings live (from the web UI) and force a reconnect."""
        with self._lock:
            if "host" in kw:
                self.host = str(kw["host"])
            if "port" in kw:
                self.port = int(kw["port"])
            if "enabled" in kw:
                self.enabled = bool(kw["enabled"])
            if "ptt_on_play" in kw:
                self.ptt_on_play = bool(kw["ptt_on_play"])
            if "ptt_pre_ms" in kw:
                self.ptt_pre_ms = max(0, int(kw["ptt_pre_ms"]))
            if "ptt_post_ms" in kw:
                self.ptt_post_ms = max(0, int(kw["ptt_post_ms"]))
            if "ptt_trigger_sound" in kw:
                self.ptt_trigger_sound = str(kw["ptt_trigger_sound"] or "")
            if self._sock is not None:
                try:
                    self._sock.close()
                except OSError:
                    pass
                self._sock = None

    # ------------------------------------------------------------------ #
    # PTT (called from engine playback threads)
    # ------------------------------------------------------------------ #

    def pre_play(self) -> None:
        """Key PTT just before a sound starts (refcounted)."""
        if not (self.enabled and self.ptt_on_play):
            return
        with self._lock:
            self._ptt_refs += 1
            first = self._ptt_refs == 1
        if first:
            if self.ptt_pre_ms > 0:
                time.sleep(self.ptt_pre_ms / 1000.0)
            self._send("P1")

    def post_play(self) -> None:
        """Release PTT after a sound finishes (refcounted).

        Always sends P0 when our refcount hits 0 (unless manual PTT is
        held). If the user is also keying the radio, the P0 is harmless:
        the radio ORs PTT sources and stays keyed by the user's mic.
        """
        if not (self.enabled and self.ptt_on_play):
            return
        with self._lock:
            self._ptt_refs = max(0, self._ptt_refs - 1)
            last = self._ptt_refs == 0
        if last and not self._manual_ptt:
            if self.ptt_post_ms > 0:
                time.sleep(self.ptt_post_ms / 1000.0)
            self._send("P0")

    def ptt_toggle(self) -> bool:
        """Toggle manual PTT. Returns the new manual state."""
        self._manual_ptt = not self._manual_ptt
        if self._manual_ptt:
            self._send("P1")
        else:
            with self._lock:
                idle = self._ptt_refs == 0
            if idle:
                self._send("P0")
        return self._manual_ptt

    # ------------------------------------------------------------------ #
    # status / test
    # ------------------------------------------------------------------ #

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "connected": self._sock is not None,
            "host": self.host,
            "port": self.port,
            "ptt": self._ptt_state,
            "ptt_refs": self._ptt_refs,
            "manual_ptt": self._manual_ptt,
            "freq": _fmt_freq(self._freq),
            "freq_hz": self._freq,
            "mode": _fmt_mode(self._mode),
            "info": self._info,
            "error": self._last_error,
            "ptt_on_play": self.ptt_on_play,
            "ptt_pre_ms": self.ptt_pre_ms,
            "ptt_post_ms": self.ptt_post_ms,
            "ptt_trigger_sound": self.ptt_trigger_sound,
        }

    def test(self) -> dict:
        """One-shot connection test with actionable diagnostics."""
        if self._sock is None and not self._try_connect():
            return {
                "ok": False,
                "error": self._last_error or "connection failed",
                "hint": f"Is FLRig (Rig Control) or rigctld listening on {self.host}:{self.port}?",
            }
        info = self._send("I") or ""
        freq = self._send("F")
        mode = self._send("M")
        ok = bool(info or freq)
        return {
            "ok": ok,
            "info": info,
            "freq": _fmt_freq(freq),
            "mode": _fmt_mode(mode),
            "error": "" if ok else (self._last_error or "no response"),
        }

    def set_freq(self, hz: int) -> bool:
        """Set the radio frequency (integer Hz). True on success."""
        return self._send(f"F{int(hz)}") is not None

    def set_mode(self, mode: str) -> bool:
        """Set the radio mode by name (FM/USB/LSB/CW/AM/DATA) or letter. True on success."""
        letter = MODE_CHARS.get(mode.upper(), mode.upper()[:1])
        return self._send(f"M{letter}") is not None

    # ------------------------------------------------------------------ #
    # transport
    # ------------------------------------------------------------------ #

    def _try_connect(self) -> bool:
        with self._lock:
            if self._sock is not None:
                return True
            try:
                s = socket.create_connection((self.host, self.port), timeout=3)
                s.settimeout(1.0)
                self._sock = s
                self._buf = b""
                self._last_error = ""
                return True
            except Exception as e:
                self._last_error = f"{type(e).__name__}: {e}"
                return False

    def _send(self, cmd: str) -> str | None:
        """Send a command line, return the response line (None on error)."""
        with self._lock:
            if self._sock is None:
                return None
            try:
                self._sock.sendall((cmd + "\n").encode())
                return self._readline_locked()
            except Exception:
                self._close_locked()
                return None

    def _readline_locked(self) -> str:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("closed by peer")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode(errors="replace").strip()

    def _close_locked(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            self._buf = b""

    # ------------------------------------------------------------------ #
    # background thread
    # ------------------------------------------------------------------ #

    def _run(self) -> None:
        backoff = 1.0
        poll = 0
        while self._running:
            if not self.enabled:
                time.sleep(0.5)
                continue

            if self._sock is None:
                if self._try_connect():
                    backoff = 1.0
                    self._info = self._send("I") or ""
                    self._freq = self._send("F")
                    self._mode = self._send("M")
                    print(f"[radio] connected: {self.host}:{self.port} {self._info}".rstrip())
                else:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 10.0)
                    continue

            # Connected: poll PTT state (source of truth for the UI).
            resp = self._send("P")
            if resp is None:
                # Dropped -- reconnect quickly on the next loop.
                backoff = 1.0
                time.sleep(0.2)
                continue
            new_state = resp == "1"
            if new_state != self._ptt_state:
                self._ptt_state = new_state
                with self._lock:
                    if new_state:
                        # Rising edge: external (user keyed the radio) only
                        # if our own playback isn't holding PTT.
                        self._ext_ptt = self._ptt_refs == 0
                    else:
                        self._ext_ptt = False
                if self.on_ptt_change is not None:
                    # Only notify on external rises -- our own P1 must not
                    # re-trigger the "radio keyed" sound.
                    if new_state and not self._ext_ptt:
                        pass
                    else:
                        try:
                            self.on_ptt_change(new_state)
                        except Exception:
                            pass
            poll += 1
            if poll % 20 == 0:  # refresh freq/mode ~2x per second
                self._freq = self._send("F")
                self._mode = self._send("M")
            time.sleep(0.1)


def setup_radio(cfg: dict, engine) -> RigClient:
    """Create, wire and start a RigClient from config.

    Hooks the engine's pre/post playback callbacks so sounds key the
    radio (PTT on playback). A muted engine never keys. If
    ``ptt_trigger_sound`` is set, that sound plays when the radio is
    keyed externally (rising PTT edge).
    """
    rig = RigClient(cfg)

    def _pre(name: str) -> None:
        if engine.global_volume == 0:
            return
        rig.pre_play()

    def _post(name: str) -> None:
        rig.post_play()

    def _on_ptt(ptt: bool) -> None:
        if ptt and rig.ptt_trigger_sound and engine.global_volume > 0:
            engine.play(rig.ptt_trigger_sound)

    engine.pre_hook = _pre
    engine.post_hook = _post
    rig.on_ptt_change = _on_ptt
    rig.start()
    return rig