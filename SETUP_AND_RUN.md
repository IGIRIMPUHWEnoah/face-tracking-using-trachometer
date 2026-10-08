# 🚀 Complete Setup & Run Guide for Face Tracking Tachometer

## 📋 What You've Already Done ✅
- ✅ ESP8266MOD has firmware uploaded
- ✅ Python environment exists with all dependencies installed
- ✅ ESP8266MOD detected on **COM25**

---

## ⚡ HARDWARE SETUP CRITICAL

### 🔌 Wiring Diagram for ESP8266MOD + ULN2003 + 28BYJ-48 Stepper

**Your uploaded firmware uses these pins:**

```
┌─────────────────────────────────────────────────────────────┐
│  ESP8266MOD          ULN2003 Driver Board      28BYJ-48     │
│  (NodeMCU/D1 Mini)                              Stepper     │
├─────────────────────────────────────────────────────────────┤
│  D1 (GPIO5)  ────────> IN1                                  │
│  D2 (GPIO4)  ────────> IN2                                  │
│  D5 (GPIO14) ────────> IN3                    ╔═══════╗     │
│  D6 (GPIO12) ────────> IN4                    ║       ║     │
│  GND ────────────────> GND ───────────────────║  28B  ║     │
│                                                ║  YJ   ║     │
│  External 5V PSU (+) ─> VCC (+5V) ────────────║  -48  ║     │
│  External 5V PSU (-) ─> GND ──────────────────║       ║     │
│                                                ╚═══════╝     │
│  USB Cable ──> Computer (for Serial)                        │
└─────────────────────────────────────────────────────────────┘

⚠️  CRITICAL POWER WARNING:
   - DO NOT power 28BYJ-48 from ESP8266 3.3V or USB 5V
   - Use separate 5V power supply (phone charger works: 5V 1A minimum)
   - Connect ALL GND together: ESP8266 GND + PSU GND + ULN2003 GND
```

**Wire Colors on 28BYJ-48 connector (5-wire cable):**
- Orange → Coil 1
- Pink → Coil 2  
- Yellow → Coil 3
- Blue → Coil 4
- Red → Common (+5V from ULN2003)

---

## 🔧 STEP 1: Verify ESP8266MOD is Working

### Test Serial Communication First

1. **Open Arduino IDE Serial Monitor** or use Python:

```bash
# From your project root
.venv\Scripts\python.exe -c "import serial; s=serial.Serial('COM25',115200,timeout=2); import time; time.sleep(2); print(s.read(s.in_waiting).decode('utf-8',errors='ignore'))"
```

**Expected output:**
```
=== ESP8266 Stepper Tachometer (Wi-Fi + MQTT) ===
Connecting to Wi-Fi SSID: RCA-A
Attempting MQTT connection to broker.hivemq.com...CONNECTED!
Subscribed to topic: robot/facetracking/position
```

If you see this, **your ESP8266MOD is working!** ✅

---

### Test Motor Movement via Serial Commands

Open Arduino Serial Monitor (Tools → Serial Monitor) or Python:

```bash
.venv\Scripts\python.exe -c "import serial; import time; s=serial.Serial('COM25',115200); time.sleep(2); s.write(b'N:0.5\n'); time.sleep(1); s.write(b'N:-0.5\n'); time.sleep(1); s.write(b'R\n'); s.close(); print('Test complete')"
```

**What should happen:**
1. Motor moves RIGHT (norm_x = 0.5)
2. Motor moves LEFT (norm_x = -0.5)
3. Motor returns to CENTER (R = reset)

**If motor doesn't move:**
- Check wiring matches diagram above
- Verify external 5V power supply is connected
- Check all GND connections
- LED on ULN2003 board should light up when motor moves

---

## 🎯 STEP 2: Run Face Tracking System

### Option A: MQTT Mode (Wi-Fi - Recommended)

