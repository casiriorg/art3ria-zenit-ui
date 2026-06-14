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
        super().__init__(daemon=False)
        self.cmd_queue: queue.Queue = queue.Queue()
        self._exit_flag = False

        self._active = False
        self._rows = []
        self._fieldnames = list(FIXED_COLUMNS)
        self._extra_fields = set()
        self._meta = {}
        self._filepath = None
        self._last_flush = 0.0

    def run(self):
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
                self._flush_to_disk()
                self._active = False

    def _start(self, participant_name: str, session_id: str, audio_file: str):
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
        if self._filepath is None:
            return
        with open(self._filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._fieldnames, restval="")
            writer.writeheader()
            writer.writerows(self._rows)
            f.flush()
        self._last_flush = time.monotonic()

    def start_session(self, participant_name: str, session_id: str, audio_file: str):
        """Inicia una nueva sesion de grabacion."""
        self.cmd_queue.put(("START", participant_name, session_id, audio_file))

    def log(self, timestamp_iso: str, estado: str, datos_dict: dict):
        """Encola una muestra para ser registrada."""
        self.cmd_queue.put(("DATA", timestamp_iso, estado, datos_dict))

    def stop(self):
        """Finaliza la sesion actual, escribiendo el CSV completo."""
        self.cmd_queue.put(("STOP",))

    def abort(self):
        """Aborta la sesion actual, escribiendo lo registrado hasta el momento."""
        self.cmd_queue.put(("ABORT",))

    def exit(self):
        """Senaliza al thread que finalice (usado al cerrar la aplicacion)."""
        self.cmd_queue.put(("EXIT",))
