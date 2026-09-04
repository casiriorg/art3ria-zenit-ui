"""Thread de logging CSV con columnas dinamicas y flush periodico."""

import csv
import os
import queue
import threading
import time
from datetime import datetime

from config import CFG, abs_path

FIXED_COLUMNS = ["timestamp", "participant_name", "session_id", "audio_file", "estado"]


class CSVLogger(threading.Thread):
    """Registra muestras de sesion en un CSV cuyas columnas se descubren dinamicamente.

    Comandos (cmd_queue):
        ("START", participant_name, session_id, audio_file)
        ("DATA", timestamp_iso, estado, datos_dict)
        ("STOP",) / ("ABORT",)
        ("EXIT",)  -> termina el thread
    """

    def __init__(self):
        """Inicializa la cola de comandos y el estado interno del logger."""
        super().__init__(daemon=False)
        self.cmd_queue: queue.Queue = queue.Queue()
        self.summary_queue: queue.Queue = queue.Queue()
        self._exit_flag = False

        self._active = False
        self._rows = []
        self._fieldnames = list(FIXED_COLUMNS)
        self._extra_fields = set()
        self._meta = {}
        self._filepath = None
        self._last_flush = 0.0

    def run(self):
        """Bucle principal del thread: procesa comandos y hace flush periodico al CSV."""
        while not self._exit_flag:
            timeout = CFG.log_flush_interval_s
            try:
                item = self.cmd_queue.get(timeout=timeout)
            except queue.Empty:
                if self._active:
                    self._flush_to_disk()
                continue

            cmd = item[0]
            if cmd == "EXIT":
                if self._active:
                    self._flush_to_disk()
                self._exit_flag = True
            elif cmd == "START":
                _, participant_name, session_id, audio_file = item
                self._start(participant_name, session_id, audio_file)
            elif cmd == "DATA":
                _, timestamp_iso, estado, datos_dict = item
                self._append_row(timestamp_iso, estado, datos_dict)
            elif cmd in ("STOP", "ABORT"):
                summary = self._compute_summary()
                self._flush_to_disk()
                self._active = False
                self.summary_queue.put(summary)

    def _start(self, participant_name: str, session_id: str, audio_file: str):
        """Abre una nueva sesion: determina el nombre del CSV y reinicia el estado interno.

        Args:
            participant_name: Nombre del participante (usado en el nombre del archivo).
            session_id: UUID unico de la sesion.
            audio_file: Nombre del archivo de audio reproducido en la sesion.
        """
        os.makedirs(abs_path(CFG.logs_folder), exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{participant_name}_{stamp}.csv"
        self._filepath = os.path.join(abs_path(CFG.logs_folder), filename)
        self._meta = {
            "participant_name": participant_name,
            "session_id": session_id,
            "audio_file": audio_file,
        }
        self._rows = []
        self._fieldnames = list(FIXED_COLUMNS)
        self._extra_fields = set()
        self._active = True
        self._last_flush = time.monotonic()

    def _append_row(self, timestamp_iso: str, estado: str, datos_dict: dict):
        """Agrega una fila al buffer en memoria y hace flush si corresponde por tiempo.

        Si datos_dict contiene claves nuevas, expande los fieldnames del CSV.

        Args:
            timestamp_iso: Timestamp en formato ISO 8601.
            estado: Estado de la sesion ('waiting' o 'record').
            datos_dict: Diccionario con los datos de la muestra (quat, senales, etc.).
        """
        if not self._active:
            return
        row = {
            "timestamp": timestamp_iso,
            "estado": estado,
            **self._meta,
            **datos_dict,
        }
        new_keys = set(datos_dict.keys()) - self._extra_fields
        if new_keys:
            self._extra_fields |= new_keys
            self._fieldnames = list(FIXED_COLUMNS) + sorted(self._extra_fields)
        self._rows.append(row)

        if time.monotonic() - self._last_flush >= CFG.log_flush_interval_s:
            self._flush_to_disk()

    def _flush_to_disk(self):
        """Escribe todas las filas del buffer al archivo CSV en disco y actualiza el timestamp."""
        if self._filepath is None:
            return
        with open(self._filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames, restval="")
            writer.writeheader()
            writer.writerows(self._rows)
            f.flush()
        self._last_flush = time.monotonic()

    def _compute_summary(self) -> dict:
        """Calcula estadisticas de la sesion a partir de las filas acumuladas en memoria.

        Solo procesa filas con estado 'record'. Se llama desde el thread del logger
        antes de limpiar el buffer, por lo que no necesita sincronizacion adicional.

        Returns:
            Diccionario con claves: participant_name, audio_file, total_rows,
            record_rows, duration_s, imu_count, signals (dict con min/mean/max/count
            por senal), filepath.
        """
        if not self._rows:
            return {}

        record_rows = [r for r in self._rows if r.get("estado") == "record"]

        duration_s = 0.0
        if len(record_rows) >= 2:
            try:
                t0 = datetime.fromisoformat(record_rows[0]["timestamp"])
                t1 = datetime.fromisoformat(record_rows[-1]["timestamp"])
                duration_s = (t1 - t0).total_seconds()
            except Exception:
                pass

        _fixed = {"timestamp", "participant_name", "session_id",
                  "audio_file", "estado", "qw", "qx", "qy", "qz",
                  "roll", "pitch", "yaw"}
        signal_data: dict = {}
        for row in record_rows:
            for key, value in row.items():
                if key in _fixed:
                    continue
                if isinstance(value, (int, float)):
                    signal_data.setdefault(key, []).append(float(value))

        signal_stats = {
            key: {
                "mean": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
                "count": len(vals),
            }
            for key, vals in signal_data.items() if vals
        }

        return {
            "participant_name": self._meta.get("participant_name", ""),
            "audio_file": self._meta.get("audio_file", ""),
            "total_rows": len(self._rows),
            "record_rows": len(record_rows),
            "duration_s": duration_s,
            "imu_count": sum(1 for r in record_rows if "qw" in r),
            "signals": signal_stats,
            "filepath": self._filepath or "",
        }

    def start_session(self, participant_name: str, session_id: str, audio_file: str):
        """Encola el inicio de una nueva sesion de grabacion.

        Args:
            participant_name: Nombre del participante.
            session_id: UUID unico de la sesion.
            audio_file: Nombre del archivo de audio de la sesion.
        """
        self.cmd_queue.put(("START", participant_name, session_id, audio_file))

    def log(self, timestamp_iso: str, estado: str, datos_dict: dict):
        """Encola una muestra para ser registrada en el CSV.

        Args:
            timestamp_iso: Timestamp en formato ISO 8601.
            estado: Estado de la sesion en este instante ('waiting' o 'record').
            datos_dict: Datos de la muestra (ej. {'qw': 1.0, 'PPG': 89.4}).
        """
        self.cmd_queue.put(("DATA", timestamp_iso, estado, datos_dict))

    def stop(self):
        """Finaliza la sesion normalmente y escribe el CSV completo a disco."""
        self.cmd_queue.put(("STOP",))

    def abort(self):
        """Aborta la sesion y escribe a disco lo registrado hasta el momento."""
        self.cmd_queue.put(("ABORT",))

    def exit(self):
        """Senaliza al thread que finalice (llamar antes de join())."""
        self.cmd_queue.put(("EXIT",))
