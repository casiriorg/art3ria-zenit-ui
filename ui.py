"""HUD, panel lateral, controles de sesion, replay y dialogos modales."""

import os
from collections import deque

import pygame

from config import CFG, abs_path

# Cuentas regresivas / countdown overlay
COUNTDOWN_FONT_SIZE = 140

# Barra de estado inferior
STATUS_BAR_HEIGHT = 24

# Color de acento para el modo replay
REPLAY_ACCENT = (130, 80, 200)


def hex_to_rgb(hex_str: str):
    """Convierte un color '#RRGGBB' a tupla (r, g, b).

    Args:
        hex_str: Color hexadecimal con o sin prefijo '#'.

    Returns:
        Tupla (r, g, b) con valores enteros en el rango 0-255.
    """
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


class Sparkline:
    """Historial de valores con normalizacion min/max deslizante, dibujable con lineas."""

    def __init__(self, maxlen: int):
        """
        Args:
            maxlen: Numero maximo de puntos a conservar en el historial deslizante.
        """
        self.values = deque(maxlen=maxlen)

    def add(self, value: float):
        """Agrega un nuevo valor al historial deslizante.

        Args:
            value: Valor numerico a agregar.
        """
        self.values.append(value)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, color):
        """Dibuja la sparkline en la superficie dentro del rectangulo indicado.

        No dibuja nada si hay menos de 2 puntos en el historial.

        Args:
            surface: Superficie pygame donde dibujar.
            rect: Rectangulo que define el area de dibujo.
            color: Color RGB o RGBA de la linea.
        """
        if len(self.values) < 2:
            return
        vmin, vmax = min(self.values), max(self.values)
        span = (vmax - vmin) or 1.0
        n = len(self.values)
        points = []
        for i, v in enumerate(self.values):
            x = rect.x + (i / (n - 1)) * rect.width
            norm = (v - vmin) / span
            y = rect.y + rect.height - norm * rect.height
            points.append((x, y))
        pygame.draw.lines(surface, color, False, points, 2)


def _draw_heart_icon(surface, x, y, color):
    """Dibuja un icono de corazon con circulos y un poligono.

    Args:
        surface: Superficie pygame destino.
        x: Coordenada x de la esquina superior izquierda del icono.
        y: Coordenada y de la esquina superior izquierda del icono.
        color: Color RGB del icono.
    """
    cx, cy = x + 13, y + 11
    pygame.draw.circle(surface, color, (cx - 5, cy), 6)
    pygame.draw.circle(surface, color, (cx + 5, cy), 6)
    pygame.draw.polygon(surface, color, [(cx - 10, cy + 2), (cx + 10, cy + 2), (cx, cy + 15)])


def _draw_hand_icon(surface, x, y, color):
    """Dibuja un icono de mano estilizado con rectangulos (usado para GSR).

    Args:
        surface: Superficie pygame destino.
        x: Coordenada x de la esquina superior izquierda del icono.
        y: Coordenada y de la esquina superior izquierda del icono.
        color: Color RGB del icono.
    """
    pygame.draw.rect(surface, color, (x + 4, y + 12, 16, 11), border_radius=4)
    for fx, fh in ((x + 5, 9), (x + 9, 11), (x + 13, 11), (x + 17, 9)):
        pygame.draw.rect(surface, color, (fx, y + 12 - fh, 3, fh), border_radius=1)
    pygame.draw.rect(surface, color, (x + 1, y + 15, 6, 4), border_radius=2)


ICON_DRAWERS = {
    "heart": _draw_heart_icon,
    "hands": _draw_hand_icon,
}


def _draw_triangle_icon(surface, center, size, color, direction="right"):
    """Dibuja un triangulo de navegacion apuntando a la izquierda o derecha.

    Args:
        surface: Superficie pygame destino.
        center: Tupla (cx, cy) con el centro del triangulo.
        size: Tamano (altura y base) del triangulo en pixeles.
        color: Color RGB del triangulo.
        direction: 'right' (por defecto) o 'left'.
    """
    cx, cy = center
    h = size / 2
    if direction == "left":
        points = [(cx + h, cy - h), (cx + h, cy + h), (cx - h, cy)]
    else:
        points = [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)]
    pygame.draw.polygon(surface, color, points)


def _draw_square_icon(surface, center, size, color):
    """Dibuja un cuadrado de stop/abortar centrado en el punto indicado.

    Args:
        surface: Superficie pygame destino.
        center: Tupla (cx, cy) con el centro del cuadrado.
        size: Lado del cuadrado en pixeles.
        color: Color RGB del cuadrado.
    """
    rect = pygame.Rect(0, 0, size, size)
    rect.center = center
    pygame.draw.rect(surface, color, rect, border_radius=2)


class SignalWidget:
    """Panel de senal principal (PPG/GSR): icono, valor numerico y sparkline."""

    def __init__(self, key: str, icon: str, color, fonts):
        """
        Args:
            key: Identificador de la senal (ej. 'PPG', 'GSR').
            icon: Nombre del icono a dibujar (ej. 'heart', 'hands').
            color: Tupla RGB del color principal del widget.
            fonts: Diccionario de fuentes pygame {'small': ..., 'big': ...}.
        """
        self.key = key
        self.icon = icon
        self.color = color
        self.fonts = fonts
        self.sparkline = Sparkline(CFG.sparkline_window_size)

    def update(self, value):
        """Agrega un nuevo valor al sparkline del widget.

        Args:
            value: Valor numerico o None si no hay lectura disponible.
        """
        if value is not None:
            self.sparkline.add(value)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, value):
        """Dibuja el widget completo: fondo, icono, etiqueta, valor y sparkline.

        Args:
            surface: Superficie pygame destino.
            rect: Rectangulo que define la posicion y tamano del widget.
            value: Valor numerico actual o None para mostrar '--'.
        """
        pygame.draw.rect(surface, (30, 34, 48, 200), rect, border_radius=8)

        drawer = ICON_DRAWERS.get(self.icon)
        if drawer is not None:
            drawer(surface, rect.x + 6, rect.y + 6, self.color)
        else:
            pygame.draw.circle(surface, self.color, (rect.x + 23, rect.y + 21), 11)

        label_surf = self.fonts["small"].render(self.key, True, (170, 175, 185))
        surface.blit(label_surf, (rect.x + 50, rect.y + 8))

        text = f"{value:7.2f}" if value is not None else "  --  "
        val_surf = self.fonts["big"].render(text, True, self.color)
        surface.blit(val_surf, (rect.x + 50, rect.y + 26))

        spark_rect = pygame.Rect(rect.x + 10, rect.bottom - 28, rect.width - 20, 22)
        self.sparkline.draw(surface, spark_rect, self.color)


