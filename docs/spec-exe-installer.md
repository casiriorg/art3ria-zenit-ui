# Spec: Exportacion a .exe con PyInstaller

## 1. Motivacion

La app corre hoy como script Python (`python main.py`), lo que requiere que quien la use
tenga Python 3.12 y las dependencias de `requirements.txt` instaladas. Para instalaciones
de arte/exhibicion (laptop dedicada, sin perfil tecnico a cargo) hace falta un `.exe`
autocontenido que se pueda copiar a cualquier Windows y ejecutar sin instalar nada mas.

Casos de uso principales:
- Llevar la app a una laptop de sala/exhibicion sin configurar entorno Python.
- Distribuir una version "congelada" a colaboradores para pruebas sin pedirles setup.

---

## 2. Alcance

### Incluido (v1)

- Empaquetado con **PyInstaller** en modo `--onedir` (carpeta con `.exe` + dependencias).
- El `.exe` funciona con y sin hardware conectado (mismo comportamiento que hoy).
- `config.json`, `logs/` y `assets/audio/` persisten junto al `.exe`, no en una carpeta
  temporal que se borra entre ejecuciones.
- Bundling de `config.example.json`, `assets/models/`, `assets/audio/test_tone.wav`.
- Icono del ejecutable (opcional, cosmetico).

### Excluido (v1)

- Instalador MSI/NSIS con wizard de instalacion. Se distribuye la carpeta `--onedir`
  (zip) directamente; evaluar instalador en una v2 si hace falta un icono de escritorio
  o entrada en "Agregar o quitar programas".
- Firma de codigo (code signing). El `.exe` no firmado disparara advertencias de
  SmartScreen en maquinas ajenas ("Mas info" -> "Ejecutar de todas formas"); aceptable
  para v1, revisar si se vuelve friccion real en la exhibicion.
- Modo `--onefile`. Se descarta para v1 (ver seccion 4.1).
- Auto-actualizacion del `.exe`.

---

## 3. Cambio de codigo requerido (bloqueante)

`config.py` calcula la raiz del proyecto asi:

```python
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

Bajo PyInstaller, `__file__` de los modulos empacados resuelve dentro del bundle, no
junto al `.exe` real. Ademas hay que distinguir dos carpetas distintas cuando la app
esta empaquetada:

- **Datos persistentes/editables** (`config.json`, `logs/`, WAVs que el usuario agrega
  en `assets/audio/`): deben vivir junto al `.exe` real (`sys.executable`) para
  sobrevivir entre ejecuciones y ser faciles de encontrar/editar.
- **Recursos de solo lectura que trae el bundle** (`config.example.json`, el modelo 3D
  por defecto, `test_tone.wav`): PyInstaller los extrae en `sys._MEIPASS`. **Esto NO es
  la misma carpeta que el `.exe`**: en `--onefile` es un temp dir que cambia en cada
  corrida; en `--onedir` con PyInstaller 6+ es la subcarpeta `_internal/` (el
  "contents directory" nuevo desde 6.0), no el nivel donde esta `art3ria.exe`. Asumir
  que ambas coinciden en `--onedir` fue el bug real detectado en el primer build (ver
  seccion 6.1): `config.example.json` no se encontraba porque quedo dentro de
  `_internal/` y el codigo buscaba junto al `.exe`.

`config.py` resuelve esto con dos variables:

```python
import sys

if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)          # persistente, junto al .exe
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", _BASE_DIR)     # solo lectura, del bundle
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _BASE_DIR
```

`_DEFAULT_PATH` (`config.example.json`) se resuelve contra `_BUNDLE_DIR`; `_CONFIG_PATH`
(`config.json`) sigue resolviendose contra `_BASE_DIR`, igual que `logs_folder` y
`audio_folder` via `abs_path()`.

Como el modelo 3D por defecto y `test_tone.wav` tambien viven solo en `_BUNDLE_DIR`
pero se acceden despues via `abs_path()` (que apunta a `_BASE_DIR`), `ensure_dirs()`
ademas copia esos dos archivos junto al `.exe` la primera vez que faltan ahi (mismo
patron que ya existia para `config.json` -> `config.example.json`, ver `_load()`):

```python
def ensure_dirs():
    for rel in (os.path.dirname(CFG.model_path), CFG.audio_folder, CFG.logs_folder):
        os.makedirs(os.path.join(_BASE_DIR, rel), exist_ok=True)
    if _BUNDLE_DIR != _BASE_DIR:
        _copy_bundled_defaults()  # modelo 3D y test_tone.wav, si no existen ya


