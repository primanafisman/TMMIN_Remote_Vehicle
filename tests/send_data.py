"""
send_data.py — Control Sender
==============================
1. Reads steer / acc / brake from Logitech wheel via LogiDrivePy
2. Packs into 6-byte packet
3. Sends over TCP socket to car (DT-06 → STM32)

IMPORTANT: Does NOT create its own LogitechController.
           Accepts the shared controller instance from main.py
           to avoid DLL conflict (only one instance allowed at a time).

Packet format (PC → STM32):
  Byte 0    : 0xAA  (header)
  Byte 1-2  : steer int16 big-endian  (degrees x10, e.g. 45.5 → 455)
  Byte 3    : acc   uint8  (0-100%)
  Byte 4    : brake uint8  (0-100%)
  Byte 5    : 0x55  (footer)

Axis mapping (G920):
  Steer : lX   — -32767 to +32767
  Acc   : lY   — 32767=released, -32767=full press
  Brake : lRz  — 0=released, 32767=full press
"""

import struct
import time
import socket


class ControlSender:
    HEADER = 0xAA
    FOOTER = 0x55

    def __init__(self, controller, conn: socket.socket,
                 physical_max: int = 450, hz: int = 20):
        """
        controller   : shared LogitechController instance from main.py
        conn         : TCP socket to car (None = read-only mode)
        physical_max : max steering degrees (450 for G920)
        hz           : send rate in Hz
        """
        self._controller   = controller
        self.conn          = conn
        self.physical_max  = physical_max
        self.interval      = 1.0 / hz
        self._running      = False
        self.last_controls = {"steer": 0.0, "acc": 0.0, "brake": 0.0}

    # ── Read ──────────────────────────────────────────────────────────────
    def read_controls(self) -> dict:
        self._controller.logi_update()
        try:
            state = self._controller.get_state_engines(0)
            if state is None:
                return {"steer": 0.0, "acc": 0.0, "brake": 0.0}
            s = state.contents
        except (ValueError, OSError):
            return {"steer": 0.0, "acc": 0.0, "brake": 0.0}

        steer = round((s.lX / 32767) * self.physical_max, 1)
        acc   = round((1.0 - (s.lY + 32767) / 65534) * 100, 1)
        brake = round((1.0 - (s.lRz + 32768) / 65535) * 100, 1)

        steer = max(-self.physical_max, min(self.physical_max, steer))
        acc   = max(0.0, min(100.0, acc))
        brake = max(0.0, min(100.0, brake))

        return {"steer": steer, "acc": acc, "brake": brake}

    # ── Pack ──────────────────────────────────────────────────────────────
    def pack(self, steer: float, acc: float, brake: float) -> bytes:
        steer_int = int(steer * 10)
        return struct.pack(
            ">BhBBB",
            self.HEADER,
            steer_int,
            int(acc),
            int(brake),
            self.FOOTER
        )

    # ── Send ──────────────────────────────────────────────────────────────
    def _send(self, payload: bytes) -> bool:
        if self.conn is None:
            return False
        try:
            self.conn.sendall(payload)
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    # ── Main loop ─────────────────────────────────────────────────────────
    def run(self):
        self._running = True
        while self._running:
            t0 = time.perf_counter()

            ctrl = self.read_controls()
            self.last_controls = ctrl

            payload = self.pack(ctrl["steer"], ctrl["acc"], ctrl["brake"])
            ok = self._send(payload)

            if not ok and self.conn is not None:
                self._running = False
                break

            elapsed = time.perf_counter() - t0
            sleep_t = self.interval - elapsed
            if sleep_t > 0:
                time.sleep(sleep_t)

    def stop(self):
        self._running = False

    def shutdown_wheel(self):
        # Shutdown handled by main.py only
        pass