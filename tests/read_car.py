"""
read_car.py — Car Feedback Reader
===================================
Continuously reads feedback packets from STM32 via DT-06 → TCP socket.
Parses speed, heading, and RPM. Stores latest values in last_feedback dict.

Packet format (STM32 → PC):
  Byte 0    : 0xBB  (header)
  Byte 1-2  : speed   uint16 big-endian  (km/h x10, e.g. 12.5 → 125)
  Byte 3-4  : heading uint16 big-endian  (degrees x10, e.g. 90.5° → 905)
  Byte 5-6  : rpm     uint16 big-endian  (raw RPM)
  Byte 7    : 0x66  (footer)
"""

import struct
import socket
import time


class CarReader:
    HEADER   = 0xBB
    FOOTER   = 0x66
    PKT_SIZE = 8

    def __init__(self, conn: socket.socket):
        self.conn          = conn
        self._running      = False
        self.last_feedback = {
            "speed_kmh": 0.0,
            "heading":   0.0,
            "rpm":       0,
            "last_seen": None,
        }
        self._buf = b""

    # ── Parse ─────────────────────────────────────────────────────────────
    def _parse(self, pkt: bytes) -> dict | None:
        if len(pkt) < self.PKT_SIZE:
            return None
        if pkt[0] != self.HEADER or pkt[7] != self.FOOTER:
            return None
        try:
            speed, heading, rpm = struct.unpack(">HHH", pkt[1:7])
            return {
                "speed_kmh": round(speed / 10, 1),
                "heading":   round(heading / 10, 1),
                "rpm":       rpm,
                "last_seen": time.time(),
            }
        except struct.error:
            return None

    # ── Receive loop ──────────────────────────────────────────────────────
    def run(self):
        self._running = True
        self._buf     = b""

        while self._running:
            try:
                chunk = self.conn.recv(256)
                if not chunk:
                    # Connection closed by remote
                    break
                self._buf += chunk
                self._process_buffer()

            except (ConnectionResetError, OSError):
                break
            except Exception:
                break

    def _process_buffer(self):
        """Extract all complete packets from buffer."""
        while len(self._buf) >= self.PKT_SIZE:
            # Find header byte
            idx = self._buf.find(bytes([self.HEADER]))
            if idx == -1:
                self._buf = b""
                return
            if idx > 0:
                # Discard garbage before header
                self._buf = self._buf[idx:]
            if len(self._buf) < self.PKT_SIZE:
                return  # wait for more bytes

            pkt = self._buf[:self.PKT_SIZE]
            result = self._parse(pkt)
            if result:
                self.last_feedback = result
                self._buf = self._buf[self.PKT_SIZE:]
            else:
                # Bad packet — skip one byte and retry
                self._buf = self._buf[1:]

    def stop(self):
        self._running = False

    def is_alive(self) -> bool:
        """Returns True if feedback was received in the last 2 seconds."""
        last = self.last_feedback.get("last_seen")
        if last is None:
            return False
        return (time.time() - last) < 2.0