def _copy_bundled_defaults():
    for rel in (CFG.model_path, os.path.join(CFG.audio_folder, "test_tone.wav")):
        src, dst = os.path.join(_BUNDLE_DIR, rel), os.path.join(_BASE_DIR, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
```

No pisa un modelo/audio que el usuario ya haya reemplazado junto al `.exe` (solo copia
si el destino no existe).

Esto es necesario **independientemente** del modo (`--onedir` u `--onefile`) porque
`sys.executable` es la unica ruta estable garantizada junto al `.exe` distribuido, y
`sys._MEIPASS` es la unica forma documentada de ubicar los recursos del bundle en
ambos modos. Este es el unico cambio de codigo necesario para que el empaquetado
funcione; el resto de este documento es configuracion de build, no cambios en la app.

---

## 4. Herramienta de empaquetado

### 4.1 Decision: PyInstaller `--onedir`

| Opcion | Veredicto |
|--------|-----------|
| **PyInstaller `--onedir`** | **Elegido.** Soporte especifico y maduro para pygame, PyOpenGL, sounddevice (hook incluido que bundlea el DLL de PortAudio) y pyserial. Arranque rapido, mas facil de debuggear (los archivos quedan visibles, no se auto-extraen a un temp dir en cada corrida). |
| PyInstaller `--onefile` | Descartado para v1. Un solo `.exe` es comodo para distribuir, pero se auto-extrae a un temp dir en cada arranque (mas lento) y el bug de `_BASE_DIR` de la seccion 3 es mas facil de reintroducir por error a futuro. Reconsiderar si se prioriza "un solo archivo" sobre performance/robustez. |
| Nuitka | Alternativa valida (compila a C, muchos menos falsos positivos de antivirus que el bootloader de PyInstaller). Requiere mas tuning manual para scipy/pygame. Usar como plan B si SmartScreen/AV se vuelve un problema real en la exhibicion. |
| cx_Freeze / Briefcase / PyOxidizer | Descartados: sin ventaja sobre PyInstaller para este stack, menos precedente con PyOpenGL+sounddevice. |

### 4.2 Dependencias de build

`pyinstaller>=6.0` esta declarado en `requirements.txt` (con un comentario aclarando
que es solo para build, no runtime) para que `pip install -r requirements.txt` lo
instale junto al resto. Instalar en el mismo entorno virtual que ya usa el proyecto
(ver `README.md`), no en un entorno separado, para que PyInstaller detecte las
versiones reales instaladas de pygame/PyOpenGL/sounddevice/scipy/numpy.

---

## 5. Archivo `.spec`

Generar con `pyi-makespec` y ajustar, o crear directamente `art3ria.spec` en la raiz
del proyecto (no versionar el `build/` ni `dist/` resultante):

```python
# art3ria.spec
a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config.example.json", "."),
        ("assets/models", "assets/models"),
        ("assets/audio/test_tone.wav", "assets/audio"),
    ],
    hiddenimports=[
        "OpenGL.platform.win32",
        "OpenGL.arrays.numpymodule",
        "scipy.io.wavfile",
    ],
    hookspath=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="art3ria",
    console=False,
    icon=None,  # ej. "assets/icon.ico" si se agrega uno
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="art3ria",
)
```

Notas sobre este spec:

- **`datas`**: no incluye `config.json` ni `logs/` — esos se generan/usan en runtime
  junto al `.exe` (ver seccion 3), no deben quedar congelados dentro del bundle.
  `assets/models/cabeza.obj` puede no existir en el repo (se autogenera un placeholder
  via `renderer.ensure_placeholder_obj`); si existe en el momento del build, se incluye
  igual porque `datas` apunta a toda la carpeta `assets/models`.
- **`hiddenimports`**: PyOpenGL carga bindings de plataforma dinamicamente via ctypes,
  lo que el analizador de PyInstaller no siempre traza solo; declarar
  `OpenGL.platform.win32` explicitamente evita el `ImportError` clasico al abrir la
  ventana OpenGL en el `.exe` (no ocurre corriendo con `python main.py` porque ahi el
  import es normal).
- **`console=False`**: sin consola visible detras de la ventana pygame (uso de
  exhibicion). Cambiar a `True` temporalmente si hace falta ver los `print()` de
  debug (deteccion de puerto, errores seriales) durante troubleshooting del build.
- **sounddevice**: no requiere entrada manual en `binaries`; el hook que trae la propia
  libreria bundlea el DLL de PortAudio. Verificar igual en el checklist (seccion 7).

---

## 6. Comando de build

Instalar PyInstaller en el mismo entorno virtual del proyecto (ya declarado en
`requirements.txt` como dependencia solo de build) y ejecutar el `.spec`:

```
python -m pip install -r requirements.txt
python -m PyInstaller art3ria.spec --clean
```

Resultado: `dist/art3ria/art3ria.exe` + carpeta `dist/art3ria/_internal/` con
dependencias y los `datas` declarados en el `.spec`. Para distribuir, comprimir la
carpeta `dist/art3ria/` completa (no solo el `.exe` — sin `_internal/` no arranca).
Ni `build/` ni `dist/` se versionan (ver `.gitignore`); `art3ria.spec` si se versiona.

Primera vez que se ejecuta el `.exe` en una maquina limpia: crea `config.json` (copia
de `config.example.json`), `logs/` y `assets/audio/` junto al `.exe`, igual que hoy
hace `config.py`/`config.ensure_dirs()` junto a `main.py`. Esto depende del fix de
`_BASE_DIR` de la seccion 3, ya aplicado en `config.py`.

### 6.1 Build verificado

Este build se corrio y genero el `.exe` correctamente con:

- Python 3.12.10 (entorno virtual del proyecto, `.venv/`).
- PyInstaller 6.22.2 (instalado via `requirements.txt`).
- `python -m PyInstaller art3ria.spec --clean` desde la raiz del repo.

Resultado: `dist/art3ria/art3ria.exe` (~10 MB) + `dist/art3ria/_internal/` (~134 MB),
carpeta total ~144 MB. Se confirmo que `config.example.json`, `assets/models/*.obj`
y `assets/audio/test_tone.wav` quedaron incluidos dentro de `_internal/` segun lo
declarado en `datas`.

Durante el analisis, PyInstaller emitio warnings de `MSVCR90.dll`/`MSVCR100.dll` no
resueltas para las DLLs de `freeglut`/`gle` que trae PyOpenGL (`OpenGL/DLLS/*.vc9.dll`,
`*.vc10.dll`). Son inofensivas: la app usa el pipeline legacy de OpenGL sin glut, esas
DLLs no se cargan en runtime.

**Primer intento de arranque fallo** con `FileNotFoundError: config.example.json` —
ver seccion 3 y la fila correspondiente en la seccion 8. Causa: PyInstaller 6+ anida
los `datas` del `--onedir` en `_internal/`, no junto al `.exe`; el fix original de
`_BASE_DIR` asumia que ambas carpetas coincidian. Se corrigio separando `_BASE_DIR`
(persistente, junto al `.exe`) de `_BUNDLE_DIR` (`sys._MEIPASS`, recursos del bundle)
en `config.py`, y se re-buildeo.

**Segundo build, verificado end-to-end de arranque:** se ejecuto
`dist/art3ria/art3ria.exe` en background ~8 s y se confirmo que, junto al `.exe`
(no dentro de `_internal/`), se crearon correctamente: `config.json` (con el contenido
esperado de `config.example.json`), `logs/` (vacia), `assets/audio/test_tone.wav` y
`assets/models/female_head.obj` (copiados desde el bundle por `_copy_bundled_defaults`).
El proceso no crasheo ni escribio traceback en ese lapso.

**Pendiente (a cargo de quien retome este spec):** correr el checklist completo de la
seccion 7 contra `dist/art3ria/art3ria.exe` — en particular todo lo que requiere
interaccion visual/audio real (ventana renderizando, reproduccion de audio, datos de
IMU/GSR entrando por el simulador, grabacion de una sesion) no se valido todavia,
solo el arranque sin crash y la creacion de archivos.

---

## 7. Checklist de verificacion post-build

Correr `dist/art3ria/art3ria.exe` (no `python main.py`) y confirmar:

- [ ] La ventana abre y el modelo 3D (o el cubo placeholder) se renderiza sin
      `ImportError` de OpenGL en consola/log.
- [ ] Sin hardware conectado, la app arranca igual mostrando "sin conexion" (no crashea).
- [ ] `config.json`, `logs/` y `assets/audio/` aparecen junto al `.exe`, no en un temp dir.
- [ ] Reproduccion de `assets/audio/test_tone.wav` suena (valida el DLL de PortAudio).
- [ ] Con `scripts/simulate_embedded.py --tcp 9000` corriendo desde una consola Python
      normal (el simulador NO se empaqueta, es herramienta de desarrollo) y apuntando
      el `.exe` a `socket://127.0.0.1:9000` via acceso directo con argumento, se ve
      orientacion IMU y las senales PPG/GSR/TEMP actualizandose en el HUD.
- [ ] Grabar una sesion corta y confirmar que el CSV se escribe en `logs/` junto al
      `.exe` con las columnas dinamicas esperadas (incluye `GSR`, `GSR_raw`,
      `GSR_variacion`).
- [ ] Cerrar la app durante una grabacion (o via Task Manager) y confirmar que el CSV
      parcial quedo en disco (valida el flush periodico + `CSVLogger.join()` no roto
      por el empaquetado).
- [ ] Probar en una segunda maquina Windows sin Python instalado (el objetivo real de
      este spec) para descartar dependencias que solo estaban "por casualidad" en el
      entorno de desarrollo.

---

## 8. Problemas conocidos / troubleshooting

| Sintoma | Causa probable | Solucion |
|---------|-----------------|----------|
| `ImportError: OpenGL.platform.win32` al abrir la ventana | Hidden import faltante | Confirmar que esta en `hiddenimports` del `.spec` (seccion 5). |
| No suena ningun audio, sin error visible | DLL de PortAudio no bundleado | Actualizar `sounddevice` a una version reciente con hook de PyInstaller incluido; si persiste, agregar el DLL manualmente a `binaries`. |
| `config.json`/`logs/` no aparecen junto al `.exe`, o se resetean cada corrida | Falta el fix de `_BASE_DIR` (seccion 3) | Aplicar el cambio en `config.py` antes de buildear. |
| `FileNotFoundError: ...config.example.json` al arrancar el `.exe` (visto en el primer build de este spec) | `_BASE_DIR` apuntaba junto al `.exe`, pero PyInstaller 6+ extrae los `datas` del `--onedir` en `_internal/`, no ahi | Ya corregido en `config.py`: `config.example.json` se busca en `_BUNDLE_DIR` (`sys._MEIPASS`), no en `_BASE_DIR` (seccion 3). Si reaparece, confirmar que no se este leyendo `_DEFAULT_PATH`/`_CONFIG_PATH` con la variable equivocada. |
| El modelo 3D por defecto no aparece (cae al cubo placeholder) o `test_tone.wav` no se encuentra, aun con el fix de `_BASE_DIR`/`_BUNDLE_DIR` aplicado | `ensure_dirs()` no llego a correr, o `_copy_bundled_defaults()` no encontro el archivo en `_BUNDLE_DIR` (revisar que el `.spec` los declare en `datas`, seccion 5) | Confirmar que `ensure_dirs()` se llama antes de `ObjModel()`/reproducir audio (en `main.py`, ya es el caso); revisar `dist/art3ria/_internal/assets/` tiene los archivos fuente. |
| SmartScreen bloquea el `.exe` en otra maquina | Binario sin firmar | Esperado sin code signing (fuera de alcance v1); indicar "Mas info -> Ejecutar de todas formas". Si es inaceptable para la exhibicion, evaluar Nuitka (seccion 4.1) o firma de codigo. |
| Antivirus especifico pone el `.exe` en cuarentena | Falso positivo del bootloader de PyInstaller (patron conocido por heuristicas de AV) | Excepcion manual en el AV de la maquina de exhibicion, o migrar a Nuitka si se repite en varias maquinas. |
| Tamano de la carpeta `dist/art3ria/` es grande (~150-300 MB) | Normal para este stack (numpy + scipy + pygame + OpenGL) | No es un bug; comprimir para distribuir. |
| Warnings de `MSVCR90.dll`/`MSVCR100.dll` no resueltas durante el build (`freeglut*.dll`, `gle*.dll`) | DLLs opcionales de glut que trae PyOpenGL, no usadas por el pipeline legacy de este proyecto | Ignorar; no afecta el build ni el `.exe` (confirmado en la seccion 6.1). |

---

## 9. Fuera de alcance / futuro

- Instalador con icono de escritorio y entrada en el menu de Windows (NSIS/Inno Setup)
  si se necesita una instalacion mas "formal" para exhibiciones publicas recurrentes.
- Firma de codigo si la friccion de SmartScreen resulta un problema en la practica.
- Evaluar migracion a Nuitka si los falsos positivos de antivirus bloquean la
  distribucion en maquinas de terceros.
