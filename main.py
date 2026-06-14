"""Entry point: inicializa threads, ventana pygame+OpenGL y el loop principal a 60 FPS."""

import queue
import sys
import uuid
from datetime import datetime

import pygame
from pygame.locals import DOUBLEBUF, OPENGL, QUIT, KEYDOWN, K_ESCAPE, K_r

from OpenGL.GL import (
    glClear, glClearColor, glEnable, glDisable, glLoadIdentity,
    glMultMatrixf, glTranslatef, glViewport,
    glOrtho, glTexCoord2f, glTexImage2D, glGenTextures, glBindTexture,
    glTexParameteri, glDeleteTextures, glPixelStorei, glMatrixMode,
    glColor4f, glBegin, glEnd, glVertex3f,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST,
    GL_QUADS, GL_PROJECTION, GL_MODELVIEW, GL_LIGHTING,
    GL_TEXTURE_2D, GL_RGBA, GL_UNSIGNED_BYTE, GL_LINEAR,
    GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, glBlendFunc,
    GL_UNPACK_ALIGNMENT,
)
from OpenGL.GLU import gluPerspective

from config import CFG, ensure_dirs
from serial_reader import SerialReader
from audio_player import AudioPlayer
from logger import CSVLogger
from renderer import (
    ObjModel, draw_axes, ensure_placeholder_obj,
    quat_mul, quat_conj, quat_to_matrix, apply_camera_profile,
)
from ui import AppUI


def upload_texture(tex_id, surface):
    """Sube una superficie pygame como textura OpenGL (RGBA)."""
    W, H = surface.get_size()
    data = pygame.image.tostring(surface, "RGBA", True)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)


def draw_hud_quad(tex_id, W, H):
    """Dibuja la textura del HUD como un quad en proyeccion ortografica de pantalla completa."""
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


def main():
    ensure_dirs()
    ensure_placeholder_obj()

    # Permite forzar el puerto serial (ej. con un puerto virtual de scripts/simulate_embedded.py):
    #   python main.py COM11
    port_override = sys.argv[1] if len(sys.argv) > 1 else None

    log_queue = queue.Queue()
    reader = SerialReader(port=port_override, log_queue=log_queue)
    audio = AudioPlayer()
    logger = CSVLogger()

    reader.start()
    audio.start()
    logger.start()

    pygame.init()
    W, H = CFG.ui["window_width"], CFG.ui["window_height"]
    pygame.display.set_caption("Visualizador IMU Biometrico")
    pygame.display.set_mode((W, H), DOUBLEBUF | OPENGL)

    ui = AppUI()
    model = ObjModel()

    glEnable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    bg = CFG.ui["bg_color"].lstrip("#")
    glClearColor(int(bg[0:2], 16) / 255, int(bg[2:4], 16) / 255, int(bg[4:6], 16) / 255, 1.0)
    glViewport(0, 0, W, H)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, W / H, 0.1, 50.0)
    glMatrixMode(GL_MODELVIEW)

    hud_tex = glGenTextures(1)
    q_offset = (1.0, 0.0, 0.0, 0.0)

    estado = "waiting"
    countdown_remaining = 0.0

    clock = pygame.time.Clock()
    running = True

    try:
        while running:
            dt = clock.tick(60) / 1000.0

            for ev in pygame.event.get():
                if ev.type == QUIT:
                    if ui.session_active:
                        ui.open_quit_confirm()
                    else:
                        running = False
                elif ev.type == KEYDOWN:
                    if ev.key == K_ESCAPE and ui.modal is None:
                        if ui.session_active:
                            ui.open_quit_confirm()
                        else:
                            running = False
                    elif ev.key == K_r and ui.modal is None:
                        q_now, _ = reader.get_imu()
                        q_offset = quat_conj(q_now)
                        print("[info] Orientacion centrada")
                        continue
                ui.handle_event(ev)

            # ---- Procesar acciones de la UI ----
            if ui.action is not None:
                action = ui.action
                ui.action = None
                if action[0] == "PLAY_REQUEST":
                    participant_name = action[1]
                    audio_file = ui.selected_audio
                    session_id = str(uuid.uuid4())
                    logger.start_session(participant_name, session_id, audio_file)
                    audio.play(ui.selected_audio_path())
                    ui.set_session_active(True)
                    estado = "waiting"
                elif action[0] == "ABORT":
                    audio.abort()
                    logger.abort()
                    ui.set_session_active(False)
                    ui.set_countdown(None, 0)
                elif action[0] == "QUIT":
                    running = False

            # ---- Procesar eventos del audio player ----
            while True:
                try:
                    ev_name, payload = audio.event_queue.get_nowait()
                except queue.Empty:
                    break
                if ev_name == "COUNTDOWN_PRE":
                    estado = "waiting"
                    countdown_remaining = float(payload)
                    ui.set_countdown("Preparando...", countdown_remaining)
                elif ev_name == "PLAYING":
                    estado = "record"
                    ui.set_countdown(None, 0)
                elif ev_name == "COUNTDOWN_POST":
                    estado = "waiting"
                    countdown_remaining = float(payload)
                    ui.set_countdown("Finalizando...", countdown_remaining)
                elif ev_name == "DONE":
                    logger.stop()
                    ui.set_session_active(False)
                    ui.set_countdown(None, 0)
                elif ev_name == "ABORTED":
                    ui.set_session_active(False)
                    ui.set_countdown(None, 0)

            if ui.countdown is not None:
                countdown_remaining = max(0.0, countdown_remaining - dt)
                ui.set_countdown(ui.countdown["label"], countdown_remaining)

            # ---- Drenar muestras hacia el logger ----
            if ui.session_active:
                while True:
                    try:
                        ts, data = log_queue.get_nowait()
                    except queue.Empty:
                        break
                    iso = datetime.fromtimestamp(ts).isoformat()
                    logger.log(iso, estado, data)
            else:
                while True:
                    try:
                        log_queue.get_nowait()
                    except queue.Empty:
                        break

            # ---- Render 3D ----
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()
            glTranslatef(0.0, -0.3, -5.5)

            q_now, _ = reader.get_imu()
            q_rel = quat_mul(q_offset, q_now)
            rw, rx, ry, rz = q_rel
            q_rel = (rw, -rx, ry, -rz)

            profile = CFG.camera_profiles.get(ui.camera_profile, {})
            q_cam = apply_camera_profile(q_rel, profile)

            glMultMatrixf(quat_to_matrix(q_cam))
            draw_axes()
            model.draw()

            # ---- HUD ----
            signals = reader.get_signals()
            ui.update_signals(signals)
            ctx = {
                "connected": reader.connected,
                "port": reader.port,
                "baud": reader.baud,
                "rate_hz": reader.rate_hz(),
                "signals": signals,
                "using_placeholder": model.using_placeholder,
            }
            hud_surface = ui.render(W, H, ctx)
            upload_texture(hud_tex, hud_surface)
            draw_hud_quad(hud_tex, W, H)

            pygame.display.flip()
    except KeyboardInterrupt:
        print("\n[info] Interrumpido (Ctrl+C). Cerrando...")
    finally:
        glDeleteTextures([hud_tex])
        model.destroy()
        reader.stop()
        audio.exit()
        logger.exit()
        logger.join()
        pygame.quit()
        print("Bye!")


if __name__ == "__main__":
    main()
