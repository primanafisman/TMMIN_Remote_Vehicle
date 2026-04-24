from logidrivepy import LogitechController
import time

controller = LogitechController()
controller.steering_initialize()

# Warm up DLL state buffer
for _ in range(10):
    controller.logi_update()
    time.sleep(0.02)

PHYSICAL_MAX = 450  # degrees, synced with Logitech G HUB default range

# ─────────────────────────────────────────────
# READ HELPERS
# ─────────────────────────────────────────────

def read_all():
    controller.logi_update()
    try:
        state = controller.get_state_engines(0)
        if state is None:
            return 0.0, 0.0, 0.0
        s = state.contents
    except (ValueError, OSError):
        return 0.0, 0.0, 0.0

    steer = round((s.lX / 32767) * PHYSICAL_MAX, 1)
    # lY = accelerator, lZ = brake
    acc   = round((1.0 - (s.lY + 32767) / 65534) * 100, 1)
    brake = round((1.0 - (s.lRz + 32768) / 65535) * 100, 1)

    steer = max(-PHYSICAL_MAX, min(PHYSICAL_MAX, steer))
    acc   = max(0.0, min(100.0, acc))
    brake = max(0.0, min(100.0, brake))
    return steer, acc, brake

def read_angle():
    steer, _, _ = read_all()
    return steer

# ─────────────────────────────────────────────
# ACTIONS
# ─────────────────────────────────────────────

def read_continuous():
    print("  Reading steer / acc / brake -- Ctrl+C to stop\n")
    print(f"  {'STEER':>10}  {'ACC':>8}  {'BRAKE':>8}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*8}")
    try:
        while True:
            steer, acc, brake = read_all()
            print(
                f"  {steer:>9}deg  {acc:>7}%  {brake:>7}%   ",
                end="\r"
            )
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n  Stopped reading.")

def move_to_angle(target_deg, duration=2.0):
    target_deg    = max(-PHYSICAL_MAX, min(PHYSICAL_MAX, target_deg))
    final_offset  = int((target_deg / PHYSICAL_MAX) * 100)
    RAMP_STEPS    = 20
    RAMP_DURATION = 0.8
    step_sleep    = RAMP_DURATION / RAMP_STEPS

    print(f"  Moving to {target_deg}deg ...")
    try:
        # Ramp up smoothly
        for i in range(1, RAMP_STEPS + 1):
            controller.play_spring_force(0, int(final_offset * i / RAMP_STEPS), 60, 80)
            controller.logi_update()
            time.sleep(step_sleep)

        # Hold
        controller.play_spring_force(0, final_offset, 80, 100)
        start = time.time()
        while time.time() - start < duration:
            steer, acc, brake = read_all()
            print(
                f"  Steer:{steer:>7}deg  Acc:{acc:>5}%  Brake:{brake:>5}%   ",
                end="\r"
            )
            time.sleep(0.05)

    except KeyboardInterrupt:
        pass

    # Ramp down
    for i in range(RAMP_STEPS, -1, -1):
        controller.play_spring_force(0, int(final_offset * i / RAMP_STEPS), 40, 60)
        time.sleep(step_sleep / 2)

    controller.stop_spring_force(0)
    steer, _, _ = read_all()
    print(f"\n  Stopped at: {steer}deg")

def return_to_zero():
    print("  Returning to center (0deg) ...")
    move_to_angle(0, duration=2.0)

# ─────────────────────────────────────────────
# MENU
# ─────────────────────────────────────────────

def show_menu():
    print("\n" + "=" * 45)
    print("   LogiDrivePy Steering Control")
    print("   Range: -450deg (left) to +450deg (right)")
    print("=" * 45)
    print("  1. Read steer / acc / brake (live)")
    print("  2. Move to target angle")
    print("  3. Return to zero (center)")
    print("  4. Exit")
    print("=" * 45)

while True:
    show_menu()
    choice = input("  Choose (1/2/3/4): ").strip()

    if choice == "1":
        read_continuous()

    elif choice == "2":
        try:
            target   = float(input("  Enter target angle (-450 to 450): "))
            duration = float(input("  Hold duration in seconds (e.g. 2.0): "))
            move_to_angle(target, duration)
        except ValueError:
            print("  Invalid input. Enter a number.")

    elif choice == "3":
        return_to_zero()

    elif choice == "4":
        print("  Shutting down...")
        controller.steering_shutdown()
        break

    else:
        print("  Invalid choice. Try again.")