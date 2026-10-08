/*
 * ESP8266MOD Stepper Motor Tachometer Controller (Wi-Fi + MQTT + Serial)
 * Tested on: NodeMCU v1.0 (ESP-12E) and Wemos D1 Mini (ESP8266MOD)
 *
 * Hardware Connections (ULN2003 Driver Board -> 28BYJ-48 Stepper):
 *   ESP8266MOD D1 (GPIO5)  -> ULN2003 IN1
 *   ESP8266MOD D2 (GPIO4)  -> ULN2003 IN2
 *   ESP8266MOD D5 (GPIO14) -> ULN2003 IN3
 *   ESP8266MOD D6 (GPIO12) -> ULN2003 IN4
 *   ESP8266MOD GND         -> External 5V PSU GND (-) AND ULN2003 GND (-)
 *   External 5V PSU (+)    -> ULN2003 VCC (+5V)
 *
 * MQTT & Serial Protocol:
 *   Topic: "robot/facetracking/position"
 *   Payload formats:
 *     1. JSON:   {"norm_x": 0.45}
 *     2. Float:  "0.45"  (range -1.0 to +1.0)
 *     3. Cmd:    "N:-0.5" | "P:512" | "R" (reset)
 */

#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>

// ====================================================================
// Wi-Fi & MQTT Configuration
// ====================================================================
const char* WIFI_SSID      = "RCA-A";
const char* WIFI_PASSWORD  = "RCA@2024";
const char* MQTT_BROKER    = "broker.hivemq.com";
const int   MQTT_PORT      = 1883;
const char* MQTT_TOPIC     = "robot/facetracking/position";
const char* MQTT_CLIENT_ID = "ESP8266_Tachometer_Needle";

// ====================================================================
// Pin Definitions - Safe pins for NodeMCU / Wemos D1 Mini
// ====================================================================
#define IN1 5   // D1 (GPIO5)
#define IN2 4   // D2 (GPIO4)
#define IN3 14  // D5 (GPIO14)
#define IN4 12  // D6 (GPIO12)

// ====================================================================
// Stepper Motor Configuration
// 28BYJ-48: 4096 steps = full 360° in half-step mode
// MAX_SWEEP_STEPS = 1024 means ~90° each side = 180° total sweep
// ====================================================================
const int HALF_STEP_SEQ[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}
};

const long MAX_SWEEP_STEPS    = 1024;  // ±90° deflection each side
const unsigned long STEP_US   = 800;   // Microseconds per step (lower = faster)
const int DEADBAND_STEPS = 2; // Deadband to prevent micro-jitter when target fluctuates by 1 step
// COIL_TIMEOUT: coils stay ON while at target to hold needle position firmly.
// Only disable after this many ms of no new commands at all (face lost).
const unsigned long COIL_HOLD_MS    = 3000;  // Hold position 3s after last command
const unsigned long COIL_TIMEOUT_MS = 500;   // Disable coils 500ms after reaching target

// ====================================================================
// State Variables
// ====================================================================
long currentPosition  = 0;
long targetPosition   = 0;
int  stepIndex        = 0;

unsigned long lastStepMicros    = 0;
unsigned long lastMoveMillis    = 0;
unsigned long lastCommandMillis = 0;  // Tracks when last command arrived
bool coilsActive = false;

WiFiClient   espClient;
PubSubClient mqttClient(espClient);

unsigned long lastMqttReconnect = 0;

// ====================================================================
// Coil Control
// ====================================================================
void setCoilState(int p1, int p2, int p3, int p4) {
  digitalWrite(IN1, p1);
  digitalWrite(IN2, p2);
  digitalWrite(IN3, p3);
  digitalWrite(IN4, p4);
}

void disableCoils() {
  setCoilState(0, 0, 0, 0);
  coilsActive = false;
}

void holdCoils() {
  // Re-energize coils at current step to hold needle in place
  setCoilState(
    HALF_STEP_SEQ[stepIndex][0],
    HALF_STEP_SEQ[stepIndex][1],
    HALF_STEP_SEQ[stepIndex][2],
    HALF_STEP_SEQ[stepIndex][3]
  );
  coilsActive = true;
}

// ====================================================================
// Stepper Movement
// ====================================================================
void performStep(int dir) {
  if (dir > 0) {
    stepIndex = (stepIndex + 1) % 8;
    currentPosition++;
  } else if (dir < 0) {
    stepIndex = (stepIndex - 1 + 8) % 8;
    currentPosition--;
  }
  setCoilState(
    HALF_STEP_SEQ[stepIndex][0],
    HALF_STEP_SEQ[stepIndex][1],
    HALF_STEP_SEQ[stepIndex][2],
    HALF_STEP_SEQ[stepIndex][3]
  );
  coilsActive      = true;
  lastMoveMillis   = millis();
}

