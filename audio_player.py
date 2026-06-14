"""Thread de reproduccion de audio WAV no bloqueante usando sounddevice."""

import queue
import threading
import time

import sounddevice as sd
from scipy.io import wavfile

from config import CFG

POLL_INTERVAL_S = 0.05


class AudioPlayer(threading.Thread):
    """Reproduce archivos WAV con cuentas regresivas pre/post, controlable por comandos.

    Comandos (cmd_queue): ("PLAY", filepath), ("ABORT", None), ("EXIT", None)
    Eventos (event_queue): "COUNTDOWN_PRE", "PLAYING", "COUNTDOWN_POST", "DONE", "ABORTED"
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.cmd_queue: queue.Queue = queue.Queue()
        self.event_queue: queue.Queue = queue.Queue()
        self._abort_event = threading.Event()
        self._exit_flag = False

    def run(self):
        while not self._exit_flag:
            try:
                cmd, payload = self.cmd_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if cmd == "EXIT":
                self._exit_flag = True
                break
            elif cmd == "PLAY":
                self._abort_event.clear()
                self._play(payload)
            elif cmd == "ABORT":
                self._abort_event.set()
                sd.stop()
                self.event_queue.put(("ABORTED", None))

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Duerme hasta `seconds` en pasos cortos. Devuelve False si fue abortado."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._abort_event.is_set():
                return False
            time.sleep(min(POLL_INTERVAL_S, end - time.monotonic()))
        return True

    def _play(self, filepath: str):
        self.event_queue.put(("COUNTDOWN_PRE", CFG.countdown_pre_s))
        if not self._interruptible_sleep(CFG.countdown_pre_s):
            return

        try:
            samplerate, data = wavfile.read(filepath)
        except Exception as e:
            print(f"[ERROR] No se pudo cargar WAV: {e}")
            self.event_queue.put(("DONE", None))
            return

        self.event_queue.put(("PLAYING", None))
        sd.play(data, samplerate)

        duration = len(data) / float(samplerate)
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if self._abort_event.is_set():
                sd.stop()
                return
            if sd.get_stream() is not None and not sd.get_stream().active:
                break
            time.sleep(POLL_INTERVAL_S)
        sd.wait()

        if self._abort_event.is_set():
            return

        self.event_queue.put(("COUNTDOWN_POST", CFG.countdown_post_s))
        if not self._interruptible_sleep(CFG.countdown_post_s):
            return

        self.event_queue.put(("DONE", None))

    def play(self, filepath: str):
        """Encola la reproduccion del archivo WAV indicado."""
        self.cmd_queue.put(("PLAY", filepath))

    def abort(self):
        """Aborta la reproduccion en curso (<=100ms)."""
        self.cmd_queue.put(("ABORT", None))

    def exit(self):
        """Senaliza al thread que finalice."""
        self.cmd_queue.put(("EXIT", None))
