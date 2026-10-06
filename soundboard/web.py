"""Web UI and HTTP API for NutTx.

Lightweight - no Flask, just http.server. Serves a single-page
control panel and a JSON REST API.
"""

import json
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path


class NutTxHandler(BaseHTTPRequestHandler):
    engine = None
    keys = None
    cfg = None
    play_log = []

    def log_message(self, format, *args):
        pass  # suppress request logging

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _html(self, content: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(content.encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._html(self._get_ui())
        elif path == "/api/status":
            self._json(200, {
                "device": self.engine.device,
                "sample_rate": self.engine.sample_rate,
                "channels": self.engine.channels,
                "volume": self.engine.global_volume,
                "muted": self.engine.global_volume == 0,
                "sounds": self.engine.loaded_sounds,
                "active": [k for k in self.keys if self.engine.is_playing(self.keys[k])],
            })
        elif path == "/api/sounds":
            self._json(200, {
                "sounds": self.engine.loaded_sounds,
                "keys": self.keys,
            })
        elif path == "/api/keys":
            self._json(200, {"keys": self.keys, "available_sounds": self.engine.loaded_sounds})
        elif path == "/api/log":
            self._json(200, {"log": self.play_log[-100:]})
        elif path == "/api/devices":
            import sounddevice as sd
            devices = []
            for idx, dev in enumerate(sd.query_devices()):
                if dev["max_output_channels"] > 0:
                    devices.append({"index": idx, "name": dev["name"],
                                    "rate": int(dev["default_samplerate"]),
                                    "channels": int(dev["max_output_channels"])})
            self._json(200, {"devices": devices, "current": self.engine.device})
        elif path == "/api/health":
            self._json(200, {"status": "ok", "uptime": time.time()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len) if content_len else b""

        # Upload handles raw bytes (multipart)
        if path == "/api/upload":
            self._handle_upload(raw_body, content_len)
            return

        body = raw_body.decode() if raw_body else ""

        if path == "/api/trigger":
            data = json.loads(body) if body else {}
            key = data.get("key", "")
            if key in self.keys:
                ok = self.engine.play(self.keys[key])
                self.play_log.append({
                    "ts": time.strftime("%H:%M:%S"),
                    "key": key,
                    "sound": self.keys[key],
                    "src": "web",
                    "ok": ok,
                })
                self._json(200, {"played": self.keys[key], "ok": ok})
            else:
                self._json(400, {"error": f"unknown key: {key}"})

        elif path == "/api/volume":
            data = json.loads(body) if body else {}
            vol = float(data.get("volume", 0.5))
            self.engine.global_volume = max(0.0, min(1.0, vol))
            self._json(200, {"volume": self.engine.global_volume})

        elif path == "/api/mute":
            cfg_vol = self.cfg.get("global", {}).get("volume", 0.8)
            self.engine.global_volume = 0.0 if self.engine.global_volume > 0 else cfg_vol
            self._json(200, {"muted": self.engine.global_volume == 0})

        elif path == "/api/panic":
            self.engine.stop_all()
            self.play_log.append({"ts": time.strftime("%H:%M:%S"), "action": "panic", "src": "web"})
            self._json(200, {"stopped": True})

        elif path == "/api/reload":
            self.engine._load_all()
            self._json(200, {"sounds": self.engine.loaded_sounds})

        elif path == "/api/device":
            data = json.loads(body) if body else {}
            dev_index = data.get("index")
            import sounddevice as sd
            if dev_index is None:
                self.engine.device = None
            else:
                dev_index = int(dev_index)
                sd.query_devices(dev_index, "output")
                self.engine.device = dev_index
            dev_name = "default"
            if self.engine.device is not None:
                dev_name = sd.query_devices(self.engine.device)["name"]
            self._json(200, {"device": self.engine.device, "name": dev_name})

        elif path == "/api/keys":
            data = json.loads(body) if body else {}
            key = data.get("key", "")
            sound = data.get("sound", "")
            if not key:
                self._json(400, {"error": "missing 'key'"})
            elif sound == "":
                # Unassign
                self.keys.pop(key, None)
                self._json(200, {"keys": self.keys, "removed": key})
            else:
                self.keys[key] = sound
                self._json(200, {"keys": self.keys, "assigned": f"{key}={sound}"})

        else:
            self._json(404, {"error": "not found"})

    def _handle_upload(self, raw: bytes, content_len: int) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._json(400, {"error": "expected multipart/form-data"})
            return
        boundary = content_type.split("boundary=")[1].encode()
        files = self._parse_multipart(raw, boundary)
        uploaded = []
        for filename, data in files:
            safe_name = Path(filename).name
            ext = Path(safe_name).suffix.lower()
            allowed = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
            if ext not in allowed:
                continue
            dest = self.engine.sounds_dir / safe_name
            dest.write_bytes(data)
            self.engine._load_file(dest)
            uploaded.append(safe_name)
        if uploaded:
            self._json(200, {"uploaded": uploaded, "sounds": self.engine.loaded_sounds})
        else:
            self._json(400, {"error": "no valid audio files uploaded", "allowed": [".wav", ".mp3", ".ogg", ".flac", ".m4a"]})

    def _parse_multipart(self, data: bytes, boundary: bytes) -> list[tuple[str, bytes]]:
        """Parse multipart form data, return list of (filename, content)."""
        files = []
        parts = data.split(b"--" + boundary)
        for part in parts:
            if b"Content-Disposition" not in part:
                continue
            # Extract filename
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            header = part[:header_end].decode("utf-8", errors="ignore")
            filename = ""
            for line in header.split("\r\n"):
                if "filename=" in line:
                    filename = line.split("filename=")[1].strip('"').strip()
                    break
            if not filename:
                continue
            # Content is after headers, before trailing \r\n
            content = part[header_end + 4:]
            if content.endswith(b"\r\n"):
                content = content[:-2]
            files.append((filename, content))
        return files

    def _get_ui(self) -> str:
        sounds = self.engine.loaded_sounds
        key_map = self.keys
        items = ""
        for key in sorted(key_map.keys()):
            snd = key_map[key]
            items += f'<button class="pad" data-key="{key}" onclick="trigger(\'{key}\')"><span class="key-label">{key}</span><span class="sound-name" onclick="event.stopPropagation();openPicker(\'{key}\')">{snd.replace(".wav","").replace(".mp3","").replace(".ogg","")}</span><span class="pulse-ring"></span></button>\n'

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NutTx - Squirrel Soundboard</title>
<style>
:root {{
    --bg-deep: #0d1117;
    --bg-panel: #161b22;
    --bg-card: #1c2333;
    --accent: #f9a826;
    --accent-glow: rgba(249,168,38,0.4);
    --green: #3fb950;
    --red: #f85149;
    --text: #e6edf3;
    --text-dim: #7d8590;
    --border: #30363d;
    --squirrel: #8B4513;
    --leaf: #2d6a4f;
    --nut: #d4a373;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    background: var(--bg-deep);
    color: var(--text);
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    min-height: 100vh;
    overflow-x: hidden;
}}

/* Animated background */
body::before {{
    content: '';
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background:
        radial-gradient(ellipse at 20% 50%, rgba(249,168,38,0.03) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 20%, rgba(63,185,80,0.03) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 80%, rgba(212,163,115,0.02) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
}}

/* Floating acorns animation */
.acorn {{
    position: fixed;
    font-size: 1.2rem;
    opacity: 0.15;
    animation: float-acorn linear infinite;
    pointer-events: none;
    z-index: 0;
}}
@keyframes float-acorn {{
    0% {{ transform: translateY(-10vh) rotate(0deg); }}
    100% {{ transform: translateY(110vh) rotate(360deg); }}
}}

/* Header */
.header {{
    text-align: center;
    padding: 1.5rem 1rem 0.5rem;
    position: relative;
    z-index: 1;
}}
.logo {{
    display: inline-flex;
    align-items: center;
    gap: 12px;
}}
.squirrel-svg {{
    width: 48px; height: 48px;
    animation: squirrel-bob 3s ease-in-out infinite;
}}
@keyframes squirrel-bob {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-4px); }}
}}
h1 {{
    font-size: 2.2rem;
    font-weight: 700;
    letter-spacing: 6px;
    background: linear-gradient(135deg, var(--accent) 0%, var(--nut) 50%, var(--accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-shadow: 0 0 30px var(--accent-glow);
}}
.subtitle {{
    font-size: 0.7rem;
    color: var(--text-dim);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-top: 4px;
}}
.signal-bars {{
    display: inline-flex; gap: 2px; align-items: flex-end; height: 14px; margin-left: 8px;
}}
.signal-bars span {{
    width: 3px; background: var(--green); border-radius: 1px;
    animation: signal-pulse 1.5s ease-in-out infinite;
}}
.signal-bars span:nth-child(1) {{ height: 4px; animation-delay: 0s; }}
.signal-bars span:nth-child(2) {{ height: 7px; animation-delay: 0.2s; }}
.signal-bars span:nth-child(3) {{ height: 10px; animation-delay: 0.4s; }}
.signal-bars span:nth-child(4) {{ height: 13px; animation-delay: 0.6s; }}
@keyframes signal-pulse {{
    0%, 100% {{ opacity: 0.4; }}
    50% {{ opacity: 1; }}
}}

/* Main container */
.container {{
    max-width: 520px;
    margin: 0 auto;
    padding: 1rem;
    position: relative;
    z-index: 1;
}}

/* Sound grid */
.grid {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-bottom: 1.5rem;
}}
.pad {{
    position: relative;
    background: var(--bg-card);
    border: 2px solid var(--border);
    color: var(--text);
    padding: 14px 4px 10px;
    border-radius: 12px;
    cursor: pointer;
    font-family: inherit;
    font-size: 1.1rem;
    font-weight: 700;
    transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
    text-align: center;
    overflow: hidden;
}}
.pad:hover {{
    border-color: var(--accent);
    box-shadow: 0 0 12px rgba(249,168,38,0.2), inset 0 0 20px rgba(249,168,38,0.05);
    transform: translateY(-2px);
}}
.pad:active, .pad.playing {{
    background: linear-gradient(135deg, #2d1b00, #3d2600);
    border-color: var(--accent);
    box-shadow: 0 0 20px var(--accent-glow), inset 0 0 30px rgba(249,168,38,0.1);
    transform: scale(0.93);
}}
.pad.playing .key-label {{
    color: var(--accent);
    text-shadow: 0 0 10px var(--accent);
}}
.key-label {{
    display: block;
    font-size: 1.4rem;
    font-weight: 800;
    color: var(--text);
}}
.sound-name {{
    display: block;
    font-size: 0.55rem;
    font-weight: 400;
    color: var(--text-dim);
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
}}
.pulse-ring {{
    position: absolute;
    top: 50%; left: 50%;
    width: 0; height: 0;
    border-radius: 50%;
    background: var(--accent-glow);
    transform: translate(-50%, -50%);
    opacity: 0;
    pointer-events: none;
}}
.pad.playing .pulse-ring {{
    animation: pulse 0.4s ease-out;
}}
@keyframes pulse {{
    0% {{ width: 0; height: 0; opacity: 0.6; }}
    100% {{ width: 120px; height: 120px; opacity: 0; }}
}}

/* Controls panel */
.controls, .panel {{
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.2rem;
    margin-bottom: 1rem;
}}
.panel-title {{
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 0.8rem;
}}
.device-row {{
    display: flex;
    align-items: center;
    gap: 10px;
}}
.device-select {{
    flex: 1;
    background: var(--bg-deep);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 12px;
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.8rem;
    cursor: pointer;
    outline: none;
}}
.device-select:focus {{
    border-color: var(--accent);
    box-shadow: 0 0 6px rgba(249,168,38,0.2);
}}
.device-name {{
    font-size: 0.65rem;
    color: var(--green);
    white-space: nowrap;
}}
.drop-zone {{
    border: 2px dashed var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
}}
.drop-zone:hover, .drop-zone.dragover {{
    border-color: var(--accent);
    background: rgba(249,168,38,0.05);
    box-shadow: inset 0 0 20px rgba(249,168,38,0.05);
}}
.drop-icon {{ font-size: 2rem; margin-bottom: 8px; }}
.drop-text {{ font-size: 0.75rem; color: var(--text-dim); line-height: 1.5; }}
.drop-text small {{ font-size: 0.6rem; opacity: 0.7; }}
.upload-status {{
    font-size: 0.7rem;
    color: var(--green);
    margin-top: 8px;
    min-height: 1.2em;
}}
.upload-status.error {{ color: var(--red); }}
.sound-name {{ cursor: pointer; }}
.sound-name:hover {{ color: var(--accent); text-decoration: underline; }}

/* Sound picker modal */
.picker-overlay {{
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    z-index: 100;
    align-items: center;
    justify-content: center;
}}
.picker-overlay.open {{ display: flex; }}
.picker {{
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 1.5rem;
    width: 90%;
    max-width: 360px;
    max-height: 70vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}}
.picker-title {{
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.picker-close {{
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 1.2rem;
    cursor: pointer;
}}
.picker-close:hover {{ color: var(--red); }}
.picker-list {{
    list-style: none;
}}
.picker-item {{
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.8rem;
    color: var(--text);
    transition: background 0.1s;
    display: flex;
    align-items: center;
    gap: 8px;
}}
.picker-item:hover {{
    background: var(--bg-card);
    border-color: var(--accent);
}}
.picker-item.current {{
    background: rgba(249,168,38,0.1);
    border: 1px solid var(--accent);
}}
.picker-item .note-icon {{ font-size: 1rem; }}
.picker-none {{
    padding: 10px 12px;
    font-size: 0.75rem;
    color: var(--text-dim);
    font-style: italic;
}}
.picker-hint {{
    font-size: 0.6rem;
    color: var(--text-dim);
    margin-top: 0.8rem;
    opacity: 0.7;
}}
.vol-section {{
    text-align: center;
    margin-bottom: 1rem;
}}
.vol-label {{
    font-size: 0.65rem;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 2px;
    margin-bottom: 6px;
}}
.vol-track {{
    position: relative;
    width: 100%;
    height: 8px;
    background: var(--bg-deep);
    border-radius: 4px;
    overflow: hidden;
}}
.vol-fill {{
    height: 100%;
    background: linear-gradient(90deg, var(--green), var(--accent));
    border-radius: 4px;
    transition: width 0.2s;
}}
.vol-track input {{
    position: absolute;
    top: -4px; left: 0;
    width: 100%;
    height: 16px;
    opacity: 0;
    cursor: pointer;
}}
.vol-val {{
    font-size: 0.8rem;
    color: var(--accent);
    margin-top: 4px;
    font-weight: 700;
}}

.btn-row {{
    display: flex;
    gap: 8px;
    justify-content: center;
    flex-wrap: wrap;
}}
.btn {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    transition: all 0.15s;
}}
.btn:hover {{
    border-color: var(--accent);
    color: var(--accent);
    box-shadow: 0 0 8px rgba(249,168,38,0.2);
}}
.btn.mute-active {{
    background: rgba(248,81,73,0.15);
    border-color: var(--red);
    color: var(--red);
    animation: mute-flash 1s ease-in-out infinite;
}}
@keyframes mute-flash {{
    0%, 100% {{ box-shadow: 0 0 4px rgba(248,81,73,0.3); }}
    50% {{ box-shadow: 0 0 12px rgba(248,81,73,0.6); }}
}}
.btn-panic {{
    background: rgba(248,81,73,0.1);
    border-color: var(--red);
    color: var(--red);
}}
.btn-panic:hover {{
    background: rgba(248,81,73,0.3);
    box-shadow: 0 0 16px rgba(248,81,73,0.4);
}}
.btn-reload {{
    border-color: var(--green);
    color: var(--green);
}}
.btn-reload:hover {{
    box-shadow: 0 0 8px rgba(63,185,80,0.3);
}}

/* Status bar */
.status-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.6rem 1rem;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 0.65rem;
    color: var(--text-dim);
}}
.status-left {{
    display: flex; align-items: center; gap: 6px;
}}
.status-dot {{
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--green);
    animation: dot-pulse 2s ease-in-out infinite;
}}
.status-dot.muted {{
    background: var(--red);
}}
@keyframes dot-pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
}}
.status-right {{
    font-size: 0.6rem;
}}

