# Visualizador IMU Biometrico

Aplicacion de escritorio (Python 3.12, Windows) para un proyecto de artes visuales sobre
percepcion del sonido y biometrias fisiologicas. Captura datos en tiempo real desde una
placa XIAO nRF52840 + sensor IMU BNO085, visualiza la orientacion en 3D mediante
quaterniones (sin gimbal lock), reproduce estimulos sonoros WAV y registra los datos
biometricos en CSV para analisis posterior.

## Instalacion

```
cd imu_visualizer
python3 -m pip install -r requirements.txt
```

> En algunos sistemas (varias instalaciones de Python, `pip` apuntando a un entorno
> distinto al de `python3`) usar `pip install -r requirements.txt` puede instalar las
> dependencias en el entorno equivocado. Usar `python3 -m pip install -r requirements.txt`
> asegura que se instalen en el mismo interprete con el que luego se ejecuta `main.py`.

## Uso

```
python3 main.py
```

Al arrancar:
- Se crean automaticamente las carpetas `assets/models/`, `assets/audio/` y `logs/` si no existen.
- Si `config.json` no existe, se copia desde `config.example.json`.
- Si `assets/models/cabeza.obj` no existe, se genera un cubo placeholder (1.2 x 0.7 x 0.15).
- Se intenta autodetectar el puerto serial de la placa (XIAO/nRF52/Seeed). Si hay
  ambiguedad, se imprime en consola la lista de puertos disponibles.
- Tambien se puede forzar el puerto manualmente: `python main.py COM11`.

### Probar sin el sistema embebido

