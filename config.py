"""Carga, valida y expone la configuracion activa de la aplicacion (objeto CFG)."""

import json
import os
import shutil
import sys

if getattr(sys, "frozen", False):
    # Empaquetado con PyInstaller: __file__ resuelve dentro del bundle, no
    # junto al .exe. _BASE_DIR (sys.executable) es donde deben vivir los
    # archivos persistentes/editables (config.json, logs/, audio del usuario).
    # _BUNDLE_DIR (sys._MEIPASS) es donde PyInstaller deja los recursos de
    # solo lectura que trae el bundle (config.example.json, modelo 3D por
    # defecto, WAV de prueba) — en onedir NO es la misma carpeta que el .exe
    # (PyInstaller 6+ los anida en "_internal/" por defecto).
    _BASE_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", _BASE_DIR)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _BASE_DIR
_DEFAULT_PATH = os.path.join(_BUNDLE_DIR, "config.example.json")
_CONFIG_PATH = os.path.join(_BASE_DIR, "config.json")


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Combina recursivamente `overrides` sobre `defaults`, completando claves faltantes.

    Args:
        defaults: Diccionario base con todos los valores por defecto.
        overrides: Diccionario con valores que sobreescriben los defaults.

    Returns:
        Nuevo diccionario con todos los valores de defaults mas los cambios de overrides.
    """
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class _Config:
    """Singleton de configuracion con acceso por atributo o por indice.

    Envuelve un diccionario plano permitiendo acceder a las claves como
    atributos (cfg.baud_rate) o como indices (cfg["baud_rate"]).
    """

    def __init__(self, data: dict, path: str):
        """
        Args:
            data: Diccionario con los valores de configuracion ya fusionados.
            path: Ruta absoluta al archivo config.json activo.
        """
        self._data = data
        self.path = path

    def __getattr__(self, name):
        """Devuelve el valor de la clave `name` como si fuera un atributo.

        Args:
            name: Nombre de la clave de configuracion.

        Returns:
            Valor asociado a la clave.

        Raises:
            AttributeError: Si la clave no existe en el diccionario.
        """
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, key):
        """Devuelve el valor de la clave `key`.

        Args:
            key: Nombre de la clave de configuracion.

        Returns:
            Valor asociado a la clave.
        """
        return self._data[key]

    def get(self, key, default=None):
        """Devuelve el valor de la clave o `default` si no existe.

        Args:
            key: Nombre de la clave de configuracion.
            default: Valor a devolver si la clave no existe.

        Returns:
            Valor de la clave, o `default` si la clave no esta presente.
        """
        return self._data.get(key, default)

    def as_dict(self) -> dict:
        """Devuelve el diccionario de configuracion completo.

        Returns:
            Diccionario con todos los pares clave/valor de la configuracion activa.
        """
        return self._data


def _load() -> _Config:
    """Carga config.example.json como defaults, fusiona config.json encima y devuelve un _Config.

    Si config.json no existe, lo crea copiando config.example.json.

    Returns:
        Instancia _Config con la configuracion fusionada lista para usar.
    """
    with open(_DEFAULT_PATH, "r", encoding="utf-8") as f:
        defaults = json.load(f)

    if not os.path.exists(_CONFIG_PATH):
        shutil.copyfile(_DEFAULT_PATH, _CONFIG_PATH)

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        overrides = json.load(f)

    merged = _deep_merge(defaults, overrides)
    return _Config(merged, _CONFIG_PATH)


def ensure_dirs():
    """Crea las carpetas necesarias de la aplicacion si no existen.

    Crea assets/models/, CFG.audio_folder y CFG.logs_folder relativas
    a la raiz del proyecto. Si la app corre empaquetada (PyInstaller),
    tambien copia junto al .exe los recursos de solo lectura que trae el
    bundle (modelo 3D por defecto y WAV de prueba) la primera vez que no
    existen ahi, para que el comportamiento sea igual que corriendo el script.
    """
    for rel in (
        os.path.dirname(CFG.model_path),
        CFG.audio_folder,
        CFG.logs_folder,
    ):
        path = os.path.join(_BASE_DIR, rel)
        os.makedirs(path, exist_ok=True)

    if _BUNDLE_DIR != _BASE_DIR:
        _copy_bundled_defaults()


def _copy_bundled_defaults():
    """Copia junto al .exe los recursos de solo lectura empaquetados que falten.

    No hace nada si el archivo de origen no esta en el bundle o si el destino
    ya existe (para no pisar un modelo/audio que el usuario haya reemplazado).
    """
    for rel in (CFG.model_path, os.path.join(CFG.audio_folder, "test_tone.wav")):
        src = os.path.join(_BUNDLE_DIR, rel)
        dst = os.path.join(_BASE_DIR, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)


def abs_path(rel_path: str) -> str:
    """Convierte una ruta relativa del proyecto a ruta absoluta.

    Args:
        rel_path: Ruta relativa desde la raiz del proyecto.

    Returns:
        Ruta absoluta como string.
    """
    return os.path.join(_BASE_DIR, rel_path)


CFG = _load()