/* Footer */
.footer {{
    text-align: center;
    padding: 1rem;
    font-size: 0.55rem;
    color: var(--text-dim);
    opacity: 0.5;
    position: relative;
    z-index: 1;
}}

/* Responsive */
@media (max-width: 400px) {{
    .grid {{ grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .pad {{ padding: 10px 2px 8px; }}
    .key-label {{ font-size: 1.2rem; }}
    h1 {{ font-size: 1.6rem; }}
}}
</style></head><body>

<!-- Floating acorns -->
<div class="acorn" style="left:10%;animation-duration:12s;animation-delay:0s;">&#127821;</div>
<div class="acorn" style="left:25%;animation-duration:15s;animation-delay:3s;">&#127821;</div>
<div class="acorn" style="left:50%;animation-duration:10s;animation-delay:6s;">&#127821;</div>
<div class="acorn" style="left:70%;animation-duration:14s;animation-delay:1s;">&#127821;</div>
<div class="acorn" style="left:85%;animation-duration:11s;animation-delay:4s;">&#127821;</div>
<div class="acorn" style="left:40%;animation-duration:13s;animation-delay:7s;">&#127821;</div>

<div class="header">
    <div class="logo">
        <svg class="squirrel-svg" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
            <!-- Squirrel body -->
            <ellipse cx="28" cy="42" rx="14" ry="12" fill="#8B4513"/>
            <!-- Head -->
            <circle cx="38" cy="30" r="9" fill="#A0522D"/>
            <!-- Ear -->
            <ellipse cx="34" cy="22" rx="3" ry="4" fill="#8B4513"/>
            <!-- Eye -->
            <circle cx="41" cy="29" r="2" fill="#fff"/>
            <circle cx="42" cy="29" r="1" fill="#000"/>
            <!-- Tail (big curly) -->
            <path d="M16 44 C8 38, 4 28, 10 20 C14 14, 22 16, 20 22 C18 28, 12 32, 16 44" fill="#D2691E" stroke="#8B4513" stroke-width="1"/>
            <!-- Nut in paws -->
            <ellipse cx="42" cy="42" rx="4" ry="5" fill="#DAA520" stroke="#8B6914" stroke-width="1"/>
            <!-- Antenna (radio) -->
            <line x1="28" y1="30" x2="24" y2="14" stroke="#f9a826" stroke-width="2" stroke-linecap="round"/>
            <circle cx="24" cy="12" r="3" fill="#f9a826">
                <animate attributeName="opacity" values="1;0.3;1" dur="1.5s" repeatCount="indefinite"/>
            </circle>
            <!-- Signal waves -->
            <path d="M20 10 C18 8, 16 6, 14 8" stroke="#f9a826" stroke-width="1" fill="none" opacity="0.6">
                <animate attributeName="opacity" values="0.6;0.1;0.6" dur="1.5s" repeatCount="indefinite"/>
            </path>
            <path d="M18 12 C15 9, 12 7, 10 10" stroke="#f9a826" stroke-width="1" fill="none" opacity="0.3">
                <animate attributeName="opacity" values="0.3;0;0.3" dur="1.5s" repeatCount="indefinite"/>
            </path>
        </svg>
        <div>
            <h1>NutTx</h1>
            <div class="subtitle">Squirrel Soundboard
                <span class="signal-bars"><span></span><span></span><span></span><span></span></span>
            </div>
        </div>
    </div>
</div>

<div class="container">
    <div class="grid">
    {items}
    </div>

    <div class="controls">
        <div class="vol-section">
            <div class="vol-label">Volume</div>
            <div class="vol-track">
                <div class="vol-fill" id="volFill" style="width:80%"></div>
                <input type="range" min="0" max="100" value="80" oninput="setVolume(this.value/100)">
            </div>
            <div class="vol-val" id="volVal">80%</div>
        </div>
        <div class="btn-row">
            <button class="btn" id="muteBtn" onclick="toggleMute()">Mute</button>
            <button class="btn btn-panic" onclick="panic()">Panic</button>
            <button class="btn btn-reload" onclick="reloadSounds()">Reload</button>
        </div>
    </div>

    <!-- Device selector -->
    <div class="panel" id="devicePanel">
        <div class="panel-title">&#128266; Output Device</div>
        <div class="device-row">
            <select id="deviceSelect" class="device-select" onchange="setDevice(this.value)">
                <option value="">-- default --</option>
            </select>
            <span class="device-name" id="deviceName">loading...</span>
        </div>
    </div>

    <!-- Upload zone -->
    <div class="panel" id="uploadPanel">
        <div class="panel-title">&#128228; Upload Sounds</div>
        <div class="drop-zone" id="dropZone" onclick="document.getElementById('fileInput').click()">
            <div class="drop-icon">&#127821;</div>
            <div class="drop-text">Drop audio files here<br><small>wav, mp3, ogg, flac, m4a</small></div>
        </div>
        <input type="file" id="fileInput" multiple accept=".wav,.mp3,.ogg,.flac,.m4a" style="display:none" onchange="uploadFiles(this.files)">
        <div class="upload-status" id="uploadStatus"></div>
    </div>

    <div class="status-bar">
        <div class="status-left">
            <div class="status-dot" id="statusDot"></div>
            <span id="statusText">connected</span>
        </div>
        <div class="status-right" id="statusRight">NutTx v0.1</div>
    </div>
</div>

<div class="footer">squeaking out signals since 2025 &middot; 73 de VK2JNC</div>

<!-- Sound picker modal -->
<div class="picker-overlay" id="pickerOverlay" onclick="if(event.target===this)closePicker()">
    <div class="picker">
        <div class="picker-title">
            <span>Assign to key <strong id="pickerKey">?</strong></span>
            <button class="picker-close" onclick="closePicker()">&times;</button>
        </div>
        <ul class="picker-list" id="pickerList"></ul>
        <div class="picker-hint">Click a sound to assign. The sound name under each key is clickable.</div>
    </div>
</div>

<script>
function trigger(k) {{
  fetch('/api/trigger', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key:k}})}})
  .then(r=>r.json()).then(d=>{{ if(d.ok) flash(k); }});
}}
function flash(k) {{
  const b = document.querySelector(`[data-key="${{k}}"]`);
  if(b) {{ b.classList.add('playing'); setTimeout(()=>b.classList.remove('playing'),400); }}
}}
function setVolume(v) {{
  document.getElementById('volFill').style.width = (v*100)+'%';
  document.getElementById('volVal').textContent = Math.round(v*100)+'%';
  fetch('/api/volume',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{volume:v}})}});
}}
function toggleMute() {{
  fetch('/api/mute',{{method:'POST'}}).then(r=>r.json()).then(d=>{{
    const btn = document.getElementById('muteBtn');
    btn.classList.toggle('mute-active', d.muted);
    btn.textContent = d.muted ? 'UNMUTE' : 'MUTE';
    document.getElementById('statusDot').classList.toggle('muted', d.muted);
  }});
}}
function panic() {{
  fetch('/api/panic',{{method:'POST'}});
  document.body.style.animation = 'none';
  setTimeout(()=>document.body.style.animation = '', 100);
}}
function reloadSounds() {{ fetch('/api/reload',{{method:'POST'}}); }}

