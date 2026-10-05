"""Tone generator: CW, beeps, Morse, SID tones, DTMF.

Generates audio in real-time (no file needed) and plays it
through the engine's output device.
"""

import numpy as np
import sounddevice as sd
from .engine import Engine


class ToneGen:
    """Generates and plays tones, CW, Morse, and DTMF."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._rate = engine.sample_rate
        self._device = engine.device
        self._playing = False

    def beep(self, freq: float = 1000.0, duration: float = 0.1, volume: float = 0.5):
        """Simple sine beep."""
        t = np.linspace(0, duration, int(self._rate * duration), endpoint=False)
        wave = volume * np.sin(2 * np.pi * freq * t).astype(np.float32)
        self._play(wave)

    def dual_tone(self, freq1: float, freq2: float, duration: float = 0.5, volume: float = 0.4):
        """Two-tone (alert, warning)."""
        t = np.linspace(0, duration, int(self._rate * duration), endpoint=False)
        wave = volume * (np.sin(2 * np.pi * freq1 * t) + np.sin(2 * np.pi * freq2 * t)) / 2
        wave = wave.astype(np.float32)
        self._play(wave)

    def sweep(self, freq_start: float, freq_end: float, duration: float = 1.0, volume: float = 0.4):
        """Frequency sweep."""
        t = np.linspace(0, duration, int(self._rate * duration), endpoint=False)
        freqs = np.linspace(freq_start, freq_end, len(t))
        phase = 2 * np.pi * np.cumsum(freqs) / self._rate
        wave = (volume * np.sin(phase)).astype(np.float32)
        self._play(wave)

    def cw(self, freq: float = 700.0, volume: float = 0.6):
        """Continuous wave (carrier). Holds until stop_cw()."""
        self._playing = True

        def callback(indata, outdata, frames, time_info, status):
            if not self._playing:
                outdata[:, :] = 0
                return
            outdata[:, 0] = volume * np.sin(2 * np.pi * freq * np.arange(frames) / self._rate)

        self._stream = sd.OutputStream(
            samplerate=self._rate, channels=1, device=self._device, callback=callback
        )
        self._stream.start()

    def stop_cw(self):
        self._playing = False
        if hasattr(self, '_stream'):
            self._stream.stop()
            self._stream.close()

    def morse(self, text: str, freq: float = 700.0, wpm: float = 15, volume: float = 0.6):
        """Play Morse code for the given text. Blocks until done."""
        morse_map = {
            'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.',
            'F': '..-.', 'G': '--.', 'H': '....', 'I': '..', 'J': '.---',
            'K': '-.-', 'L': '.-..', 'M': '--', 'N': '-.', 'O': '---',
            'P': '.--.', 'Q': '--.-', 'R': '.-.', 'S': '...', 'T': '-',
            'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-', 'Y': '-.--',
            'Z': '--..', '0': '-----', '1': '.----', '2': '..---',
            '3': '...--', '4': '....-', '5': '.....', '6': '-....',
            '7': '--...', '8': '---..', '9': '----.',
            '.': '.-.-.-', ',': '--..--', '?': '..--..', '/': '-..-.',
        }
        dot = 60.0 / wpm / 10.0  # seconds
        dash = dot * 3
        gap_intra = dot
        gap_inter = dot * 3
        gap_word = dot * 7

        # Build full waveform
        segments = []
        for char in text.upper():
            if char == ' ':
                segments.append((0, gap_word))
                continue
            code = morse_map.get(char, '')
            for i, symbol in enumerate(code):
                if i > 0:
                    segments.append((0, gap_intra))
                if symbol == '.':
                    segments.append((freq, dot))
                elif symbol == '-':
                    segments.append((freq, dash))
            if char != ' ':
                segments.append((0, gap_inter))

        total_dur = sum(d for _, d in segments)
        total_samples = int(total_dur * self._rate)
        wave = np.zeros(total_samples, dtype=np.float32)

        pos = 0
        for freq_val, duration in segments:
            n = int(duration * self._rate)
            t = np.arange(n) / self._rate
            if freq_val > 0:
                wave[pos:pos+n] = volume * np.sin(2 * np.pi * freq_val * t)
            pos += n

        self._play(wave)

    def sid_tone(self, freq: float = 67.0, duration: float = 1.0, volume: float = 0.8):
        """SSB sideband check tone (typically 67 Hz or 1000 Hz)."""
        t = np.linspace(0, duration, int(self._rate * duration), endpoint=False)
        wave = (volume * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        self._play(wave)

    def dtmf(self, digit: str, duration: float = 0.15, volume: float = 0.5):
        """DTMF dual-tone (phone keypad)."""
        dtmf_map = {
            '1': (697, 1209), '2': (697, 1336), '3': (697, 1477),
            '4': (770, 1209), '5': (770, 1336), '6': (770, 1477),
            '7': (852, 1209), '8': (852, 1336), '9': (852, 1477),
            '0': (941, 1336), '*': (941, 1209), '#': (941, 1477),
        }
        if digit not in dtmf_map:
            return
        f1, f2 = dtmf_map[digit]
        t = np.linspace(0, duration, int(self._rate * duration), endpoint=False)
        wave = volume * (np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)) / 2
        self._play(wave.astype(np.float32))

    def dtmf_sequence(self, digits: str, gap: float = 0.05, volume: float = 0.5):
        """Play a sequence of DTMF digits."""
        t_all = []
        for d in digits:
            f1, f2 = {
                '1': (697, 1209), '2': (697, 1336), '3': (697, 1477),
                '4': (770, 1209), '5': (770, 1336), '6': (770, 1477),
                '7': (852, 1209), '8': (852, 1336), '9': (852, 1477),
                '0': (941, 1336), '*': (941, 1209), '#': (941, 1477),
            }.get(d, (700, 1200))
            dur = 0.15
            t = np.linspace(0, dur, int(self._rate * dur), endpoint=False)
            seg = volume * (np.sin(2 * np.pi * f1 * t) + np.sin(2 * np.pi * f2 * t)) / 2
            t_all.append(seg)
            if d != digits[-1]:
                t_all.append(np.zeros(int(gap * self._rate), dtype=np.float32))
        wave = np.concatenate(t_all).astype(np.float32)
        self._play(wave)

    def arptone(self, duration: float = 2.0, volume: float = 0.7):
        """ARRL ARPTone (300 Hz + 2500 Hz)."""
        self.dual_tone(300.0, 2500.0, duration, volume)

    def _play(self, wave: np.ndarray) -> None:
        """Play a waveform through the engine's device."""
        vol = self.engine.global_volume
        if vol == 0:
            return
        data = (wave * vol).astype(np.float32)
        sd.play(data, self._rate, device=self._device)
