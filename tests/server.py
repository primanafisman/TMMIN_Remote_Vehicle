"""
server.py — TCP Server
======================
Listens for incoming connection from DT-06 WiFi module.
Acts as the transport layer — does NOT parse data itself.
send_data.py and read_car.py use the socket this provides.

Packet protocol (defined here as reference):
  PC → STM32 : 6 bytes  [0xAA][steer_hi][steer_lo][acc][brake][0x55]
  STM32 → PC : 8 bytes  [0xBB][spd_hi][spd_lo][hdg_hi][hdg_lo][rpm_hi][rpm_lo][0x66]
"""

import socket
import threading


class TCPServer:
    HEADER_OUT = 0xAA
    FOOTER_OUT = 0x55
    HEADER_IN  = 0xBB
    FOOTER_IN  = 0x66
    PKT_OUT_SIZE = 6
    PKT_IN_SIZE  = 8

    def __init__(self, host: str = "0.0.0.0", port: int = 9000):
        self.host = host
        self.port = port
        self._server_sock = None
        self._conn        = None
        self._conn_event  = threading.Event()

    def start(self):
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(1)
        # Accept in background so main thread isn't blocked at startup
        t = threading.Thread(target=self._accept, daemon=True)
        t.start()

    def _accept(self):
        try:
            conn, addr = self._server_sock.accept()
            # Disable Nagle algorithm — send small packets immediately
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._conn = conn
            self._conn_event.set()
        except OSError:
            pass

    def wait_for_connection(self, timeout: float = 60.0):
        """Block until DT-06 connects. Returns socket or None on timeout."""
        self._conn_event.wait(timeout)
        return self._conn

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except:
                pass
        if self._server_sock:
            try:
                self._server_sock.close()
            except:
                pass
