#!/usr/bin/env python3
"""
Camera preview with 9-zone grid overlay.
Open http://robotarm.local:5001
Adjust ZONE_* constants below until the green grid matches your taped area.
"""
from flask import Flask, Response, render_template_string, request, jsonify
import cv2
import numpy as np
from picamera2 import Picamera2
import json, time, os

app = Flask(__name__)

# ── Adjust these so the green grid lines up with your masking tape ──────────
ZONE_X0 = 80    # left edge of work area in pixels
ZONE_Y0 = 40    # top edge
ZONE_X1 = 560   # right edge
ZONE_Y1 = 440   # bottom edge
# ────────────────────────────────────────────────────────────────────────────

CONFIG_FILE = "zone_config.json"

def load_config():
    global ZONE_X0, ZONE_Y0, ZONE_X1, ZONE_Y1
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            c = json.load(f)
            ZONE_X0, ZONE_Y0 = c["x0"], c["y0"]
            ZONE_X1, ZONE_Y1 = c["x1"], c["y1"]

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({"x0": ZONE_X0, "y0": ZONE_Y0, "x1": ZONE_X1, "y1": ZONE_Y1}, f)

load_config()

cam = Picamera2()
config = cam.create_preview_configuration(main={"size": (640, 480), "format": "BGR888"})
cam.configure(config)
cam.start()
time.sleep(2)

def get_zone(px, py):
    if not (ZONE_X0 <= px <= ZONE_X1 and ZONE_Y0 <= py <= ZONE_Y1):
        return None
    col = int((px - ZONE_X0) / (ZONE_X1 - ZONE_X0) * 3)
    row = int((py - ZONE_Y0) / (ZONE_Y1 - ZONE_Y0) * 3)
    return max(0, min(2, row)) * 3 + max(0, min(2, col)) + 1

def detect_blob(frame):
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
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
        return color, get_zone(cx, cy), cx, cy
    return None