class AppUI:
    """Orquesta todo el HUD: panel lateral, widgets de senales, controles y dialogos."""

    def __init__(self):
        """Inicializa el HUD: colores, fuentes, lista de audios, widgets y estado de replay."""
        self.colors = {
            "bg": hex_to_rgb(CFG.ui["bg_color"]),
            "accent": hex_to_rgb(CFG.ui["accent_color"]),
            "text": hex_to_rgb(CFG.ui["text_color"]),
        }
        self.fonts = self._load_fonts()

        self.panel_expanded = True
        self.audio_files = []
        self.audio_scroll = 0
        self.selected_audio = None
        self.refresh_audio_files()

        self.camera_profiles = list(CFG.camera_profiles.keys())
        self.camera_profile = CFG.active_camera_profile
        if self.camera_profile not in self.camera_profiles:
            self.camera_profile = self.camera_profiles[0]

        self.signal_widgets = {}
        for key, meta in CFG.known_signals.items():
            icon = meta.get("icon", "")
            self.signal_widgets[key] = SignalWidget(key, icon, hex_to_rgb(meta["color"]), self.fonts)

        self.session_active = False
        self.countdown = None
        self.action = None

        self.modal = None
        self.rects = {}

        # Estado de replay
        self.log_files: list = []
        self.log_scroll: int = 0
        self.selected_log: str | None = None
        self.refresh_log_files()
        self._replay_mode: bool = False
        self._replay_ref = None
        self._normal_accent = None

    # ------------------------------------------------------------------
    def _load_fonts(self):
        """Carga las fuentes del sistema configuradas en CFG.ui.font_family.

        Returns:
            Diccionario con fuentes pygame: {'title', 'label', 'small', 'big', 'countdown'}.
        """
        family = CFG.ui.get("font_family", "Arial")
        try:
            title = pygame.font.SysFont(family, 22, bold=True)
            label = pygame.font.SysFont(family, 16, bold=True)
            small = pygame.font.SysFont(family, 14)
            big = pygame.font.SysFont("Consolas", 28, bold=True)
            countdown = pygame.font.SysFont(family, COUNTDOWN_FONT_SIZE, bold=True)
        except Exception:
            title = pygame.font.SysFont("Arial", 22, bold=True)
            label = pygame.font.SysFont("Arial", 16, bold=True)
            small = pygame.font.SysFont("Arial", 14)
            big = pygame.font.SysFont("Courier", 28, bold=True)
            countdown = pygame.font.SysFont("Arial", COUNTDOWN_FONT_SIZE, bold=True)
        return {
            "title": title, "label": label, "small": small,
            "big": big, "countdown": countdown,
        }

    # ------------------------------------------------------------------
    def refresh_audio_files(self):
        """Reescanea CFG.audio_folder buscando archivos .wav y actualiza la lista.

        Reinicia el scroll y deselecciona el audio actual si ya no existe en la carpeta.
        """
        folder = abs_path(CFG.audio_folder)
        os.makedirs(folder, exist_ok=True)
        self.audio_files = sorted(
            f for f in os.listdir(folder) if f.lower().endswith(".wav")
        )
        if self.selected_audio not in self.audio_files:
            self.selected_audio = None
        self.audio_scroll = 0

    def refresh_log_files(self):
        """Reescanea CFG.logs_folder buscando archivos .csv y actualiza la lista de logs.

        Ordena de mas reciente a mas antiguo. Reinicia el scroll y limpia la seleccion
        si el archivo ya no existe.
        """
        folder = abs_path(CFG.logs_folder)
        os.makedirs(folder, exist_ok=True)
        self.log_files = sorted(
            (f for f in os.listdir(folder) if f.lower().endswith(".csv")),
            reverse=True,
        )
        if self.selected_log not in self.log_files:
            self.selected_log = None
        self.log_scroll = 0

    def selected_audio_path(self):
        """Devuelve la ruta absoluta del archivo de audio seleccionado.

        Returns:
            Ruta absoluta como string, o None si no hay ninguno seleccionado.
        """
        if self.selected_audio is None:
            return None
        return os.path.join(abs_path(CFG.audio_folder), self.selected_audio)

    # ------------------------------------------------------------------
    def update_signals(self, signals: dict):
        """Actualiza los sparklines de los widgets de senales conocidas (PPG, GSR, etc.).

        Args:
            signals: Diccionario {clave: valor_float} con las ultimas lecturas del sensor.
        """
        for key, widget in self.signal_widgets.items():
            widget.update(signals.get(key))

    def set_countdown(self, label, remaining):
        """Establece o limpia el overlay de cuenta regresiva.

        Args:
            label: Texto a mostrar (ej. 'Preparando...'). Pasa None para ocultar el overlay.
            remaining: Segundos restantes de la cuenta regresiva.
        """
        self.countdown = {"label": label, "remaining": remaining} if label else None

    def set_session_active(self, active: bool):
        """Actualiza el estado de sesion activa, habilitando o deshabilitando controles.

        Args:
            active: True si hay una sesion en curso; False en caso contrario.
        """
        self.session_active = active

    def open_session_modal(self):
        """Abre el dialogo modal para ingresar el nombre del participante."""
        self.modal = {"mode": "session", "text": ""}

    def open_quit_confirm(self):
        """Abre el dialogo de confirmacion para salir con una sesion activa."""
        self.modal = {
            "mode": "confirm",
            "message": "Hay una sesion activa. Salir de todos modos?",
            "on_yes": "QUIT",
        }

    def open_log_select_modal(self):
        """Refresca la lista de logs y abre el modal de seleccion de sesion para replay."""
        self.refresh_log_files()
        self.modal = {"mode": "log_select"}

    def show_summary(self, summary: dict):
        """Abre el modal de resumen con las estadisticas de la sesion recien finalizada.

        Args:
            summary: Diccionario de estadisticas devuelto por CSVLogger._compute_summary().
        """
        self.modal = {"mode": "summary", "data": summary}

    def set_replay_mode(self, active: bool, replay_ref=None):
        """Activa o desactiva el modo replay, cambiando el color de acento de la interfaz.

        En modo replay el acento cambia a purpura (REPLAY_ACCENT) y los controles de
        sesion se reemplazan por controles de transporte.

        Args:
            active: True para entrar en modo replay, False para salir.
            replay_ref: Instancia de ReplayReader activa (necesaria cuando active=True).
        """
        if active:
            self._normal_accent = self.colors["accent"]
            self.colors["accent"] = REPLAY_ACCENT
            self._replay_mode = True
            self._replay_ref = replay_ref
            self.selected_log = None
        else:
            if self._normal_accent is not None:
                self.colors["accent"] = self._normal_accent
                self._normal_accent = None
            self._replay_mode = False
            self._replay_ref = None

    # ------------------------------------------------------------------
    def handle_event(self, event):
        """Procesa un evento pygame y puede establecer self.action como efecto secundario.

        Args:
            event: Evento pygame (KEYDOWN, MOUSEBUTTONDOWN, MOUSEWHEEL, etc.).
        """
        if self.modal is not None:
            self._handle_modal_event(event)
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            self.panel_expanded = not self.panel_expanded
            return

        if event.type == pygame.MOUSEWHEEL:
            if self.rects.get("audio_list") and \
                    self.rects["audio_list"].collidepoint(pygame.mouse.get_pos()):
                self.audio_scroll = max(0, self.audio_scroll - event.y)
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        pos = event.pos

        # Controles de transporte del replay (zona inferior de pantalla)
        if self._replay_mode and self._replay_ref is not None:
            if self.rects.get("rp_play") and self.rects["rp_play"].collidepoint(pos):
                self._replay_ref.toggle_play()
                return
            for spd in (0.5, 1.0, 2.0):
                key = f"rp_spd_{spd}"
                if self.rects.get(key) and self.rects[key].collidepoint(pos):
                    self._replay_ref.set_speed(spd)
                    return
            if self.rects.get("rp_exit") and self.rects["rp_exit"].collidepoint(pos):
                self.action = ("EXIT_REPLAY",)
                return

        if self.rects.get("panel_toggle") and self.rects["panel_toggle"].collidepoint(pos):
            self.panel_expanded = not self.panel_expanded
            return

        if not self.panel_expanded:
            self._handle_session_buttons(pos)
            return

        for i, item_rect in enumerate(self.rects.get("audio_items", [])):
            if item_rect.collidepoint(pos):
                idx = i + self.audio_scroll
                if 0 <= idx < len(self.audio_files):
                    self.selected_audio = self.audio_files[idx]
                return

        if self.rects.get("refresh_btn") and self.rects["refresh_btn"].collidepoint(pos):
            self.refresh_audio_files()
            return

        if self.rects.get("cam_prev") and self.rects["cam_prev"].collidepoint(pos):
            self._cycle_camera_profile(-1)
            return
        if self.rects.get("cam_next") and self.rects["cam_next"].collidepoint(pos):
            self._cycle_camera_profile(1)
            return

        if self.rects.get("replay_btn") and self.rects["replay_btn"].collidepoint(pos):
            if self._replay_mode:
                self.action = ("EXIT_REPLAY",)
            else:
                self.open_log_select_modal()
            return

        self._handle_session_buttons(pos)

    def _cycle_camera_profile(self, step):
        """Avanza o retrocede el perfil de camara activo en la lista de perfiles.

        Args:
            step: 1 para avanzar al siguiente perfil, -1 para retroceder al anterior.
        """
        idx = self.camera_profiles.index(self.camera_profile)
        idx = (idx + step) % len(self.camera_profiles)
        self.camera_profile = self.camera_profiles[idx]

    def _handle_session_buttons(self, pos):
        """Procesa clics en los botones REPRODUCIR y ABORTAR.

        Args:
            pos: Tupla (x, y) de la posicion del clic del raton.
        """
        play_rect = self.rects.get("play_btn")
        abort_rect = self.rects.get("abort_btn")
        if play_rect and play_rect.collidepoint(pos) and self._play_enabled():
            self.open_session_modal()
        elif abort_rect and abort_rect.collidepoint(pos) and self.session_active:
            self.action = ("ABORT",)

    def _play_enabled(self):
        """Indica si el boton REPRODUCIR debe estar habilitado.

        Returns:
            True si hay un audio seleccionado, no hay sesion activa y no hay replay.
        """
        return self.selected_audio is not None and not self.session_active and not self._replay_mode

    def _handle_modal_event(self, event):
        """Procesa eventos de teclado y raton cuando hay un dialogo modal abierto.

        Args:
            event: Evento pygame a procesar.
        """
        mode = self.modal["mode"]

        # Scroll de la lista de logs con la rueda del raton
        if event.type == pygame.MOUSEWHEEL:
            if mode == "log_select":
                max_scroll = max(0, len(self.log_files) - (160 // 26))
                self.log_scroll = max(0, min(max_scroll, self.log_scroll - event.y))
            return

        if event.type == pygame.KEYDOWN:
            if mode == "summary":
                if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                    self.modal = None
                return
            if mode == "log_select":
                if event.key == pygame.K_ESCAPE:
                    self.modal = None
                elif event.key == pygame.K_RETURN and self.selected_log:
                    self.action = ("START_REPLAY", self.selected_log)
                    self.modal = None
                return
            if mode == "session":
                if event.key == pygame.K_RETURN:
                    name = self.modal["text"].strip()
                    if name:
                        self.action = ("PLAY_REQUEST", name)
                        self.modal = None
                elif event.key == pygame.K_BACKSPACE:
                    self.modal["text"] = self.modal["text"][:-1]
                elif event.key == pygame.K_ESCAPE:
                    self.modal = None
                elif event.unicode and event.unicode.isprintable():
                    if len(self.modal["text"]) < 40:
                        self.modal["text"] += event.unicode
            else:  # confirm
                if event.key in (pygame.K_RETURN, pygame.K_y):
                    self.action = (self.modal["on_yes"],)
                    self.modal = None
                elif event.key in (pygame.K_ESCAPE, pygame.K_n):
                    self.modal = None
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if mode == "summary":
                if self.rects.get("modal_confirm") and self.rects["modal_confirm"].collidepoint(pos):
                    self.modal = None
                return
            if mode == "log_select":
                for i, item_rect in enumerate(self.rects.get("log_items", [])):
                    if item_rect.collidepoint(pos):
                        idx = i + self.log_scroll
                        if 0 <= idx < len(self.log_files):
                            self.selected_log = self.log_files[idx]
                        return
                if self.rects.get("modal_confirm") and self.rects["modal_confirm"].collidepoint(pos):
                    if self.selected_log:
                        self.action = ("START_REPLAY", self.selected_log)
                        self.modal = None
                elif self.rects.get("modal_cancel") and self.rects["modal_cancel"].collidepoint(pos):
                    self.modal = None
                return
            if mode == "session":
                if self.rects.get("modal_confirm") and self.rects["modal_confirm"].collidepoint(pos):
                    name = self.modal["text"].strip()
                    if name:
                        self.action = ("PLAY_REQUEST", name)
                        self.modal = None
                elif self.rects.get("modal_cancel") and self.rects["modal_cancel"].collidepoint(pos):
                    self.modal = None
            else:
                if self.rects.get("modal_confirm") and self.rects["modal_confirm"].collidepoint(pos):
                    self.action = (self.modal["on_yes"],)
                    self.modal = None
                elif self.rects.get("modal_cancel") and self.rects["modal_cancel"].collidepoint(pos):
                    self.modal = None

    # ------------------------------------------------------------------
    def render(self, W, H, ctx: dict) -> pygame.Surface:
        """Construye la superficie HUD completa para el frame actual.

        Args:
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
            ctx: Diccionario con el estado de la app: {connected, port, baud,
                rate_hz, signals, using_placeholder}.

        Returns:
            Superficie pygame SRCALPHA con el HUD renderizado, lista para subir como textura.
        """
        surf = pygame.Surface((W, H), pygame.SRCALPHA)
        self.rects = {}

        self._draw_signal_panel(surf, W, ctx.get("signals", {}))
        self._draw_side_panel(surf, W, H, ctx)
        self._draw_session_controls(surf, W, H)
        self._draw_status_bar(surf, W, H, ctx)

        if self.countdown is not None:
            self._draw_countdown(surf, W, H)

        if self.modal is not None:
            self._draw_modal(surf, W, H)

        return surf

    def _draw_signal_panel(self, surf, W, signals):
        """Dibuja los widgets de senales principales (PPG, GSR) en la esquina superior derecha.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            signals: Diccionario {clave: valor} con las lecturas actuales de las senales.
        """
        x = W - 230
        y = 20
        for key, widget in self.signal_widgets.items():
            rect = pygame.Rect(x, y, 210, 80)
            widget.draw(surf, rect, signals.get(key))
            y += 90

    def _draw_side_panel(self, surf, W, H, ctx):
        """Dibuja el panel lateral con lista de audios, senales adicionales, camara y replay.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
            ctx: Diccionario de contexto de la app (usado para 'signals').
        """
        toggle_rect = pygame.Rect(0, H // 2 - 20, 24, 40)
        self.rects["panel_toggle"] = toggle_rect
        pygame.draw.rect(surf, (40, 44, 60, 220), toggle_rect, border_radius=4)
        direction = "left" if self.panel_expanded else "right"
        _draw_triangle_icon(surf, toggle_rect.center, 12, self.colors["text"], direction)

        if not self.panel_expanded:
            return

        panel_w = 280
        alpha = int(CFG.panel_alpha * 255)
        panel = pygame.Surface((panel_w, H), pygame.SRCALPHA)
        panel.fill((20, 24, 36, alpha))

        pad = 16
        y = pad

        title = self.fonts["title"].render("Audio (WAV)", True, self.colors["text"])
        panel.blit(title, (pad, y))
        y += 36

        list_height = 180
        list_rect = pygame.Rect(pad, y, panel_w - 2 * pad, list_height)
        self.rects["audio_list"] = list_rect.move(toggle_rect.width, 0)
        pygame.draw.rect(panel, (10, 12, 20, 180), list_rect, border_radius=6)

        item_h = 26
        visible = list_height // item_h
        item_rects = []
        for i in range(visible):
            idx = i + self.audio_scroll
            if idx >= len(self.audio_files):
                break
            item_rect = pygame.Rect(list_rect.x + 2, list_rect.y + 2 + i * item_h,
                                     list_rect.width - 4, item_h - 2)
            name = self.audio_files[idx]
            if name == self.selected_audio:
                pygame.draw.rect(panel, self.colors["accent"], item_rect, border_radius=4)
                txt_color = (10, 10, 10)
            else:
                txt_color = self.colors["text"]
            label = self.fonts["small"].render(name, True, txt_color)
            panel.blit(label, (item_rect.x + 6, item_rect.y + 4))
            item_rects.append(item_rect.move(toggle_rect.width, 0))
        self.rects["audio_items"] = item_rects
        y += list_height + 10

        refresh_rect = pygame.Rect(pad, y, panel_w - 2 * pad, 30)
        pygame.draw.rect(panel, (40, 44, 60, 220), refresh_rect, border_radius=6)
        refresh_label = self.fonts["label"].render("Refrescar", True, self.colors["text"])
        panel.blit(refresh_label, (refresh_rect.x + 10, refresh_rect.y + 5))
        self.rects["refresh_btn"] = refresh_rect.move(toggle_rect.width, 0)
        y += 30 + 14

        pygame.draw.line(panel, (80, 84, 100), (pad, y), (panel_w - pad, y), 1)
        y += 16

        extra_title = self.fonts["title"].render("Senales adicionales", True, self.colors["text"])
        panel.blit(extra_title, (pad, y))
        y += 32

        extra_signals = {
            k: v for k, v in ctx.get("signals", {}).items()
            if k not in self.signal_widgets
        }
        if not extra_signals:
            none_label = self.fonts["small"].render("(ninguna)", True, (140, 144, 156))
            panel.blit(none_label, (pad, y))
            y += 22
        for key, value in extra_signals.items():
            line = self.fonts["small"].render(f"{key}: {value:.3f}", True, self.colors["text"])
            panel.blit(line, (pad, y))
            y += 22

        y += 10
        pygame.draw.line(panel, (80, 84, 100), (pad, y), (panel_w - pad, y), 1)
        y += 16

        cam_title = self.fonts["title"].render("Perfil de camara", True, self.colors["text"])
        panel.blit(cam_title, (pad, y))
        y += 32

        prev_rect = pygame.Rect(pad, y, 28, 28)
        next_rect = pygame.Rect(panel_w - pad - 28, y, 28, 28)
        pygame.draw.rect(panel, (40, 44, 60, 220), prev_rect, border_radius=4)
        pygame.draw.rect(panel, (40, 44, 60, 220), next_rect, border_radius=4)
        _draw_triangle_icon(panel, prev_rect.center, 10, self.colors["text"], "left")
        _draw_triangle_icon(panel, next_rect.center, 10, self.colors["text"], "right")
        self.rects["cam_prev"] = prev_rect.move(toggle_rect.width, 0)
        self.rects["cam_next"] = next_rect.move(toggle_rect.width, 0)

        name_label = self.fonts["label"].render(f"[ {self.camera_profile} ]", True, self.colors["accent"])
        name_rect = name_label.get_rect(center=(panel_w // 2, y + 14))
        panel.blit(name_label, name_rect)
        y += 40

        # ---- Seccion Replay ----
        pygame.draw.line(panel, (80, 84, 100), (pad, y), (panel_w - pad, y), 1)
        y += 14

        replay_btn_rect = pygame.Rect(pad, y, panel_w - 2 * pad, 30)
        btn_color = (60, 30, 80, 220) if self._replay_mode else (40, 44, 60, 220)
        pygame.draw.rect(panel, btn_color, replay_btn_rect, border_radius=6)
        pygame.draw.rect(panel, REPLAY_ACCENT, replay_btn_rect, 1, border_radius=6)
        replay_btn_text = "Salir del Replay" if self._replay_mode else "Abrir Replay..."
        replay_label = self.fonts["label"].render(replay_btn_text, True, REPLAY_ACCENT)
        panel.blit(replay_label, (replay_btn_rect.x + 10, replay_btn_rect.y + 6))
        self.rects["replay_btn"] = replay_btn_rect.move(toggle_rect.width, 0)

        surf.blit(panel, (toggle_rect.width, 0))

    def _draw_session_controls(self, surf, W, H):
        """Dibuja los controles inferiores: botones de sesion o controles de replay.

        En modo replay muestra los controles de transporte en lugar de REPRODUCIR/ABORTAR.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
        """
        if self._replay_mode:
            self._draw_replay_controls(surf, W, H)
            return

        btn_w, btn_h = 180, 44
        gap = 20
        total_w = btn_w * 2 + gap
        x0 = (W - total_w) // 2
        y0 = H - STATUS_BAR_HEIGHT - 12 - btn_h

        play_rect = pygame.Rect(x0, y0, btn_w, btn_h)
        abort_rect = pygame.Rect(x0 + btn_w + gap, y0, btn_w, btn_h)
        self.rects["play_btn"] = play_rect
        self.rects["abort_btn"] = abort_rect

        play_enabled = self._play_enabled()
        play_color = self.colors["accent"] if play_enabled else (60, 64, 76)
        pygame.draw.rect(surf, play_color, play_rect, border_radius=8)
        play_label = self.fonts["label"].render("REPRODUCIR", True, (15, 18, 26))
        play_text_rect = play_label.get_rect(center=play_rect.center)
        _draw_triangle_icon(surf, (play_text_rect.x - 14, play_text_rect.centery), 12, (15, 18, 26))
        surf.blit(play_label, play_text_rect)

        abort_color = (210, 70, 70) if self.session_active else (60, 64, 76)
        pygame.draw.rect(surf, abort_color, abort_rect, border_radius=8)
        abort_label = self.fonts["label"].render("ABORTAR", True, (15, 18, 26))
        abort_text_rect = abort_label.get_rect(center=abort_rect.center)
        _draw_square_icon(surf, (abort_text_rect.x - 14, abort_text_rect.centery), 12, (15, 18, 26))
        surf.blit(abort_label, abort_text_rect)

    def _draw_replay_controls(self, surf, W, H):
        """Dibuja los controles de transporte del replay en la zona inferior de la ventana.

        Muestra: boton play/pausa, botones de velocidad (0.5x 1x 2x),
        barra de progreso con tiempo y boton de salida.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
        """
        if self._replay_ref is None:
            return

        rr = self._replay_ref
        bar_h = 56
        by = H - STATUS_BAR_HEIGHT - bar_h - 8
        pad_x = 20

        # Fondo semitransparente
        bg_rect = pygame.Rect(0, by, W, bar_h + 8)
        bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        bg_surf.fill((10, 12, 20, 160))
        surf.blit(bg_surf, bg_rect.topleft)

        cy = by + bar_h // 2

        # Boton play / pausa
        pp_rect = pygame.Rect(pad_x, by + 8, 44, 40)
        pygame.draw.rect(surf, (50, 40, 70, 240), pp_rect, border_radius=8)
        pygame.draw.rect(surf, REPLAY_ACCENT, pp_rect, 1, border_radius=8)
        if rr.playing:
            pygame.draw.rect(surf, REPLAY_ACCENT, (pp_rect.x + 11, pp_rect.y + 11, 7, 18))
            pygame.draw.rect(surf, REPLAY_ACCENT, (pp_rect.x + 24, pp_rect.y + 11, 7, 18))
        else:
            _draw_triangle_icon(surf, pp_rect.center, 18, REPLAY_ACCENT)
        self.rects["rp_play"] = pp_rect

        # Botones de velocidad
        speeds = [("0.5x", 0.5), ("1x", 1.0), ("2x", 2.0)]
        sx = pp_rect.right + 14
        for spd_label, spd_val in speeds:
            sr = pygame.Rect(sx, by + 13, 44, 30)
            active = abs(rr.speed - spd_val) < 0.01
            bg = REPLAY_ACCENT if active else (40, 34, 56, 220)
            pygame.draw.rect(surf, bg, sr, border_radius=6)
            txt_color = (15, 10, 25) if active else (170, 150, 200)
            spd_surf = self.fonts["small"].render(spd_label, True, txt_color)
            surf.blit(spd_surf, spd_surf.get_rect(center=sr.center))
            self.rects[f"rp_spd_{spd_val}"] = sr
            sx += 52

        # Barra de progreso
        exit_w = 90
        prog_x = sx + 10
        prog_w = W - prog_x - exit_w - 16
        prog_track = pygame.Rect(prog_x, cy - 4, prog_w, 8)
        pygame.draw.rect(surf, (40, 30, 60, 220), prog_track, border_radius=4)

        elapsed = rr.elapsed_s
        total = rr.total_s or 1.0
        fill_w = max(8, int(prog_track.width * min(elapsed / total, 1.0)))
        pygame.draw.rect(surf, REPLAY_ACCENT,
                         pygame.Rect(prog_track.x, prog_track.y, fill_w, prog_track.height),
                         border_radius=4)

        # Etiqueta de tiempo
        def fmt_t(s):
            """Formatea segundos a M:SS."""
            return f"{int(s) // 60}:{int(s) % 60:02d}"

        time_lbl = self.fonts["small"].render(
            f"{fmt_t(elapsed)} / {fmt_t(total)}", True, (190, 170, 210)
        )
        surf.blit(time_lbl, (prog_track.x, prog_track.bottom + 4))

        # Boton salir
        exit_rect = pygame.Rect(W - exit_w - 10, by + 8, exit_w, 40)
        pygame.draw.rect(surf, (60, 30, 30, 220), exit_rect, border_radius=8)
        exit_lbl = self.fonts["label"].render("Salir", True, (220, 90, 90))
        surf.blit(exit_lbl, exit_lbl.get_rect(center=exit_rect.center))
        self.rects["rp_exit"] = exit_rect

    def _draw_status_bar(self, surf, W, H, ctx):
        """Dibuja la barra de estado inferior con informacion del puerto, Hz y camara.

        En modo replay muestra el indicador REPLAY con nombre del participante y archivo.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
            ctx: Diccionario de contexto con 'connected', 'port', 'baud', 'rate_hz',
                'using_placeholder'.
        """
        bar_rect = pygame.Rect(0, H - STATUS_BAR_HEIGHT, W, STATUS_BAR_HEIGHT)
        pygame.draw.rect(surf, (10, 12, 20, 200), bar_rect)

        if self._replay_mode and self._replay_ref is not None:
            rr = self._replay_ref
            dot = self.fonts["label"].render("◉ REPLAY", True, REPLAY_ACCENT)
            surf.blit(dot, (10, bar_rect.y + 3))
            info = (
                f"  {rr.participant or '?'}  |  {rr.port}  |  "
                f"{'▶' if rr.playing else '⏸'}  |  {rr.speed}x  |  "
                f"Camara: {self.camera_profile}"
            )
            info_lbl = self.fonts["small"].render(info, True, (190, 170, 210))
            surf.blit(info_lbl, (10 + dot.get_width(), bar_rect.y + 3))
            return

        dot_color = (60, 200, 120) if ctx.get("connected") else (220, 90, 90)
        pygame.draw.circle(surf, dot_color, (16, bar_rect.centery), 6)

        placeholder_warn = "  |  MODELO PLACEHOLDER" if ctx.get("using_placeholder") else ""
        text = (
            f"Puerto: {ctx.get('port') or '--'}  |  Baud: {ctx.get('baud')}  |  "
            f"{ctx.get('rate_hz', 0):4.1f} Hz  |  Camara: {self.camera_profile}  |  "
            f"Config: {CFG.path}{placeholder_warn}"
        )
        label = self.fonts["small"].render(text, True, (170, 175, 185))
        surf.blit(label, (28, bar_rect.y + 2))

    def _draw_countdown(self, surf, W, H):
        """Dibuja el overlay de cuenta regresiva centrado en la ventana.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
        """
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 140))
        surf.blit(overlay, (0, 0))

        number = max(0, int(self.countdown["remaining"]) + 1)
        num_surf = self.fonts["countdown"].render(str(number), True, self.colors["accent"])
        surf.blit(num_surf, num_surf.get_rect(center=(W // 2, H // 2 - 30)))

        label_surf = self.fonts["title"].render(self.countdown["label"], True, self.colors["text"])
        surf.blit(label_surf, label_surf.get_rect(center=(W // 2, H // 2 + 70)))

    def _draw_modal(self, surf, W, H):
        """Dibuja el dialogo modal activo segun su modo.

        Modos soportados: 'session', 'confirm', 'summary', 'log_select'.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
        """
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((5, 6, 12, 180))
        surf.blit(overlay, (0, 0))

        if self.modal["mode"] == "summary":
            self._draw_summary_content(surf, W, H)
            return

        if self.modal["mode"] == "log_select":
            self._draw_log_select_modal(surf, W, H)
            return

        box_w, box_h = 420, 180
        box_rect = pygame.Rect((W - box_w) // 2, (H - box_h) // 2, box_w, box_h)
        pygame.draw.rect(surf, (24, 28, 42, 255), box_rect, border_radius=10)
        pygame.draw.rect(surf, self.colors["accent"], box_rect, 2, border_radius=10)

        if self.modal["mode"] == "session":
            title = self.fonts["title"].render("Nombre del participante", True, self.colors["text"])
            surf.blit(title, (box_rect.x + 20, box_rect.y + 18))

            input_rect = pygame.Rect(box_rect.x + 20, box_rect.y + 60, box_w - 40, 32)
            pygame.draw.rect(surf, (10, 12, 20), input_rect, border_radius=4)
            pygame.draw.rect(surf, self.colors["accent"], input_rect, 1, border_radius=4)
            text_surf = self.fonts["label"].render(self.modal["text"] + "|", True, self.colors["text"])
            surf.blit(text_surf, (input_rect.x + 8, input_rect.y + 6))

            confirm_rect = pygame.Rect(box_rect.x + 20, box_rect.bottom - 50, 160, 36)
            cancel_rect = pygame.Rect(box_rect.right - 180, box_rect.bottom - 50, 160, 36)
        else:
            msg = self.fonts["label"].render(self.modal["message"], True, self.colors["text"])
            surf.blit(msg, msg.get_rect(center=(box_rect.centerx, box_rect.y + 50)))

            confirm_rect = pygame.Rect(box_rect.x + 20, box_rect.bottom - 50, 160, 36)
            cancel_rect = pygame.Rect(box_rect.right - 180, box_rect.bottom - 50, 160, 36)

        pygame.draw.rect(surf, self.colors["accent"], confirm_rect, border_radius=6)
        pygame.draw.rect(surf, (60, 64, 76), cancel_rect, border_radius=6)
        confirm_label = self.fonts["label"].render("Confirmar", True, (15, 18, 26))
        cancel_label = self.fonts["label"].render("Cancelar", True, self.colors["text"])
        surf.blit(confirm_label, confirm_label.get_rect(center=confirm_rect.center))
        surf.blit(cancel_label, cancel_label.get_rect(center=cancel_rect.center))

        self.rects["modal_confirm"] = confirm_rect
        self.rects["modal_cancel"] = cancel_rect

    def _draw_log_select_modal(self, surf, W, H):
        """Dibuja el modal de seleccion de archivo CSV para iniciar un replay.

        Muestra una lista scrollable de sesiones grabadas en logs/ con botones
        de confirmacion y cancelacion.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
        """
        box_w, box_h = 500, 310
        box_rect = pygame.Rect((W - box_w) // 2, (H - box_h) // 2, box_w, box_h)
        pygame.draw.rect(surf, (20, 14, 32, 255), box_rect, border_radius=10)
        pygame.draw.rect(surf, REPLAY_ACCENT, box_rect, 2, border_radius=10)

        pad = 20
        y = box_rect.y + pad

        title = self.fonts["title"].render("Seleccionar sesion para replay", True, REPLAY_ACCENT)
        surf.blit(title, (box_rect.x + pad, y))
        y += 30
        pygame.draw.line(surf, (80, 60, 100),
                         (box_rect.x + pad, y), (box_rect.right - pad, y), 1)
        y += 12

        # Lista de logs
        list_height = 160
        list_rect = pygame.Rect(box_rect.x + pad, y, box_w - 2 * pad, list_height)
        pygame.draw.rect(surf, (10, 8, 18, 220), list_rect, border_radius=6)
        self.rects["log_list"] = list_rect

        item_h = 26
        visible = list_height // item_h
        item_rects = []

        if not self.log_files:
            no_lbl = self.fonts["small"].render(
                "(no hay sesiones en logs/)", True, (130, 110, 150)
            )
            surf.blit(no_lbl, (list_rect.x + 12, list_rect.y + 12))
        else:
            for i in range(visible):
                idx = i + self.log_scroll
                if idx >= len(self.log_files):
                    break
                item_rect = pygame.Rect(
                    list_rect.x + 2, list_rect.y + 2 + i * item_h,
                    list_rect.width - 4, item_h - 2,
                )
                name = self.log_files[idx]
                if name == self.selected_log:
                    pygame.draw.rect(surf, REPLAY_ACCENT, item_rect, border_radius=4)
                    txt_color = (15, 10, 25)
                else:
                    txt_color = (200, 185, 220)
                lbl = self.fonts["small"].render(name, True, txt_color)
                surf.blit(lbl, (item_rect.x + 8, item_rect.y + 5))
                item_rects.append(item_rect)

        self.rects["log_items"] = item_rects
        y += list_height + 16

        # Indicador de scroll si hay mas archivos de los visibles
        if len(self.log_files) > visible:
            shown = f"{self.log_scroll + 1}-{min(self.log_scroll + visible, len(self.log_files))} de {len(self.log_files)}"
            scroll_lbl = self.fonts["small"].render(shown, True, (130, 110, 150))
            surf.blit(scroll_lbl, (list_rect.right - scroll_lbl.get_width() - 4, y - 14))

        # Botones
        confirm_enabled = self.selected_log is not None
        confirm_rect = pygame.Rect(box_rect.right - pad - 170, y, 170, 36)
        cancel_rect = pygame.Rect(box_rect.x + pad, y, 120, 36)

        pygame.draw.rect(surf, REPLAY_ACCENT if confirm_enabled else (50, 40, 65),
                         confirm_rect, border_radius=6)
        pygame.draw.rect(surf, (55, 58, 74), cancel_rect, border_radius=6)

        confirm_txt_color = (15, 10, 25) if confirm_enabled else (90, 80, 110)
        confirm_lbl = self.fonts["label"].render("Iniciar Replay", True, confirm_txt_color)
        cancel_lbl = self.fonts["label"].render("Cancelar", True, (170, 175, 185))
        surf.blit(confirm_lbl, confirm_lbl.get_rect(center=confirm_rect.center))
        surf.blit(cancel_lbl, cancel_lbl.get_rect(center=cancel_rect.center))

        self.rects["modal_confirm"] = confirm_rect
        self.rects["modal_cancel"] = cancel_rect

    def _draw_summary_content(self, surf, W, H):
        """Dibuja el contenido del modal de resumen de sesion.

        Muestra metadatos (participante, audio, duracion, muestras IMU) y una tabla
        con min/promedio/max por cada senal fisiologica registrada.

        Args:
            surf: Superficie destino.
            W: Ancho de la ventana en pixeles.
            H: Alto de la ventana en pixeles.
        """
        data = self.modal["data"]
        signals = data.get("signals", {})

        pad = 20
        line_h = 24
        signal_section_h = (50 + len(signals) * 26) if signals else 0
        box_w = 500
        box_h = pad + 30 + 14 + 4 * line_h + signal_section_h + 60
        box_rect = pygame.Rect((W - box_w) // 2, (H - box_h) // 2, box_w, box_h)

        pygame.draw.rect(surf, (24, 28, 42, 255), box_rect, border_radius=10)
        pygame.draw.rect(surf, self.colors["accent"], box_rect, 2, border_radius=10)

        y = box_rect.y + pad

        title = self.fonts["title"].render("Resumen de sesion", True, self.colors["accent"])
        surf.blit(title, (box_rect.x + pad, y))
        y += 30

        pygame.draw.line(surf, (80, 84, 100),
                         (box_rect.x + pad, y), (box_rect.right - pad, y), 1)
        y += 14

        lbl_x = box_rect.x + pad
        val_x = box_rect.x + pad + 175

        def meta_row(label, value):
            """Dibuja una fila etiqueta-valor en el modal de resumen."""
            nonlocal y
            surf.blit(self.fonts["small"].render(label, True, (140, 144, 156)), (lbl_x, y))
            surf.blit(self.fonts["label"].render(str(value), True, self.colors["text"]), (val_x, y))
            y += line_h

        meta_row("Participante", data.get("participant_name", "--"))
        meta_row("Audio", data.get("audio_file", "--"))
        meta_row("Duracion (grabacion)", f"{data.get('duration_s', 0.0):.1f} s")
        meta_row("Muestras IMU", str(data.get("imu_count", 0)))

        if signals:
            y += 8
            pygame.draw.line(surf, (80, 84, 100),
                             (box_rect.x + pad, y), (box_rect.right - pad, y), 1)
            y += 12

            x_key  = box_rect.x + pad
            x_min  = box_rect.x + pad + 90
            x_mean = box_rect.x + pad + 210
            x_max  = box_rect.x + pad + 330

            for header, x in [("Senal", x_key), ("Min", x_min), ("Prom", x_mean), ("Max", x_max)]:
                surf.blit(self.fonts["small"].render(header, True, (140, 144, 156)), (x, y))
            y += 20

            for key, stats in signals.items():
                surf.blit(self.fonts["label"].render(key, True, self.colors["text"]), (x_key, y))
                surf.blit(self.fonts["label"].render(f"{stats['min']:.3f}", True, self.colors["text"]), (x_min, y))
                surf.blit(self.fonts["label"].render(f"{stats['mean']:.3f}", True, self.colors["text"]), (x_mean, y))
                surf.blit(self.fonts["label"].render(f"{stats['max']:.3f}", True, self.colors["text"]), (x_max, y))
                y += 26

        confirm_rect = pygame.Rect(box_rect.centerx - 80, box_rect.bottom - 50, 160, 36)
        pygame.draw.rect(surf, self.colors["accent"], confirm_rect, border_radius=6)
        ok_label = self.fonts["label"].render("Aceptar", True, (15, 18, 26))
        surf.blit(ok_label, ok_label.get_rect(center=confirm_rect.center))
        self.rects["modal_confirm"] = confirm_rect
