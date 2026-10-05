"""Sound sequences, looping, and fade effects."""

import threading
import time
import numpy as np
from .engine import Engine


class Sequencer:
    """Plays sequences of sounds with optional fade/loop."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._stop_event = threading.Event()

    def sequence(self, names: list[str], gap: float = 0.05, blocking: bool = False) -> None:
        """Play a list of sounds in order with a gap between each."""
        self._stop_event.clear()

        def _run():
            for name in names:
                if self._stop_event.is_set():
                    return
                if not self.engine.play(name, blocking=True):
                    time.sleep(0.01)
                time.sleep(gap)

        if blocking:
            _run()
        else:
            threading.Thread(target=_run, daemon=True).start()

    def loop(self, name: str, gap: float = 0.0, max_loops: int = 0) -> None:
        """Loop a sound. max_loops=0 means infinite (call stop() to halt)."""
        self._stop_event.clear()
        loops = 0

        def _run():
            while not self._stop_event.is_set():
                if not self.engine.play(name, blocking=True):
                    break
                loops += 1
                if max_loops and loops >= max_loops:
                    break
                if gap > 0:
                    time.sleep(gap)

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> None:
        self._stop_event.set()
        self.engine.stop_all()

    def fade_play(self, name: str, fade_in: float = 0.1, fade_out: float = 0.1, blocking: bool = False) -> None:
        """Play a sound with linear fade in/out."""
        sound = self.engine._sounds.get(name)
        if sound is None:
            return

        data = sound.data.copy()
        n = len(data)
        vol = self.engine.global_volume * sound.volume

        # Fade in
        fi = int(fade_in * self.engine.sample_rate)
        if fi > 0 and fi < n:
            data[:fi] *= np.linspace(0, 1, fi, dtype=np.float32)

        # Fade out
        fo = int(fade_out * self.engine.sample_rate)
        if fo > 0 and fo < n:
            data[-fo:] *= np.linspace(1, 0, fo, dtype=np.float32)

        data *= vol

        if blocking:
            import sounddevice as sd
            sd.play(data, self.engine.sample_rate, device=self.engine.device)
            sd.wait()
        else:
            import sounddevice as sd
            sd.play(data, self.engine.sample_rate, device=self.engine.device)


class Recorder:
    """Record audio from an input device and save as a sound."""

    def __init__(self, engine: Engine, input_device: int | None = None):
        self.engine = engine
        self.input_device = input_device
        self._recording = False
        self._stream = None

    def record(self, filename: str, duration: float | None = None) -> str | None:
        """Record audio. If duration is None, records until stop().
        Returns the saved filename, or None on error.
        """
        import sounddevice as sd
        from pathlib import Path

        sr = self.engine.sample_rate
        channels = 1

        collected = []
        self._recording = True
        end_time = time.time() + duration if duration else None

        def callback(indata, frames, time_info, status):
            if status:
                print(f"[record] {status}")
            collected.append(indata.copy())
            if end_time and time.time() >= end_time:
                self._stop()

        self._stream = sd.InputStream(
            samplerate=sr, channels=channels, device=self.input_device,
            callback=callback, blocksize=int(sr * 0.1)
        )
        self._stream.start()
        print(f"[record] Recording for {duration or '?'}s... (Ctrl+C to stop early)")

        try:
            if duration:
                time.sleep(duration)
            else:
                while self._recording:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            pass

        self._stop()

        if not collected:
            print("[record] No audio captured")
            return None

        data = np.concatenate(collected, axis=0)
        out_path = Path(self.engine.sounds_dir) / filename
        if not out_path.suffix:
            out_path = out_path.with_suffix(".wav")

        import soundfile as sf
        sf.write(str(out_path), data, sr, subtype='PCM_16')
        print(f"[record] Saved: {out_path} ({len(data)/sr:.2f}s)")
        return str(out_path)

    def _stop(self) -> None:
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
