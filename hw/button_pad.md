# NutTx 3D-Printable Button Pad

## Design Spec

A 2x5 grid (10 buttons) + 1 extra (mute) for a total of 11 buttons.

### Dimensions
- Overall: 120mm x 60mm x 18mm (fits in a jacket pocket)
- Button pitch: 20mm x 20mm
- Button type: 6x6mm tactile (standard keyboard switches)
- Wall thickness: 2mm
- Button holes: 8mm diameter (fits 6x6mm switch)
- Label area above each button: 16mm x 12mm

### Layout
```
+------------------------------------------+
|  [1]    [2]    [3]    [4]    [5]        |
|  [6]    [7]    [8]    [9]    [0]        |
|  [MUTE]                                    |
+------------------------------------------+
        USB-C port (right side)
        3.5mm jack (left side, optional)
```

### Materials
- PLA or PETG
- 0.2mm layer height
- 2 walls, 15% infill
- Top/bottom: 4 layers

### Features
- USB-C port cutout (11mm x 4mm) on right edge
- Optional 3.5mm jack hole on left (for wired fallback)
- PCB standoff holes (M3) at 4 corners
- Textured top surface (20% concentric) to prevent slipping
- Optional: engraved labels for "1" through "0" and "M"

### ESP32 Fit
- ESP32 DevKitC (38mm x 30mm) fits in a recessed pocket on the bottom
- Buttons face up, ESP32 faces down (PCB-to-PCB)
- Wire from buttons to ESP32 via internal channels (or use a small PCB)

### Recommended PCB
For a cleaner build, use a small perfboard:
- 11 tactile switches
- ESP32 (classic, ~38x30mm)
- 10K resistors (if using external pull-downs)
- USB-C connector (for ESP32-S3) or micro-USB (classic)

### Print Settings
| Setting | Value |
|---------|-------|
| Nozzle | 0.4mm |
| Layer height | 0.2mm |
| Infill | 15% (gyroid) |
| Walls | 2 |
| Top layers | 4 |
| Bottom layers | 4 |
| Speed | 50mm/s |
| Support | None (if flat) |
| Temperature | PLA: 200/60, PETG: 240/80 |

### STL
Generate from the spec above using:
- Fusion 360 (free for hobbyists)
- FreeCAD
- TinkerCAD (easiest for this simple box)

Or use this Python script to generate a basic box:
```python
# gen_pad.py - generates a simple 3D pad box
# Run: pip install build123d
# Then: python gen_pad.py
import build123d as bd

W, D, H = 120, 60, 18  # mm
WALL = 2.0
BTN_PITCH_X, BTN_PITCH_Y = 20, 20
BTN_R = 4.0  # 8mm hole

with bd.new_part() as part:
    body = bd.box(W, D, H, centered=True)
    # Button holes (2x5 grid)
    for row in range(2):
        for col in range(5):
            x = -40 + col * BTN_PITCH_X
            y = 10 - row * BTN_PITCH_Y
            hole = bd.cylinder(BTN_R, H + 2, pos=(x, y, 0))
            body = body - hole
    # Mute button (bottom row)
    mute_hole = bd.cylinder(BTN_R, H + 2, pos=(-40, -20, 0))
    body = body - mute_hole
    # USB-C cutout (right side)
    usb = bd.box(14, 5, 8, pos=(W/2 - 1, 0, H/4))
    body = body - usb

    part.add(body)
    part.export_step("nuttx_pad.step")
    part.export_stl("nuttx_pad.stl")
```

### Enclosure Options
1. **Open-top** (shown above) - easiest, wire visible
2. **Hinged lid** - add a 10mm lip + 180-degree hinge groove
3. **Clamp mount** - 5/8" diameter hole for mic stand clamp
