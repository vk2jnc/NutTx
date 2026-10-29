"""Text-to-speech via any OpenAI-compatible /audio/speech endpoint.

Stdlib `urllib` only -- no new dependencies. The API returns MP3 bytes;
those are decoded with `soundfile` and played through the *same* Engine
output path as the soundbank (radio line-in or PipeWire sink).

Nothing is hardcoded. Endpoint, model and voice come from the ``[tts]``
section of config.toml, and every setting can be overridden by an
environment variable (env wins over config):

    NUTTX_TTS_ENABLED    1/true/yes/on to force-enable
    NUTTX_TTS_BASE_URL   base URL of the endpoint, e.g. https://host/v1
    NUTTX_TTS_KEY_ENV    name of the env var holding the API key
    NUTTX_TTS_API_KEY    the API key itself (default key_env name)
    NUTTX_TTS_MODEL      model name
    NUTTX_TTS_VOICE      voice name

The API key is only ever read from the environment -- never stored in
config files.
"""

import json
import os
import time
import urllib.request
from urllib.parse import urlparse

DEFAULT_KEY_ENV = "NUTTX_TTS_API_KEY"


def _env(name: str) -> str | None:
    """Non-empty env var value or None."""
    v = os.environ.get(name)
    return v.strip() if v is not None and v.strip() else None


class TTSClient:
    """Thin client for an OpenAI-compatible /audio/speech endpoint."""

    def __init__(self, cfg: dict):
        t = cfg.get("tts", {}) or {}
        env_en = _env("NUTTX_TTS_ENABLED")
        if env_en is not None:
            self.enabled = env_en.lower() in ("1", "true", "yes", "on")
        else:
            self.enabled = bool(t.get("enabled", False))
        self.base_url = (_env("NUTTX_TTS_BASE_URL") or t.get("base_url", "") or "").rstrip("/")
        self.key_env = (_env("NUTTX_TTS_KEY_ENV") or t.get("key_env") or DEFAULT_KEY_ENV)
        self.model = _env("NUTTX_TTS_MODEL") or t.get("model") or "tts-1"
        self.voice = _env("NUTTX_TTS_VOICE") or t.get("voice") or "alloy"
        self.timeout = int(t.get("request_timeout", 30))
        self.max_chars = int(t.get("max_text_chars", 500))
        self.cache_dir = t.get("cache_dir", "") or ""

    def _key(self) -> str:
        return os.environ.get(self.key_env, "").strip()

    def available(self) -> bool:
        """True when TTS is enabled, has a URL, and the API key is set."""
        return bool(self.enabled and self.base_url and self._key())

    def _host(self) -> str:
        try:
            return urlparse(self.base_url).netloc or self.base_url
        except Exception:
            return "?"

    def status(self) -> str:
        if not self.enabled:
            return "disabled (set [tts] enabled = true or NUTTX_TTS_ENABLED=1)"
        if not self.base_url:
            return "no endpoint (set [tts].base_url or NUTTX_TTS_BASE_URL)"
        if not self._key():
            return f"missing key (env {self.key_env})"
        return f"ready ({self._host()}, model={self.model}, voice={self.voice})"

    def synthesize(self, text: str) -> bytes:
        """POST /audio/speech and return raw MP3 bytes."""
        text = (text or "").strip()
        if not text:
            raise ValueError("empty text")
        if len(text) > self.max_chars:
            raise ValueError(f"text too long ({len(text)} chars, max {self.max_chars})")
        key = self._key()
        if not key:
            raise RuntimeError(f"API key not set (env var {self.key_env})")

        url = f"{self.base_url}/audio/speech"
        payload = json.dumps({
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": "mp3",
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {key}")

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            audio = resp.read()
        if not audio:
            raise RuntimeError("TTS returned empty audio")
        return audio

    def speak(self, text: str, engine, blocking: bool = True) -> bool:
        """Synthesize text and play it through the engine's output path.

        ``blocking=True`` waits for the clip to finish (used by the CLI so
        the process doesn't exit before the audio plays). The web UI uses
        ``blocking=False`` so the HTTP handler returns immediately.
        """
        if not self.available():
            raise RuntimeError(f"TTS not available: {self.status()}")
        mp3 = self.synthesize(text)
        # Optional: persist the clip if a cache dir is configured.
        if self.cache_dir:
            try:
                from pathlib import Path
                cdir = Path(self.cache_dir)
                cdir.mkdir(parents=True, exist_ok=True)
                slug = "".join(c if (c.isalnum() or c in "-_") else "_" for c in text[:40]).strip("_") or "clip"
                (cdir / f"{int(time.time())}_{slug}.mp3").write_bytes(mp3)
            except Exception as e:
                print(f"[tts] cache write failed: {e}")
        return engine.play_clip(mp3, name="tts", blocking=blocking)