`scripts/simulate_embedded.py` simula la placa enviando paquetes IMU y senales
(PPG, GSR, TEMP) con valores aleatorios dentro de rangos configurables. Requiere un
par de puertos serie virtuales (p.ej. con [com0com](https://com0com.sourceforge.net/)
en Windows):

```
python scripts/simulate_embedded.py COM10
python imu_visualizer/main.py COM11
```

### Controles de teclado

| Tecla | Accion |
|-------|--------|
| `R`   | Centrar orientacion (zero-out) |
| `Tab` | Expandir / colapsar el panel lateral |
| `ESC` | Salir (pide confirmacion si hay una sesion activa) |

### Flujo de sesion

1. Selecciona un archivo `.wav` en el panel lateral izquierdo.
2. Pulsa **▶ REPRODUCIR** (habilitado solo con un WAV seleccionado y sin sesion activa).
3. Ingresa el nombre del participante en el dialogo modal y confirma.
4. Cuenta regresiva "Preparando..." (`countdown_pre_s`), reproduccion del audio,
   cuenta regresiva "Finalizando..." (`countdown_post_s`).
5. Al finalizar (o con **■ ABORTAR**) se cierra el archivo CSV de la sesion.

## Configuracion (`config.json`)

| Clave | Descripcion |
|-------|-------------|
| `baud_rate` | Baudrate del puerto serial. |
| `countdown_pre_s` / `countdown_post_s` | Duracion (segundos) de las cuentas regresivas previa/posterior a la reproduccion. |
| `sparkline_window_size` | Cantidad de puntos mostrados en los sparklines de PPG/GSR. |
| `panel_alpha` | Transparencia (0-1) del panel lateral. |
| `active_camera_profile` | Perfil de camara activo (ver `camera_profiles`). |
| `camera_profiles` | Diccionario de perfiles. Cada perfil define `pitch_sign`, `yaw_sign`, `roll_sign` (multiplicadores de eje, ±1) y `offset_deg: [pitch, yaw, roll]` (rotacion adicional aplicada como quaternion al presionar `R`). |
| `known_signals` | Senales fisiologicas con widget dedicado en el HUD (icono y color). Por defecto `PPG` y `GSR`. |
| `imu_packet_prefix` | Prefijo de las lineas seriales que contienen el paquete IMU (por defecto `IMU`). |
| `ui` | Colores (`bg_color`, `accent_color`, `text_color`), fuente (`font_family`) y tamano de ventana (`window_width`, `window_height`). |
| `model_path` | Ruta relativa al modelo OBJ a renderizar. |
| `model_pivot_offset` | Desplazamiento `[x, y, z]` del punto de rotacion respecto al centro del bounding box del modelo (en las mismas unidades del OBJ, ya autocentrado). Util para mover el origen al punto donde va el sensor (p.ej. la parte de atras de la cabeza). |
| `audio_folder` | Carpeta donde se buscan los archivos `.wav`. |
| `logs_folder` | Carpeta donde se escriben los CSV de sesion. |
| `log_flush_interval_s` | Intervalo (segundos) de flush a disco del CSV. |

## Protocolo serial esperado

Cada linea recibida por el puerto serial puede ser de dos tipos:

- **Paquete IMU**: `IMU:qw,qx,qy,qz,roll,pitch,yaw` (el prefijo es configurable via
  `imu_packet_prefix`). Ejemplo:
  ```
  IMU:0.999,0.01,-0.02,0.003,1.2,-0.5,45.3
  ```
- **Senal fisiologica/comportamental**: `CLAVE:VALOR`, donde `CLAVE` es un identificador
  arbitrario y `VALOR` es numerico. Se soportan entre 1 y 20 senales distintas. Ejemplos:
  ```
  PPG:89.45
  GSR:0.032
  ```

Lineas que comienzan con `#` se imprimen en consola como mensajes de depuracion de la placa.

## Esquema de columnas del CSV

Cada sesion genera `logs/{participante}_{YYYYMMDD_HHMMSS}.csv` con columnas:

- **Fijas**: `timestamp`, `participant_name`, `session_id`, `audio_file`, `estado`
  (`waiting` durante las cuentas regresivas, `record` durante la reproduccion).
- **Dinamicas**: `qw`, `qx`, `qy`, `qz` y cualquier clave de senal recibida
  (`PPG`, `GSR`, etc.). Las columnas se descubren automaticamente a medida que llegan
  datos nuevos; las filas anteriores quedan con celdas vacias para columnas no observadas
  en ese instante.

## Reemplazar el modelo 3D

1. Exporta tu modelo de cabeza a formato OBJ (vertices `v`, normales `vn` y caras `f`
   trianguladas o cuadrangulares).
2. Sobrescribe `assets/models/cabeza.obj` con tu archivo (o cambia `model_path` en
   `config.json` para apuntar a otra ruta).
3. Si el archivo no se puede cargar, la aplicacion usa automaticamente un cubo
   placeholder y muestra el aviso "MODELO PLACEHOLDER" en la barra de estado.

### Ajustar escala y tamano de archivo de un OBJ propio

El placeholder mide ~1.2 x 0.7 x 0.15 unidades y la camara esta a distancia fija
(`glTranslatef(0, -0.3, -5.5)`, `gluPerspective` con near/far 0.1/50.0). Si tu modelo
viene de un escaneo 3D o de otra escena, es probable que tenga una escala muy distinta
(decenas de unidades) y/o demasiados poligonos para el pipeline OpenGL legacy
(`glBegin/glEnd`), lo que ralentiza la app.

Antes de usarlo:

1. **Medir el bounding box**: usa [3dviewer.net](https://3dviewer.net) para ver las
   dimensiones X/Y/Z y el conteo de vertices/triangulos de tu OBJ.
2. **Escalar**: si la dimension mas grande es muy distinta de ~1.5 unidades, escala el
   modelo con [ilove3dm.com/en/scale-model](https://ilove3dm.com/en/scale-model) usando
   un factor `1.5 / dimension_mas_grande` (por ejemplo, si tu modelo mide 19 unidades
   de alto, usa un factor ~0.08).
3. **Reducir el tamano del archivo**: si el OBJ pesa varios MB (decenas de miles de
   vertices/caras), comprimelo con
   [3dencoder.com/model-to-small](https://3dencoder.com/model-to-small)
   para reducir el conteo de poligonos. Apunta a unos pocos miles de triangulos
   (idealmente < 10,000) para mantener los 60 FPS, ya que el render no usa VBOs.
4. Coloca el archivo resultante en `assets/models/` y actualiza `model_path` en
   `config.json` (y en `config.example.json` si quieres que sea el default del
   proyecto).

> **Nota sobre el centrado**: no es necesario centrar el modelo manualmente antes de
> importarlo. La aplicacion autocentra cualquier OBJ cargado en el origen (recalcula
> el centro del bounding box al leer el archivo), independientemente de donde haya
> quedado la geometria tras escalarlo/comprimirlo. Si quieres mover el punto de
> rotacion (por ejemplo, al lugar de la cabeza donde va el sensor en vez del centro
> geometrico), usa `model_pivot_offset` en `config.json`.
