/**
 * NutTx - ESP32 WiFi UDP Mode (Wireless)
 *
 * Connects to your WiFi and sends UDP datagrams to the PC running NutTx.
 * No USB cable needed — fully wireless operation at your radio.
 *
 * Protocol: single ASCII char per datagram on port 5566
 *   '1'-'9','0' = play sound bound to that key
 *   'm'          = mute toggle
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
 *   GPIO 32 -> Button 11 (sends 'm')
 *
 * LED on GPIO 27 indicates WiFi status:
 *   - Fast blink: connecting
 *   - Steady on:  connected
 *   - Off:        not connected
 *
 * On the PC: NutTx listens with `python main.py --udp 5566`
 */

#include <WiFi.h>
#include <WiFiUdp.h>

// === CONFIGURE THESE ===
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";
const char* TARGET_IP = "192.168.1.100";  // IP of PC running NutTx
const int   TARGET_PORT = 5566;
// ========================

const int PINs[] = {2, 4, 5, 18, 19, 21, 22, 23, 25, 26, 32};
const int NUM_BUTTONS = 11;
const char SEND[] = "1234567890m";
const int LED_PIN = 27;

WiFiUDP udp;
bool connected = false;
unsigned long lastSend = 0;

void setup() {
    pinMode(LED_PIN, OUTPUT);
    for (int i = 0; i < NUM_BUTTONS; i++) {
        pinMode(PINs[i], INPUT_PULLUP);
    }

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    // Blink LED while connecting
    while (WiFi.status() != WL_CONNECTED) {
        delay(50);
        digitalWrite(LED_PIN, HIGH);
        delay(150);
        digitalWrite(LED_PIN, LOW);
        delay(150);
    }

    digitalWrite(LED_PIN, HIGH);  // steady = connected

    udp.begin(TARGET_PORT);
    connected = true;
    Serial.printf("Connected to WiFi. Sending to %s:%d\n", TARGET_IP, TARGET_PORT);
}

void loop() {
    if (!connected) {
        // Reconnect
        digitalWrite(LED_PIN, LOW);
        WiFi.reconnect();
        if (WiFi.status() == WL_CONNECTED) {
            connected = true;
            digitalWrite(LED_PIN, HIGH);
            udp.begin(TARGET_PORT);
        }
        delay(5000);
        return;
    }

    for (int i = 0; i < NUM_BUTTONS; i++) {
        if (digitalRead(PINs[i]) == LOW) {
            int confirm = 0;
            for (int d = 0; d < 3; d++) {
                delay(5);
                if (digitalRead(PINs[i]) == LOW) confirm++;
            }
            if (confirm == 3) {
                // Send as a 1-byte UDP datagram
                char msg = SEND[i];
                udp.beginPacket(TARGET_IP, TARGET_PORT);
                udp.write(msg);
                udp.endPacket();
                lastSend = millis();

                while (digitalRead(PINs[i]) == LOW) delay(10);
            }
        }
    }
    delay(10);
}
