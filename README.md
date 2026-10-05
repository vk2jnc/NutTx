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

## ESP32 Hardware Button Pad

Use physical buttons at your radio. Three modes, pick what suits:

### Mode 1: USB HID Keyboard (simplest)

ESP32 emulates a keyboard. Plug it in, press buttons, sounds fire.
**No extra NutTx flags needed** — it just works.

```
ESP32 GPIO 2,4,5,18,19,21,22,23,25,26  →  buttons 1-0
Each button: GPIO to GND (internal pull-up)
```

Flash: `esp32/hid/nuttx_hid.ino` in Arduino IDE (board: ESP32 Dev Module).

### Mode 2: USB Serial (CDC)

ESP32 appears as `/dev/ttyACM0`. Sends one char per press.

```bash
python main.py --serial /dev/ttyACM0
```

Flash: `esp32/serial/nuttx_serial.ino`. Works best on ESP32-S3 (native USB).
Classic ESP32 needs a UART-to-USB bridge or USB-Serial-JTAG.

### Mode 3: WiFi UDP (wireless)

No cable. ESP32 connects to your WiFi and sends 1-byte UDP packets.

```bash
python main.py --udp 5566    # listens on all interfaces
```

Flash: `esp32/wifi/nuttx_wifi.ino`. Edit the WiFi credentials and
target PC IP at the top of the sketch before flashing.

### BOM (for all modes)

| Qty | Part |
|-----|------|
| 1   | ESP32 (classic, S2, or S3) |
| 10-11 | Tactile buttons (6x6mm) |
| 1   | Breadboard or perfboard |
| 11  | Jumper wires |
| 1   | 10K resistor pack (optional, for external pull-down) |
| 1   | USB-A to micro-C cable (or USB-C for S3) |
| 1   | 18650 battery + holder (optional, for wireless/field use) |

### Wiring Diagram (all modes)

```
    VCC ───┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐
           │  │  │  │  │  │  │  │  │  │  │
          [B1][B2][B3][B4][B5][B6][B7][B8][B9][B10]
           │  │  │  │  │  │  │  │  │  │  │
          GND GND GND GND GND GND GND GND GND GND

    GPIO: 2  4  5  18 19 21 22 23 25 26  (32 = mute)
    Each button: one leg to GPIO, other leg to GND
    Internal pull-up handles the "high when not pressed" state
```

## Why "NutTx"?

Squirrels hoard nuts. Ham operators transmit. NutTx hoards sounds and
transmits them on command.
