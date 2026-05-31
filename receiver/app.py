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
app.config['SECRET_KEY'] = 'lifi-receiver-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

BUFFER_TIMEOUT = 1.5

SYS_PATTERNS = ['[CAL]', '[SYS]', 'Conectado', 'Esperando', 'desconect',
                'inicializando', 'listo', 'Receptor', 'Emisor', 'Puerto', 'Baudrate']

state = {
    'tx':  { 'port': None, 'serial': None, 'connected': False },
    'rx':  { 'port': None, 'serial': None, 'connected': False },
    'history': [],
    'char_buffer': '',
    'last_char_time': 0,
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

def parse_arduino_line(line):
    if '→' in line and 'Bits:' in line:
        partes = line.split('→')
        if len(partes) == 2:
            char = partes[1].strip()
            if char == '\\n' or char == '(nueva línea)' or char == '(newline)':
                return '\n'
            if char and char != '(carácter no imprimible)':
                return char
            if not char:
                bits_part = partes[0].replace('Bits:', '').strip()
                if bits_part == '00001010':
                    return '\n'
    return None

def save_and_emit_message():
    msg_text = state['char_buffer'].strip()
    state['char_buffer'] = ''
    state['last_char_time'] = 0
    if not msg_text:
        return
    entry = {
        'id': len(state['history']) + 1,
        'text': msg_text,
        'direction': 'received',
        'sender': 'General',
        'timestamp': datetime.datetime.now().strftime('%H:%M:%S'),
        'date': datetime.datetime.now().strftime('%Y-%m-%d')
    }
    state['history'].append(entry)
    save_history()
    socketio.emit('new_message', entry)

def is_system_line(line):
    return any(p in line for p in SYS_PATTERNS)

def read_rx_loop():
    """Lee del puerto RX del Arduino receptor en background."""
    while True:
        try:
            rx = state['rx']
            if rx['serial'] and rx['connected']:

                if (state['char_buffer'] and
                        state['last_char_time'] > 0 and
                        time.time() - state['last_char_time'] > BUFFER_TIMEOUT):
                    save_and_emit_message()

                if rx['serial'].in_waiting > 0:
                    raw = rx['serial'].read_until(b'\n', size=256).decode(
                        ENCODING, errors='ignore'
                    ).strip()

                    if not raw:
                        eventlet.sleep(0.02)
                        continue

                    socketio.emit('arduino_log', {'msg': raw})

                    char = parse_arduino_line(raw)

                    if char is not None:
                        if char == '\n':
                            save_and_emit_message()
                        else:
                            state['char_buffer'] += char
                            state['last_char_time'] = time.time()
                            socketio.emit('char_received', {
                                'char': char,
                                'buffer': state['char_buffer']
                            })
                    elif not is_system_line(raw):
                        socketio.emit('char_received', {'char': '', 'buffer': raw})

            eventlet.sleep(0.02)

        except Exception as e:
            socketio.emit('arduino_log', {'msg': f'[Error RX]: {str(e)}'})
            eventlet.sleep(1)

@app.route('/')
def index():
    return render_template('index.html', mode='receiver', title='LiFi Chat — Carla')

@app.route('/api/ports')
def get_ports():
    ports = [{'device': p.device, 'desc': p.description}
             for p in serial.tools.list_ports.comports()]
    return jsonify(ports)

@app.route('/api/connect', methods=['POST'])
def connect_port():
    data = request.json
    port = data.get('port')
    role = data.get('role', 'rx')
    if not port:
        return jsonify({'ok': False, 'error': 'Puerto no especificado'})
    try:
        target = state[role]
        if target['serial'] and target['serial'].is_open:
            target['serial'].close()
        target['serial'] = serial.Serial(port, BAUDRATE, timeout=0.1)
        target['port'] = port
        target['connected'] = True
        if role == 'rx':
            state['char_buffer'] = ''
            state['last_char_time'] = 0
            eventlet.spawn(read_rx_loop)
        socketio.emit('status_change', {'connected': True, 'port': port, 'role': role})
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
            'sender': 'Carla',
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
        'mode': 'receiver',
        'tx': state['tx'],
        'rx': state['rx']
    })

@socketio.on('connect')
def on_connect():
    for role in ('tx', 'rx'):
        t = state[role]
        emit('status_change', {'connected': t['connected'], 'port': t['port'], 'role': role})
    emit('history_load', state['history'])

@socketio.on('flush_buffer')
def flush_buffer():
    save_and_emit_message()

if __name__ == '__main__':
    print("=" * 50)
    print("  LiFi Web — RECEPTOR (TX+RX)")
    print("  Abre: http://localhost:5001")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)
