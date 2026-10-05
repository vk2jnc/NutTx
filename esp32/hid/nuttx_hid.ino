/**
 * NutTx - ESP32 USB HID Keyboard Mode
 *
 * Emulates a keyboard. Pressing buttons sends keystrokes (1-0) to the PC.
 * NutTx picks them up as normal key input — no extra software needed.
 *
 * Wiring:
 *   GPIO 2  -> Button 1 (key "1")
 *   GPIO 4  -> Button 2 (key "2")
 *   GPIO 5  -> Button 3 (key "3")
 *   GPIO 18 -> Button 4 (key "4")
 *   GPIO 19 -> Button 5 (key "5")
 *   GPIO 21 -> Button 6 (key "6")
 *   GPIO 22 -> Button 7 (key "7")
 *   GPIO 23 -> Button 8 (key "8")
 *   GPIO 25 -> Button 9 (key "9")
 *   GPIO 26 -> Button 10 (key "0")
 *
 * Each button wired between GPIO and GND (internal pull-up used).
 *
 * Flash via: Tools > Board > ESP32 Arduino, then Serial Port > your device
 * USB connection: USB-to-USB cable directly into ESP32 (or via UART if no USB)
 */

#include <HID.h>

// Button pins (10 buttons)
const int PINs[] = {2, 4, 5, 18, 19, 21, 22, 23, 25, 26};
const int NUM_BUTTONS = 10;

// Keys sent: '1','2','3','4','5','6','7','8','9','0'
const char KEYS[] = "1234567890";

void setup() {
    HID.begin();

    for (int i = 0; i < NUM_BUTTONS; i++) {
        pinMode(PINs[i], INPUT_PULLUP);
    }
}

void loop() {
    for (int i = 0; i < NUM_BUTTONS; i++) {
        // Debounce: require 3 consecutive reads at 5ms intervals
        if (digitalRead(PINs[i]) == LOW) {
            int confirm = 0;
            for (int d = 0; d < 3; d++) {
                delay(5);
                if (digitalRead(PINs[i]) == LOW) confirm++;
            }
            if (confirm == 3) {
                HID.pressKey(KEYS[i]);
                delay(50);
                HID.releaseKey(KEYS[i]);
                // Wait for button release
                while (digitalRead(PINs[i]) == LOW) delay(10);
            }
        }
    }
    delay(10);
}
