// ClearPath - Ramp Sentinel (ESP32): detects a car blocking an accessibility ramp and publishes MQTT events.
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* MQTT_BROKER   = "broker.hivemq.com";
const int   MQTT_PORT     = 1883;

const char* DEVICE_ID = "ramp-paulista-01";
const char* LOCATION  = "Ramp at Av. Paulista x R. Augusta";
const float LAT = -23.5558;
const float LON = -46.6623;

const char* TOPIC = "clearpath/fiap-gs/sensors/ramp-paulista-01";

const float THRESHOLD_CM  = 80.0;   // an object closer than this = blocking
const float HYSTERESIS_CM = 20.0;   // avoids flickering around the threshold
const unsigned long OBSTRUCTION_TIME_MS = 10000;  // 10 s in the demo (60 s in the field)
const unsigned long CLEAR_TIME_MS       = 5000;
const unsigned long HEARTBEAT_MS        = 60000;

const int PIN_TRIG      = 5;
const int PIN_ECHO      = 18;
const int PIN_BUTTON    = 4;
const int PIN_LED_RED   = 26;
const int PIN_LED_GREEN = 27;
const int PIN_BUZZER    = 25;

WiFiClient wifi;
PubSubClient mqtt(wifi);

enum State { CLEAR, SUSPECTED, BLOCKED, CLEARING };
State state = CLEAR;
unsigned long stateStart = 0;
unsigned long lastHeartbeat = 0;
unsigned long lastButton = 0;
float currentDistance = 400;

float readDistanceCm() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  unsigned long us = pulseIn(PIN_ECHO, HIGH, 30000);
  if (us == 0) return 400;
  return us / 58.0;
}

// Median of 5 readings: filters spurious echoes (a leaf, a person walking by).
float filteredDistance() {
  float v[5];
  for (int i = 0; i < 5; i++) { v[i] = readDistanceCm(); delay(15); }
  for (int i = 0; i < 4; i++)
    for (int j = i + 1; j < 5; j++)
      if (v[j] < v[i]) { float t = v[i]; v[i] = v[j]; v[j] = t; }
  return v[2];
}

void beep(int times, int ms) {
  for (int i = 0; i < times; i++) {
    tone(PIN_BUZZER, 1800, ms);
    delay(ms + 80);
  }
}

void showState(bool blocked) {
  digitalWrite(PIN_LED_RED, blocked ? HIGH : LOW);
  digitalWrite(PIN_LED_GREEN, blocked ? LOW : HIGH);
}

void connectWiFi() {
  Serial.print("Connecting to Wi-Fi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  while (WiFi.status() != WL_CONNECTED) { delay(250); Serial.print("."); }
  Serial.println(" ok");
}

void connectMQTT() {
  while (!mqtt.connected()) {
    String id = String("clearpath-esp32-") + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.print("Connecting to the MQTT broker... ");
    if (mqtt.connect(id.c_str())) {
      Serial.println("ok");
    } else {
      Serial.printf("failed (rc=%d), retrying in 2 s\n", mqtt.state());
      delay(2000);
    }
  }
}

void publish(const char* event, unsigned long durationMs = 0) {
  JsonDocument doc;
  doc["device"]      = DEVICE_ID;
  doc["location"]    = LOCATION;
  doc["lat"]         = LAT;
  doc["lon"]         = LON;
  doc["event"]       = event;
  doc["distance_cm"] = round(currentDistance * 10) / 10.0;
  if (durationMs) doc["duration_s"] = durationMs / 1000;
  char buf[256];
  size_t n = serializeJson(doc, buf);
  bool ok = mqtt.publish(TOPIC, (const uint8_t*)buf, n, false);
  Serial.printf("[MQTT %s] %s\n", ok ? "sent" : "FAILED", buf);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_LED_GREEN, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  showState(false);

  connectWiFi();
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setBufferSize(512);
  connectMQTT();
  publish("heartbeat");
  lastHeartbeat = millis();
}

void loop() {
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  currentDistance = filteredDistance();
  unsigned long now = millis();
  bool close = currentDistance < THRESHOLD_CM;
  bool far = currentDistance > THRESHOLD_CM + HYSTERESIS_CM;

  // State machine: an obstruction is only declared after OBSTRUCTION_TIME_MS in a row,
  // so it does not fire for pedestrians or cars passing by.
  switch (state) {
    case CLEAR:
      if (close) { state = SUSPECTED; stateStart = now; }
      break;
    case SUSPECTED:
      if (!close) { state = CLEAR; }
      else if (now - stateStart >= OBSTRUCTION_TIME_MS) {
        state = BLOCKED;
        showState(true);
        publish("obstruction", now - stateStart);
        beep(1, 200);
        stateStart = now;
      }
      break;
    case BLOCKED:
      if (far) { state = CLEARING; stateStart = now; }
      break;
    case CLEARING:
      if (!far) { state = BLOCKED; }
      else if (now - stateStart >= CLEAR_TIME_MS) {
        state = CLEAR;
        showState(false);
        publish("cleared");
      }
      break;
  }

  // Confirmation button (1.5 s debounce)
  if (digitalRead(PIN_BUTTON) == LOW && now - lastButton > 1500) {
    lastButton = now;
    publish("confirmation");
    beep(2, 120);
  }

  if (now - lastHeartbeat >= HEARTBEAT_MS) {
    lastHeartbeat = now;
    publish("heartbeat");
  }

  delay(100);
}
