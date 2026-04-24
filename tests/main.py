"""
ADAS Remote Control System
==========================
Entry point — start everything from here.

Files:
  main.py          → this file, menu + orchestrator
  server.py        → TCP server, handles connection from DT-06
  send_data.py     → reads wheel inputs, packs and sends to car
  read_car.py      → receives and parses feedback from car
  angle_control.py → local wheel troubleshoot (read + move + zero)

Run:
  python main.py
"""

import threading
import time
import sys
import os

from logidrivepy import LogitechController
from server    import TCPServer
from send_data import ControlSender
from read_car  import CarReader

# ─────────────────────────────────────────────
# CONFIG — edit these
# ─────────────────────────────────────────────
SERVER_HOST  = "0.0.0.0"
SERVER_PORT  = 9000
SEND_HZ      = 20
PHYSICAL_MAX = 450
MAX_RIGHT_DEGREE = 0
MAX_LEFT_DEGREE=0
# ─────────────────────────────────────────────

# Single global controller — DLL only supports one instance at a time
_controller = LogitechController()
_controller.steering_initialize()
for _ in range(10):
    _controller.logi_update()
    time.sleep(0.02)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def print_header():
    clear()
    print("=" * 55)
    print("   ADAS Remote Control System")
    print("   PC -> Internet -> DT-06 -> STM32")
    print("=" * 55)

def show_main_menu():
    print("""
  -- TRANSMISSION ------------------------------------------
  1. Start full system (send controls + receive feedback)
  2. Read car sensors only
  3. Send controls only (no feedback display)
  4. Read wheel inputs only (no transmission)

  -- TROUBLESHOOT ------------------------------------------
  5. Wheel troubleshoot (read / move / zero steer+pedals)

  ---------------------------------------------------------
  6. Exit
""")
    print("-" * 55)

# ─────────────────────────────────────────────
# TROUBLESHOOT — angle_control integration
# ─────────────────────────────────────────────

def _make_controller():
    # Always return the single global instance
    return _controller

def _read_all(controller):
    controller.logi_update()
    try:
        state = controller.get_state_engines(0)
        if state is None:
            return 0.0, 0.0, 0.0
        s = state.contents
    except (ValueError, OSError):
        return 0.0, 0.0, 0.0

    steer = round((s.lX / 32767) * PHYSICAL_MAX, 1)
    # acc:   lY  — 32767=released, -32767=full press → invert to 0-100%
    # brake: lRz — 0=released, 32767=full press → direct to 0-100%
    acc   = round((1.0 - (s.lY + 32767) / 65534) * 100, 1)
    brake = round((1.0 - (s.lRz + 32768) / 65535) * 100, 1)
    steer = max(-PHYSICAL_MAX, min(PHYSICAL_MAX, steer))
    acc   = max(0.0, min(100.0, acc))
    brake = max(0.0, min(100.0, brake))
    return steer, acc, brake

