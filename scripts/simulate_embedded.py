"""Simulador de la placa embebida (XIAO nRF52840 + BNO085) para desarrollo sin hardware.

Escribe lineas con el mismo formato que espera `serial_reader.py`:

    IMU:qw,qx,qy,qz,roll,pitch,yaw
    PPG:valor
    GSR:valor
    TEMP:valor

La orientacion (roll/pitch/yaw) y cada senal fisiologica varian mediante un
"random walk" acotado a los rangos definidos en las constantes de este archivo.

Modo TCP (recomendado, no requiere drivers ni puertos virtuales):
    1. Ejecuta el simulador como servidor TCP local:
           python scripts/simulate_embedded.py --tcp 9000
    2. Apunta la app al socket en lugar de un puerto serial real:
           python main.py socket://127.0.0.1:9000

Modo puerto serial / virtual (com0com en Windows):
    1. Crea un par de puertos serie virtuales enlazados, p.ej. COM10 <-> COM11.
    2. Ejecuta:
           python scripts/simulate_embedded.py COM10
    3. Apunta la app al otro extremo del par:
           python main.py COM11

Uso:
    python scripts/simulate_embedded.py PUERTO [--baud BAUD]
    python scripts/simulate_embedded.py --tcp PUERTO_TCP [--host HOST]
"""

import argparse
import math
import random
import socket
import sys
import time

import serial

# ---------------------------------------------------------------------------
# Constantes de configuracion
# ---------------------------------------------------------------------------
BAUD_RATE = 115200

IMU_RATE_HZ = 30.0       # frecuencia de envio del paquete IMU
SIGNAL_RATE_HZ = 5.0     # frecuencia de envio de cada senal fisiologica

# Rangos y paso maximo del "random walk" para orientacion (grados)
EULER_RANGES_DEG = {
    "roll":  (-45.0, 45.0),
    "pitch": (-45.0, 45.0),
    "yaw":   (-180.0, 180.0),
}
EULER_STEP_DEG = 2.0

# Rangos y paso maximo del "random walk" para cada senal fisiologica/comportamental
SIGNAL_RANGES = {
    "PPG":  (55.0, 110.0),   # pulsaciones por minuto
    "GSR":  (0.01, 0.08),    # conductancia (uS)
    "TEMP": (35.5, 37.5),    # temperatura corporal (C)
}
SIGNAL_STEPS = {
    "PPG":  1.5,
    "GSR":  0.002,
    "TEMP": 0.05,
}

IMU_PACKET_PREFIX = "IMU"


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def random_walk(value: float, step: float, lo: float, hi: float) -> float:
    """Da un paso aleatorio acotado dentro de [lo, hi]."""
    return clamp(value + random.uniform(-step, step), lo, hi)


def euler_to_quat(roll_deg: float, pitch_deg: float, yaw_deg: float):
    """Convierte angulos Euler (grados) a quaternion (w,x,y,z)."""
    roll, pitch, yaw = (math.radians(a) for a in (roll_deg, pitch_deg, yaw_deg))

    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)

    return (
        cr*cp*cy + sr*sp*sy,
        sr*cp*cy - cr*sp*sy,
        cr*sp*cy + sr*cp*sy,
        cr*cp*sy - sr*sp*cy,
    )


# ---------------------------------------------------------------------------
# Simulacion
# ---------------------------------------------------------------------------
def simulation_loop(write):
    """Genera datos sin fin, invocando `write(bytes)` para cada linea cuando corresponde."""
    euler = {key: random.uniform(*rng) for key, rng in EULER_RANGES_DEG.items()}
    signals = {key: random.uniform(*rng) for key, rng in SIGNAL_RANGES.items()}

    next_imu = time.monotonic()
    next_signal = time.monotonic()

    while True:
        now = time.monotonic()

        if now >= next_imu:
            for key in euler:
                lo, hi = EULER_RANGES_DEG[key]
                euler[key] = random_walk(euler[key], EULER_STEP_DEG, lo, hi)

            qw, qx, qy, qz = euler_to_quat(euler["roll"], euler["pitch"], euler["yaw"])
            line = (
                f"{IMU_PACKET_PREFIX}:{qw:.5f},{qx:.5f},{qy:.5f},{qz:.5f},"
                f"{euler['roll']:.2f},{euler['pitch']:.2f},{euler['yaw']:.2f}\n"
            )
            write(line.encode("utf-8"))
            next_imu += 1.0 / IMU_RATE_HZ

        if now >= next_signal:
            for key in signals:
                lo, hi = SIGNAL_RANGES[key]
                signals[key] = random_walk(signals[key], SIGNAL_STEPS[key], lo, hi)
                write(f"{key}:{signals[key]:.4f}\n".encode("utf-8"))
            next_signal += 1.0 / SIGNAL_RATE_HZ

        time.sleep(0.001)


def run_serial(port: str, baud: int):
    print(f"[sim] Abriendo {port} @ {baud}...")
    with serial.Serial(port, baud, timeout=1) as ser:
        print("[sim] Enviando datos simulados. Ctrl+C para detener.")
        simulation_loop(ser.write)


def run_tcp(host: str, port: int):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(1)
    # Timeout de 1 s en accept() para que Ctrl+C pueda ser procesado en Windows.
    # Sin timeout, accept() bloquea indefinidamente y la consola se congela.
    srv.settimeout(1.0)
    print(f"[sim] Escuchando en {host}:{port}")
    print(f"[sim] Apunta la app a: socket://{host}:{port}")
    print("[sim] Ctrl+C para detener.")

    try:
        while True:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            print(f"[sim] Cliente conectado desde {addr}")
            try:
                with conn:
                    simulation_loop(conn.sendall)
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                print(f"[sim] Cliente desconectado ({e}). Esperando nueva conexion...")
    finally:
        srv.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("port", nargs="?", help="Puerto serial al que escribir (ej. COM10)")
    parser.add_argument("--baud", type=int, default=BAUD_RATE, help="Baudrate (default: %(default)s)")
    parser.add_argument("--tcp", type=int, metavar="PUERTO_TCP",
                         help="Levanta un servidor TCP local en lugar de usar un puerto serial")
    parser.add_argument("--host", default="127.0.0.1", help="Host para --tcp (default: %(default)s)")
    args = parser.parse_args()

    try:
        if args.tcp is not None:
            run_tcp(args.host, args.tcp)
        elif args.port:
            run_serial(args.port, args.baud)
        else:
            parser.error("se requiere PUERTO o --tcp PUERTO_TCP")
    except serial.SerialException as e:
        print(f"[ERROR] No se pudo abrir el puerto: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[sim] Detenido.")


if __name__ == "__main__":
    main()
