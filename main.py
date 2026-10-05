#!/usr/bin/env python3
"""NutTx - Portable soundboard for ham radio & streaming."""

import argparse
import sys

from soundboard.engine import Engine
from soundboard.device import list_devices, resolve_device
from soundboard.config import load_config
from soundboard.ui import TUI


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
    parser.add_argument("--serial", metavar="PORT", help="Listen on serial port (e.g. /dev/ttyACM0) for ESP32")
    parser.add_argument("--udp", metavar="PORT", type=int, help="Listen on UDP port for ESP32 WiFi (default 5566)")

    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        sys.exit(0)

    cfg = load_config(args.config)

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

    if args.test:
        engine.play_file(args.test)
        print(f"Played: {args.test}")
        sys.exit(0)

    keys = cfg.get("keys", {})

    # Define the action that fires when a key is received (from any source)
    def trigger_key(ch: str):
        if ch == "m":
            cfg_vol = cfg["global"].get("volume", 0.8)
            engine.global_volume = 0.0 if engine.global_volume > 0 else cfg_vol
        elif ch in keys:
            engine.play(keys[ch])

    # Start external input listeners
    serial_input = None
    udp_input = None

    if args.serial:
        from soundboard.serial_input import SerialInput
        serial_input = SerialInput(args.serial, trigger_key)
        serial_input.start()

    if args.udp is not None:
        from soundboard.udp_input import UDPInput
        udp_input = UDPInput(args.udp, trigger_key)
        udp_input.start()

    tui = TUI(engine, keys, cfg)
    tui.run()

    if serial_input:
        serial_input.stop()
    if udp_input:
        udp_input.stop()


if __name__ == "__main__":
    main()
