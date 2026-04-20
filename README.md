# LiFi Chat Web System


## Estructura

```
lifi_web/
├── sender/
│   ├── app.py          ← Servidor Flask para PC A (Emisor)
│   └── history.json    ← Se crea automáticamente
├── receiver/
│   ├── app.py          ← Servidor Flask para PC B (Receptor)
│   └── history.json    ← Se crea automáticamente
├── shared/
│   └── protocol.py     ← Constantes (baudrate, etc.)
├── templates/
│   └── index.html      ← Interfaz web (misma para ambos)
├── requirements.txt
└── README.md
```

## Instalación (una sola vez en cada PC)

```bash
pip install flask flask-socketio pyserial eventlet
```

## Uso

### PC A — Emisor
```bash
cd LIFI/sender
python app.py
```
Luego abre en el navegador: http://localhost:5000

### PC B — Receptor
```bash
cd LIFI/receiver
python app.py
```
Luego abre en el navegador: http://localhost:5001

## Desde la interfaz web

1. Conecta el Arduino a la PC por USB
2. Haz clic en el ícono de actualizar (🔄) para detectar puertos COM
3. Selecciona el puerto del Arduino en el desplegable
4. Clic en **Conectar**
5. Escribe y envía mensajes desde el chat

## Notas importantes

- Cierra el Monitor Serial del IDE de Arduino antes de conectar
- El emisor corre en puerto 5000, el receptor en 5001
- El historial se guarda automáticamente en history.json
- El Log Arduino muestra los datos crudos del puerto serial
