# NutTx 3D-Printable Button Pad - STL Generator

"""Generate a basic NutTx button pad STL using build123d."""

try:
    import build123d as bd
except ImportError:
    print("pip install build123d")
    raise

W, D, H = 120, 60, 18  # overall mm
BTN_PITCH_X, BTN_PITCH_Y = 20, 20
BTN_R = 4.0  # 8mm diameter holes
MUTE_Y_OFFSET = -25  # below main grid

def make_pad() -> None:
    with bd.new_part() as part:
        body = bd.box(W, D, H, centered=True)

        # 2x5 grid of button holes
        for row in range(2):
            for col in range(5):
                x = -40 + col * BTN_PITCH_X
                y = 8 - row * BTN_PITCH_Y
                body = body - bd.cylinder(BTN_R, H + 2, pos=(x, y, 0))

        # Mute button (bottom-left)
        body = body - bd.cylinder(BTN_R, H + 2, pos=(-40, MUTE_Y_OFFSET, 0))

        # USB-C port cutout (right edge)
        usb_w, usb_h, usb_d = 14, 5, 8
        body = body - bd.box(usb_w, usb_h, usb_d, pos=(W/2 - 2, 0, H/4))

        # ESP32 pocket on bottom (recessed 5mm)
        esp_w, esp_d, esp_h = 40, 32, 5
        body = body - bd.box(esp_w, esp_d, esp_h, pos=(20, 0, -H/2 + esp_h/2))

        # M3 corner screw holes
        for sx in [-1, 1]:
            for sy in [-1, 1]:
                body = body - bd.cylinder(1.7, H + 2, pos=(sx * (W/2 - 5), sy * (D/2 - 5), 0))

        part.add(body)
        part.export_step("nuttx_pad.step")
        part.export_stl("nuttx_pad.stl")
        print("Generated: nuttx_pad.stl, nuttx_pad.step")

if __name__ == "__main__":
    make_pad()
