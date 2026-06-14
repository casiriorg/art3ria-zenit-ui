"""
XIAO nRF52840 Sense - Visualizador 3D de orientacion (quaternion, sin gimbal lock)

Lee "qw,qx,qy,qz,roll,pitch,yaw" por USB Serial. Rota el cubo con el quaternion
directamente (no hay gimbal lock). Los angulos Euler solo se muestran en el HUD.

Requisitos:
    pip install pygame PyOpenGL PyOpenGL_accelerate pyserial

Uso:
    python3 imu_visualizer.py                        # autodetecta el puerto
    python3 imu_visualizer.py COM7                   # Windows
    python3 imu_visualizer.py /dev/ttyACM0           # Linux
    python3 imu_visualizer.py /dev/tty.usbmodem1101  # macOS

Controles:
    R   - centrar orientacion (zero-out)
    ESC - salir
"""

import sys
import threading
import time
import math
from collections import deque

import serial
import serial.tools.list_ports
import pygame
from pygame.locals import DOUBLEBUF, OPENGL, QUIT, KEYDOWN, K_ESCAPE, K_r

from OpenGL.GL import (
    glClear, glClearColor, glEnable, glDisable, glBegin, glEnd,
    glVertex3f, glColor3f, glColor4f, glMatrixMode, glLoadIdentity,
    glMultMatrixf, glTranslatef, glLineWidth, glViewport,
    glOrtho, glTexCoord2f, glTexImage2D, glGenTextures, glBindTexture,
    glTexParameteri, glDeleteTextures, glPixelStorei,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST,
    GL_QUADS, GL_LINES, GL_PROJECTION, GL_MODELVIEW, GL_LIGHTING,
    GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE, GL_LINEAR,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, glBlendFunc,
    GL_UNPACK_ALIGNMENT,
)
from OpenGL.GLU import gluPerspective

BAUD = 115200


