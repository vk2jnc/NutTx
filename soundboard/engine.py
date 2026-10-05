"""Core audio playback engine."""

import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Sound:
    name: str
    data: np.ndarray
    sample_rate: int
    volume: float = 1.0


class Engine:
    """Non-blocking audio playback with preloaded sounds."""

    def __init__(
        self,
        device: int | None,
        sounds_dir: str = "sounds/",
        sample_rate: int = 0,
        channels: int = 1,
        global_volume: float = 0.8,
        preload: bool = True,
        overrides: dict | None = None,
    ):
        self.device = device
        self.sounds_dir = Path(sounds_dir)
        self.global_volume = global_volume
        self.overrides = overrides or {}
        self._sounds: dict[str, Sound] = {}
        self._lock = threading.Lock()
        self._active: set[str] = set()

        # Determine sample rate
        if sample_rate == 0:
            info = sd.query_devices(device, "output")
            self.sample_rate = int(info["default_samplerate"])
        else:
            self.sample_rate = sample_rate
        self.channels = channels

        if preload:
            self._load_all()

    def _load_all(self) -> None:
        """Load all supported audio files from sounds_dir into RAM."""
        extensions = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
        if not self.sounds_dir.exists():
            return
        for f in sorted(self.sounds_dir.iterdir()):
            if f.suffix.lower() in extensions:
                self._load_file(f)
        print(f"Loaded {len(self._sounds)} sounds into RAM.")

    def _load_file(self, path: Path) -> Sound | None:
        try:
            data, sr = sf.read(str(path), dtype="float32", always_2d=False)
        except Exception as e:
            print(f"  Skipping {path.name}: {e}")
            return None

        # Resample if needed
        if sr != self.sample_rate:
            data = self._resample(data, sr, self.sample_rate)
            sr = self.sample_rate

        # Convert to mono if needed
        if data.ndim == 2 and self.channels == 1:
            data = data.mean(axis=1)
        elif data.ndim == 1 and self.channels == 2:
            data = np.column_stack([data, data])

        vol = self.overrides.get(path.stem, 1.0)
        sound = Sound(name=path.stem, data=data, sample_rate=sr, volume=vol)
        self._sounds[path.stem] = sound
        return sound

    def _resample(self, data: np.ndarray, from_sr: int, to_sr: int) -> np.ndarray:
        """Simple linear interpolation resample."""
        if data.ndim == 2:
            return np.column_stack([
                self._resample(data[:, ch], from_sr, to_sr) for ch in range(data.shape[1])
            ])
        duration = len(data) / from_sr
        new_len = int(duration * to_sr)
        old_idx = np.linspace(0, len(data) - 1, new_len)
        return np.interp(old_idx, np.arange(len(data)), data).astype(np.float32)

    def play(self, name: str, blocking: bool = False) -> bool:
        """Play a sound by name (filename stem). Returns True if found and played."""
        with self._lock:
            if name in self._active:
                return False  # already playing
            sound = self._sounds.get(name)
            if sound is None:
                return False
            self._active.add(name)

        data = sound.data * (self.global_volume * sound.volume)

        def _done():
            with self._lock:
                self._active.discard(name)

        if blocking:
            sd.play(data, self.sample_rate, device=self.device)
            sd.wait()
            _done()
        else:
            sd.play(data, self.sample_rate, device=self.device, callback=_done)
        return True

    def play_file(self, filepath: str, blocking: bool = True) -> bool:
        """Play an arbitrary file (not necessarily in sounds dir)."""
        path = Path(filepath)
        sound = self._load_file(path)
        if sound is None:
            return False
        data = sound.data * self.global_volume
        sd.play(data, self.sample_rate, device=self.device)
        if blocking:
            sd.wait()
        return True

    def is_playing(self, name: str) -> bool:
        with self._lock:
            return name in self._active

    @property
    def loaded_sounds(self) -> list[str]:
        return sorted(self._sounds.keys())

    def stop_all(self) -> None:
        sd.stop()
        with self._lock:
            self._active.clear()