**Verify your Wi-Fi credentials in firmware match your actual network:**
```cpp
const char* WIFI_SSID     = "RCA-A";       // ← Your network name
const char* WIFI_PASSWORD = "RCA@2024";    // ← Your network password
```

**If they don't match, update firmware and re-upload to ESP8266MOD.**

Run the face tracking:

```bash
# Activate virtual environment first
.venv\Scripts\Activate.ps1

# Run face tracking with MQTT
python -m src.face_tracking
```

**What happens:**
1. Webcam opens showing your face
2. Green bounding box tracks your face
3. Top-left shows "MQTT: ONLINE" and "SERIAL: ONLINE"
4. Bottom-right shows tachometer dial simulation
5. ESP8266MOD receives MQTT signals and motor follows your face!

---

### Option B: USB Serial Mode (Fallback if Wi-Fi doesn't work)

The system automatically uses serial if MQTT is offline. Just run:

```bash
python -m src.face_tracking
```

The serial controller will auto-detect COM25 and send commands directly via USB.

---

## 🎮 INTERACTIVE CONTROLS WHILE RUNNING

| Key | Action |
|-----|--------|
| **q** | Quit program |
| **m** | Reconnect MQTT (if Wi-Fi drops) |
| **s** | Reconnect Serial (if USB disconnects) |
| **r** | Reset motor to center position |

---

## 📊 STEP 3: Understanding the Live Display

### HUD Elements:

1. **White Crosshair (Center):** Frame center reference point
2. **Green Line:** Vector from center to your face
3. **Top Bar:** Horizontal offset indicator (-1.0 to +1.0)
4. **Bottom-Right Dial:** Simulated tachometer needle matching motor position
5. **Top-Left Status:**
   - `MQTT: ONLINE` → Wi-Fi working
   - `MQTT: OFFLINE` → Fallback to Serial
   - `Speed Vx: 12.5 px/s` → How fast you're moving horizontally
   - `FPS: 28.3` → Camera frame rate

### Motor Behavior:

- **Face moves LEFT** → norm_x = -1.0 → Motor deflects LEFT
- **Face at CENTER** → norm_x = 0.0 → Motor at CENTER
- **Face moves RIGHT** → norm_x = +1.0 → Motor deflects RIGHT

Range: ±512 steps = ±90° deflection

---

## 🔍 TROUBLESHOOTING

### Problem: "Camera not available (index 0)"
**Solution:** 
```bash
# Test camera first
python -m src.camera
```
If no output, check Windows Privacy Settings → Camera → Allow desktop apps

---

### Problem: Motor doesn't move
**Checklist:**
1. ✅ External 5V power connected to ULN2003?
2. ✅ All GND pins connected together?
3. ✅ Wiring matches: D1→IN1, D2→IN2, D5→IN3, D6→IN4?
4. ✅ 28BYJ-48 cable fully inserted into ULN2003 white socket?
5. ✅ LED on ULN2003 board lights up when commands sent?

Test manual motor control:
```bash
python -m src.serial_controller
```

---

### Problem: MQTT shows OFFLINE
**Checklist:**
1. ✅ Wi-Fi credentials correct in firmware?
2. ✅ ESP8266MOD shows "CONNECTED!" in Serial Monitor?
3. ✅ Computer and ESP8266MOD on same Wi-Fi network?

**Fix:** The system automatically falls back to USB Serial, so it will still work!

---

### Problem: Face detection too slow / jittery
**Edit `src/face_tracking.py` line 150:**
```python
det = Haar5ptDetector(min_size=(70, 70), smooth_alpha=0.85, debug=False)
#                                                        ↑ increase to 0.90 for smoother tracking
```

---

## 🎓 ADVANCED: Enrolling Your Face for Recognition

If you want the system to **recognize you by name** (not just track):

```bash
# Run enrollment
python -m src.enroll

# Enter your name (e.g., "Noah")
# Press SPACE to capture samples (capture 15-20 from different angles)
# Press 's' to save
# Press 'q' to quit

# Then run recognition mode
python -m src.recognize
```

