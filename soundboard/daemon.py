"""Daemon mode: run NutTx headless without TUI."""

import signal
import sys
import time


def run_daemon(engine, keys, cfg, serial_port=None, udp_port=None):
    """Run NutTx as a background daemon.

    Listens on keyboard (via pty), serial, and/or UDP.
    Stays alive until SIGTERM/SIGINT.
    """
    print("[daemon] NutTx daemon started")
    print(f"[daemon] Device: {engine.device}, Rate: {engine.sample_rate} Hz, "
          f"Ch: {engine.channels}, Vol: {engine.global_volume}")
    print(f"[daemon] Sounds loaded: {len(engine.loaded_sounds)}")

    def trigger_key(ch: str):
        if ch == "m":
            cfg_vol = cfg["global"].get("volume", 0.8)
            engine.global_volume = 0.0 if engine.global_volume > 0 else cfg_vol
            print(f"[daemon] Mute: {'ON' if engine.global_volume == 0 else 'OFF'}")
        elif ch == "p":
            engine.stop_all()
            print("[daemon] PANIC - all stopped")
        elif ch in keys:
            ok = engine.play(keys[ch])
            if ok:
                print(f"[daemon] Play: {keys[ch]}")

    # Start external inputs
    serial_input = None
    udp_input = None

    if serial_port:
        from soundboard.serial_input import SerialInput
        serial_input = SerialInput(serial_port, trigger_key)
        serial_input.start()

    if udp_port:
        from soundboard.udp_input import UDPInput
        udp_input = UDPInput(udp_port, trigger_key)
        udp_input.start()

    # Web UI / HTTP API
    from soundboard.web import WebServer
    web = WebServer(engine, keys, cfg, host=cfg.get("web", {}).get("host", "0.0.0.0"),
                    port=cfg.get("web", {}).get("port", 8347))
    web.start()
    print(f"[daemon] Web UI: http://0.0.0.0:{web.port}")

    # MIDI input
    midi_input = None
    if cfg.get("midi", {}).get("enabled", False):
        try:
            from soundboard.midi import MidiInput
            midi_input = MidiInput(trigger_key)
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

    # Auto-mute timeout
    auto_mute_secs = cfg.get("global", {}).get("auto_mute_secs", 0)
    last_activity = [time.time()]

    def touch():
        last_activity[0] = time.time()

    original_trigger = trigger_key
    def trigger_with_touch(ch):
        touch()
        original_trigger(ch)

    print("[daemon] Waiting for input... (Ctrl+C to stop)")

    try:
        while running[0]:
            if auto_mute_secs > 0 and engine.global_volume > 0:
                if time.time() - last_activity[0] > auto_mute_secs:
                    engine.global_volume = 0.0
                    print(f"[daemon] Auto-mute after {auto_mute_secs}s idle")
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass

    print("[daemon] Stopping...")
    engine.stop_all()
    web.stop()
    if serial_input:
        serial_input.stop()
    if udp_input:
        udp_input.stop()
    if midi_input:
        midi_input.stop()
    print("[daemon] Bye.")
