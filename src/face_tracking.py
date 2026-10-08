# src/face_tracking.py
"""
Face Tracking with Stepper Motor Tachometer Signal Generation (MQTT Wi-Fi & Serial).

Features:
  - Full-screen camera window with all labels/HUD
  - Mirrored frame so your movement matches screen (natural mirror view)
  - Tracks face horizontal offset, sends to ESP8266 motor via MQTT + Serial
  - Needle returns to center when face is lost
  - Stable smoothed signal, configurable sensitivity

Run:
    python -m src.face_tracking

Controls:
    q       : quit
    m       : reconnect MQTT
    s       : reconnect Serial
    r       : reset motor to center
    + / =   : increase sensitivity
    -       : decrease sensitivity
    f       : toggle fullscreen on/off
"""
from __future__ import annotations

import argparse
import math
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from pathlib import Path
from .haar_5pt import Haar5ptDetector, align_face_5pt
from .mqtt_controller import MQTTController
from .serial_controller import SerialController
from .recognize import ArcFaceEmbedderONNX, FaceDBMatcher, load_db_npz

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
SENSITIVITY: float        = 2.0   # Amplify offset → more motor travel per head turn
SIGNAL_SMOOTH_ALPHA: float = 0.85  # EMA on motor command (0=raw, 1=frozen)
FACE_LOST_RETURN_DELAY: float = 0.4  # Seconds before needle returns to center

WIN_NAME = "Face Tracking Tachometer"