def draw_grid(frame):
    zw = (ZONE_X1 - ZONE_X0) // 3
    zh = (ZONE_Y1 - ZONE_Y0) // 3
    for i in range(4):
        cv2.line(frame, (ZONE_X0 + i*zw, ZONE_Y0), (ZONE_X0 + i*zw, ZONE_Y1), (0,255,0), 1)
        cv2.line(frame, (ZONE_X0, ZONE_Y0 + i*zh), (ZONE_X1, ZONE_Y0 + i*zh), (0,255,0), 1)
    for row in range(3):
        for col in range(3):
            zone = row * 3 + col + 1
            tx = ZONE_X0 + col * zw + 6
            ty = ZONE_Y0 + row * zh + 22
            color = (100,100,100) if zone == 5 else (0,255,0)
            cv2.putText(frame, str(zone), (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

def generate_frames():
    while True:
        frame = cam.capture_array()
        draw_grid(frame)

        result = detect_blob(frame)
        if result:
            color, zone, cx, cy = result
            dot = {'red':(0,0,255),'green':(0,200,0),'blue':(255,80,0)}.get(color,(128,128,128))
            cv2.circle(frame, (cx, cy), 18, dot, -1)
            cv2.circle(frame, (cx, cy), 18, (255,255,255), 2)
            label = f"{color.upper()} Z{zone}" if zone else f"{color.upper()} OUT"
            cv2.putText(frame, label, (cx-30, cy-25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, dot, 2)

        _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
               + jpeg.tobytes() + b'\r\n')
        time.sleep(0.05)

HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Robot Arm Camera</title>
  <style>
    body{background:#111;color:#eee;font-family:sans-serif;display:flex;
         flex-direction:column;align-items:center;margin:0;padding:16px}
    h2{color:#7eb8f7;letter-spacing:2px;margin-bottom:4px}
    p{color:#888;font-size:.8rem;margin:2px 0 12px}
    img{width:100%;max-width:640px;border:2px solid #333;border-radius:8px}
    .panel{background:#1a1a2a;border:1px solid #333;border-radius:8px;
           padding:14px 20px;max-width:640px;width:100%;margin-top:14px}
    .panel h3{color:#7eb8f7;margin:0 0 10px;font-size:.95rem}
    label{font-size:.8rem;color:#aaa;display:block;margin:6px 0 2px}
    input[type=range]{width:100%;accent-color:#7eb8f7}
    .row{display:flex;gap:10px}
    .row>div{flex:1}
    .val{color:#7eb8f7;font-size:.75rem}
    button{margin-top:12px;width:100%;padding:10px;background:#1e3a5f;
           border:1px solid #3a6fa8;color:#7eb8f7;border-radius:8px;
           font-size:.9rem;cursor:pointer}
    #msg{text-align:center;color:#4caf50;font-size:.8rem;margin-top:6px;height:16px}
  </style>
</head>
<body>
  <h2>Camera Preview</h2>
  <p>Green grid = 9 zones. Colored dot = detected box + zone number.</p>
  <img src="/video">
  <div class="panel">
    <h3>Adjust grid to match your taped area</h3>
    <div class="row">
      <div>
        <label>Left edge (X0) <span class="val" id="vx0"></span></label>
        <input type="range" id="x0" min="0" max="320" oninput="update()">
      </div>
      <div>
        <label>Right edge (X1) <span class="val" id="vx1"></span></label>
        <input type="range" id="x1" min="320" max="640" oninput="update()">
      </div>
    </div>
    <div class="row">
      <div>
        <label>Top edge (Y0) <span class="val" id="vy0"></span></label>
        <input type="range" id="y0" min="0" max="240" oninput="update()">
      </div>
      <div>
        <label>Bottom edge (Y1) <span class="val" id="vy1"></span></label>
        <input type="range" id="y1" min="240" max="480" oninput="update()">
      </div>
    </div>
    <button onclick="save()">Save Grid Settings</button>
    <div id="msg"></div>
  </div>
  <script>
    async function loadCurrent() {
      const r = await fetch('/config'); const d = await r.json();
      document.getElementById('x0').value = d.x0; document.getElementById('vx0').textContent = d.x0;
      document.getElementById('x1').value = d.x1; document.getElementById('vx1').textContent = d.x1;
      document.getElementById('y0').value = d.y0; document.getElementById('vy0').textContent = d.y0;
      document.getElementById('y1').value = d.y1; document.getElementById('vy1').textContent = d.y1;
    }
    function update() {
      ['x0','x1','y0','y1'].forEach(id => {
        document.getElementById('v'+id).textContent = document.getElementById(id).value;
      });
      fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          x0: +document.getElementById('x0').value,
          x1: +document.getElementById('x1').value,
          y0: +document.getElementById('y0').value,
          y1: +document.getElementById('y1').value,
        })
      });
    }
    async function save() {
      await fetch('/save', {method:'POST'});
      document.getElementById('msg').textContent = 'Saved!';
      setTimeout(()=>document.getElementById('msg').textContent='', 2000);
    }
    loadCurrent();
  </script>
</body>
</html>"""

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/video')
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/config', methods=['GET','POST'])
def config_route():
    global ZONE_X0, ZONE_Y0, ZONE_X1, ZONE_Y1
    if request.method == 'POST':
        d = request.get_json()
        ZONE_X0, ZONE_Y0, ZONE_X1, ZONE_Y1 = d['x0'], d['y0'], d['x1'], d['y1']
        return jsonify(ok=True)
    return jsonify(x0=ZONE_X0, y0=ZONE_Y0, x1=ZONE_X1, y1=ZONE_Y1)

@app.route('/save', methods=['POST'])
def save_route():
    save_config(); return jsonify(ok=True)

if __name__ == '__main__':
    print("Open http://robotarm.local:5001 in your browser")
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
