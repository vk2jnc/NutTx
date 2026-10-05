# NutTx

Portable soundboard for ham radio & streaming. Squeaks out signals.

A terminal-based soundboard that pipes audio to **any** output device —
ham radio line-in, virtual sink for OBS, HDMI, speakers — with hotkey
triggers for fast, low-latency playback.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
# Or: pipx install . (once we add pyproject.toml)

# List available audio output devices
python main.py --list-devices

# Run with a specific device
python main.py -d "NVidia HDMI 0"

# Run with default settings (reads config.toml)
python main.py

# Test a single file
python main.py --test sounds/cQ.wav
```

## Configuration

Edit `config.toml`:

```toml
[device]
name = "NVidia HDMI 0"    # or device index as string: "3"

[engine]
preload = true            # preload into RAM for zero-latency
sample_rate = 0           # 0 = auto (use device native)
channels = 1              # 1 = mono (radio), 2 = stereo (streaming)

[global]
volume = 0.8              # 0.0 - 1.0

[keys]
"1" = "cQ.wav"
"2" = "73.wav"
"3" = "thank_you.wav"
...

[overrides]
"alert.wav" = 1.0         # per-sound volume override
```

## Using with Ham Radio

1. Connect your sound card / USB sound device to the radio's phone/line-in
2. Identify the device: `python main.py --list-devices`
3. Set it in config: `name = "Your Radio USB Sound Card"`
4. Use `channels = 1` for mono
5. Run NutTx and hit your hotkeys

## Using for Streaming (OBS / etc.)

Create a PipeWire virtual sink:
```bash
pactl load-module module-null-sink sink_name=NutTx
```

Then point NutTx at it:
```toml
[device]
name = "NutTx"
```

In OBS, add "Audio Input Capture" and select the `NutTx.monitor` source.

## TUI Controls

| Key | Action |
|-----|--------|
| 1-0 | Play bound sound |
| m   | Mute / unmute |
| l   | Reload sounds from disk |
| q   | Quit |

## Sounds Directory

Drop audio files in `sounds/`. They're referenced by filename stem in config.

```
sounds/
├── cQ.wav
├── 73.wav
├── thank_you.wav
├── roger.wav
└── ...
```

## Why "NutTx"?

Squirrels hoard nuts. Ham operators transmit. NutTx hoards sounds and
transmits them on command.
