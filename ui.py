"""HUD, panel lateral, controles de sesion y dialogos modales."""

import os
from collections import deque

import pygame

from config import CFG, abs_path

# Cuentas regresivas / countdown overlay
COUNTDOWN_FONT_SIZE = 140

# Barra de estado inferior
STATUS_BAR_HEIGHT = 24


def hex_to_rgb(hex_str: str):
    """Convierte '#RRGGBB' a tupla (r,g,b)."""
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


class Sparkline:
    """Historial de valores con normalizacion min/max deslizante, dibujable con lineas."""

    def __init__(self, maxlen: int):
        self.values = deque(maxlen=maxlen)

    def add(self, value: float):
        self.values.append(value)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, color):
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
    """Dibuja un icono de corazon con primitivas (sin depender de glifos de fuente)."""
    cx, cy = x + 13, y + 11
    pygame.draw.circle(surface, color, (cx - 5, cy), 6)
    pygame.draw.circle(surface, color, (cx + 5, cy), 6)
    pygame.draw.polygon(surface, color, [(cx - 10, cy + 2), (cx + 10, cy + 2), (cx, cy + 15)])


def _draw_hand_icon(surface, x, y, color):
    """Dibuja un icono de mano (GSR) con primitivas (sin depender de glifos de fuente)."""
    # palma
    pygame.draw.rect(surface, color, (x + 4, y + 12, 16, 11), border_radius=4)
    # dedos
    for fx, fh in ((x + 5, 9), (x + 9, 11), (x + 13, 11), (x + 17, 9)):
        pygame.draw.rect(surface, color, (fx, y + 12 - fh, 3, fh), border_radius=1)
    # pulgar
    pygame.draw.rect(surface, color, (x + 1, y + 15, 6, 4), border_radius=2)


ICON_DRAWERS = {
    "heart": _draw_heart_icon,
    "hands": _draw_hand_icon,
}


def _draw_triangle_icon(surface, center, size, color, direction="right"):
    """Triangulo de navegacion/play (sin depender de glifos como ◀ ▶)."""
    cx, cy = center
    h = size / 2
    if direction == "left":
        points = [(cx + h, cy - h), (cx + h, cy + h), (cx - h, cy)]
    else:
        points = [(cx - h, cy - h), (cx - h, cy + h), (cx + h, cy)]
    pygame.draw.polygon(surface, color, points)


def _draw_square_icon(surface, center, size, color):
    """Cuadrado de stop/abortar (sin depender del glifo ■)."""
    rect = pygame.Rect(0, 0, size, size)
    rect.center = center
    pygame.draw.rect(surface, color, rect, border_radius=2)


class SignalWidget:
    """Panel de senal principal (PPG/GSR): icono, valor numerico y sparkline."""

    def __init__(self, key: str, icon: str, color, fonts):
        self.key = key
        self.icon = icon
        self.color = color
        self.fonts = fonts
        self.sparkline = Sparkline(CFG.sparkline_window_size)

    def update(self, value):
        if value is not None:
            self.sparkline.add(value)

    def draw(self, surface: pygame.Surface, rect: pygame.Rect, value):
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
        self.countdown = None  # {"label": str, "remaining": float}
        self.action = None  # ("PLAY_REQUEST", participant_name) | ("ABORT",) | ("QUIT",)

        self.modal = None  # {"mode": "session"|"confirm", "text": str, "message": str}
        self.rects = {}

    # ------------------------------------------------------------------
    def _load_fonts(self):
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
        """Reescanea CFG.audio_folder buscando archivos .wav."""
        folder = abs_path(CFG.audio_folder)
        os.makedirs(folder, exist_ok=True)
        self.audio_files = sorted(
            f for f in os.listdir(folder) if f.lower().endswith(".wav")
        )
        if self.selected_audio not in self.audio_files:
            self.selected_audio = None
        self.audio_scroll = 0

    def selected_audio_path(self):
        if self.selected_audio is None:
            return None
        return os.path.join(abs_path(CFG.audio_folder), self.selected_audio)

    # ------------------------------------------------------------------
    def update_signals(self, signals: dict):
        """Empuja nuevas muestras a los sparklines de PPG/GSR conocidas."""
        for key, widget in self.signal_widgets.items():
            widget.update(signals.get(key))

    def set_countdown(self, label, remaining):
        self.countdown = {"label": label, "remaining": remaining} if label else None

    def set_session_active(self, active: bool):
        self.session_active = active

    def open_session_modal(self):
        self.modal = {"mode": "session", "text": ""}

    def open_quit_confirm(self):
        self.modal = {
            "mode": "confirm",
            "message": "Hay una sesion activa. Salir de todos modos?",
            "on_yes": "QUIT",
        }

    # ------------------------------------------------------------------
    def handle_event(self, event):
        """Procesa un evento pygame. Puede establecer self.action."""
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

        self._handle_session_buttons(pos)

    def _cycle_camera_profile(self, step):
        idx = self.camera_profiles.index(self.camera_profile)
        idx = (idx + step) % len(self.camera_profiles)
        self.camera_profile = self.camera_profiles[idx]

    def _handle_session_buttons(self, pos):
        play_rect = self.rects.get("play_btn")
        abort_rect = self.rects.get("abort_btn")
        if play_rect and play_rect.collidepoint(pos) and self._play_enabled():
            self.open_session_modal()
        elif abort_rect and abort_rect.collidepoint(pos) and self.session_active:
            self.action = ("ABORT",)

    def _play_enabled(self):
        return self.selected_audio is not None and not self.session_active

    def _handle_modal_event(self, event):
        mode = self.modal["mode"]
        if event.type == pygame.KEYDOWN:
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
        """Construye la superficie HUD completa para esta frame.

        ctx: {connected, port, baud, rate_hz, euler, signals, using_placeholder}
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
        x = W - 230
        y = 20
        for key, widget in self.signal_widgets.items():
            rect = pygame.Rect(x, y, 210, 80)
            widget.draw(surf, rect, signals.get(key))
            y += 90

    def _draw_side_panel(self, surf, W, H, ctx):
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

        surf.blit(panel, (toggle_rect.width, 0))

    def _draw_session_controls(self, surf, W, H):
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

    def _draw_status_bar(self, surf, W, H, ctx):
        bar_rect = pygame.Rect(0, H - STATUS_BAR_HEIGHT, W, STATUS_BAR_HEIGHT)
        pygame.draw.rect(surf, (10, 12, 20, 200), bar_rect)

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
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 140))
        surf.blit(overlay, (0, 0))

        number = max(0, int(self.countdown["remaining"]) + 1)
        num_surf = self.fonts["countdown"].render(str(number), True, self.colors["accent"])
        surf.blit(num_surf, num_surf.get_rect(center=(W // 2, H // 2 - 30)))

        label_surf = self.fonts["title"].render(self.countdown["label"], True, self.colors["text"])
        surf.blit(label_surf, label_surf.get_rect(center=(W // 2, H // 2 + 70)))

    def _draw_modal(self, surf, W, H):
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((5, 6, 12, 180))
        surf.blit(overlay, (0, 0))

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
