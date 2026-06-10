#!/usr/bin/env python3
"""
Robot Arm Color Sorter — 9-zone version
Camera overhead detects box color + zone → arm picks up and sorts.
"""
import pigpio, json, time, cv2, numpy as np, os
from picamera2 import Picamera2

PINS = {
    "S1_base":       17,
    "S3_middle_arm": 22,
    "S4_upper_arm":  23,
    "S5_wrist":      24,
    "S6_claw":       25,
}

POSITIONS_FILE = "positions.json"
CONFIG_FILE    = "zone_config.json"
CLAW_OPEN      = 1300
CLAW_CLOSE     = 1840

def load_json(path):
    with open(path) as f: return json.load(f)

def get_zone_bounds():
    if os.path.exists(CONFIG_FILE):
        c = load_json(CONFIG_FILE)
        return c["x0"], c["y0"], c["x1"], c["y1"]
    return 80, 40, 560, 440  # defaults

def get_zone(px, py, bounds):
    x0, y0, x1, y1 = bounds
    if not (x0 <= px <= x1 and y0 <= py <= y1):
        return None
    col = int((px - x0) / (x1 - x0) * 3)
    row = int((py - y0) / (y1 - y0) * 3)
    return max(0, min(2, row)) * 3 + max(0, min(2, col)) + 1

def set_pw(pi, pin, pw):
    pi.set_PWM_frequency(pin, 50)
    pi.set_PWM_range(pin, 20000)
    pi.set_PWM_dutycycle(pin, pw)

def stop_pw(pi, pin):
    pi.set_PWM_dutycycle(pin, 0)

def move_smooth(pi, from_pos, to_pos, duration=1.0, steps=40):
    for step in range(steps + 1):
        t = step / steps
        for name, pin in PINS.items():
            pw = int(from_pos.get(name, 1500) + (to_pos.get(name, 1500) - from_pos.get(name, 1500)) * t)
            set_pw(pi, pin, pw)
        time.sleep(duration / steps)

def detect_blob(frame, bounds):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_BGR2HSV)

    masks = {
        'red':   cv2.bitwise_or(
                     cv2.inRange(hsv, np.array([0,   120, 70]), np.array([10,  255, 255])),
                     cv2.inRange(hsv, np.array([160, 120, 70]), np.array([180, 255, 255]))),
        'green': cv2.inRange(hsv, np.array([40,  100, 70]), np.array([80,  255, 255])),
        'blue':  cv2.inRange(hsv, np.array([100, 100, 70]), np.array([130, 255, 255])),
    }

    best = None
    for color, mask in masks.items():
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            area = cv2.contourArea(c)
            if area > 500:
                M = cv2.moments(c)
                if M['m00'] > 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    if best is None or area > best[3]:
                        best = (color, cx, cy, area)

    if best:
        color, cx, cy, _ = best
        zone = get_zone(cx, cy, bounds)
        return color, zone
    return None, None

def main():
    pi = pigpio.pi()
    if not pi.connected:
        print("ERROR: pigpiod not running")
        return

    positions = load_json(POSITIONS_FILE)
    bounds    = get_zone_bounds()

    # Check all zone positions are calibrated
    missing = [f"zone_{z}" for z in range(1,10)
               if f"zone_{z}" not in positions]
    if missing:
        print(f"Missing calibration for: {missing}")
        print("Run python3 calibrate.py first.")
        return

    print("Starting camera...")
    cam = Picamera2()
    cfg = cam.create_preview_configuration(main={"size": (640, 480), "format": "BGR888"})
    cam.configure(cfg)
    cam.start()
    time.sleep(2)

    print("Moving to home...")
    cur = dict(positions["home"])
    for name, pin in PINS.items():
        set_pw(pi, pin, cur[name])
    time.sleep(1.2)

    try:
        print("\nColor sorter running. Place boxes in the grid zone.")
        print("Press Ctrl+C to stop.\n")

        while True:
            # 1. Detect from home position (camera sees full grid)
            color, zone = None, None
            for _ in range(20):
                frame = cam.capture_array()
                color, zone = detect_blob(frame, bounds)
                if color and zone:
                    break
                time.sleep(0.3)

            if not color or not zone:
                print("  No box found. Waiting...\n")
                time.sleep(1)
                continue

            print(f"[ DETECTED ] {color.upper()} in zone {zone}")

            # 2. Move to that zone's pickup position (claw open)
            zone_key = f"zone_{zone}"
            pickup = dict(positions[zone_key])
            pickup["S6_claw"] = CLAW_OPEN
            print(f"[ PICK ] Moving to {zone_key}...")
            move_smooth(pi, cur, pickup, duration=1.2)
            cur = dict(pickup)
            time.sleep(0.3)

            # 3. Close claw
            print("  → Grabbing...")
            set_pw(pi, PINS["S6_claw"], CLAW_CLOSE)
            cur["S6_claw"] = CLAW_CLOSE
            time.sleep(0.8)

            # 4. Lift up before rotating
            lifted = dict(cur)
            lifted["S3_middle_arm"] = positions["home"]["S3_middle_arm"]
            lifted["S4_upper_arm"]  = positions["home"]["S4_upper_arm"]
            move_smooth(pi, cur, lifted, duration=0.8)
            cur = dict(lifted)

            # 5. Move to drop container
            drop_key = f"drop_{color}"
            print(f"[ DROP ] Moving to {drop_key}...")
            drop = dict(positions[drop_key])
            drop["S6_claw"] = CLAW_CLOSE
            move_smooth(pi, cur, drop, duration=1.5)
            cur = dict(drop)
            time.sleep(0.3)

            # 6. Release
            print("  → Releasing...")
            set_pw(pi, PINS["S6_claw"], CLAW_OPEN)
            cur["S6_claw"] = CLAW_OPEN
            time.sleep(0.8)

            # 7. Return home
            print("[ HOME ] Returning...\n")
            move_smooth(pi, cur, positions["home"], duration=1.2)
            cur = dict(positions["home"])
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cam.stop()
        move_smooth(pi, cur, positions["home"], duration=1.0)
        time.sleep(1)
        for name, pin in PINS.items():
            stop_pw(pi, pin)
        pi.stop()
        print("Done.")

if __name__ == "__main__":
    main()
