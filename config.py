"""Carga, valida y expone la configuracion activa de la aplicacion (objeto CFG)."""

import json
import os
import shutil

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(_BASE_DIR, "config.example.json")
_CONFIG_PATH = os.path.join(_BASE_DIR, "config.json")


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Combina recursivamente `overrides` sobre `defaults`, completando claves faltantes."""
    result = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class _Config:
    """Acceso de tipo atributo y diccionario a la configuracion cargada."""

    def __init__(self, data: dict, path: str):
        self._data = data
        self.path = path

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def as_dict(self) -> dict:
        return self._data


def _load() -> _Config:
    with open(_DEFAULT_PATH, "r", encoding="utf-8") as f:
        defaults = json.load(f)

    if not os.path.exists(_CONFIG_PATH):
        shutil.copyfile(_DEFAULT_PATH, _CONFIG_PATH)

    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        overrides = json.load(f)

    merged = _deep_merge(defaults, overrides)
    return _Config(merged, _CONFIG_PATH)


def ensure_dirs():
    """Crea las carpetas necesarias (assets/models, assets/audio, logs) si no existen."""
    for rel in (
        os.path.dirname(CFG.model_path),
        CFG.audio_folder,
        CFG.logs_folder,
    ):
        path = os.path.join(_BASE_DIR, rel)
        os.makedirs(path, exist_ok=True)


def abs_path(rel_path: str) -> str:
    """Convierte una ruta relativa del proyecto a ruta absoluta."""
    return os.path.join(_BASE_DIR, rel_path)


CFG = _load()
