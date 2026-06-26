"""Lector de sesiones CSV para reproduccion de sesiones grabadas sin hardware."""

import csv
import os
import time
from datetime import datetime


class ReplayReader:
    """Reproduce una sesion grabada en CSV, exponiendo la misma interfaz que SerialReader.

    El caller debe invocar update() en cada frame del loop principal para avanzar
    la posicion de reproduccion segun el tiempo real y la velocidad configurada.
    """

    def __init__(self, csv_path: str):
        """
        Args:
            csv_path: Ruta absoluta al archivo CSV de sesion a reproducir.

        Raises:
            ValueError: Si el CSV no contiene filas con estado 'record' o no tiene
                columnas de quaternion validas.
            OSError: Si el archivo no puede abrirse.
        """
        self._path = csv_path
        self._frames: list = []
        self._total_s: float = 0.0
        self._audio_file: str = ""
        self._participant_name: str = ""

        self._playing: bool = False
        self._speed: float = 1.0
        self._start_mono: float = 0.0
        self._elapsed_at_pause: float = 0.0

        self._quat: tuple = (1.0, 0.0, 0.0, 0.0)
        self._signals: dict = {}
        self._current_idx: int = 0
        self._done: bool = False
        self._recent_t: list = []

        self._parse(csv_path)

    def _parse(self, path: str):
        """Parsea el CSV y construye la lista de frames ordenados por tiempo relativo.

        Solo procesa filas con estado 'record'. Cada frame puede contener datos de
        quaternion, de senales, o ambos, segun lo que haya en esa fila.

        Args:
            path: Ruta absoluta al archivo CSV.

        Raises:
            ValueError: Si no hay filas validas para reproducir.
        """
        with open(path, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("estado") == "record"]

        if not rows:
            raise ValueError("El CSV no contiene filas con estado 'record'.")

        self._audio_file = rows[0].get("audio_file", "")
        self._participant_name = rows[0].get("participant_name", "")

        _fixed = {"timestamp", "participant_name", "session_id",
                  "audio_file", "estado", "qw", "qx", "qy", "qz"}

        t0 = datetime.fromisoformat(rows[0]["timestamp"])
        frames = []
        for row in rows:
            try:
                rel_t = (datetime.fromisoformat(row["timestamp"]) - t0).total_seconds()
            except Exception:
                continue

            quat = None
            if row.get("qw") not in ("", None):
                try:
                    quat = (float(row["qw"]), float(row["qx"]),
                            float(row["qy"]), float(row["qz"]))
                except (ValueError, KeyError):
                    pass

            signals = {}
            for key, value in row.items():
                if key in _fixed or value in ("", None):
                    continue
                try:
                    signals[key] = float(value)
                except ValueError:
                    pass

            frames.append({"rel_t": rel_t, "quat": quat, "signals": signals})

        if not frames:
            raise ValueError("No se pudieron parsear frames validos del CSV.")

        self._frames = frames
        self._total_s = max(frames[-1]["rel_t"], 1.0)

    # ---- Controles de transporte ----

    def play(self):
        """Inicia o reanuda la reproduccion. Si ya termino, reinicia desde el principio."""
        if self._done:
            self._done = False
            self._current_idx = 0
            self._elapsed_at_pause = 0.0
            self._quat = (1.0, 0.0, 0.0, 0.0)
            self._signals = {}
            self._recent_t = []
        self._start_mono = time.monotonic()
        self._playing = True

    def pause(self):
        """Pausa la reproduccion conservando la posicion actual."""
        if self._playing:
            self._elapsed_at_pause += (time.monotonic() - self._start_mono) * self._speed
            self._playing = False

    def toggle_play(self):
        """Alterna entre reproduccion y pausa."""
        if self._playing:
            self.pause()
        else:
            self.play()

    def set_speed(self, speed: float):
        """Cambia la velocidad de reproduccion en caliente sin perder la posicion.

        Args:
            speed: Factor de velocidad (ej. 0.5, 1.0, 2.0).
        """
        if self._playing:
            self._elapsed_at_pause += (time.monotonic() - self._start_mono) * self._speed
            self._start_mono = time.monotonic()
        self._speed = speed

    def update(self):
        """Avanza el puntero de reproduccion segun el tiempo real transcurrido.

        Debe llamarse una vez por frame en el loop principal. Actualiza el quaternion
        y las senales al estado correspondiente al tiempo actual del replay.
        """
        if not self._playing or self._done:
            return

        elapsed = self._elapsed_at_pause + (time.monotonic() - self._start_mono) * self._speed

        if elapsed >= self._total_s:
            self._playing = False
            self._done = True
            elapsed = self._total_s

        while (self._current_idx < len(self._frames) - 1 and
               self._frames[self._current_idx + 1]["rel_t"] <= elapsed):
            self._current_idx += 1
            frame = self._frames[self._current_idx]
            if frame["quat"] is not None:
                self._quat = frame["quat"]
            if frame["signals"]:
                self._signals.update(frame["signals"])
            self._recent_t.append(time.monotonic())
            if len(self._recent_t) > 60:
                self._recent_t.pop(0)

    # ---- Interfaz compatible con SerialReader ----

    def get_imu(self) -> tuple:
        """Devuelve el ultimo quaternion del replay en el mismo formato que SerialReader.

        Returns:
            Tupla (quat, euler) donde quat=(qw, qx, qy, qz) y euler=(0, 0, 0)
            (el euler no se almacena en el CSV).
        """
        return self._quat, (0.0, 0.0, 0.0)

    def get_signals(self) -> dict:
        """Devuelve las ultimas senales del replay.

        Returns:
            Diccionario {clave: valor_float} con el estado actual de las senales.
        """
        return dict(self._signals)

    def rate_hz(self) -> float:
        """Tasa de actualizacion efectiva del replay en Hz.

        Returns:
            Hz calculados sobre los ultimos 60 avances de frame, o 0.0 si hay pocos datos.
        """
        if len(self._recent_t) < 2:
            return 0.0
        dt = self._recent_t[-1] - self._recent_t[0]
        return (len(self._recent_t) - 1) / dt if dt > 0 else 0.0

    def stop(self):
        """Detiene la reproduccion (compatibilidad con la interfaz de SerialReader)."""
        self._playing = False

    # ---- Propiedades de estado ----

    @property
    def elapsed_s(self) -> float:
        """Segundos transcurridos de reproduccion (ajustados por velocidad)."""
        if self._playing:
            return min(
                self._elapsed_at_pause + (time.monotonic() - self._start_mono) * self._speed,
                self._total_s,
            )
        return min(self._elapsed_at_pause, self._total_s)

    @property
    def total_s(self) -> float:
        """Duracion total de la sesion en segundos."""
        return self._total_s

    @property
    def done(self) -> bool:
        """True cuando la reproduccion llego al final del CSV."""
        return self._done

    @property
    def playing(self) -> bool:
        """True si esta reproduciendo actualmente."""
        return self._playing

    @property
    def speed(self) -> float:
        """Factor de velocidad actual."""
        return self._speed

    @property
    def audio_file(self) -> str:
        """Nombre del archivo de audio de la sesion original."""
        return self._audio_file

    @property
    def participant(self) -> str:
        """Nombre del participante de la sesion original."""
        return self._participant_name

    # ---- Compatibilidad de atributos con SerialReader ----

    @property
    def connected(self) -> bool:
        """Siempre True: en replay el sensor virtual siempre esta disponible."""
        return True

    @property
    def port(self) -> str:
        """Nombre del archivo CSV, usado en la barra de estado."""
        return os.path.basename(self._path)

    @property
    def baud(self) -> int:
        """Siempre 0 en modo replay."""
        return 0