// Sound picker
let pickerKey = '';
function openPicker(key) {{
  pickerKey = key;
  document.getElementById('pickerKey').textContent = key;
  fetch('/api/keys').then(r=>r.json()).then(d=>{{
    const list = document.getElementById('pickerList');
    const current = d.keys[key];
    list.innerHTML = '';
    // "Unassign" option
    const none = document.createElement('li');
    none.className = 'picker-item picker-none';
    none.textContent = '(unassign)';
    none.onclick = () => assignKey(key, '');
    list.appendChild(none);
    // All available sounds
    d.available_sounds.forEach(snd => {{
      const li = document.createElement('li');
      li.className = 'picker-item' + (snd === current ? ' current' : '');
      li.innerHTML = `<span class="note-icon">&#9835;</span> ${{snd}}`;
      li.onclick = () => assignKey(key, snd);
      list.appendChild(li);
    }});
  }});
  document.getElementById('pickerOverlay').classList.add('open');
}}
function closePicker() {{
  document.getElementById('pickerOverlay').classList.remove('open');
}}
function assignKey(key, sound) {{
  fetch('/api/keys', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key, sound}})}})
  .then(r=>r.json()).then(d=>{{
    closePicker();
    // Update the button label
    const btn = document.querySelector(`[data-key="${{key}}"]`);
    if(btn) {{
      const nameEl = btn.querySelector('.sound-name');
      nameEl.textContent = sound ? sound.replace(/\\.(wav|mp3|ogg|flac|m4a)$/,'') : '(none)';
    }}
  }});
}}

