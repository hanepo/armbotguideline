#!/usr/bin/env python3
"""
Robot Arm Calibration Tool — 9-zone version
Calibrates zone_1 to zone_9 (skip zone_5 = arm center, unreachable)
plus home and drop positions.
"""
import pigpio, json, sys, tty, termios, os

PINS = {
    "S1_base":       17,
    "S3_middle_arm": 22,
    "S4_upper_arm":  23,
    "S5_wrist":      24,
    "S6_claw":       25,
}

POSITIONS_FILE = "positions.json"

PW_LIMITS = {
    "S1_base":       (500, 2500),
    "S3_middle_arm": (300, 2700),
    "S4_upper_arm":  (300, 2700),
    "S5_wrist":      (500, 2500),
    "S6_claw":       (500, 2500),
}
PW_HOME   = 1500
STEP_SMALL = 20
STEP_BIG   = 100

POSITION_NAMES = [
    "home",
    "zone_1", "zone_2", "zone_3",
    "zone_4", "zone_5", "zone_6",
    "zone_7", "zone_8", "zone_9",
    "drop_red", "drop_green", "drop_blue",
]

ZONE_LAYOUT = """
  ┌───┬───┬───┐
  │ 1 │ 2 │ 3 │
  ├───┼───┼───┤
  │ 4 │ 5 │ 6 │
  ├───┼───┼───┤
  │ 7 │ 8 │ 9 │
  └───┴───┴───┘
      [ARM]     <- arm sits below zone 8
"""

def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch2 = sys.stdin.read(2)
            return ch + ch2
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch

def set_pw(pi, pin, pw):
    if pw == 0:
        pi.set_PWM_dutycycle(pin, 0)
    else:
        pi.set_PWM_frequency(pin, 50)
        pi.set_PWM_range(pin, 20000)
        pi.set_PWM_dutycycle(pin, pw)

def pw_to_angle(pw):
    return round((pw - 500) / (2500 - 500) * 180)

def load_positions():
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    return {}

def save_positions(positions):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)

def print_state(current_servo, pw_map, position_name, already_saved):
    os.system('clear')
    print("=" * 56)
    print("   ROBOT ARM CALIBRATION  —  9 ZONE MODE")
    print(ZONE_LAYOUT)
    status = "✓ already saved" if already_saved else "NOT YET SAVED"
    print(f"   Now setting: [{position_name.upper()}]  {status}")
    print("=" * 56)
    servo_list = list(PINS.items())
    for i, (name, pin) in enumerate(servo_list):
        pw = pw_map[name]
        angle = pw_to_angle(pw)
        marker = " <<" if i == current_servo else ""
        sel = ">" if i == current_servo else " "
        print(f"  {sel} S{name[1]} {name:<18} {angle:>4}°  (pw={pw}){marker}")
    print("-" * 56)
    print("  ← →   select servo     ↑ ↓   move ±20")
    print("  W/X   move ±100        H     all to home")
    print("  S     save position    N     next position")
    print("  Q     quit")
    print("=" * 56)

def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: pigpiod not running. Run: sudo systemctl start pigpiod")
        return

    servo_list = list(PINS.items())
    positions  = load_positions()
    pw_map     = {name: PW_HOME for name in PINS}

    for name, pin in PINS.items():
        set_pw(pi, pin, PW_HOME)

    current_servo = 0
    pos_index     = 0

    try:
        while pos_index < len(POSITION_NAMES):
            position_name = POSITION_NAMES[pos_index]
            already_saved = position_name in positions

            # Pre-load saved position if it exists
            if already_saved:
                for name in PINS:
                    pw_map[name] = positions[position_name].get(name, PW_HOME)
                for name, pin in PINS.items():
                    set_pw(pi, pin, pw_map[name])

            print_state(current_servo, pw_map, position_name, already_saved)
            key = getch()

            if key == '\x1b[D':
                current_servo = (current_servo - 1) % len(servo_list)
            elif key == '\x1b[C':
                current_servo = (current_servo + 1) % len(servo_list)
            elif key == '\x1b[A':
                name, pin = servo_list[current_servo]
                lo, hi = PW_LIMITS[name]
                pw_map[name] = min(hi, pw_map[name] + STEP_SMALL)
                set_pw(pi, pin, pw_map[name])
            elif key == '\x1b[B':
                name, pin = servo_list[current_servo]
                lo, hi = PW_LIMITS[name]
                pw_map[name] = max(lo, pw_map[name] - STEP_SMALL)
                set_pw(pi, pin, pw_map[name])
            elif key.lower() == 'w':
                name, pin = servo_list[current_servo]
                lo, hi = PW_LIMITS[name]
                pw_map[name] = min(hi, pw_map[name] + STEP_BIG)
                set_pw(pi, pin, pw_map[name])
            elif key.lower() == 'x':
                name, pin = servo_list[current_servo]
                lo, hi = PW_LIMITS[name]
                pw_map[name] = max(lo, pw_map[name] - STEP_BIG)
                set_pw(pi, pin, pw_map[name])
            elif key.lower() == 'h':
                for name, pin in PINS.items():
                    pw_map[name] = PW_HOME
                    set_pw(pi, pin, PW_HOME)
            elif key.lower() == 's':
                positions[position_name] = dict(pw_map)
                save_positions(positions)
                import time; time.sleep(0.5)
                pos_index += 1
            elif key.lower() == 'n':
                pos_index += 1
            elif key.lower() == 'q':
                break

        print("\n  All done! Saved positions:", list(positions.keys()))

    finally:
        for name, pin in PINS.items():
            set_pw(pi, pin, 0)
        pi.stop()

if __name__ == "__main__":
    main()
