import serial
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from shared.protocol import BAUDRATE, ENCODING, TIMEOUT
from config import SERIAL_PORT

def main():
    print("=" * 50)
    print("  LiFi Chat — MODO EMISOR")
    print(f"  Puerto: {SERIAL_PORT} @ {BAUDRATE} baud")
    print("  Escribe un mensaje y presiona ENTER para enviarlo.")
    print("  Escribe 'salir' para terminar.")
    print("=" * 50)

    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=TIMEOUT)
        print(f"[OK] Conectado a {SERIAL_PORT}\n")
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir el puerto: {e}")
        sys.exit(1)

    try:
        while True:
            mensaje = input("Tú > ").strip()

            if mensaje.lower() == 'salir':
                print("Cerrando conexión...")
                break

            if not mensaje:
                continue

            # Enviar al Arduino Emisor con salto de línea (el Arduino usa readStringUntil('\n'))
            linea = mensaje + '\n'
            ser.write(linea.encode(ENCODING))
            print(f"[Enviado {len(mensaje)} caracteres via LiFi]")

            # Leer respuesta de confirmación del Arduino (opcional)
            respuesta = ser.readline().decode(ENCODING, errors='ignore').strip()
            if respuesta:
                print(f"[Arduino Emisor]: {respuesta}")

    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
    finally:
        ser.close()
        print("[Conexión cerrada]")

if __name__ == '__main__':
    main()