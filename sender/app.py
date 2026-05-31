import eventlet
eventlet.monkey_patch()

import serial
import serial.tools.list_ports
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import sys, os, json, datetime, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.protocol import BAUDRATE, ENCODING, TIMEOUT

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.config['SECRET_KEY'] = 'lifi-sender-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

SYS_PATTERNS = ['[CAL]', '[SYS]', 'Conectado', 'Esperando', 'desconect',
                'inicializando', 'listo', 'Bits:', 'Error', '[Error]',
                'Receptor', 'Emisor', 'Puerto', 'Baudrate']

state = {
    'tx':  { 'port': None, 'serial': None, 'connected': False },
    'rx':  { 'port': None, 'serial': None, 'connected': False },
    'history': [],
    'last_recv_time': 0
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

def is_system_line(line):
    return any(p in line for p in SYS_PATTERNS)

def read_rx_loop():
    while True:
        try:
            rx = state['rx']
            if rx['serial'] and rx['connected']:
                if rx['serial'].in_waiting > 0:
                    line = rx['serial'].readline().decode(ENCODING, errors='ignore').strip()
                    if line:
                        socketio.emit('arduino_log', {'msg': line})
                        socketio.emit('char_received', {'char': '', 'buffer': line})
                        if not is_system_line(line):
                            now = time.time()
                            if state['last_recv_time'] > 0 and now - state['last_recv_time'] < 0.5:
                                continue
                            state['last_recv_time'] = now
                            entry = {
                                'id': len(state['history']) + 1,
                                'text': line,
                                'direction': 'received',
                                'sender': 'General',
                                'timestamp': datetime.datetime.now().strftime('%H:%M:%S'),
                                'date': datetime.datetime.now().strftime('%Y-%m-%d')
                            }
                            state['history'].append(entry)
                            save_history()
                            socketio.emit('new_message', entry)
            eventlet.sleep(0.05)
        except Exception as e:
            socketio.emit('arduino_log', {'msg': f'[Error RX]: {str(e)}'})
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
    role = data.get('role', 'tx')
    if not port:
        return jsonify({'ok': False, 'error': 'Puerto no especificado'})
    try:
        target = state[role]
        if target['serial'] and target['serial'].is_open:
            target['serial'].close()
        target['serial'] = serial.Serial(port, BAUDRATE, timeout=TIMEOUT)
        target['port'] = port
        target['connected'] = True
        socketio.emit('status_change', {'connected': True, 'port': port, 'role': role})
        if role == 'rx':
            eventlet.spawn(read_rx_loop)
        return jsonify({'ok': True, 'port': port, 'role': role})
    except Exception as e:
        state[role]['connected'] = False
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/disconnect', methods=['POST'])
def disconnect_port():
    data = request.json
    role = data.get('role', 'tx')
    try:
        target = state[role]
        if target['serial']:
            target['serial'].close()
        target['connected'] = False
        target['port'] = None
        socketio.emit('status_change', {'connected': False, 'port': None, 'role': role})
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/api/send', methods=['POST'])
def send_message():
    data = request.json
    msg = data.get('message', '').strip()
    recipient = data.get('recipient', 'General')
    if not msg:
        return jsonify({'ok': False, 'error': 'Mensaje vacío'})
    tx = state['tx']
    if not tx['connected'] or not tx['serial']:
        return jsonify({'ok': False, 'error': 'Puerto TX no conectado'})
    try:
        tx['serial'].write((msg + '\n').encode(ENCODING))
        entry = {
            'id': len(state['history']) + 1,
            'text': msg,
            'direction': 'sent',
            'recipient': recipient,
            'sender': 'Aldo',
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
    return jsonify({
        'connected': state['tx']['connected'] or state['rx']['connected'],
        'port': state['tx']['port'] or state['rx']['port'],
        'mode': 'sender',
        'tx': state['tx'],
        'rx': state['rx']
    })

@socketio.on('connect')
def on_connect():
    for role in ('tx', 'rx'):
        t = state[role]
        emit('status_change', {'connected': t['connected'], 'port': t['port'], 'role': role})
    emit('history_load', state['history'])

if __name__ == '__main__':
    print("=" * 50)
    print("  LiFi Web — EMISOR (TX+RX)")
    print("  Abre: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