Now it will show your name above the bounding box! But for tachometer tracking, you don't need this — `face_tracking.py` is sufficient.

---

## ⚙️ SYSTEM ARCHITECTURE SUMMARY

```
┌──────────────┐
│   Webcam     │ Captures video @ 30 FPS
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│  Haar Cascade Detection      │ Fast CPU face detection
│  + MediaPipe 5pt Landmarks   │ Extracts eye, nose, mouth points
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Face Center Calculation     │ Fx = (x1 + x2) / 2
│  norm_x = (Fx - W/2)/(W/2)   │ Normalize to [-1.0, +1.0]
└──────┬───────────────────────┘
       │
       ├──────────────────┬─────────────────┐
       ▼                  ▼                 ▼
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│ MQTT Publish│   │ Serial Write │   │ Display HUD  │
│ broker.     │   │ COM25        │   │ cv2.imshow() │
│ hivemq.com  │   │ 115200 baud  │   └──────────────┘
└──────┬──────┘   └──────┬───────┘
       │                 │
       │ Wi-Fi           │ USB Cable
       ▼                 ▼
┌─────────────────────────────────┐
│  ESP8266MOD Firmware            │
│  - Parses norm_x from payload   │
│  - Converts to steps: n×512     │
│  - Drives stepper via ULN2003   │
└─────────────┬───────────────────┘
              │
              ▼
        ┌──────────┐
        │ ULN2003  │ Darlington driver
        │ Driver   │ (handles 5V current)
        └────┬─────┘
             │
             ▼
       ┌───────────┐
       │ 28BYJ-48  │ Stepper motor
       │ Tachometer│ (±90° deflection)
       └───────────┘
```

---

## 🚀 QUICK START COMMAND SUMMARY

```bash
# 1. Activate Python environment
.venv\Scripts\Activate.ps1

# 2. (Optional) Test camera works
python -m src.camera

# 3. Run face tracking system
python -m src.face_tracking

# 4. Move your face left/right and watch the motor follow!
```

---

## 📝 EXPECTED BEHAVIOR

**When working correctly:**
1. Window opens with webcam feed
2. Green box appears around your face
3. Status shows "MQTT: ONLINE" (or "SERIAL: ONLINE")
4. Tachometer dial in corner rotates as you move
5. **Physical motor needle moves in sync with your face!**
6. Motor smoothly tracks your horizontal movement
7. Motor returns to center when you're centered
8. Motor stops and coils auto-disable after 500ms idle

**Performance:**
- Latency: ~50-100ms from face movement to motor response
- FPS: 25-30 fps on most systems
- Motor speed: 1200µs per step = smooth motion
- MQTT rate: 25 Hz max (40ms throttle)
- Serial rate: 20 Hz max (50ms throttle)

---

## 🎉 SUCCESS CRITERIA

You'll know everything is working when:
✅ Face detection shows green bounding box
✅ Status shows connection (MQTT or SERIAL online)
✅ Motor physically moves when you move your face left/right
✅ Motor returns to center when your face is centered
✅ No lag or jitter in motor response
✅ System runs continuously without crashes

---

## 📚 NEXT STEPS / ENHANCEMENTS

After basic tracking works, you can:
1. **Tune smoothing:** Adjust `smooth_alpha` in `face_tracking.py` (line 150)
2. **Add face recognition:** Run enrollment with `python -m src.enroll`
3. **Adjust motor speed:** Change `STEP_INTERVAL_US` in firmware (currently 1200µs)
4. **Increase motor range:** Change `MAX_SWEEP_STEPS` in firmware (currently 512)
5. **Add vertical tracking:** Extend to 2-axis servo pan/tilt mechanism
6. **Change MQTT broker:** Use local broker instead of public hivemq

---

## ⚡ START NOW

```bash
# Single command to run everything:
.venv\Scripts\Activate.ps1; python -m src.face_tracking
```

**The motor should start tracking your face immediately!** 🎯
