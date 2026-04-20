import eventlet
eventlet.monkey_patch()

import serial
import serial.tools.list_ports
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import sys, os, json, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.protocol import BAUDRATE, ENCODING, TIMEOUT

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = 'lifi-sender-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Estado global
state = {
    'port': None,
    'serial': None,
    'connected': False,
    'history': []
}

HISTORY_FILE = os.path.join(os.path.dirname(__file__), 'history.json')

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history():
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(state['history'], f, ensure_ascii=False, indent=2)

state['history'] = load_history()

def read_serial_loop():
    """Lee respuestas del Arduino emisor en background."""
    while True:
        try:
            if state['serial'] and state['connected']:
                if state['serial'].in_waiting > 0:
                    line = state['serial'].readline().decode(ENCODING, errors='ignore').strip()
                    if line:
                        socketio.emit('arduino_log', {'msg': line})
            eventlet.sleep(0.05)
        except Exception as e:
            socketio.emit('arduino_log', {'msg': f'[Error lectura]: {str(e)}'})
            eventlet.sleep(1)

@app.route('/')
def index():
    return render_template('index.html', mode='sender', title='LiFi Chat — Emisor')

@app.route('/api/ports')
def get_ports():
    ports = [{'device': p.device, 'desc': p.description}
             for p in serial.tools.list_ports.comports()]
    return jsonify(ports)

@app.route('/api/connect', methods=['POST'])
def connect_port():
    data = request.json
    port = data.get('port')
    if not port:
        return jsonify({'ok': False, 'error': 'Puerto no especificado'})
    try:
        if state['serial'] and state['serial'].is_open:
            state['serial'].close()
        state['serial'] = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        state['port'] = port
        state['connected'] = True
        socketio.emit('status_change', {'connected': True, 'port': port})
        eventlet.spawn(read_serial_loop)
        return jsonify({'ok': True, 'port': port})
    except Exception as e:
        state['connected'] = False
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/disconnect', methods=['POST'])
def disconnect_port():
    try:
        if state['serial']:
            state['serial'].close()
        state['connected'] = False
        state['port'] = None
        socketio.emit('status_change', {'connected': False, 'port': None})
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/send', methods=['POST'])
def send_message():
    data = request.json
    msg = data.get('message', '').strip()
    if not msg:
        return jsonify({'ok': False, 'error': 'Mensaje vacío'})
    if not state['connected'] or not state['serial']:
        return jsonify({'ok': False, 'error': 'No conectado al puerto serial'})
    try:
        line = msg + '\n'
        state['serial'].write(line.encode(ENCODING))
        entry = {
            'id': len(state['history']) + 1,
            'text': msg,
            'direction': 'sent',
            'timestamp': datetime.datetime.now().strftime('%H:%M:%S'),
            'date': datetime.datetime.now().strftime('%Y-%m-%d')
        }
        state['history'].append(entry)
        save_history()
        socketio.emit('new_message', entry)
        return jsonify({'ok': True, 'entry': entry})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/history')
def get_history():
    return jsonify(state['history'])

@app.route('/api/clear_history', methods=['POST'])
def clear_history():
    state['history'] = []
    save_history()
    return jsonify({'ok': True})

@app.route('/api/status')
def get_status():
    return jsonify({'connected': state['connected'], 'port': state['port'], 'mode': 'sender'})

@socketio.on('connect')
def on_connect():
    emit('status_change', {'connected': state['connected'], 'port': state['port']})
    emit('history_load', state['history'])

if __name__ == '__main__':
    print("=" * 50)
    print("  LiFi Web — EMISOR")
    print("  Abre: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
