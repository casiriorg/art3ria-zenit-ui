"""Thread lector serial: parsea paquetes IMU y senales fisiologicas/comportamentales."""

import queue
import threading
import time
from collections import deque

import serial
import serial.tools.list_ports

from config import CFG


def find_port():
    """Autodetecta el puerto USB de la placa XIAO/nRF52. Imprime la lista si hay ambiguedad."""
    keywords = ("nRF52", "Seeed", "XIAO", "USB Serial", "CDC", "usbmodem")
    usb_candidates = []
    for p in serial.tools.list_ports.comports():
        desc = f"{p.description} {p.manufacturer or ''} {p.product or ''} {p.device}"
        if any(k.lower() in desc.lower() for k in keywords):
            return p.device
        if p.vid is not None:
            usb_candidates.append(p.device)
    if len(usb_candidates) == 1:
        return usb_candidates[0]

    print("No se pudo autodetectar el puerto. Puertos disponibles:")
    for p in serial.tools.list_ports.comports():
        print(f"  {p.device}  -  {p.description}")
    return None


class SerialReader(threading.Thread):
    """Lee continuamente el puerto serial y expone el ultimo quaternion/euler y senales."""

    def __init__(self, port=None, baud=None, log_queue: queue.Queue = None):
        super().__init__(daemon=True)
        self.port = port if port is not None else find_port()
        self.baud = baud if baud is not None else CFG.baud_rate
        self.log_queue = log_queue if log_queue is not None else queue.Queue()

        self.lock = threading.Lock()
        self.quat = (1.0, 0.0, 0.0, 0.0)
        self.euler = (0.0, 0.0, 0.0)
        self.signals = {}

        self.connected = False
        self.stop_flag = False
        self._samples = deque(maxlen=60)

    def run(self):
        if self.port is None:
            print("[ERROR] No hay puerto serial disponible.")
            return
        try:
            # serial_for_url soporta puertos normales (COMx, /dev/ttyACMx) y
            # URLs especiales como socket://host:puerto (usado por
            # scripts/simulate_embedded.py --tcp para simular sin hardware).
            ser = serial.serial_for_url(self.port, self.baud, timeout=1)
            time.sleep(2)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            self.connected = True
            print(f"[OK] Conectado a {self.port} @ {self.baud}")
            prefix = CFG.imu_packet_prefix + ":"

            while not self.stop_flag:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("#"):
                    print(f"[XIAO] {line.lstrip('# ').strip()}")
                    continue

                if line.startswith(prefix):
                    self._parse_imu(line[len(prefix):])
                    continue

                if ":" in line:
                    self._parse_signal(line)
                    continue

                print(f"[XIAO] {line}")
        except serial.SerialException as e:
            print(f"[ERROR] Serial: {e}")
            self.connected = False

    def _parse_imu(self, payload: str):
        parts = payload.split(",")
        if len(parts) != 7:
            return
        try:
            qw, qx, qy, qz, r, p, y = (float(v) for v in parts)
        except ValueError:
            return
        with self.lock:
            self.quat = (qw, qx, qy, qz)
            self.euler = (r, p, y)
        self._samples.append(time.time())
        self.log_queue.put((time.time(), {"qw": qw, "qx": qx, "qy": qy, "qz": qz}))

    def _parse_signal(self, line: str):
        key, _, raw_value = line.partition(":")
        key = key.strip()
        try:
            value = float(raw_value.strip())
        except ValueError:
            return
        with self.lock:
            self.signals[key] = value
        self._samples.append(time.time())
        self.log_queue.put((time.time(), {key: value}))

    def get_imu(self):
        """Devuelve el ultimo (quat, euler) recibido."""
        with self.lock:
            return self.quat, self.euler

    def get_signals(self) -> dict:
        """Devuelve una copia del diccionario de senales fisiologicas/comportamentales."""
        with self.lock:
            return dict(self.signals)

    def rate_hz(self) -> float:
        """Tasa de actualizacion real medida en Hz."""
        if len(self._samples) < 2:
            return 0.0
        dt = self._samples[-1] - self._samples[0]
        return (len(self._samples) - 1) / dt if dt > 0 else 0.0

    def stop(self):
        self.stop_flag = True
