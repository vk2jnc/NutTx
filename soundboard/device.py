"""Audio device discovery and selection."""

import sounddevice as sd
import numpy as np


def list_devices() -> None:
    """Print all audio output devices."""
    print("\nAvailable output devices:\n")
    default_out = sd.default.device[1]
    devices = sd.query_devices()
    for idx, dev in enumerate(devices):
        if dev["max_output_channels"] > 0:
            marker = " [default]" if idx == default_out else ""
            print(f"  {idx:>3}  {dev['name']}{marker}")
            print(f"       {dev['default_samplerate']} Hz, {int(dev['max_output_channels'])} ch, "
                  f"{dev['default_samplerate'] / 1000:.0f}kHz")
    print()


def resolve_device(name_or_index: str) -> int | None:
    """Resolve a device name or index string to a device index.

    Returns None to use the default output device.
    """
    if not name_or_index:
        return None

    # Try as integer index
    try:
        idx = int(name_or_index)
        sd.query_devices(idx, "output")
        return idx
    except (ValueError, IndexError):
        pass

    # Fuzzy match by name (case-insensitive)
    devices = sd.query_devices()
    target = name_or_index.lower()
    for idx, dev in enumerate(devices):
        if dev["max_output_channels"] > 0 and target in dev["name"].lower():
            return idx

    print(f"Warning: could not resolve device '{name_or_index}', using default.")
    return None
