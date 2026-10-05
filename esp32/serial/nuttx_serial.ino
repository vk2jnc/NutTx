/**
 * NutTx - ESP32 USB CDC Serial Mode
 *
 * Connects as a USB serial device (/dev/ttyACM0). Sends single-character
 * commands when buttons are pressed. NutTx listens on the serial port.
 *
 * Protocol: single ASCII char per button press
 *   '1'-'9','0' = play sound bound to that key
 *   'm'          = mute toggle (optional 11th button)
 *
 * Wiring:
 *   GPIO 2  -> Button 1  (sends '1')
 *   GPIO 4  -> Button 2  (sends '2')
 *   GPIO 5  -> Button 3  (sends '3')
 *   GPIO 18 -> Button 4  (sends '4')
 *   GPIO 19 -> Button 5  (sends '5')
 *   GPIO 21 -> Button 6  (sends '6')
 *   GPIO 22 -> Button 7  (sends '7')
 *   GPIO 23 -> Button 8  (sends '8')
 *   GPIO 25 -> Button 9  (sends '9')
 *   GPIO 26 -> Button 10 (sends '0')
 *   GPIO 32 -> Button 11 (sends 'm' - mute, optional)
 *
 * Buttons wired GPIO to GND, internal pull-ups.
 *
 * On the PC: NutTx listens with `python main.py --serial /dev/ttyACM0`
 */

#include <HardwareSerial.h>
// USB CDC is native on ESP32-S2/S3. For classic ESP32 use USB-Serial-JTAG or a UART bridge.
// For ESP32-S3: USB CDC is built-in, no extra library needed.

const int PINs[] = {2, 4, 5, 18, 19, 21, 22, 23, 25, 26, 32};
const int NUM_BUTTONS = 11;
const char SEND[] = "1234567890m";

void setup() {
    // For ESP32-S3 with native USB CDC:
    // USB.begin();  // uncomment if needed
    Serial.begin(115200);

    for (int i = 0; i < NUM_BUTTONS; i++) {
        pinMode(PINs[i], INPUT_PULLUP);
    }
}

void loop() {
    for (int i = 0; i < NUM_BUTTONS; i++) {
        if (digitalRead(PINs[i]) == LOW) {
            int confirm = 0;
            for (int d = 0; d < 3; d++) {
                delay(5);
                if (digitalRead(PINs[i]) == LOW) confirm++;
            }
            if (confirm == 3) {
                Serial.write(SEND[i]);
                while (digitalRead(PINs[i]) == LOW) delay(10);
            }
        }
    }
    delay(10);
}
