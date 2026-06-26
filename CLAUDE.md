# CLAUDE.md

Guia para Claude Code al trabajar en este repositorio.

## Que es este proyecto

Aplicacion de escritorio (Python 3.12, Windows) para un proyecto de artes visuales sobre
percepcion del sonido y biometrias fisiologicas. Lee datos en tiempo real de una placa
XIAO nRF52840 + sensor IMU BNO085 por USB serial, visualiza la orientacion en 3D con
quaterniones (sin gimbal lock), reproduce estimulos sonoros WAV y registra los datos
biometricos en CSV.

Ver `README.md` para instalacion, uso, protocolo serial y esquema CSV.

## Estructura

```
├── main.py            # Entry point, loop pygame+OpenGL a 60 FPS
├── config.py          # Carga config.json (singleton CFG), merge sobre config.example.json
├── serial_reader.py   # Thread daemon: autodetecta puerto, parsea IMU + senales KEY:VALUE
├── audio_player.py     # Thread daemon: reproduccion WAV con sounddevice (no pygame.mixer)
├── logger.py           # Thread NO daemon: CSV con columnas dinamicas, flush periodico
├── renderer.py         # Quaterniones, loader OBJ con fallback a cubo, display lists, perfiles de camara
├── ui.py               # HUD, panel lateral, sparklines, dialogos modales
├── config.json         # Config activa (generada, no se versiona)
├── config.example.json # Defaults de referencia (si se edita, mantener sincronizado el README)
├── scripts/simulate_embedded.py  # Simulador de la placa (modo serial o TCP)
├── assets/models/cabeza.obj  # Placeholder generado automaticamente si falta
├── assets/audio/        # WAVs del usuario (ignorados salvo test_tone.wav)
└── logs/                 # CSVs de sesion (ignorados)
```

## Documentacion de funciones

Toda funcion o metodo Python que se cree o modifique debe tener un docstring en
**formato Google**. Estructura obligatoria:

```python
def ejemplo(param1: str, param2: int = 0) -> bool:
    """Resumen de una linea que describe que hace la funcion.

    Args:
        param1: Descripcion del primer parametro.
        param2: Descripcion del segundo parametro.

    Returns:
        Descripcion del valor de retorno.

    Raises:
        ValueError: Cuando y por que se lanza esta excepcion.
    """
```

Reglas:
- La primera linea es un resumen corto (no termina en punto).
- Omitir secciones que no apliquen (si no hay `Returns`, no escribir la seccion).
- Para metodos `__init__`, documentar los parametros en la seccion `Args` del propio `__init__`.
- Los metodos privados (`_nombre`) tambien requieren docstring si tienen parametros no obvios.

## Restricciones importantes (no romper)

- Python 3.12 / Windows. No usar APIs exclusivas de Linux/macOS.
- PyOpenGL **legacy pipeline** (sin shaders): `glBegin/glEnd`, `glVertex3f`, `glMultMatrixf`.
- Audio **solo con `sounddevice` + `scipy.io.wavfile`**, nunca `pygame.mixer`.
- Todos los threads son daemon **salvo `CSVLogger`**, que debe `join()` limpiamente al salir
  para no perder datos de sesion.
- Comunicacion entre threads solo via `queue.Queue` / `threading.Event` / locks — nada
  bloqueante en el loop principal de graficos.
- El CSV debe sobrevivir a un cierre inesperado (flush periodico via
  `CFG.log_flush_interval_s`); las columnas se descubren dinamicamente segun las
  claves de senales recibidas (no hay lista fija en el codigo).
- `CFG` (de `config.py`) es la unica fuente de configuracion; no hardcodear valores
  que ya existan en `config.example.json`.

## Como probar

```
python3 -m pip install -r requirements.txt
python3 main.py
```

Sin hardware conectado: la app igual arranca (muestra "sin conexion"), usa el modelo
placeholder/configurado y permite probar la UI, el panel lateral y la reproduccion de
`assets/audio/test_tone.wav` (WAV corto incluido en el repo para pruebas de la app sin
necesitar audios reales del usuario). Para simular paquetes IMU/senales sin hardware,
ver `scripts/simulate_embedded.py` (modo `--tcp` + `python3 main.py socket://host:puerto`).

Para chequeo rapido de sintaxis de todos los modulos:

```
python -m py_compile config.py serial_reader.py audio_player.py logger.py renderer.py ui.py main.py
```
