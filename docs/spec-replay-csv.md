# Spec: Replay de CSV

## 1. Motivacion

Las sesiones grabadas quedan como archivos CSV en `logs/`. El replay permite reproducir
una sesion pasada directamente en la ventana 3D, mostrando la orientacion de la cabeza
y los valores de las senales fisiologicas tal como ocurrieron, sin necesidad del hardware.

Casos de uso principales:
- Verificar la calidad de una sesion antes de una presentacion.
- Explorar el movimiento de la cabeza en momentos especificos del audio.
- Mostrar el trabajo a otras personas sin hardware conectado.

---

## 2. Alcance

### Incluido (v1 implementado)

- Seleccion de sesion desde la interfaz grafica (modal con lista de CSVs).
- Reproduccion de la orientacion 3D (quaterniones) desde el CSV.
- Visualizacion de PPG/GSR y senales adicionales en los widgets del HUD.
- Reproduccion del audio original con `sounddevice` (sin countdown, inicio inmediato).
- Controles de transporte: play/pausa, velocidad (0.5x / 1x / 2x).
- Barra de progreso con tiempo actual y total.
- Cambio visual de color (acento purpura, fondo oscuro) al entrar en modo replay.
- Al finalizar el CSV el replay se detiene en el ultimo frame; el usuario sale manualmente.

### Excluido (v1)

- Scrubbing (arrastrar la barra de progreso a un punto arbitrario).
- Exportar el replay como video.
- Sincronizacion exacta audio/datos (el audio empieza al mismo tiempo que los datos,
  pero no hay compensacion de drift).

---

## 3. Interfaz de usuario

### 3.1 Inicio del modo replay

1. Clic en **"Abrir Replay..."** en la seccion inferior del panel lateral.
2. Se abre el modal de seleccion con la lista de CSVs en `logs/` (mas reciente primero).
3. Seleccionar un archivo con clic; confirmar con **"Iniciar Replay"** o `Enter`.

Al entrar en modo replay:
- El acento de la UI cambia a **purpura** (`#8250c8`).
- El fondo OpenGL adopta un tinte purpura oscuro (`#120A1C` aprox.).
- Los botones REPRODUCIR/ABORTAR son reemplazados por controles de transporte.
- La barra de estado muestra `◉ REPLAY` con nombre del participante, archivo y velocidad.
- El boton del panel cambia a **"Salir del Replay"**.

### 3.2 Fin del replay

Al llegar al ultimo frame del CSV:
- La reproduccion se pausa automaticamente en el ultimo frame.
- La barra de progreso queda al 100% y el boton muestra el icono de pausa.
- La interfaz permanece en modo replay hasta que el usuario salga manualmente.

### 3.3 Salida del modo replay

| Accion | Resultado |
|--------|-----------|
| Boton **"Salir"** en controles de transporte | Sale del modo replay |
| Clic en **"Salir del Replay"** en panel lateral | Sale del modo replay |
| Tecla `ESC` | Sale del modo replay |

Al salir se restauran los colores normales, se detiene el audio y los controles
de sesion vuelven a REPRODUCIR/ABORTAR.

### 3.4 Controles de transporte

Reemplazan a REPRODUCIR/ABORTAR en la zona inferior de la ventana:

```
[▶/⏸]  [0.5x] [1x] [2x]   ████████████░░░░░░  0:23 / 1:12   [Salir]
```

| Control | Tecla | Accion |
|---------|-------|--------|
| Play / Pausa | `Espacio` | Alterna entre reproduccion y pausa |
| Velocidad 0.5x | `1` | Reproduce a mitad de velocidad |
| Velocidad 1x | `2` | Velocidad normal (por defecto al iniciar) |
| Velocidad 2x | `3` | Reproduce al doble de velocidad |
| Salir | `ESC` | Sale del modo replay sin cerrar la app |

La velocidad se puede cambiar en caliente sin perder la posicion de reproduccion.

### 3.5 Barra de estado en modo replay

```
◉ REPLAY   Juan Perez  |  juan_20260625_143000.csv  |  ▶  |  1x  |  Camara: default
```

---

## 4. Datos requeridos del CSV

El replay funciona con cualquier CSV generado por la app. Solo se procesan filas
con `estado == "record"`.

| Columna | Uso |
|---------|-----|
| `timestamp` | Controla el timing (los datos avanzan segun la diferencia de timestamps) |
| `estado` | Filtro: solo filas `"record"` |
| `audio_file` | Se busca el WAV en `assets/audio/` para reproduccion |
| `qw`, `qx`, `qy`, `qz` | Alimentan el render 3D; filas sin estos valores solo actualizan senales |
| *(senales dinamicas)* | Se muestran en los widgets del HUD (PPG, GSR, etc.) |

