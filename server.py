from flask import Flask, render_template, request, jsonify
import serial
import serial.tools.list_ports
import time
import threading

app = Flask(__name__)

BAUD = 9600
PORT = "/dev/cu.usbmodem11401"  # your Arduino port

arduino = None
serial_lock = threading.Lock()

def connect_arduino():
    global arduino
    try:
        arduino = serial.Serial(PORT, BAUD, timeout=2)
        time.sleep(2)  # wait for Arduino reset
        arduino.readline()  # consume "READY"
        print(f"Connected to Arduino on {PORT}")
    except Exception as e:
        print(f"Could not connect to Arduino: {e}")
        print("Server will still run — connect Arduino and restart.")
        arduino = None

def send_command(cmd):
    with serial_lock:
        if arduino and arduino.is_open:
            arduino.write((cmd + "\n").encode())
            time.sleep(0.05)
            response = arduino.readline().decode().strip()
            return response
    return "DISCONNECTED"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/move", methods=["POST"])
def move():
    data = request.get_json()
    servo = int(data["servo"])   # 1-6
    angle = int(data["angle"])   # 0-180
    if not (1 <= servo <= 6 and 0 <= angle <= 180):
        return jsonify({"status": "error", "message": "out of range"}), 400
    resp = send_command(f"S{servo}:{angle}")
    return jsonify({"status": "ok", "response": resp})

@app.route("/home", methods=["POST"])
def home():
    resp = send_command("HOME")
    return jsonify({"status": "ok", "response": resp})

@app.route("/status")
def status():
    resp = send_command("STATUS")
    return jsonify({"status": "ok", "response": resp})

if __name__ == "__main__":
    connect_arduino()
    print("Open http://localhost:5000 in your browser")
    app.run(host="0.0.0.0", port=5000, debug=False)