// Device selection
function loadDevices() {{
  fetch('/api/devices').then(r=>r.json()).then(d=>{{
    const sel = document.getElementById('deviceSelect');
    sel.innerHTML = '<option value="">-- default --</option>';
    d.devices.forEach(dev => {{
      const opt = document.createElement('option');
      opt.value = dev.index;
      opt.textContent = `${{dev.name}} (${{dev.rate}}Hz/${{dev.channels}}ch)`;
      if(dev.index === d.current) opt.selected = true;
      sel.appendChild(opt);
    }});
    if(d.current === null) {{
      document.getElementById('deviceName').textContent = 'default';
    }} else {{
      const cur = d.devices.find(x=>x.index===d.current);
      document.getElementById('deviceName').textContent = cur ? cur.name : 'device '+d.current;
    }}
  }}).catch(()=>{{ document.getElementById('deviceName').textContent = 'error'; }});
}}
function setDevice(idx) {{
  const payload = idx === '' ? {{}} : {{index: parseInt(idx)}};
  fetch('/api/device', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}})
  .then(r=>r.json()).then(d=>{{
    document.getElementById('deviceName').textContent = d.name;
  }});
}}
loadDevices();

// File upload
function uploadFiles(files) {{
  if(!files || files.length === 0) return;
  const fd = new FormData();
  for(const f of files) fd.append('file', f);
  const status = document.getElementById('uploadStatus');
  status.className = 'upload-status';
  status.textContent = `Uploading ${{files.length}} file(s)...`;
  fetch('/api/upload', {{method:'POST', body: fd}})
  .then(r=>r.json()).then(d=>{{
    if(d.uploaded) {{
      status.textContent = `Uploaded: ${{d.uploaded.join(', ')}}`;
      status.className = 'upload-status';
      setTimeout(()=>{{ status.textContent = ''; }}, 4000);
    }} else {{
      status.textContent = d.error;
      status.className = 'upload-status error';
    }}
  }}).catch(e=>{{
    status.textContent = 'Upload failed: ' + e;
    status.className = 'upload-status error';
  }});
  document.getElementById('fileInput').value = '';
}}

