"""Web UI and HTTP API for NutTx.

Lightweight - no Flask, just http.server. Serves a single-page
control panel and a JSON REST API.
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


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
        elif path == "/api/log":
            self._json(200, {"log": self.play_log[-100:]})
        elif path == "/api/health":
            self._json(200, {"status": "ok", "uptime": time.time()})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode() if content_len else ""

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

        else:
            self._json(404, {"error": "not found"})

    def _get_ui(self) -> str:
        sounds = self.engine.loaded_sounds
        key_map = self.keys
        items = ""
        for key in sorted(key_map.keys()):
            snd = key_map[key]
            items += f'<button class="pad" data-key="{key}" onclick="trigger(\'{key}\')">{key}<br><small>{snd}</small></button>\n'

        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NutTx</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#1a1a2e; color:#e0e0e0; font-family:'Courier New',monospace; padding:1rem; }}
h1 {{ text-align:center; color:#f9a826; font-size:1.5rem; margin-bottom:1rem; letter-spacing:4px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(80px,1fr)); gap:8px; max-width:500px; margin:0 auto; }}
.pad {{ background:#16213e; border:2px solid #0f3460; color:#e0e0e0; padding:12px 4px;
       border-radius:8px; cursor:pointer; font-family:inherit; font-size:1rem;
       transition:all .1s; text-align:center; }}
.pad:active, .pad.playing {{ background:#e94560; border-color:#e94560; transform:scale(0.95); }}
.pad small {{ display:block; font-size:0.6rem; color:#888; margin-top:4px; }}
.controls {{ text-align:center; margin-top:1.5rem; }}
.controls button {{ background:#0f3460; border:1px solid #533483; color:#e0e0e0;
                   padding:8px 16px; margin:4px; border-radius:6px; cursor:pointer; font-family:inherit; }}
.controls button:hover {{ background:#533483; }}
.vol {{ width:60%; max-width:300px; margin:10px auto; display:block; accent-color:#f9a826; }}
.mute {{ background:#e94560 !important; }}
#status {{ text-align:center; font-size:0.75rem; color:#666; margin-top:1rem; }}
</style></head><body>
<h1>N u t T x</h1>
<div class="grid">
{items}
</div>
<div class="controls">
<input type="range" class="vol" min="0" max="100" value="80" oninput="setVolume(this.value/100)">
<br>
<button onclick="toggleMute()" id="muteBtn">MUTE</button>
<button onclick="panic()" style="background:#c0392b;">PANIC</button>
<button onclick="reloadSounds()">RELOAD</button>
</div>
<div id="status">connected</div>
<script>
function trigger(k) {{
  fetch('/api/trigger', {{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{key:k}})}})
  .then(r=>r.json()).then(d=>{{ if(d.ok) flash(k); }});
}}
function flash(k) {{
  const b = document.querySelector(`[data-key="${{k}}"]`);
  if(b) {{ b.classList.add('playing'); setTimeout(()=>b.classList.remove('playing'),300); }}
}}
function setVolume(v) {{ fetch('/api/volume',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{volume:v}})}}); }}
function toggleMute() {{
  fetch('/api/mute',{{method:'POST'}}).then(r=>r.json()).then(d=>{{
    document.getElementById('muteBtn').classList.toggle('mute', d.muted);
  }});
}}
function panic() {{ fetch('/api/panic',{{method:'POST'}}); }}
function reloadSounds() {{ fetch('/api/reload',{{method:'POST'}}); }}
setInterval(()=>fetch('/api/status').then(r=>r.json()).then(d=>{{
  document.getElementById('status').textContent = d.muted ? 'MUTED' : `vol: ${{Math.round(d.volume*100)}}% | ${{d.active.length}} playing`;
}}).catch(()=>{{ document.getElementById('status').textContent='disconnected'; }}), 2000);
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
