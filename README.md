# NutTx

Portable soundboard for ham radio & streaming. Squeaks out signals.

A terminal-based soundboard that pipes audio to **any** output device —
ham radio line-in, virtual sink for OBS, HDMI, speakers — with hotkey
triggers, ESP32 button pads, MIDI controllers, web UI, tone generation,
and more.

## Quick Start

```bash
pip install -r requirements.txt

# List audio devices
python main.py --list-devices

# Run with a specific device
python main.py -d "NVidia HDMI 0"

# Run with defaults
python main.py

# Test a single file
python main.py --test sounds/cQ.wav
```

## Features

- **Any output device** — ham radio, HDMI, virtual sink, speakers
- **Hotkey triggers** — 1-0 on keyboard, zero latency (preloaded)
- **ESP32 button pad** — USB HID / serial / WiFi wireless
- **MIDI input** — USB keyboard/controller triggers
- **Web UI + HTTP API** — trigger from phone, tablet, browser
- **Tone generator** — CW, Morse, beeps, DTMF, SID tones, ARPTone
- **Sequencer** — play sound chains in order
- **Loop mode** — loop any sound indefinitely
- **Fade in/out** — clean audio transitions
- **Recording** — capture mic input as a new sound
- **Sound banks** — switch between radio/streaming/generic presets
- **Panic button** — instant hard-stop of all audio
- **Ducking** — reduce volume for priority sounds
- **Auto-mute** — silence after idle timeout
- **Daemon mode** — headless, runs in background
- **Logging** — timestamped playback history
- **3D-printable button pad** — design spec included
- **Systemd service** — auto-start on boot

## Configuration

Edit `config.toml`:

```toml
[device]
name = "NVidia HDMI 0"

[engine]
preload = true
sample_rate = 0
channels = 1

[global]
volume = 0.8
auto_mute_secs = 0

[keys]
"1" = "cQ.wav"
"2" = "73.wav"
...

[web]
enabled = true
port = 8347

[safety]
duck_level = 0.1
duck_release_ms = 200

[midi]
enabled = false
device = "default"

[sequences]
"check_in" = ["cQ.wav", "id.wav"]
"de_key" = ["break.wav", "break.wav"]
```

## TUI Controls

| Key | Action |
|-----|--------|
| 1-0 | Play bound sound |
| m   | Mute / unmute |
| l   | Reload sounds from disk |
| q   | Quit |

## ESP32 Hardware Button Pad

Physical buttons at your radio. Three modes:

### USB HID (simplest)
ESP32 emulates a keyboard. Plug in, press buttons, done. No flags needed.

```
python main.py    # just works
```

### USB Serial
```
python main.py --serial /dev/ttyACM0
```

### WiFi UDP (wireless)
```
python main.py --udp 5566
```

See `esp32/` directory for firmware. See `hw/button_pad.md` for 3D-print design.

## MIDI Controllers

Enable in config:
```toml
[midi]
enabled = true
device = "default"
```

Default mapping: C4-C#5 (notes 60-69) = keys 1-0, C5 = mute.
Install: `pip install python-rtmidi`

## Web UI & HTTP API

Start with `--daemon` or in interactive mode (auto-starts if `[web] enabled = true`).

**Web UI:** http://localhost:8347 — grid of buttons, volume slider, mute/panic.

**HTTP API:**
```bash
# Trigger sound
curl -X POST http://localhost:8347/api/trigger -d '{"key":"1"}'

# Set volume
curl -X POST http://localhost:8347/api/volume -d '{"volume":0.5}'

# Mute
curl -X POST http://localhost:8347/api/mute

# Panic (stop all)
curl -X POST http://localhost:8347/api/panic

# Status
curl http://localhost:8347/api/status
```

## Tone Generator

```bash
# Simple beep
python main.py --tone beep --tone-freq 1000 --tone-dur 0.2

# CW carrier (Ctrl+C to stop)
python main.py --tone cw --tone-freq 700

# Morse code
python main.py --tone morse --tone-text "CQ CQ CQ DE VK2JNC" --tone-wpm 15

# SID check tone
python main.py --tone sid --tone-freq 67

# DTMF digits
python main.py --tone dtmf --tone-digits "12345"

# ARPTone
python main.py --tone arptone --tone-dur 2.0

# Frequency sweep
python main.py --tone sweep --tone-freq 400 --tone-dur 1.0
```

## Sequences & Looping

```bash
# Play a named sequence (defined in config)
python main.py --seq check_in

# Loop a sound (Ctrl+C to stop)
python main.py --loop alert.wav
```

## Recording

```bash
# Record 3 seconds to sounds/my_catchphrase.wav
python main.py --record my_catchphrase --record-dur 3

# Record until Ctrl+C
python main.py --record my_catchphrase

# Specify input device
python main.py --record my_catchphrase --input-device "USB Mic"
```

## Sound Banks

Switch between preset configurations (radio, streaming, etc.):

```bash
# List banks
python main.py --list-banks

# Load a bank
python main.py --bank ham_radio

# Save current config as a bank
python main.py --save-bank my_setup
```

Banks live in `banks/*.json`.

## Daemon Mode

Run headless (no TUI), ideal for background/automated operation:

```bash
python main.py --daemon --udp 5566
```

Starts web UI, UDP listener, and (optionally) MIDI. Logs to stdout.

## Systemd Service

```bash
sudo cp systemd/nuttx.service /etc/systemd/system/
# Edit the User= and paths in the service file
sudo systemctl daemon-reload
sudo systemctl enable --now nuttx
```

## Using with Ham Radio

1. Connect sound card / USB audio to radio's phone/line-in
2. `python main.py --list-devices` to find it
3. Set in config: `name = "Your Radio USB Sound Card"`
4. `channels = 1` for mono
5. Run and go

## Using for Streaming (OBS)

```bash
pactl load-module module-null-sink sink_name=NutTx
```

```toml
[device]
name = "NutTx"
```

In OBS: Audio Input Capture → select `NutTx.monitor`.

## Sounds Directory

Drop audio files in `sounds/`. Referenced by filename stem in config.

## Project Structure

```
NutTx/
├── main.py               # Entry point
├── config.toml           # Configuration
├── pyproject.toml        # Package definition
├── requirements.txt
├── soundboard/
│   ├── engine.py         # Audio playback engine
│   ├── device.py         # Device discovery
│   ├── config.py         # Config loader
│   ├── ui.py             # Curses TUI
│   ├── daemon.py         # Headless daemon mode
│   ├── web.py            # Web UI + HTTP API
│   ├── tones.py          # Tone/CW/Morse/DTMF generator
│   ├── sequencer.py      # Sequences, loops, recording
│   ├── midi.py           # MIDI input
│   ├── banks.py          # Sound bank presets
│   ├── safety.py         # Panic, ducking, auto-mute
│   ├── playlog.py        # Playback logging
│   ├── serial_input.py   # ESP32 serial listener
│   └── udp_input.py      # ESP32 WiFi UDP listener
├── esp32/
│   ├── hid/              # USB HID firmware
│   ├── serial/           # USB CDC firmware
│   └── wifi/             # WiFi UDP firmware
├── hw/
│   ├── button_pad.md     # 3D print design spec
│   └── gen_pad.py        # STL generator script
├── systemd/
│   └── nuttx.service     # Systemd unit
├── banks/                # Sound bank presets
└── sounds/               # Your audio files
```

## Why "NutTx"?

Squirrels hoard nuts. Ham operators transmit. NutTx hoards sounds and
transmits them on command.