// Drag and drop
const dz = document.getElementById('dropZone');
dz.addEventListener('dragover', e => {{ e.preventDefault(); dz.classList.add('dragover'); }});
dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
dz.addEventListener('drop', e => {{
  e.preventDefault();
  dz.classList.remove('dragover');
  uploadFiles(e.dataTransfer.files);
}});

setInterval(()=>fetch('/api/status').then(r=>r.json()).then(d=>{{
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  const right = document.getElementById('statusRight');
  if(d.muted) {{
    dot.classList.add('muted');
    txt.textContent = 'MUTED';
  }} else {{
    dot.classList.remove('muted');
    txt.textContent = 'LIVE';
  }}
  right.textContent = `${{Math.round(d.volume*100)}}% | ${{d.sounds.length}} sounds | ${{d.active.length}} tx`;
}}).catch(()=>{{
  document.getElementById('statusDot').classList.add('muted');
  document.getElementById('statusText').textContent = 'disconnected';
}}), 2000);
</script>
</body></html>"""


class WebServer:
    """Threaded HTTP server for NutTx control."""

    def __init__(self, engine, keys: dict, cfg: dict, host: str = "0.0.0.0", port: int = 8347):
        self.host = host
        self.port = port
        self._server = None
        self._thread = None

        NutTxHandler.engine = engine
        NutTxHandler.keys = keys
        NutTxHandler.cfg = cfg
        NutTxHandler.play_log = []

    def start(self) -> None:
        self._server = HTTPServer((self.host, self.port), NutTxHandler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
