import serial
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.protocol import BAUDRATE, ENCODING, TIMEOUT
from config import SERIAL_PORT

def main():
    print("=" * 50)
    print("  LiFi Chat — MODO RECEPTOR")
    print(f"  Puerto: {SERIAL_PORT} @ {BAUDRATE} baud")
    print("  Esperando mensajes del emisor LiFi...")
    print("  Ctrl+C para terminar.")
    print("=" * 50)

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"[OK] Conectado a {SERIAL_PORT}\n")
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir el puerto: {e}")
        sys.exit(1)

    buffer = ""

    try:
        while True:
            if ser.in_waiting > 0:
                byte = ser.read(1).decode(ENCODING, errors='ignore')

                # El Arduino imprime cada carácter individualmente con su representación en bits
                # Filtramos líneas del tipo "Bits: 01001000 → H" para extraer solo el carácter
                buffer += byte

                if '\n' in buffer:
                    linea = buffer.strip()
                    buffer = ""

                    if '→' in linea and 'Bits:' in linea:
                        # Formato del receptor Arduino: "Bits: 01001000 → H"
                        partes = linea.split('→')
                        if len(partes) == 2:
                            caracter = partes[1].strip()
                            if caracter and caracter != '(carácter no imprimible)':
                                print(caracter, end='', flush=True)
                    elif linea.startswith('[CAL]') or linea.startswith('Esperando'):
                        # Mensajes de estado del Arduino, mostrar en consola
                        print(f"\n[Arduino Receptor]: {linea}")
                    # Ignorar otras líneas de debug del Arduino

    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.")
    finally:
        ser.close()
        print("[Conexión cerrada]")

if __name__ == '__main__':
    main()