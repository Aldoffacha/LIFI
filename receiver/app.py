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
app.config['SECRET_KEY'] = 'lifi-receiver-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

state = {
    'port': None,
    'serial': None,
    'connected': False,
    'history': [],
    'char_buffer': ''
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
    """
    El Arduino receptor imprime: "Bits: 01001000 → H"
    Retorna el carácter decodificado, o None si la línea no es de ese formato.
    También maneja el caso especial del carácter '\n' (ASCII 10).
    """
    if '→' in line and 'Bits:' in line:
        partes = line.split('→')
        if len(partes) == 2:
            char = partes[1].strip()
            # El Arduino puede imprimir el salto de línea como literal '\n' o vacío
            if char == '\\n' or char == '(nueva línea)' or char == '(newline)':
                return '\n'
            if char and char != '(carácter no imprimible)':
                return char
            # Si char está vacío pero el bits indican ASCII 10 → salto de línea
            if not char:
                bits_part = partes[0].replace('Bits:', '').strip()
                if bits_part == '00001010':
                    return '\n'
    return None


def save_and_emit_message():
    """Guarda el buffer actual como mensaje en el historial y lo emite."""
    msg_text = state['char_buffer'].strip()
    state['char_buffer'] = ''
    if not msg_text:
        return
    entry = {
        'id': len(state['history']) + 1,
        'text': msg_text,
        'direction': 'received',
        'timestamp': datetime.datetime.now().strftime('%H:%M:%S'),
        'date': datetime.datetime.now().strftime('%Y-%m-%d')
    }
    state['history'].append(entry)
    save_history()
    socketio.emit('new_message', entry)


def read_serial_loop():
    """Lee continuamente el puerto serial del Arduino receptor."""
    while True:
        try:
            if state['serial'] and state['connected']:
                if state['serial'].in_waiting > 0:
                    raw = state['serial'].readline().decode(ENCODING, errors='ignore').strip()
                    if not raw:
                        eventlet.sleep(0.02)
                        continue

                    # Reenviar log crudo al frontend
                    socketio.emit('arduino_log', {'msg': raw})

                    # Intentar extraer carácter decodificado
                    char = parse_arduino_line(raw)

                    if char is not None:
                        if char == '\n':
                            # Fin de mensaje — guardar lo acumulado
                            save_and_emit_message()
                        else:
                            state['char_buffer'] += char
                            # Emitir progreso del buffer al frontend
                            socketio.emit('char_received', {
                                'char': char,
                                'buffer': state['char_buffer']
                            })

                    # Mensajes de calibración/estado del Arduino
                    elif raw.startswith('[CAL]') or 'Esperando' in raw or 'Receptor' in raw:
                        socketio.emit('system_msg', {'msg': raw})

            eventlet.sleep(0.02)
        except Exception as e:
            socketio.emit('arduino_log', {'msg': f'[Error]: {str(e)}'})
            eventlet.sleep(1)


@app.route('/')
def index():
    return render_template('index.html', mode='receiver', title='LiFi Chat — Receptor')

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
        state['char_buffer'] = ''  # Limpiar buffer al reconectar
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
    return jsonify({'connected': state['connected'], 'port': state['port'], 'mode': 'receiver'})

@socketio.on('connect')
def on_connect():
    emit('status_change', {'connected': state['connected'], 'port': state['port']})
    emit('history_load', state['history'])

@socketio.on('flush_buffer')
def flush_buffer():
    """Permite forzar el guardado del buffer actual como mensaje (botón manual)."""
    save_and_emit_message()

if __name__ == '__main__':
    print("=" * 50)
    print("  LiFi Web — RECEPTOR")
    print("  Abre: http://localhost:5001")
    print("=" * 50)
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)