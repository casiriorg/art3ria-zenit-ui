# Zenit - Visualizador IMU/Biometricos

Aplicacion de escritorio para el proyecto de artes visuales **Zenit**. Lee datos en tiempo real
desde una placa electronica (XIAO nRF52840 + sensor IMU BNO085) conectada por USB, visualiza
la orientacion de la cabeza en 3D y registra las senales fisiologicas (PPG, GSR, etc.) en un
archivo CSV sincronizado con la reproduccion de audio.

---

## Indice

1. [Requisitos previos](#1-requisitos-previos)
2. [Instalacion](#2-instalacion)
3. [Ejecutar la aplicacion](#3-ejecutar-la-aplicacion)
   - [3.1 Con hardware conectado](#31-con-hardware-conectado)
   - [3.2 Sin hardware — modo exploracion](#32-sin-hardware--modo-exploracion)
   - [3.3 Con simulador integrado (TCP)](#33-con-simulador-integrado-tcp)
   - [3.4 Alternativa: puertos serie virtuales](#34-alternativa-puertos-serie-virtuales)
4. [Controles e interfaz](#4-controles-e-interfaz)
   - [4.1 Controles de teclado](#41-controles-de-teclado)
   - [4.2 Flujo de sesion](#42-flujo-de-sesion)
5. [Configuracion](#5-configuracion)
6. [Modelo 3D](#6-modelo-3d)
   - [6.1 Ajustar escala y rendimiento](#61-ajustar-escala-y-rendimiento)
7. [Referencia tecnica](#7-referencia-tecnica)
   - [7.1 Protocolo serial](#71-protocolo-serial)
   - [7.2 Esquema del CSV](#72-esquema-del-csv)
8. [Verificacion rapida](#8-verificacion-rapida)
9. [Compilar a .exe (Windows)](#9-compilar-a-exe-windows)

---

## 1. Requisitos previos

Antes de instalar, asegurate de tener:

- **Python 3.12** instalado. Podés verificarlo abriendo una terminal y ejecutando:
  ```
  python --version
  ```
  Si no lo tenés, descargalo desde [python.org](https://www.python.org/downloads/).
- **Windows 10 u 11** (la app no corre en macOS ni Linux).
- Conexion a internet la primera vez (para descargar las dependencias).

---

## 2. Instalacion

Abre una terminal en la carpeta del proyecto y ejecuta:

```
python -m pip install -r requirements.txt
```

Esto instala todas las librerias necesarias (OpenGL, PySerial, SoundDevice, etc.).

> **Por que `python -m pip` y no solo `pip`?**
> En algunos sistemas con varias versiones de Python instaladas, `pip` puede apuntar
> a una version distinta a la que usas para correr la app. Usar `python -m pip` garantiza
> que las dependencias se instalen en el mismo Python que vas a usar.

---

## 3. Ejecutar la aplicacion

### 3.1 Con hardware conectado

Conecta la placa por USB y ejecuta:

```
python main.py
```

La app detecta automaticamente el puerto USB de la placa. Si hay mas de uno disponible,
imprime la lista en consola y te pide que especifiques cual usar:

```
python main.py COM11
```

(Reemplaza `COM11` por el puerto que corresponda a tu placa.)

### 3.2 Sin hardware — modo exploracion

Podes correr la app sin tener la placa conectada. En ese caso la app arranca igual,
muestra "Sin conexion" en la barra de estado y te permite explorar la interfaz, el panel
lateral y reproducir el audio de prueba (`assets/audio/test_tone.wav`).

```
python main.py
```

### 3.3 Con simulador integrado (TCP)

Si queres probar el flujo completo (datos IMU + senales fisiologicas) sin tener el hardware,
podes usar el simulador incluido. Este genera datos falsos pero realistas y los envia a la
app como si fuera la placa real.

**Necesitas abrir dos terminales al mismo tiempo.**

**Terminal 1 — inicia el simulador:**
```
python scripts/simulate_embedded.py --tcp 9000
```

Vas a ver algo como:
```
[sim] Escuchando en 127.0.0.1:9000
[sim] Apunta la app a: socket://127.0.0.1:9000
[sim] Ctrl+C para detener.
```

**Terminal 2 — inicia la app apuntando al simulador:**
```
python main.py socket://127.0.0.1:9000
```

La app se conecta al simulador y empieza a recibir datos como si la placa estuviera enchufada.
Para detener el simulador, presiona `Ctrl+C` en la Terminal 1.

> **Que es el `9000`?** Es el numero de puerto de red que usa la comunicacion interna entre
> el simulador y la app. Podes usar cualquier numero entre 1024 y 65535 que no este ocupado.
> Si el 9000 da error, proba con 9001, 9002, etc.

### 3.4 Alternativa: puertos serie virtuales

Si preferis el metodo basado en puertos COM virtuales (requiere instalar
[com0com](https://com0com.sourceforge.net/)):

```
python scripts/simulate_embedded.py COM10
python main.py COM11
```

Este metodo es mas complejo de configurar; **se recomienda el modo TCP** de la seccion 3.3.

---

## 4. Controles e interfaz

### 4.1 Controles de teclado

| Tecla | Accion |
|-------|--------|
| `R`   | Centrar la orientacion (vuelve al punto de referencia) |
| `Tab` | Mostrar / ocultar el panel lateral |
| `ESC` | Salir (pide confirmacion si hay una sesion activa) |

### 4.2 Flujo de sesion

1. **Selecciona un archivo de audio** (`.wav`) en el panel lateral izquierdo.
2. **Pulsa "▶ REPRODUCIR"** — el boton aparece activo solo cuando hay un WAV seleccionado
   y no hay una sesion en curso.
3. **Ingresa el nombre del participante** en el cuadro de dialogo y confirma.
4. La app hace una cuenta regresiva ("Preparando..."), luego reproduce el audio y finalmente
   otra cuenta regresiva ("Finalizando...").
5. Al terminar (o al presionar **"■ ABORTAR"**), se cierra y guarda el archivo CSV de la sesion.

Los archivos CSV se guardan en la carpeta `logs/` con el formato
`{nombre_participante}_{YYYYMMDD_HHMMSS}.csv`.

---

## 5. Configuracion

La primera vez que corres la app se crea `config.json` a partir de `config.example.json`.
Podes editarlo con cualquier editor de texto (Bloc de notas, VS Code, etc.).

| Clave | Que hace |
|-------|----------|
| `baud_rate` | Velocidad de comunicacion con la placa (no cambiar salvo que el firmware lo requiera). |
| `countdown_pre_s` | Segundos de espera antes de que empiece el audio. |
| `countdown_post_s` | Segundos de espera despues de que termina el audio. |
| `sparkline_window_size` | Cuantos puntos historicos se muestran en los graficos de PPG/GSR. |
| `panel_alpha` | Transparencia del panel lateral (0 = invisible, 1 = solido). |
| `active_camera_profile` | Perfil de camara activo (define como se mapean los ejes del sensor al modelo 3D). |
| `camera_profiles` | Perfiles de camara disponibles. Cada uno define la orientacion inicial y la direccion de los ejes. |
| `known_signals` | Senales fisiologicas que aparecen con widget propio en la pantalla (icono y color). |
| `imu_packet_prefix` | Prefijo que identifica los paquetes de orientacion en el protocolo serial (por defecto `IMU`). |
| `ui` | Colores de la interfaz, fuente y tamano de ventana. |
| `model_path` | Ruta al modelo 3D de la cabeza (formato OBJ). |
| `model_pivot_offset` | Mueve el punto de rotacion del modelo (util si el sensor no esta en el centro de la cabeza). |
| `audio_folder` | Carpeta donde la app busca archivos `.wav`. |
| `logs_folder` | Carpeta donde se guardan los CSV. |
| `log_flush_interval_s` | Cada cuantos segundos se guarda el CSV a disco (protege datos si la app cierra de golpe). |

---

## 6. Modelo 3D

Por defecto la app muestra un cubo como placeholder. Para usar un modelo real:

1. Exporta tu modelo en formato **OBJ** (con vertices `v`, normales `vn` y caras `f`
   trianguladas o cuadrangulares).
2. Copia el archivo a `assets/models/` y renombralo `cabeza.obj` (o apunta a el con
   `model_path` en `config.json`).
3. Si el archivo no se puede cargar, la app vuelve al cubo placeholder y muestra el aviso
   "MODELO PLACEHOLDER" en pantalla.

### 6.1 Ajustar escala y rendimiento

Si el modelo viene de un escaneo 3D o de otro programa, probablemente tenga una escala muy
diferente a la esperada por la app (~1.5 unidades en la dimension mas grande) o demasiados
poligonos (lo que ralentiza el render).

Pasos para ajustarlo:

1. **Medir el tamano del modelo**: abrilo en [3dviewer.net](https://3dviewer.net) para
   ver sus dimensiones X/Y/Z y la cantidad de triangulos.
2. **Escalar**: si la dimension mas grande es muy diferente de ~1.5 unidades, escalalo en
   [ilove3dm.com/en/scale-model](https://ilove3dm.com/en/scale-model). El factor a usar es
   `1.5 / dimension_mas_grande` (ejemplo: si mide 19 unidades de alto, el factor es ~0.08).
3. **Reducir poligonos**: si el OBJ pesa varios MB o tiene mas de ~10.000 triangulos,
   comprimi la geometria con [3dencoder.com/model-to-small](https://3dencoder.com/model-to-small)
   para mantener los 60 FPS.
4. Coloca el archivo resultante en `assets/models/` y actualiza `model_path` en `config.json`.

> **El centrado es automatico.** No necesitas centrar el modelo antes de importarlo; la app
> lo autocentra al cargarlo. Si queres mover el punto de rotacion (por ejemplo, hacia donde
> va el sensor en la cabeza), usa `model_pivot_offset` en `config.json`.

---

## 7. Referencia tecnica

### 7.1 Protocolo serial

La app espera recibir lineas de texto por el puerto serie, de dos tipos:

**Paquete de orientacion IMU:**
```
IMU:qw,qx,qy,qz,roll,pitch,yaw
```
Ejemplo: `IMU:0.999,0.01,-0.02,0.003,1.2,-0.5,45.3`

**Senal fisiologica o comportamental (formato general):**
```
CLAVE:VALOR
```
Ejemplo:
```
PPG:89.45
```
`CLAVE` puede ser cualquier identificador de texto y `VALOR` debe ser numerico.
Se soportan entre 1 y 20 senales distintas por sesion.

**Senal GSR (caso especial, 3 valores):**
```
GSR:raw,filtrado,variacion
```
Ejemplo: `GSR:0.0315,0.0298,0.0012`

A diferencia de las demas senales, GSR siempre llega con 3 valores separados por coma:
la lectura cruda del sensor, la senal ya filtrada (pasabajos) y la variacion respecto
a la muestra filtrada anterior. La app expone esto como tres senales independientes:
`GSR` (valor filtrado, el que se muestra en el widget principal), `GSR_raw` y
`GSR_variacion` (ambas visibles en el panel de "Senales adicionales" y en el CSV).

Las lineas que comienzan con `#` se muestran en consola como mensajes de debug y son ignoradas por la app.

### 7.2 Esquema del CSV

Cada sesion genera un archivo en `logs/` con estas columnas:

| Columna | Descripcion |
|---------|-------------|
| `timestamp` | Fecha y hora del registro (ISO 8601). |
| `participant_name` | Nombre ingresado al iniciar la sesion. |
| `session_id` | Identificador unico de la sesion. |
| `audio_file` | Nombre del archivo de audio reproducido. |
| `estado` | `waiting` durante las cuentas regresivas, `record` durante la reproduccion. |
| `qw`, `qx`, `qy`, `qz` | Quaternion de orientacion del sensor IMU. |
| `roll`, `pitch`, `yaw` | Angulos Euler de orientacion (grados), derivados del mismo paquete IMU. |
| *(senales dinamicas)* | Una columna por cada senal recibida (`PPG`, `GSR`, `GSR_raw`, `GSR_variacion`, etc.). |

Las columnas de senales se crean automaticamente la primera vez que se recibe cada clave.
Las filas anteriores a ese momento quedan con celdas vacias en esa columna.

---

## 8. Verificacion rapida

Para comprobar que todos los modulos tienen sintaxis valida sin necesidad de ejecutar la app:

```
python -m py_compile config.py serial_reader.py audio_player.py logger.py renderer.py ui.py main.py
```

Si no aparece ningun mensaje de error, todos los modulos estan bien.

---

## 9. Compilar a .exe (Windows)

Se puede empaquetar la app como un `.exe` autocontenido (no requiere Python instalado
en la maquina de destino) usando **PyInstaller**. El detalle completo de esta decision,
el archivo `.spec`, el troubleshooting y las verificaciones ya corridas estan en
[`docs/spec-exe-installer.md`](docs/spec-exe-installer.md) — esta seccion resume los
pasos practicos para reproducir el build.

### 9.1 Requisitos

- Mismo entorno virtual del proyecto (seccion 2). `pyinstaller>=6.0` ya esta declarado
  en `requirements.txt` (marcado como dependencia solo de build, no se importa en
  runtime), asi que no hace falta instalarlo aparte.
- El archivo `art3ria.spec` en la raiz del repo (ya versionado) define que se empaqueta:
  entry point `main.py`, datos incluidos (`config.example.json`, `assets/models/`,
  `assets/audio/test_tone.wav`) y los hidden imports necesarios para PyOpenGL/scipy.

### 9.2 Build

```
python -m pip install -r requirements.txt
python -m PyInstaller art3ria.spec --clean
```

Si ya existe una build previa en `dist/art3ria/`, agregar `--noconfirm` para
sobreescribirla sin que PyInstaller pida confirmacion interactiva:

```
python -m PyInstaller art3ria.spec --clean --noconfirm
```

### 9.3 Resultado

El build genera `dist/art3ria/`, con:

- `art3ria.exe` — el ejecutable (~10 MB).
- `_internal/` — dependencias y recursos empaquetados (~130-140 MB).

**Para distribuir hay que copiar la carpeta `dist/art3ria/` completa**, no solo el
`.exe` — sin `_internal/` al lado no arranca. Ni `build/` ni `dist/` se versionan en
git (ver `.gitignore`); `art3ria.spec` si.

Al primer arranque en una maquina, el `.exe` crea junto a si mismo `config.json`,
`logs/` y `assets/audio/` (con `test_tone.wav` ya copiado adentro) y `assets/models/`
(con el modelo 3D por defecto ya copiado adentro) — mismo comportamiento que corriendo
`python main.py` en modo desarrollo.

### 9.4 Verificacion

Antes de dar por buena una build, correr `dist/art3ria/art3ria.exe` y confirmar al
menos: la ventana abre y renderiza, un WAV de prueba se reproduce (valida el DLL de
PortAudio), el simulador (seccion 3.3) alimenta datos IMU/senales correctamente, y una
sesion grabada genera un CSV valido en `logs/`. El checklist completo esta en la
seccion 7 de `docs/spec-exe-installer.md`.
