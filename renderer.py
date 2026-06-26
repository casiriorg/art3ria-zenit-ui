"""Visualizacion 3D: matematica de quaterniones, loader OBJ con fallback, ejes y perfiles de camara."""

import math
import os

from OpenGL.GL import (
    glBegin, glEnd, glVertex3f, glColor3f, glLineWidth,
    glGenLists, glNewList, glEndList, glCallList, glDeleteLists,
    GL_QUADS, GL_TRIANGLES, GL_LINES, GL_COMPILE,
)

from config import CFG, abs_path

PLACEHOLDER_HEADER = (
    "# cabeza.obj - PLACEHOLDER\n"
    "# Cubo generado automaticamente (1.2 x 0.7 x 0.15).\n"
    "# Reemplaza este archivo por el modelo real de la cabeza\n"
    "# manteniendo el nombre 'cabeza.obj' o actualizando 'model_path' en config.json.\n"
)


# ---------------- Quaternion math ----------------
def quat_mul(a, b):
    """Calcula el producto de Hamilton de dos quaterniones (w, x, y, z).

    Args:
        a: Quaternion (w, x, y, z).
        b: Quaternion (w, x, y, z).

    Returns:
        Quaternion resultante (w, x, y, z).
    """
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (
        aw*bw - ax*bx - ay*by - az*bz,
        aw*bx + ax*bw + ay*bz - az*by,
        aw*by - ax*bz + ay*bw + az*bx,
        aw*bz + ax*by - ay*bx + az*bw,
    )


def quat_conj(q):
    """Devuelve el conjugado del quaternion (w, x, y, z).

    Args:
        q: Quaternion (w, x, y, z).

    Returns:
        Quaternion conjugado (w, -x, -y, -z).
    """
    w, x, y, z = q
    return (w, -x, -y, -z)


def quat_to_matrix(q):
    """Convierte un quaternion a matriz de rotacion 4x4 column-major para OpenGL.

    Args:
        q: Quaternion (w, x, y, z).

    Returns:
        Lista de 16 floats en orden column-major, lista para pasar a glMultMatrixf.
    """
    w, x, y, z = q
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z

    return [
        1 - 2*(yy + zz), 2*(xy + wz),     2*(xz - wy),     0.0,
        2*(xy - wz),     1 - 2*(xx + zz), 2*(yz + wx),     0.0,
        2*(xz + wy),     2*(yz - wx),     1 - 2*(xx + yy), 0.0,
        0.0,             0.0,             0.0,             1.0,
    ]


def quat_to_euler(q):
    """Convierte un quaternion a angulos Euler (roll, pitch, yaw) en grados.

    Solo para visualizacion en el HUD; el render 3D trabaja directamente
    con quaterniones para evitar gimbal lock.

    Args:
        q: Quaternion (w, x, y, z).

    Returns:
        Tupla (roll, pitch, yaw) en grados.
    """
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


def euler_to_quat(pitch_deg, yaw_deg, roll_deg):
    """Construye un quaternion (w, x, y, z) a partir de angulos Euler en grados.

    Convencion de orden: ZYX (yaw -> pitch -> roll).

    Args:
        pitch_deg: Angulo de pitch en grados.
        yaw_deg: Angulo de yaw en grados.
        roll_deg: Angulo de roll en grados.

    Returns:
        Quaternion normalizado (w, x, y, z).
    """
    pitch, yaw, roll = (math.radians(a) for a in (pitch_deg, yaw_deg, roll_deg))

    cr, sr = math.cos(roll * 0.5), math.sin(roll * 0.5)
    cp, sp = math.cos(pitch * 0.5), math.sin(pitch * 0.5)
    cy, sy = math.cos(yaw * 0.5), math.sin(yaw * 0.5)

    return (
        cr*cp*cy + sr*sp*sy,
        sr*cp*cy - cr*sp*sy,
        cr*sp*cy + sr*cp*sy,
        cr*cp*sy - sr*sp*cy,
    )


def apply_camera_profile(q, profile: dict):
    """Aplica los signos de eje y el offset angular del perfil de camara al quaternion.

    Args:
        q: Quaternion de orientacion relativa (w, x, y, z).
        profile: Diccionario de perfil con claves 'roll_sign', 'pitch_sign',
            'yaw_sign' (cada uno ±1) y 'offset_deg' ([pitch, yaw, roll]).

    Returns:
        Quaternion transformado (w, x, y, z) listo para pasar a glMultMatrixf.
    """
    w, x, y, z = q
    signed = (
        w,
        x * profile.get("roll_sign", 1),
        y * profile.get("pitch_sign", 1),
        z * profile.get("yaw_sign", 1),
    )
    pitch_deg, yaw_deg, roll_deg = profile.get("offset_deg", [0, 0, 0])
    offset_quat = euler_to_quat(pitch_deg, yaw_deg, roll_deg)
    return quat_mul(offset_quat, signed)


