"""Ducking and safety features: panic, ducking, auto-mute."""

import time
import threading


class Safety:
    """Audio safety: panic stop, ducking, auto-mute timeout."""

    def __init__(self, engine, cfg: dict):
        self.engine = engine
        self.cfg = cfg
        self._duck_level = cfg.get("safety", {}).get("duck_level", 0.1)
        self._duck_release = cfg.get("safety", {}).get("duck_release_ms", 200)
        self._auto_mute_secs = cfg.get("safety", {}).get("auto_mute_secs", 0)
        self._base_volume = cfg.get("global", {}).get("volume", 0.8)
        self._last_activity = time.time()
        self._ducked = False
        self._muted = False
        self._watchdog = None

    def panic(self) -> None:
        """Immediate hard stop of all audio."""
        self.engine.stop_all()
        self.engine.global_volume = 0.0
        self._muted = True
        print("[safety] PANIC - all audio stopped, muted")

    def duck(self) -> None:
        """Lower volume to duck_level (for priority sounds)."""
        if not self._ducked:
            self.engine.global_volume = self._duck_level
            self._ducked = True

    def unduck(self) -> None:
        """Restore volume after ducking."""
        if self._ducked:
            import threading
            def _restore():
                import time
                time.sleep(self._duck_release / 1000.0)
                if self._ducked:
                    self.engine.global_volume = self._base_volume if not self._muted else 0.0
                    self._ducked = False
            threading.Thread(target=_restore, daemon=True).start()

    def touch(self) -> None:
        """Mark activity (resets auto-mute timer)."""
        self._last_activity = time.time()

    def start_watchdog(self) -> None:
        """Start the auto-mute watchdog thread."""
        if self._auto_mute_secs <= 0:
            return
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog.start()

    def _watchdog_loop(self) -> None:
        while True:
            time.sleep(1.0)
            if self.engine.global_volume > 0:
                if time.time() - self._last_activity > self._auto_mute_secs:
                    print(f"[safety] Auto-mute after {self._auto_mute_secs}s idle")
                    self.engine.global_volume = 0.0
                    self._muted = True

    def unmute(self) -> None:
        self._muted = False
        self.engine.global_volume = self._base_volume
        self.touch()

    def is_muted(self) -> bool:
        return self.engine.global_volume == 0

    @property
    def idle_secs(self) -> float:
        return time.time() - self._last_activity
