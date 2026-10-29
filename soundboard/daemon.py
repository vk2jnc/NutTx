"""Daemon mode: run NutTx headless without TUI."""

import signal
import time

from soundboard.safety import Safety
from soundboard.playlog import PlayLog


def run_daemon(engine, keys, cfg, serial_port=None, udp_port=None,
               web_port=None, playlog: PlayLog | None = None):
    """Run NutTx as a background daemon.

    Listens on serial, UDP, MIDI and the web UI.
    Stays alive until SIGTERM/SIGINT.
    """
    playlog = playlog or PlayLog()
    safety = Safety(engine, cfg)
    safety.start_watchdog()

    print("[daemon] NutTx daemon started")
    print(f"[daemon] Device: {engine.device}, Rate: {engine.sample_rate} Hz, "
          f"Ch: {engine.channels}, Vol: {engine.global_volume}")
    print(f"[daemon] Sounds loaded: {len(engine.loaded_sounds)}")

    def trigger_key(ch: str, source: str = "daemon"):
        safety.touch()
        if ch == "m":
            if safety.is_muted():
                safety.unmute()
            else:
                engine.global_volume = 0.0
            print(f"[daemon] Mute: {'ON' if engine.global_volume == 0 else 'OFF'}")
        elif ch == "p":
            safety.panic()
        elif ch == "d":
            safety.duck()
            print("[daemon] Ducking")
        elif ch == "u":
            safety.unduck()
            print("[daemon] Unducked")
        elif ch in keys:
            ok = engine.play(keys[ch])
            playlog.record(ch, keys[ch], source, ok)
            if ok:
                print(f"[daemon] Play: {keys[ch]} ({source})")

    # Start external inputs
    serial_input = None
    udp_input = None

    if serial_port:
        from soundboard.serial_input import SerialInput
        serial_input = SerialInput(serial_port, lambda ch: trigger_key(ch, "serial"))
        serial_input.start()

    if udp_port:
        from soundboard.udp_input import UDPInput
        udp_input = UDPInput(udp_port, lambda ch: trigger_key(ch, "udp"))
        udp_input.start()

    # Web UI / HTTP API (respects config + --no-web via cfg flag)
    web = None
    if cfg.get("web", {}).get("enabled", True):
        from soundboard.web import WebServer
        web = WebServer(engine, keys, cfg, host=cfg.get("web", {}).get("host", "0.0.0.0"),
                        port=web_port or cfg.get("web", {}).get("port", 8347),
                        config_path=cfg.get("_config_path", "config.toml"),
                        playlog=playlog, safety=safety)
        web.start()
        print(f"[daemon] Web UI: http://0.0.0.0:{web.port}")
    else:
        print("[daemon] Web UI disabled by config")

    # MIDI input
    midi_input = None
    if cfg.get("midi", {}).get("enabled", False):
        try:
            from soundboard.midi import MidiInput
            note_map = {int(k): v for k, v in cfg.get("midi", {}).get("notes", {}).items()}
            midi_input = MidiInput(
                lambda ch: trigger_key(ch, "midi"),
                device=cfg["midi"].get("device", "default"),
                note_map=note_map or None,
            )
            midi_input.start()
            print(f"[daemon] MIDI: listening on '{cfg['midi'].get('device', 'default')}'")
        except ImportError:
            print("[daemon] MIDI: python-rtmidi not installed, skipping")

    # Signal handling
    running = [True]

    def handle_sig(signum, frame):
        running[0] = False
        print("\n[daemon] Shutting down...")

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    print("[daemon] Waiting for input... (Ctrl+C to stop)")

    try:
        while running[0]:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass

    print("[daemon] Stopping...")
    engine.stop_all()
    if web:
        web.stop()
    if serial_input:
        serial_input.stop()
    if udp_input:
        udp_input.stop()
    if midi_input:
        midi_input.stop()
    print("[daemon] Bye.")