// ====================================================================
// Command Parsing
// ====================================================================
void setTargetFromNorm(float norm) {
  norm          = constrain(norm, -1.0f, 1.0f);
  targetPosition = (long)(norm * MAX_SWEEP_STEPS);
  lastCommandMillis = millis();

  // Re-enable coils immediately if they were off
  if (!coilsActive) {
    holdCoils();
  }

  Serial.print("[CMD] norm_x=");
  Serial.print(norm, 3);
  Serial.print("  target=");
  Serial.println(targetPosition);
}

void parsePayload(String payload) {
  payload.trim();
  if (payload.length() == 0) return;

  if (payload.startsWith("P:")) {
    long t = payload.substring(2).toInt();
    targetPosition    = constrain(t, -MAX_SWEEP_STEPS, MAX_SWEEP_STEPS);
    lastCommandMillis = millis();
    if (!coilsActive) holdCoils();
  }
  else if (payload.startsWith("N:")) {
    setTargetFromNorm(payload.substring(2).toFloat());
  }
  else if (payload.startsWith("{")) {
    // Minimal JSON parse: find "norm_x": value
    int idx = payload.indexOf("\"norm_x\":");
    if (idx != -1) {
      setTargetFromNorm(payload.substring(idx + 9).toFloat());
    }
  }
  else if (payload.equals("R")) {
    targetPosition    = 0;
    lastCommandMillis = millis();
    if (!coilsActive) holdCoils();
    Serial.println("[CMD] Reset to center");
  }
  else {
    // Bare float: "0.45"
    float v = payload.toFloat();
    if (v != 0.0f || payload == "0" || payload == "0.0" || payload == "0.00") {
      setTargetFromNorm(v);
    }
  }
}

// ====================================================================
// MQTT
// ====================================================================
void mqttCallback(char* topic, byte* payloadBytes, unsigned int length) {
  char msg[256];
  if (length >= sizeof(msg)) length = sizeof(msg) - 1;
  memcpy(msg, payloadBytes, length);
  msg[length] = '\0';
  parsePayload(String(msg));
}

void reconnectMqtt() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqttClient.connected()) return;

  unsigned long now = millis();
  if (now - lastMqttReconnect < 5000) return;
  lastMqttReconnect = now;

  Serial.print("MQTT connecting to ");
  Serial.print(MQTT_BROKER);
  Serial.print("...");
  if (mqttClient.connect(MQTT_CLIENT_ID)) {
    Serial.println(" CONNECTED");
    mqttClient.subscribe(MQTT_TOPIC);
    Serial.print("Subscribed: ");
    Serial.println(MQTT_TOPIC);
  } else {
    Serial.print(" failed rc=");
    Serial.println(mqttClient.state());
  }
}

// ====================================================================
// Setup
// ====================================================================
void setup() {
  Serial.begin(115200);
  delay(100);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  disableCoils();

  Serial.println("\n=== ESP8266MOD Face-Tracking Tachometer ===");
  Serial.print("Max sweep: ±"); Serial.print(MAX_SWEEP_STEPS);
  Serial.print(" steps  |  Step interval: "); Serial.print(STEP_US); Serial.println(" µs");

  // Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi '");
  Serial.print(WIFI_SSID);
  Serial.print("' ");

  unsigned long wt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wt < 10000) {
    delay(300);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println(" OK");
    Serial.print("IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println(" FAILED — serial fallback only");
  }

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(30);
}

// ====================================================================
// Main Loop
// ====================================================================
void loop() {
  // --- MQTT maintenance ---
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) reconnectMqtt();
    mqttClient.loop();
  }

  // --- Serial command parser ---
  while (Serial.available() > 0) {
    String line = Serial.readStringUntil('\n');
    parsePayload(line);
  }

  // --- Non-blocking stepper execution ---
  unsigned long nowUs = micros();
  if (abs(currentPosition - targetPosition) > DEADBAND_STEPS) {
    if (nowUs - lastStepMicros >= STEP_US) {
      lastStepMicros = nowUs;
      int dir = (targetPosition > currentPosition) ? 1 : -1;
      performStep(dir);
    }
  } else {
    // At target or within deadband: decide whether to hold or release coils
    unsigned long idleMs = millis() - lastCommandMillis;
    if (coilsActive && idleMs > COIL_HOLD_MS) {
      // No commands for 3 seconds → face lost → release coils
      disableCoils();
      Serial.println("[IDLE] Coils disabled — no face detected");
    } else if (!coilsActive && idleMs < COIL_HOLD_MS) {
      // New command arrived while coils were off → re-enable
      holdCoils();
    }
  }
}