# ---------------- Quaternion math ----------------
def quat_mul(a, b):
    """Hamilton product of two quaternions (w,x,y,z)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw*bw - ax*bx - ay*by - az*bz,
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
    )


def quat_conj(q):
    w, x, y, z = q
    return (w, -x, -y, -z)


def quat_to_matrix(q):
    """Convert quaternion (w,x,y,z) to a 4x4 column-major OpenGL matrix."""
    w, x, y, z = q
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z

    # Column-major 4x4
    return [
        1 - 2*(yy + zz), 2*(xy + wz),     2*(xz - wy),     0.0,
        2*(xy - wz),     1 - 2*(xx + zz), 2*(yz + wx),     0.0,
        2*(xz + wy),     2*(yz - wx),     1 - 2*(xx + yy), 0.0,
        0.0,             0.0,             0.0,             1.0,
    ]


def quat_to_euler(q):
    """Convert quaternion to (roll, pitch, yaw) in degrees, only for display."""
    w, x, y, z = q
    sinr_cosp = 2 * (w*x + y*z)
    cosr_cosp = 1 - 2 * (x*x + y*y)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2 * (w*y - z*x)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2 * (w*z + x*y)
    cosy_cosp = 1 - 2 * (y*y + z*z)
    yaw = math.atan2(siny_cosp, cosy_cosp)

    return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


# ---------------- Serial reader thread ----------------
class IMUReader(threading.Thread):
    def __init__(self, port, baud=BAUD):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.lock = threading.Lock()
        # Latest quaternion (w,x,y,z) and Euler (deg)
        self.quat = (1.0, 0.0, 0.0, 0.0)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.connected = False
        self.stop_flag = False
        self._samples = deque(maxlen=60)

    def run(self):
        try:
            ser = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)
            ser.reset_input_buffer()
            self.connected = True
            print(f"[OK] Conectado a {self.port} @ {self.baud}")
            while not self.stop_flag:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                if line.startswith("#"):
                    print(f"[XIAO] {line.lstrip('# ').strip()}")
                    continue
                parts = line.split(",")
                if len(parts) != 7:
                    print(f"[XIAO] {line}")
                    continue
                try:
                    qw, qx, qy, qz, r, p, y = (float(x) for x in parts)
                except ValueError:
                    continue
                with self.lock:
                    self.quat = (qw, qx, qy, qz)
                    self.roll, self.pitch, self.yaw = r, p, y
                self._samples.append(time.time())
        except serial.SerialException as e:
            print(f"[ERROR] Serial: {e}")
            self.connected = False

    def get(self):
        with self.lock:
            return self.quat, (self.roll, self.pitch, self.yaw)

    def rate_hz(self):
        if len(self._samples) < 2:
            return 0.0
        dt = self._samples[-1] - self._samples[0]
        return (len(self._samples) - 1) / dt if dt > 0 else 0.0

    def stop(self):
        self.stop_flag = True


# ---------------- 3D drawing ----------------
def draw_cube():
    w, h, d = 1.2, 0.7, 0.15
    faces = [
        (((-w, h, -d), (w, h, -d), (w, h, d), (-w, h, d)), (0.90, 0.30, 0.30)),
        (((-w, -h, -d), (-w, -h, d), (w, -h, d), (w, -h, -d)), (0.25, 0.25, 0.28)),
        (((-w, -h, d), (-w, h, d), (w, h, d), (w, -h, d)), (0.20, 0.75, 0.55)),
        (((-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d)), (0.30, 0.55, 0.90)),
        (((w, -h, -d), (w, -h, d), (w, h, d), (w, h, -d)), (0.95, 0.75, 0.25)),
        (((-w, -h, -d), (-w, h, -d), (-w, h, d), (-w, -h, d)), (0.55, 0.45, 0.85)),
    ]
    glBegin(GL_QUADS)
    for verts, color in faces:
        glColor3f(*color)
        for v in verts:
            glVertex3f(*v)
    glEnd()

    glColor3f(0.05, 0.05, 0.05)
    glLineWidth(2.0)
    corners = [
        (-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),
        (-w, -h,  d), (w, -h,  d), (w, h,  d), (-w, h,  d),
    ]
    pairs = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    glBegin(GL_LINES)
    for a, b in pairs:
        glVertex3f(*corners[a])
        glVertex3f(*corners[b])
    glEnd()


def draw_axes():
    glLineWidth(2.0)
    glBegin(GL_LINES)
    glColor3f(0.9, 0.3, 0.3); glVertex3f(0, 0, 0); glVertex3f(2.2, 0, 0)
    glColor3f(0.3, 0.9, 0.4); glVertex3f(0, 0, 0); glVertex3f(0, 2.2, 0)
    glColor3f(0.3, 0.5, 0.95); glVertex3f(0, 0, 0); glVertex3f(0, 0, 2.2)
    glEnd()


# ---------------- HUD ----------------
def make_hud_surface(W, H, roll, pitch, yaw, rate, connected, fonts):
    surf = pygame.Surface((W, H), pygame.SRCALPHA)

    title = fonts["title"].render(
        "XIAO nRF52840 Sense  -  Orientation", True, (235, 235, 240)
    )
    surf.blit(title, (20, 18))

    status_color = (60, 200, 120) if connected else (220, 90, 90)
    pygame.draw.circle(surf, status_color, (W - 30, 32), 6)
    status = fonts["small"].render(
        "conectado" if connected else "sin conexion", True, (200, 200, 210)
    )
    surf.blit(status, (W - 42 - status.get_width(), 22))

    lines = [
        ("Roll",  roll,  (235, 110, 110)),
        ("Pitch", pitch, (110, 215, 150)),
        ("Yaw",   yaw,   (120, 170, 245)),
    ]
    y = 70
    for label, value, color in lines:
        lab = fonts["label"].render(label, True, (160, 160, 170))
        surf.blit(lab, (24, y + 8))
        val = fonts["big"].render(f"{value:+7.2f} deg", True, color)
        surf.blit(val, (110, y))
        y += 46

    foot = fonts["small"].render(
        f"Tasa: {rate:5.1f} Hz        R = centrar       ESC = salir",
        True, (150, 150, 160),
    )
    surf.blit(foot, (20, H - 30))
    return surf


def upload_texture(tex_id, surface):
    W, H = surface.get_size()
    data = pygame.image.tostring(surface, "RGBA", True)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)


def draw_hud_quad(tex_id, W, H):
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(0, W, 0, H, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    glDisable(GL_DEPTH_TEST)
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glBindTexture(GL_TEXTURE_2D, tex_id)

    glColor4f(1, 1, 1, 1)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex3f(0, 0, 0)
    glTexCoord2f(1, 0); glVertex3f(W, 0, 0)
    glTexCoord2f(1, 1); glVertex3f(W, H, 0)
    glTexCoord2f(0, 1); glVertex3f(0, H, 0)
    glEnd()

    glDisable(GL_TEXTURE_2D)
    glDisable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, W / H, 0.1, 50.0)
    glMatrixMode(GL_MODELVIEW)


# ---------------- Port autodetect ----------------
def find_xiao_port():
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
    return None


# ---------------- Main ----------------
def main():
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = find_xiao_port()
        if port is None:
            print("No pude autodetectar la XIAO. Puertos disponibles:")
            for p in serial.tools.list_ports.comports():
                print(f"  {p.device}  -  {p.description}")
            print("\nUso: python3 imu_visualizer.py <PUERTO>")
            sys.exit(1)
        print(f"[info] Puerto autodetectado: {port}")

    reader = IMUReader(port)
    reader.start()

    pygame.init()
    W, H = 960, 720
    pygame.display.set_caption("XIAO nRF52840 Sense - IMU 3D")
    pygame.display.set_mode((W, H), DOUBLEBUF | OPENGL)

    fonts = {
        "title": pygame.font.SysFont("Arial", 22, bold=True),
        "label": pygame.font.SysFont("Arial", 18, bold=True),
        "big":   pygame.font.SysFont("Consolas", 34, bold=True),
        "small": pygame.font.SysFont("Arial", 16),
    }
    if fonts["big"].get_height() < 12:
        fonts["big"] = pygame.font.SysFont("Courier", 34, bold=True)

    glEnable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glClearColor(0.10, 0.11, 0.13, 1.0)
    glViewport(0, 0, W, H)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, W / H, 0.1, 50.0)
    glMatrixMode(GL_MODELVIEW)

    hud_tex = glGenTextures(1)
    # "R" saves the conjugate of the current quaternion as an offset.
    # Displayed quaternion = q_offset * q_current  (relative rotation)
    q_offset = (1.0, 0.0, 0.0, 0.0)

    clock = pygame.time.Clock()
    running = True

    while running:
        for ev in pygame.event.get():
            if ev.type == QUIT:
                running = False
            elif ev.type == KEYDOWN:
                if ev.key == K_ESCAPE:
                    running = False
                elif ev.key == K_r:
                    q_now, _ = reader.get()
                    q_offset = quat_conj(q_now)
                    print("[info] Orientacion centrada")

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(0.0, -0.3, -5.5)

        q_now, _ = reader.get()
        q_rel = quat_mul(q_offset, q_now)
        # Invertir pitch y yaw para alinear con convencion OpenGL (DESPUES de calibrar)
        rw, rx, ry, rz = q_rel
        q_rel = (rw, -rx, ry, -rz)

        # Apply quaternion rotation directly (no gimbal lock)
        glMultMatrixf(quat_to_matrix(q_rel))

        draw_axes()
        draw_cube()

        # For the HUD: recompute Euler from q_rel so it matches the cube after "R"
        roll, pitch, yaw = quat_to_euler(q_rel)
        hud_surface = make_hud_surface(W, H, roll, pitch, yaw, reader.rate_hz(),
                                       reader.connected, fonts)
        upload_texture(hud_tex, hud_surface)
        draw_hud_quad(hud_tex, W, H)

        pygame.display.flip()
        clock.tick(60)

    glDeleteTextures([hud_tex])
    reader.stop()
    pygame.quit()
    print("Bye!")


if __name__ == "__main__":
    main()