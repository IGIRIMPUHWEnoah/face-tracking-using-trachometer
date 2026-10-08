# src/serial_controller.py
"""
Serial communication controller for sending face tracking signals to ESP8266MOD.

Protocol:
  - Baud rate: 115200
  - Target step command: "P:<int>\n"
  - Normalized position command: "N:<float>\n" (-1.0 to +1.0)
  - Zero reset: "R\n"
"""
from __future__ import annotations

import time
import threading
from typing import Optional, List

try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    serial = None
    HAS_PYSERIAL = False


class SerialController:
    """
    Manages serial connection to ESP8266 microcontroller.
    Supports auto-reconnection and mock simulation mode when device is unplugged.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 115200,
        min_send_interval_s: float = 0.033,  # ~30 Hz
    ):
        self.port = port
        self.baudrate = baudrate
        self.min_send_interval_s = min_send_interval_s
        self.ser: Optional[serial.Serial] = None
        self.connected = False
        self.last_send_time = 0.0

        if not HAS_PYSERIAL:
            print("[SerialController] Warning: pyserial not installed. Operating in SIMULATION mode.")
            print("[SerialController] Install via: pip install pyserial")

    @staticmethod
    def list_available_ports() -> List[str]:
        if not HAS_PYSERIAL:
            return []
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]

    def connect(self) -> bool:
        if not HAS_PYSERIAL:
            return False

        if self.port is None:
            available = self.list_available_ports()
            if not available:
                print("[SerialController] No COM ports detected. Running in SIMULATION mode.")
                return False
            self.port = available[0]

        try:
            print(f"[SerialController] Connecting to {self.port} at {self.baudrate} baud...")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1.0)
            time.sleep(2.0)  # Allow ESP8266 reset completion
            self.connected = True
            print(f"[SerialController] Connected successfully to {self.port}.")
            return True
        except Exception as e:
            print(f"[SerialController] Failed to connect on {self.port}: {e}")
            self.connected = False
            return False

    def send_normalized_position(self, norm_pos: float) -> bool:
        """
        Sends normalized position in range [-1.0, +1.0].
        -1.0 = Far Left, 0.0 = Center, +1.0 = Far Right.
        """
        now = time.time()
        if now - self.last_send_time < self.min_send_interval_s:
            return False  # Throttle to prevent serial buffer overflow

        norm_pos = max(-1.0, min(1.0, float(norm_pos)))
        cmd = f"N:{norm_pos:.3f}\n"

        if self.connected and self.ser and self.ser.is_open:
            try:
                self.ser.write(cmd.encode("utf-8"))
                self.last_send_time = now
                return True
            except Exception as e:
                print(f"[SerialController] Write error: {e}")
                self.connected = False
                return False
        else:
            # Simulation feedback
            self.last_send_time = now
            return True

    def reset_zero(self) -> bool:
        if self.connected and self.ser and self.ser.is_open:
            try:
                self.ser.write(b"R\n")
                return True
            except Exception:
                return False
        return True

    def close(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.connected = False


def main():
    print("=== Testing SerialController ===")
    sc = SerialController()
    sc.connect()

    print("Sending test sweep signals [-1.0 -> 0.0 -> +1.0]...")
    for val in [-1.0, -0.5, 0.0, 0.5, 1.0, 0.0]:
        print(f"Sending norm_pos: {val}")
        sc.send_normalized_position(val)
        time.sleep(0.5)

    sc.close()
    print("Test complete.")


if __name__ == "__main__":
    main()
