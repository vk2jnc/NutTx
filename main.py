#!/usr/bin/env python3
"""NutTx - Portable soundboard for ham radio & streaming."""

import argparse
import sys

from soundboard.engine import Engine
from soundboard.device import list_devices, resolve_device
from soundboard.config import load_config
from soundboard.ui import TUI
from soundboard.tones import ToneGen
from soundboard.sequencer import Sequencer, Recorder
from soundboard.banks import BankManager
from soundboard.safety import Safety
from soundboard.playlog import PlayLog


def main():
    parser = argparse.ArgumentParser(
        prog="nuttx",
        description="NutTx - portable soundboard for ham radio & streaming",
    )
    parser.add_argument("-c", "--config", default="config.toml", help="Config file path")
    parser.add_argument("-d", "--device", help="Override output device (name or index)")
    parser.add_argument("-s", "--sounds", default="sounds/", help="Sounds directory")
    parser.add_argument("-l", "--list-devices", action="store_true", help="List audio output devices")
    parser.add_argument("--no-preload", action="store_true", help="Don't preload sounds into RAM")
    parser.add_argument("-v", "--volume", type=float, help="Override global volume (0.0-1.0)")
    parser.add_argument("--test", metavar="FILE", help="Play a specific sound file and exit")
    parser.add_argument("--speak", metavar="TEXT", help="Synthesize text-to-speech and play through the output device")
    parser.add_argument("--serial", metavar="PORT", help="Listen on serial port (e.g. /dev/ttyACM0)")
    parser.add_argument("--udp", metavar="PORT", type=int, help="Listen on UDP port for ESP32 WiFi")

    # Tone generator commands
    parser.add_argument("--tone", metavar="TYPE",
                        help="Generate a tone: beep|sweep|cw|morse|sid|dtmf|arptone")
    parser.add_argument("--tone-freq", type=float, default=700.0, help="Tone frequency")
    parser.add_argument("--tone-dur", type=float, default=1.0, help="Tone duration (seconds)")
    parser.add_argument("--tone-text", help="Text for Morse code")
    parser.add_argument("--tone-digits", help="Digits for DTMF sequence")
    parser.add_argument("--tone-wpm", type=float, default=15.0, help="Morse WPM")

    # Sequencer
    parser.add_argument("--seq", metavar="NAME", help="Play a named sequence from config")
    parser.add_argument("--loop", metavar="SOUND", help="Loop a sound (Ctrl+C to stop)")

    # Recording
    parser.add_argument("--record", metavar="NAME", help="Record a sound (Ctrl+C to stop)")
    parser.add_argument("--record-dur", type=float, help="Record duration in seconds")
    parser.add_argument("--input-device", help="Input device for recording (name or index)")

    # Fade playback
    parser.add_argument("--play", metavar="NAME", help="Play a loaded sound by name")
    parser.add_argument("--fade-in", type=float, default=0.0, help="Fade-in seconds (with --play)")
    parser.add_argument("--fade-out", type=float, default=0.0, help="Fade-out seconds (with --play)")

    # Banks
    parser.add_argument("--bank", metavar="NAME", help="Load a sound bank")
    parser.add_argument("--banks-dir", default="banks/", help="Banks directory")
    parser.add_argument("--list-banks", action="store_true", help="List available banks")
    parser.add_argument("--save-bank", metavar="NAME", help="Save current config as a bank")

    # Daemon mode
    parser.add_argument("--daemon", action="store_true", help="Run as headless daemon (no TUI)")
    parser.add_argument("--web-port", type=int, help="Override web UI port")
    parser.add_argument("--no-web", action="store_true", help="Disable web UI")

    # Logging
    parser.add_argument("--log-file", help="Playback log file (JSON lines)")

    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        sys.exit(0)

    cfg = load_config(args.config)

    # --- Banks ---
    bank_mgr = BankManager(args.banks_dir)
    if args.list_banks:
        print("Available banks:")
        for name in bank_mgr.list_banks():
            b = bank_mgr.get(name)
            print(f"  {name}: {len(b.keys)} keys, vol={b.volume}, ch={b.channels}")
        sys.exit(0)

    if args.bank:
        bank = bank_mgr.load(args.bank)
        if bank:
            cfg["keys"] = bank.keys
            cfg["global"]["volume"] = bank.volume
            cfg["engine"]["channels"] = bank.channels
            if bank.device:
                cfg["device"]["name"] = bank.device

    if args.save_bank:
        from soundboard.banks import SoundBank
        bank = SoundBank(
            name=args.save_bank,
            keys=cfg.get("keys", {}),
            volume=cfg["global"].get("volume", 0.8),
            channels=cfg["engine"].get("channels", 1),
            device=cfg["device"].get("name", ""),
        )
        bank_mgr.save(bank)
        sys.exit(0)

    # --- Apply overrides ---
    if args.device:
        cfg["device"]["name"] = args.device
    if args.no_preload:
        cfg["engine"]["preload"] = False
    if args.volume is not None:
        cfg["global"]["volume"] = args.volume

    device = resolve_device(cfg["device"].get("name", ""))

    engine = Engine(
        device=device,
        sounds_dir=args.sounds,
        sample_rate=cfg["engine"].get("sample_rate", 0),
        channels=cfg["engine"].get("channels", 1),
        global_volume=cfg["global"].get("volume", 0.8),
        preload=cfg["engine"].get("preload", True),
        overrides=cfg.get("overrides", {}),
    )

    keys = cfg.get("keys", {})

    # Playback log (in-memory ring buffer + optional JSON-lines file)
    log_cfg = cfg.get("log", {})
    playlog = PlayLog(
        log_file=args.log_file or log_cfg.get("file") or None,
        maxlen=int(log_cfg.get("maxlen", 500)),
    )

    # --- Subcommands that don't need the TUI ---

    if args.test:
        engine.play_file(args.test)
        print(f"Played: {args.test}")
        sys.exit(0)

    # Text-to-speech
    if args.speak:
        from soundboard.tts import TTSClient
        tts = TTSClient(cfg)
        if not tts.available():
            print(f"TTS not available: {tts.status()}")
            print(f"  Set the env var: export {tts.key_env}=...")
            sys.exit(1)
        try:
            print(f"Synthesizing: {args.speak!r}")
            tts.speak(args.speak, engine, blocking=True)
        except Exception as e:
            print(f"TTS failed: {e}")
            sys.exit(1)
        sys.exit(0)

    # Tone generation
    if args.tone:
        tg = ToneGen(engine)
        if args.tone == "beep":
            tg.beep(args.tone_freq, args.tone_dur)
        elif args.tone == "sweep":
            tg.sweep(args.tone_freq, args.tone_freq * 2, args.tone_dur)
        elif args.tone == "cw":
            tg.cw(args.tone_freq)
            import time
            print("CW running (Ctrl+C to stop)")
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                tg.stop_cw()
        elif args.tone == "morse":
            if not args.tone_text:
                parser.error("--tone-text required for morse")
            tg.morse(args.tone_text, args.tone_freq, args.tone_wpm)
        elif args.tone == "sid":
            tg.sid_tone(args.tone_freq, args.tone_dur)
        elif args.tone == "dtmf":
            if not args.tone_digits:
                parser.error("--tone-digits required for dtmf")
            tg.dtmf_sequence(args.tone_digits)
        elif args.tone == "arptone":
            tg.arptone(args.tone_dur)
        else:
            parser.error(f"Unknown tone type: {args.tone}")
        sys.exit(0)

    # Sequencer
    if args.seq:
        seqs = cfg.get("sequences", {})
        if args.seq not in seqs:
            print(f"Unknown sequence: {args.seq}")
            print(f"Available: {list(seqs.keys())}")
            sys.exit(1)
        seq = Sequencer(engine)
        seq.sequence(seqs[args.seq], blocking=True)
        sys.exit(0)

    # Loop
    if args.loop:
        seq = Sequencer(engine)
        print(f"Looping '{args.loop}' (Ctrl+C to stop)")
        try:
            seq.loop(args.loop)
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            seq.stop()
        sys.exit(0)

    # Recording
    if args.record:
        from soundboard.device import resolve_device as rd
        in_dev = rd(args.input_device) if args.input_device else None
        rec = Recorder(engine, input_device=in_dev)
        rec.record(args.record, duration=args.record_dur)
        sys.exit(0)

    # Play a loaded sound with fade in/out
    if args.play:
        seq = Sequencer(engine)
        seq.fade_play(args.play,
                      fade_in=args.fade_in,
                      fade_out=args.fade_out,
                      blocking=True)
        sys.exit(0)

    # --- Main modes ---

    if args.daemon:
        from soundboard.daemon import run_daemon
        cfg["_config_path"] = args.config
        if args.no_web:
            cfg.setdefault("web", {})["enabled"] = False
        run_daemon(engine, keys, cfg,
                   serial_port=args.serial,
                   udp_port=args.udp,
                   web_port=args.web_port,
                   playlog=playlog)
    else:
        # Interactive TUI mode (optionally with external inputs)
        safety = Safety(engine, cfg)

        def trigger_key(ch: str, source: str = "keyboard"):
            safety.touch()
            if ch == "m":
                if safety.is_muted():
                    safety.unmute()
                else:
                    engine.global_volume = 0.0
            elif ch in keys:
                ok = engine.play(keys[ch])
                playlog.record(ch, keys[ch], source, ok)

        serial_input = None
        udp_input = None

        if args.serial:
            from soundboard.serial_input import SerialInput
            serial_input = SerialInput(args.serial, lambda ch: trigger_key(ch, "serial"))
            serial_input.start()

        if args.udp is not None:
            from soundboard.udp_input import UDPInput
            udp_input = UDPInput(args.udp, lambda ch: trigger_key(ch, "udp"))
            udp_input.start()

        # MIDI input (interactive mode too)
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
            except ImportError:
                print("MIDI: python-rtmidi not installed, skipping")

        # Web UI in interactive mode too
        if not args.no_web and cfg.get("web", {}).get("enabled", True):
            from soundboard.web import WebServer
            web = WebServer(engine, keys, cfg,
                            host=cfg.get("web", {}).get("host", "0.0.0.0"),
                            port=args.web_port or cfg.get("web", {}).get("port", 8347),
                            config_path=args.config,
                            playlog=playlog, safety=safety)
            web.start()
            print(f"Web UI: http://localhost:{web.port}")
        else:
            web = None

        tui = TUI(engine, keys, cfg, playlog=playlog, safety=safety)
        tui.run()

        if serial_input:
            serial_input.stop()
        if udp_input:
            udp_input.stop()
        if midi_input:
            midi_input.stop()
        if web:
            web.stop()


if __name__ == "__main__":
    main()