def troubleshoot_read(controller):
    print("\n  Reading steer / acc / brake -- Ctrl+C to stop\n")
    print(f"  {'STEER':>10}  {'ACC':>8}  {'BRAKE':>8}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*8}")
    try:
        while True:
            steer, acc, brake = _read_all(controller)
            print(
                f"  {steer:>9}deg  {acc:>7}%  {brake:>7}%   ",
                end="\r"
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n  Stopped.")

def troubleshoot_move(controller):
    try:
        target   = float(input("  Target angle (-450 to 450): "))
        duration = float(input("  Hold duration in seconds (e.g. 2.0): "))
    except ValueError:
        print("  Invalid input.")
        return

    target = max(-PHYSICAL_MAX, min(PHYSICAL_MAX, target))
    final_offset = int((target / PHYSICAL_MAX) * 100)

    # Smooth ramp: gradually increase offset over 0.8s to avoid jerk
    RAMP_STEPS    = 20
    RAMP_DURATION = 0.8
    step_sleep    = RAMP_DURATION / RAMP_STEPS

    print(f"\n  Moving to {target}deg ...")
    try:
        # Ramp up
        for i in range(1, RAMP_STEPS + 1):
            ramp_offset = int(final_offset * (i / RAMP_STEPS))
            controller.play_spring_force(0, ramp_offset, 60, 80)
            controller.logi_update()
            time.sleep(step_sleep)

        # Hold at target
        controller.play_spring_force(0, final_offset, 80, 100)
        start = time.time()
        while time.time() - start < duration:
            steer, acc, brake = _read_all(controller)
            print(
                f"  Steer:{steer:>7}deg  Acc:{acc:>5}%  Brake:{brake:>5}%   ",
                end="\r"
            )
            time.sleep(0.05)

    except KeyboardInterrupt:
        pass

    # Ramp down
    current_offset = final_offset
    for i in range(RAMP_STEPS, -1, -1):
        ramp_offset = int(final_offset * (i / RAMP_STEPS))
        controller.play_spring_force(0, ramp_offset, 40, 60)
        time.sleep(step_sleep / 2)

    controller.stop_spring_force(0)
    steer, _, _ = _read_all(controller)
    print(f"\n  Stopped at: {steer}deg")

def troubleshoot_zero(controller):
    print("\n  Returning to center (0deg) ...")
    controller.play_spring_force(0, 0, 100, 100)
    start = time.time()
    try:
        while time.time() - start < 2.0:
            steer, acc, brake = _read_all(controller)
            print(
                f"  Steer:{steer:>7}deg  Acc:{acc:>5}%  Brake:{brake:>5}%   ",
                end="\r"
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    controller.stop_spring_force(0)
    steer, _, _ = _read_all(controller)
    print(f"\n  Centered at: {steer}deg")

def run_troubleshoot():
    print("\n  Initializing wheel controller...")
    controller = _make_controller()
    print("  Wheel ready.\n")

    while True:
        print("""
  -- WHEEL TROUBLESHOOT ------------------------------------
  T1. Read steer / acc / brake  (live continuous)
  T2. Move wheel to target angle
  T3. Return wheel to zero (center)
  T4. Back to main menu
""")
        print("-" * 55)
        choice = input("  Choose (T1/T2/T3/T4): ").strip().upper()

        if choice == "T1":
            troubleshoot_read(controller)
        elif choice == "T2":
            troubleshoot_move(controller)
        elif choice == "T3":
            troubleshoot_zero(controller)
        elif choice == "T4":
            print("  Returning to main menu...")
            break
        else:
            print("  Invalid choice.")

# ─────────────────────────────────────────────
# TRANSMISSION MODES
# ─────────────────────────────────────────────

def live_display(sender: ControlSender, reader: CarReader):
    try:
        while True:
          
            ctrl  = sender.last_controls
            fb    = reader.last_feedback
            alive = "[LIVE]" if reader.is_alive() else "[WAIT]"
            print(
                f"  [CTRL]"
                f" Steer:{ctrl.get('steer', 0.0):>7}deg"
                f"  Acc:{ctrl.get('acc', 0.0):>5}%"
                f"  Brake:{ctrl.get('brake', 0.0):>5}%"
                f"  |  {alive}"
                f"  Speed:{fb.get('speed_kmh', '--')}kmh"
                f"  Hdg:{fb.get('heading', '--')}deg"
                f"  RPM:{fb.get('rpm', '--')}   ",
                end="\r"
            )
                
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass

def run_full_system(server: TCPServer):
    print("\n  Waiting for DT-06 to connect...")
    conn = server.wait_for_connection()
    if conn is None:
        print("  Timeout waiting for connection.")
        return
    print("  DT-06 connected.\n")

    sender = ControlSender(_controller, conn, PHYSICAL_MAX, SEND_HZ)
    reader = CarReader(conn)

    t_send = threading.Thread(target=sender.run, daemon=True)
    t_recv = threading.Thread(target=reader.run, daemon=True)
    t_send.start()
    t_recv.start()

    print("  Running -- Ctrl+C to stop\n")
    live_display(sender, reader)

    sender.stop()
    reader.stop()
    print("\n  System stopped.")

def run_read_only(server: TCPServer):
    print("\n  Waiting for DT-06 to connect...")
    conn = server.wait_for_connection()
    if conn is None:
        print("  Timeout.")
        return
    reader = CarReader(conn)
    threading.Thread(target=reader.run, daemon=True).start()
    print("  Reading car sensors -- Ctrl+C to stop\n")
    try:
        while True:
            fb    = reader.last_feedback
            alive = "[LIVE]" if reader.is_alive() else "[WAIT]"
            print(
                f"  {alive}"
                f"  Speed:{fb.get('speed_kmh','--')}kmh"
                f"  Heading:{fb.get('heading','--')}deg"
                f"  RPM:{fb.get('rpm','--')}   ",
                end="\r"
            )
            time.sleep(0.1)
    except KeyboardInterrupt:
        reader.stop()
        print("\n  Stopped.")

def run_send_only(server: TCPServer):
    print("\n  Waiting for DT-06 to connect...")
    conn = server.wait_for_connection()
    if conn is None:
        print("  Timeout.")
        return
    sender = ControlSender(_controller, conn, PHYSICAL_MAX, SEND_HZ)
    threading.Thread(target=sender.run, daemon=True).start()
    print("  Sending controls -- Ctrl+C to stop\n")
    try:
        while True:
            ctrl = sender.last_controls
            print(
                f"  Steer:{ctrl.get('steer', 0.0):>7}deg"
                f"  Acc:{ctrl.get('acc', 0.0):>5}%"
                f"  Brake:{ctrl.get('brake', 0.0):>5}%   ",
                end="\r"
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        sender.stop()
        print("\n  Stopped.")

def run_wheel_only():
    sender = ControlSender(_controller, conn=None, physical_max=PHYSICAL_MAX, hz=SEND_HZ)
    print("  Reading wheel inputs (no transmission) -- Ctrl+C to stop\n")
    try:
        while True:
            ctrl = sender.read_controls()
            print(
                f"  Steer:{ctrl['steer']:>7}deg"
                f"  Acc:{ctrl['acc']:>5}%"
                f"  Brake:{ctrl['brake']:>5}%   ",
                end="\r"
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        sender.shutdown_wheel()
        print("\n  Stopped.")

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print_header()

    server = TCPServer(SERVER_HOST, SERVER_PORT)
    server.start()
    print(f"  TCP server started on port {SERVER_PORT}")
    print(f"  Expose via:  ngrok tcp {SERVER_PORT}\n")

    while True:
        show_main_menu()
        choice = input("  Choose (1-6): ").strip()

        if choice == "1":
            # check if max left and max right  == 0 ? munculkan menu calibration

            # left
            # steer input udah mentok di 520 , user tekan tombol ctrl + s
            # set input ke variable max left degree
            # right
            # sama
            # done -> direct ke function run full system
            run_full_system(server)
        elif choice == "2":
            run_read_only(server)
        elif choice == "3":
            run_send_only(server)
        elif choice == "4":
            run_wheel_only()
        elif choice == "5":
            run_troubleshoot()
        elif choice == "6":
            print("  Bye.")
            _controller.steering_shutdown()
            server.close()
            sys.exit(0)
        else:
            print("  Invalid choice.")