# ---------------- Placeholder OBJ ----------------
def ensure_placeholder_obj(path: str = None):
    """Genera un cubo OBJ placeholder si el archivo del modelo no existe.

    El cubo mide 1.2 x 0.7 x 0.15 unidades (proporciones aproximadas de una
    cabeza). No hace nada si el archivo ya existe.

    Args:
        path: Ruta absoluta al archivo OBJ. Si es None, usa CFG.model_path.
    """
    path = path or abs_path(CFG.model_path)
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)

    w, h, d = 1.2, 0.7, 0.15
    verts = [
        (-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),
        (-w, -h,  d), (w, -h,  d), (w, h,  d), (-w, h,  d),
    ]
    normals = [
        (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0),
    ]
    # Caras como indices 1-based (v//vn), orden coincide con draw_cube original
    faces = [
        ((4, 3, 7, 8), 1),  # top    (+y)
        ((1, 5, 6, 2), 2),  # bottom (-y)
        ((5, 8, 7, 6), 3),  # front  (+z)
        ((1, 2, 3, 4), 4),  # back   (-z)
        ((2, 6, 7, 3), 5),  # right  (+x)
        ((1, 4, 8, 5), 6),  # left   (-x)
    ]

    lines = [PLACEHOLDER_HEADER]
    for vx, vy, vz in verts:
        lines.append(f"v {vx:.4f} {vy:.4f} {vz:.4f}\n")
    for nx, ny, nz in normals:
        lines.append(f"vn {nx:.1f} {ny:.1f} {nz:.1f}\n")
    for (a, b, c, d_), n in faces:
        lines.append(f"f {a}//{n} {b}//{n} {c}//{n} {d_}//{n}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ---------------- OBJ model ----------------
class ObjModel:
    """Carga un modelo OBJ (v/vn/f) con fallback al cubo hardcoded del script base."""

    def __init__(self, path: str = None):
        """Carga el modelo OBJ desde `path` y compila la display list de OpenGL.

        Args:
            path: Ruta absoluta al archivo OBJ. Si es None, usa CFG.model_path.
        """
        self.path = path or abs_path(CFG.model_path)
        self.vertices = []
        self.normals = []
        self.faces = []  # list of (vertex_indices, normal_index_or_None)
        self.using_placeholder = False
        self._hardcoded_fallback = False
        self._display_list = None
        self.load(self.path)

    def load(self, path: str):
        """Carga el OBJ indicado. En caso de error usa el cubo hardcoded como fallback.

        Args:
            path: Ruta absoluta al archivo OBJ a cargar.
        """
        try:
            self._load_obj(path)
            self.using_placeholder = self._is_placeholder_file(path)
        except (OSError, ValueError) as e:
            print(f"[WARN] No se pudo cargar el modelo '{path}': {e}. Usando cubo placeholder.")
            self._load_fallback_cube()
            self.using_placeholder = True
            self._hardcoded_fallback = True
        self._build_display_list()

    @staticmethod
    def _is_placeholder_file(path: str) -> bool:
        """Comprueba si el OBJ en `path` es el placeholder generado automaticamente.

        Args:
            path: Ruta al archivo OBJ.

        Returns:
            True si la primera linea contiene 'PLACEHOLDER'; False en caso contrario o error.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                first_line = f.readline()
            return "PLACEHOLDER" in first_line
        except OSError:
            return False

    def _load_obj(self, path: str):
        """Parsea el archivo OBJ y llena self.vertices, self.normals y self.faces.

        Autocentra la geometria al centro del bounding box y aplica
        model_pivot_offset de la configuracion.

        Args:
            path: Ruta absoluta al archivo OBJ.

        Raises:
            ValueError: Si el archivo no contiene vertices o caras validos.
            OSError: Si el archivo no puede abrirse.
        """
        vertices = []
        normals = []
        faces = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                tag = parts[0]
                if tag == "v":
                    vertices.append(tuple(float(p) for p in parts[1:4]))
                elif tag == "vn":
                    normals.append(tuple(float(p) for p in parts[1:4]))
                elif tag == "f":
                    idx = []
                    nidx = None
                    for token in parts[1:]:
                        comps = token.split("/")
                        v_i = int(comps[0])
                        idx.append(v_i - 1 if v_i > 0 else len(vertices) + v_i)
                        if len(comps) == 3 and comps[2]:
                            n_i = int(comps[2])
                            nidx = n_i - 1 if n_i > 0 else len(normals) + n_i
                    faces.append((idx, nidx))
        if not vertices or not faces:
            raise ValueError("el archivo no contiene geometria valida")

        # Autocentrado: recalcula el origen al centro del bounding box, y aplica
        # un offset configurable para mover el punto de rotacion (p.ej. al punto
        # donde iria el sensor en la cabeza).
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        cz = (min(zs) + max(zs)) / 2
        ox, oy, oz = CFG.get("model_pivot_offset", [0, 0, 0])
        vertices = [(x - cx - ox, y - cy - oy, z - cz - oz) for x, y, z in vertices]

        self.vertices = vertices
        self.normals = normals
        self.faces = faces

    def _load_fallback_cube(self):
        """Carga un cubo hardcoded como fallback cuando el OBJ no puede leerse."""
        w, h, d = 1.2, 0.7, 0.15
        self.vertices = [
            (-w, -h, -d), (w, -h, -d), (w, h, -d), (-w, h, -d),
            (-w, -h,  d), (w, -h,  d), (w, h,  d), (-w, h,  d),
        ]
        self.normals = [(0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0)]
        # (vertex_indices 0-based, normal_index, color)
        self._cube_faces = [
            ((3, 2, 6, 7), 0, (0.90, 0.30, 0.30)),
            ((0, 4, 5, 1), 1, (0.25, 0.25, 0.28)),
            ((4, 7, 6, 5), 2, (0.20, 0.75, 0.55)),
            ((0, 1, 2, 3), 3, (0.30, 0.55, 0.90)),
            ((1, 5, 6, 2), 4, (0.95, 0.75, 0.25)),
            ((0, 3, 7, 4), 5, (0.55, 0.45, 0.85)),
        ]
        self.faces = [(f[0], f[1]) for f in self._cube_faces]

    def _build_display_list(self):
        """Compila la geometria en una display list de OpenGL para render eficiente.

        Evita miles de llamadas glBegin/glVertex3f por frame, que son el costo
        dominante en el pipeline legacy de PyOpenGL.
        """
        if self._display_list is not None:
            glDeleteLists(self._display_list, 1)

        self._display_list = glGenLists(1)
        glNewList(self._display_list, GL_COMPILE)
        if self._hardcoded_fallback:
            self._draw_fallback_cube()
        else:
            self._draw_model()
        glEndList()

    def draw(self):
        """Dibuja el modelo cargado (o el cubo placeholder) via display list."""
        glCallList(self._display_list)

    def destroy(self):
        """Libera la display list de OpenGL asociada al modelo."""
        if self._display_list is not None:
            glDeleteLists(self._display_list, 1)
            self._display_list = None

    def _draw_model(self):
        """Emite las llamadas glBegin/glVertex3f para cada cara del modelo OBJ cargado."""
        for idx, nidx in self.faces:
            if nidx is not None and 0 <= nidx < len(self.normals):
                nx, ny, nz = self.normals[nidx]
                glColor3f(0.5 + 0.5*nx, 0.5 + 0.5*ny, 0.5 + 0.5*nz)
            else:
                glColor3f(0.6, 0.6, 0.65)
            mode = GL_QUADS if len(idx) == 4 else GL_TRIANGLES
            glBegin(mode)
            for vi in idx:
                glVertex3f(*self.vertices[vi])
            glEnd()

    def _draw_fallback_cube(self):
        """Dibuja el cubo hardcoded con colores por cara y aristas negras."""
        glBegin(GL_QUADS)
        for idx, _nidx, color in self._cube_faces:
            glColor3f(*color)
            for vi in idx:
                glVertex3f(*self.vertices[vi])
        glEnd()

        glColor3f(0.05, 0.05, 0.05)
        glLineWidth(2.0)
        pairs = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        glBegin(GL_LINES)
        for a, b in pairs:
            glVertex3f(*self.vertices[a])
            glVertex3f(*self.vertices[b])
        glEnd()


def draw_axes():
    """Dibuja los ejes de referencia: X en rojo, Y en verde, Z en azul."""
    glLineWidth(2.0)
    glBegin(GL_LINES)
    glColor3f(0.9, 0.3, 0.3); glVertex3f(0, 0, 0); glVertex3f(2.2, 0, 0)
    glColor3f(0.3, 0.9, 0.4); glVertex3f(0, 0, 0); glVertex3f(0, 2.2, 0)
    glColor3f(0.3, 0.5, 0.95); glVertex3f(0, 0, 0); glVertex3f(0, 0, 2.2)
    glEnd()