Si el CSV no tiene filas `"record"` validas, el replay lanza `ValueError` y no entra
en modo replay (se muestra el error en consola).

---

## 5. Implementacion

### 5.1 Modulos

| Archivo | Rol |
|---------|-----|
| `replay_reader.py` | Parsea el CSV y avanza el puntero de reproduccion segun tiempo real y velocidad. Expone la misma interfaz duck-type que `SerialReader`. |
| `ui.py` | Modal de seleccion de log, controles de transporte, cambio de colores, barra de estado en modo replay. |
| `main.py` | Orquesta el ciclo de replay: instancia `ReplayReader`, reproduce audio con `sounddevice`, usa `active_reader` para seleccionar la fuente de datos activa. |

### 5.2 Interfaz publica de ReplayReader

```python
class ReplayReader:
    # Misma interfaz que SerialReader
    def get_imu(self) -> tuple: ...          # (quat, euler) — euler siempre (0,0,0)
    def get_signals(self) -> dict: ...       # {clave: float}
    def rate_hz(self) -> float: ...
    def stop(self): ...
    connected: bool  # siempre True
    port: str        # nombre del CSV (para la barra de estado)
    baud: int        # siempre 0

    # Controles de transporte
    def play(self): ...
    def pause(self): ...
    def toggle_play(self): ...
    def set_speed(self, speed: float): ...
    def update(self): ...  # llamar una vez por frame en el loop principal

    # Estado
    elapsed_s: float
    total_s: float
    done: bool
    playing: bool
    speed: float
    audio_file: str
    participant: str
```

### 5.3 Patron de fuente de datos activa

`main.py` utiliza duck-typing para no distinguir entre hardware y replay:

```python
active_reader = replay_reader if replay_reader is not None else reader

q_now, _ = active_reader.get_imu()
signals   = active_reader.get_signals()
ctx = {
    "connected": active_reader.connected,
    "port":      active_reader.port,
    ...
}
```

### 5.4 Audio en modo replay

El audio se reproduce directamente con `sounddevice.play()` (sin countdown ni
eventos del `AudioPlayer`). El archivo se busca en `assets/audio/` por el nombre
almacenado en la columna `audio_file` del CSV. Si no se encuentra, el replay
continua sin audio con un aviso en consola.

Los eventos del `AudioPlayer` se descartan mientras hay un replay activo para
evitar interferencias con el estado de sesion.

### 5.5 Timing

`ReplayReader` almacena todos los frames con su tiempo relativo (segundos desde
el primer frame). En cada llamada a `update()` calcula:

```
elapsed = elapsed_at_pause + (monotonic() - start_mono) * speed
```

y avanza el puntero hasta el frame cuyo `rel_t <= elapsed`. No usa `sleep()`;
el avance ocurre en el mismo thread del loop principal a 60 FPS.

---

## 6. Decisiones de diseno

| Decision | Eleccion | Razon |
|----------|----------|-------|
| Seleccion de CSV | Modal en la UI (no CLI) | Mas accesible; no requiere recordar rutas |
| Audio | `sounddevice` directo, sin countdown | Inicio inmediato, sin interferir con el estado de sesion |
| Fin del replay | Pausa en ultimo frame, sin salida automatica | El investigador puede observar el estado final antes de salir |
| Fuente de datos | Duck-typing (`active_reader`) | `main.py` no necesita ramas `if replay_mode` para el render |
| Cambio de color | Acento + fondo OpenGL | Diferenciacion visual inmediata sin modificar la estructura del HUD |

---

## 7. Criterios de aceptacion

- [x] Boton "Abrir Replay..." en el panel lateral abre el modal de seleccion.
- [x] El modal lista los CSVs de `logs/` ordenados de mas reciente a mas antiguo.
- [x] Al confirmar, el modelo 3D reproduce la orientacion del CSV frame a frame.
- [x] Los widgets de senales (PPG, GSR) muestran los valores del CSV en tiempo real.
- [x] Play/pausa funciona con el boton y con la tecla `Espacio`.
- [x] Los tres modos de velocidad (0.5x, 1x, 2x) son funcionales en caliente.
- [x] La barra de progreso muestra el tiempo transcurrido y total.
- [x] Al llegar al final, el replay queda pausado en el ultimo frame (no sale solo).
- [x] `ESC`, boton "Salir" y "Salir del Replay" salen del modo sin errores.
- [x] Si el WAV no se encuentra, el replay continua sin audio con aviso en consola.
- [x] El acento de la UI cambia a purpura al entrar y se restaura al salir.
- [x] No se inicia ninguna sesion de logging durante el replay.