# ─────────────────────────────────────────────────────────────────────────────
# HUD
# ─────────────────────────────────────────────────────────────────────────────
def draw_hud(
    frame: np.ndarray,
    face_center: Optional[Tuple[int, int]],
    raw_norm: float,
    smoothed_norm: float,
    speed_x: float,
    sensitivity: float,
    mqtt_connected: bool,
    serial_connected: bool,
    fps: float,
) -> None:
    H, W = frame.shape[:2]
    Cx, Cy = W // 2, H // 2

    # ── Center crosshair ──────────────────────────────────────────────
    cv2.line(frame, (Cx - 25, Cy), (Cx + 25, Cy), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.line(frame, (Cx, Cy - 25), (Cx, Cy + 25), (255, 255, 255), 1, cv2.LINE_AA)
    cv2.circle(frame, (Cx, Cy), 5, (0, 255, 255), -1)

    # ── Face vector ───────────────────────────────────────────────────
    if face_center is not None:
        Fx, Fy = face_center
        color = (0, 220, 0) if abs(smoothed_norm) < 0.1 else (0, 165, 255)
        cv2.line(frame, (Cx, Cy), (Fx, Fy), color, 2, cv2.LINE_AA)
        cv2.circle(frame, (Fx, Fy), 8, color, -1)

    # ── Offset bar (top center) ───────────────────────────────────────
    bar_w = int(W * 0.45)
    bar_h = 16
    bar_y = 55
    bar_x1 = Cx - bar_w // 2
    bar_x2 = Cx + bar_w // 2

    cv2.rectangle(frame, (bar_x1, bar_y - bar_h // 2),
                  (bar_x2, bar_y + bar_h // 2), (40, 40, 40), -1)
    cv2.rectangle(frame, (bar_x1, bar_y - bar_h // 2),
                  (bar_x2, bar_y + bar_h // 2), (110, 110, 110), 1)
    # Center tick
    cv2.line(frame, (Cx, bar_y - bar_h // 2), (Cx, bar_y + bar_h // 2),
             (200, 200, 200), 1)
    # Left / Right labels
    cv2.putText(frame, "L", (bar_x1 - 18, bar_y + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(frame, "R", (bar_x2 + 6, bar_y + 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1, cv2.LINE_AA)

    # Raw marker (gray)
    raw_x = int(Cx + raw_norm * (bar_w // 2))
    raw_x = max(bar_x1, min(bar_x2, raw_x))
    cv2.circle(frame, (raw_x, bar_y), 5, (140, 140, 140), -1)

    # Smoothed marker (colored = actual motor command)
    sm_x = int(Cx + smoothed_norm * (bar_w // 2))
    sm_x = max(bar_x1, min(bar_x2, sm_x))
    sm_color = (0, 220, 0) if abs(smoothed_norm) < 0.1 else (0, 165, 255)
    cv2.circle(frame, (sm_x, bar_y), 8, sm_color, -1)

    cv2.putText(
        frame,
        f"Motor: {smoothed_norm:+.2f}  Raw: {raw_norm:+.2f}",
        (bar_x1, bar_y - bar_h // 2 - 8),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA,
    )

    # ── Tachometer dial (bottom right) ───────────────────────────────
    dial_r  = max(55, H // 9)
    dial_cx = W - dial_r - 30
    dial_cy = H - dial_r - 30

    # Background
    cv2.circle(frame, (dial_cx, dial_cy), dial_r, (25, 25, 25), -1)
    cv2.circle(frame, (dial_cx, dial_cy), dial_r, (160, 160, 160), 2, cv2.LINE_AA)

    # Arc range indicator (from -90° to +90°)
    for a in range(-90, 91, 1):
        ar = math.radians(a - 90)
        ox = int(dial_cx + (dial_r - 2) * math.cos(ar))
        oy = int(dial_cy + (dial_r - 2) * math.sin(ar))
        ix = int(dial_cx + (dial_r - 5) * math.cos(ar))
        iy = int(dial_cy + (dial_r - 5) * math.sin(ar))
        frac = (a + 90) / 180.0
        color_arc = (
            int(0   + frac * 0),
            int(220 - frac * 220),
            int(0   + frac * 220),
        )
        cv2.line(frame, (ix, iy), (ox, oy), color_arc, 1)

    # Tick marks every 30°
    for tick in range(-90, 91, 30):
        tr = math.radians(tick - 90)
        x1 = int(dial_cx + (dial_r - 4)  * math.cos(tr))
        y1 = int(dial_cy + (dial_r - 4)  * math.sin(tr))
        x2 = int(dial_cx + (dial_r - 14) * math.cos(tr))
        y2 = int(dial_cy + (dial_r - 14) * math.sin(tr))
        cv2.line(frame, (x1, y1), (x2, y2), (200, 200, 200), 2, cv2.LINE_AA)

    # L / C / R labels on dial
    for label, deg in [("L", -90), ("C", 0), ("R", 90)]:
        lr = math.radians(deg - 90)
        lx = int(dial_cx + (dial_r - 20) * math.cos(lr))
        ly = int(dial_cy + (dial_r - 20) * math.sin(lr))
        cv2.putText(frame, label, (lx - 5, ly + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1, cv2.LINE_AA)

    # Needle
    needle_angle = math.radians(smoothed_norm * 90.0 - 90.0)
    nx = int(dial_cx + (dial_r - 10) * math.cos(needle_angle))
    ny = int(dial_cy + (dial_r - 10) * math.sin(needle_angle))
    cv2.line(frame, (dial_cx, dial_cy), (nx, ny), (0, 0, 255), 3, cv2.LINE_AA)
    cv2.circle(frame, (dial_cx, dial_cy), 6, (255, 255, 255), -1)

    cv2.putText(
        frame, "TACHOMETER",
        (dial_cx - 45, dial_cy + dial_r + 20),
        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 160, 160), 1, cv2.LINE_AA,
    )

    # ── Status panel (top left) ───────────────────────────────────────
    panel = [
        (f"MQTT:   {'ONLINE' if mqtt_connected else 'OFFLINE'}",
         (0, 220, 0) if mqtt_connected else (0, 120, 255)),
        (f"SERIAL: {'ONLINE' if serial_connected else 'OFFLINE'}",
         (0, 220, 0) if serial_connected else (0, 120, 255)),
        (f"Speed Vx: {speed_x:+.0f} px/s",    (220, 220, 220)),
        (f"FPS: {fps:.1f}",                     (220, 220, 220)),
        (f"Sensitivity [+/-]: {sensitivity:.1f}x", (200, 200, 80)),
        ("q=quit  r=reset  f=fullscreen",        (140, 140, 140)),
    ]
    for i, (txt, col) in enumerate(panel):
        cv2.putText(frame, txt, (14, 28 + i * 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1, cv2.LINE_AA)

    # ── Face-lost warning ─────────────────────────────────────────────
    if face_center is None:
        msg = "NO FACE DETECTED"
        (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
        cv2.putText(frame, msg,
                    (Cx - tw // 2, Cy + 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 60, 255), 2, cv2.LINE_AA)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Identity-Locked Face Tracking Tachometer")
    parser.add_argument("--target", type=str, default="noah", help="Name of the enrolled person to track")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (0=often internal PC, 1=external USB)")
    args = parser.parse_args()
    
    target_name = args.target.lower()

    global SENSITIVITY

    print("=== Face Tracking Tachometer ===")
    print(f"Target Identity: '{target_name.upper()}'")
    print(f"Sensitivity: {SENSITIVITY}x  |  Smoothing alpha: {SIGNAL_SMOOTH_ALPHA}")

    det = Haar5ptDetector(min_size=(60, 60), smooth_alpha=0.60, debug=False)

    db_path = Path("data/db/face_db.npz")
    db = load_db_npz(db_path)
    # Increased distance threshold to be much more forgiving for home lighting
    matcher = FaceDBMatcher(db=db, dist_thresh=0.60)
    embedder = ArcFaceEmbedderONNX(model_path="models/embedder_arcface.onnx", input_size=(112, 112), debug=False)

    mqtt_ctrl = MQTTController(broker="broker.hivemq.com", min_send_interval_s=0.04)
    mqtt_ctrl.connect()

    serial_ctrl = SerialController(min_send_interval_s=0.033)
    serial_ctrl.connect()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise RuntimeError(f"Camera not available at index {args.camera}.")

    # ── Create fullscreen window ───────────────────────────────────────
    cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    fullscreen = True

    prev_fx:       Optional[float] = None
    prev_time:     float           = time.time()
    speed_smooth:  float           = 0.0
    smoothed_norm: float           = 0.0

    face_lost_since: Optional[float] = None
    center_sent:     bool            = True

    t0     = time.time()
    frames = 0
    fps    = 0.0

    print("Controls: q=quit  m=MQTT  s=Serial  r=reset  +/-=sensitivity  f=fullscreen")

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        # Mirror so your movement matches the screen naturally
        frame = cv2.flip(frame, 1)

        now       = time.time()
        dt        = max(0.001, now - prev_time)
        prev_time = now

        H, W = frame.shape[:2]
        Cx   = W // 2

        faces       = det.detect(frame, max_faces=5)
        face_center = None
        raw_norm    = 0.0

        target_f = None
        
        for f in faces:
            # Draw standard boxes for all faces
            cv2.rectangle(frame, (f.x1, f.y1), (f.x2, f.y2), (0, 150, 0), 1)

            aligned, _ = align_face_5pt(frame, f.kps, out_size=(112, 112))
            emb = embedder.embed(aligned)
            mr = matcher.match(emb)
            
            if mr.accepted and mr.name and mr.name.lower() == target_name:
                target_f = f
                cv2.rectangle(frame, (f.x1, f.y1), (f.x2, f.y2), (0, 255, 0), 2)
                cv2.putText(frame, f"{target_name.upper()} LOCKED ({mr.distance:.2f})", (f.x1, max(0, f.y1 - 10)), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                for (kx, ky) in f.kps.astype(int):
                    cv2.circle(frame, (kx, ky), 3, (0, 255, 0), -1)
                break

        if target_f is not None:
            face_lost_since = None
            center_sent     = False

            f = target_f
            Fx = (f.x1 + f.x2) / 2.0
            Fy = (f.y1 + f.y2) / 2.0
            face_center = (int(Fx), int(Fy))

            raw_norm = float((Fx - Cx) / (W / 2.0))
            boosted  = max(-1.0, min(1.0, raw_norm * SENSITIVITY))
            smoothed_norm = (SIGNAL_SMOOTH_ALPHA * smoothed_norm
                             + (1.0 - SIGNAL_SMOOTH_ALPHA) * boosted)

            if prev_fx is not None:
                inst_speed   = (Fx - prev_fx) / dt
                speed_smooth = 0.6 * speed_smooth + 0.4 * inst_speed
            prev_fx = Fx

            mqtt_ctrl.publish_position(smoothed_norm, offset_x=Fx - Cx, speed_x=speed_smooth)
            serial_ctrl.send_normalized_position(smoothed_norm)

        else:
            prev_fx      = None
            speed_smooth = 0.0

            if face_lost_since is None:
                face_lost_since = now

            if (now - face_lost_since) > FACE_LOST_RETURN_DELAY and not center_sent:
                print("[Tracking] Face lost → center")
                smoothed_norm = 0.0
                serial_ctrl.send_normalized_position(0.0)
                mqtt_ctrl.publish_position(0.0)
                if serial_ctrl.connected and serial_ctrl.ser and serial_ctrl.ser.is_open:
                    serial_ctrl.ser.write(b"R\n")
                center_sent = True

            smoothed_norm *= 0.85  # Decay needle toward center on screen

        # FPS
        frames += 1
        if (now - t0) >= 1.0:
            fps    = frames / (now - t0)
            frames = 0
            t0     = now

        draw_hud(
            frame=frame,
            face_center=face_center,
            raw_norm=raw_norm,
            smoothed_norm=smoothed_norm,
            speed_x=speed_smooth,
            sensitivity=SENSITIVITY,
            mqtt_connected=mqtt_ctrl.connected,
            serial_connected=serial_ctrl.connected,
            fps=fps,
        )

        cv2.imshow(WIN_NAME, frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break
        elif key == ord("f"):
            fullscreen = not fullscreen
            prop = cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL
            cv2.setWindowProperty(WIN_NAME, cv2.WND_PROP_FULLSCREEN, prop)
        elif key == ord("m"):
            print("[INFO] Reconnecting MQTT...")
            mqtt_ctrl.close()
            mqtt_ctrl.connect()
        elif key == ord("s"):
            print("[INFO] Reconnecting Serial...")
            serial_ctrl.close()
            serial_ctrl.connect()
        elif key == ord("r"):
            print("[INFO] Reset center...")
            smoothed_norm = 0.0
            serial_ctrl.reset_zero()
            mqtt_ctrl.publish_position(0.0)
        elif key in (ord("+"), ord("=")):
            SENSITIVITY = min(5.0, round(SENSITIVITY + 0.5, 1))
            print(f"[INFO] Sensitivity → {SENSITIVITY}x")
        elif key == ord("-"):
            SENSITIVITY = max(0.5, round(SENSITIVITY - 0.5, 1))
            print(f"[INFO] Sensitivity → {SENSITIVITY}x")

    # Clean shutdown
    serial_ctrl.reset_zero()
    mqtt_ctrl.publish_position(0.0)
    time.sleep(0.2)

    cap.release()
    mqtt_ctrl.close()
    serial_ctrl.close()
    cv2.destroyAllWindows()
    print("=== Stopped ===")


if __name__ == "__main__":
    main()
