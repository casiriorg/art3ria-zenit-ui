"""Entry point: inicializa threads, ventana pygame+OpenGL y el loop principal a 60 FPS."""

import os
import queue
import sys
import uuid
from datetime import datetime

import pygame
from pygame.locals import (
    DOUBLEBUF, OPENGL, QUIT, KEYDOWN,
    K_ESCAPE, K_r, K_SPACE, K_1, K_2, K_3,
)

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
import sounddevice as _sd
from scipy.io import wavfile as _wavfile

from config import CFG, abs_path, ensure_dirs
from serial_reader import SerialReader
from audio_player import AudioPlayer
from logger import CSVLogger
from replay_reader import ReplayReader
from renderer import (
    ObjModel, draw_axes, ensure_placeholder_obj,
    quat_mul, quat_conj, quat_to_matrix, apply_camera_profile,
)
from ui import AppUI


def upload_texture(tex_id, surface):
    """Sube una superficie pygame como textura OpenGL RGBA.

    Args:
        tex_id: ID de textura OpenGL previamente generado con glGenTextures.
        surface: Superficie pygame.Surface a cargar como textura.
    """
    W, H = surface.get_size()
    data = pygame.image.tostring(surface, "RGBA", True)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)


def draw_hud_quad(tex_id, W, H):
    """Dibuja la textura del HUD como quad en proyeccion ortografica a pantalla completa.

    Deshabilita el depth test durante el dibujado y restaura la proyeccion
    perspectiva al finalizar.

    Args:
        tex_id: ID de textura OpenGL con el HUD renderizado.
        W: Ancho de la ventana en pixeles.
        H: Alto de la ventana en pixeles.
    """
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


def _start_replay(log_name: str, ui: AppUI, audio: AudioPlayer):
    """Carga un archivo CSV y entra en modo replay.

    Reproduce el audio original de la sesion con sounddevice (sin countdown)
    si el WAV existe en assets/audio/. Aborta cualquier sesion de audio activa.

    Args:
        log_name: Nombre del archivo CSV (sin ruta) en la carpeta logs/.
        ui: Instancia del HUD para activar el modo replay.
        audio: AudioPlayer; se aborta si hay audio en curso.

    Returns:
        Instancia de ReplayReader lista para update(), o None si el CSV fallo.
    """
    log_path = os.path.join(abs_path(CFG.logs_folder), log_name)
    try:
        rr = ReplayReader(log_path)
    except Exception as e:
        print(f"[ERROR] No se pudo cargar el replay '{log_name}': {e}")
        return None

    audio.abort()

    wav_name = rr.audio_file
    if wav_name:
        wav_path = os.path.join(abs_path(CFG.audio_folder), wav_name)
        if os.path.exists(wav_path):
            try:
                sr, wav_data = _wavfile.read(wav_path)
                _sd.play(wav_data, sr)
                print(f"[replay] Audio: {wav_name}")
            except Exception as e:
                print(f"[WARN] Replay: no se pudo reproducir '{wav_name}': {e}")
        else:
            print(f"[WARN] Replay: audio '{wav_name}' no encontrado en assets/audio/")

    ui.set_replay_mode(True, rr)
    rr.play()
    print(f"[replay] '{log_name}'  {rr.total_s:.1f} s")
    return rr


def _stop_replay(ui: AppUI):
    """Sale del modo replay, detiene el audio direct y restaura colores normales.

    Args:
        ui: Instancia del HUD para desactivar el modo replay.
    """
    try:
        _sd.stop()
    except Exception:
        pass
    ui.set_replay_mode(False)
    print("[replay] Replay finalizado.")


def main():
    """Punto de entrada: inicializa todos los subsistemas y ejecuta el loop principal.

    Acepta un argumento de linea de comandos opcional con el puerto serial o socket
    (ej. 'COM11' o 'socket://127.0.0.1:9000').
    """
    ensure_dirs()
    ensure_placeholder_obj()

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

    bg_hex = CFG.ui["bg_color"].lstrip("#")
    _bg_r = int(bg_hex[0:2], 16) / 255
    _bg_g = int(bg_hex[2:4], 16) / 255
    _bg_b = int(bg_hex[4:6], 16) / 255
    _replay_bg = (0.07, 0.04, 0.11)  # tinte purpura oscuro para el modo replay

    glClearColor(_bg_r, _bg_g, _bg_b, 1.0)
    glViewport(0, 0, W, H)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, W / H, 0.1, 50.0)
    glMatrixMode(GL_MODELVIEW)

    hud_tex = glGenTextures(1)
    q_offset = (1.0, 0.0, 0.0, 0.0)

    estado = "waiting"
    countdown_remaining = 0.0
    replay_reader = None

    clock = pygame.time.Clock()
    running = True

    try:
        while running:
            dt = clock.tick(60) / 1000.0

            _replay_was_done = replay_reader is not None and replay_reader.done

            for ev in pygame.event.get():
                if ev.type == QUIT:
                    if ui.session_active:
                        ui.open_quit_confirm()
                    else:
                        running = False
                elif ev.type == KEYDOWN:
                    # Teclas de transporte del replay (solo activas sin modal abierto)
                    if replay_reader is not None and ui.modal is None:
                        if ev.key == K_SPACE:
                            replay_reader.toggle_play()
                            continue
                        if ev.key == K_1:
                            replay_reader.set_speed(0.5)
                            continue
                        if ev.key == K_2:
                            replay_reader.set_speed(1.0)
                            continue
                        if ev.key == K_3:
                            replay_reader.set_speed(2.0)
                            continue
                        if ev.key == K_ESCAPE:
                            _stop_replay(ui)
                            replay_reader = None
                            continue

                    if ev.key == K_ESCAPE and ui.modal is None:
                        if ui.session_active:
                            ui.open_quit_confirm()
                        else:
                            running = False
                    elif ev.key == K_r and ui.modal is None and replay_reader is None:
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

                elif action[0] == "START_REPLAY":
                    if replay_reader is not None:
                        _stop_replay(ui)
                    q_offset = (1.0, 0.0, 0.0, 0.0)
                    replay_reader = _start_replay(action[1], ui, audio)

                elif action[0] == "EXIT_REPLAY":
                    _stop_replay(ui)
                    replay_reader = None

                elif action[0] == "QUIT":
                    running = False

            # ---- Reiniciar audio si el replay se reinicio desde el final ----
            if _replay_was_done and replay_reader is not None and not replay_reader.done:
                wav_name = replay_reader.audio_file
                if wav_name:
                    wav_path = os.path.join(abs_path(CFG.audio_folder), wav_name)
                    if os.path.exists(wav_path):
                        try:
                            sr, wav_data = _wavfile.read(wav_path)
                            _sd.play(wav_data, sr)
                        except Exception as e:
                            print(f"[WARN] Replay: no se pudo reiniciar audio '{wav_name}': {e}")

            # ---- Procesar eventos del audio player ----
            while True:
                try:
                    ev_name, payload = audio.event_queue.get_nowait()
                except queue.Empty:
                    break
                if replay_reader is not None:
                    continue  # ignorar eventos de audio durante el replay
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

            # ---- Resumen de sesion ----
            while True:
                try:
                    summary = logger.summary_queue.get_nowait()
                    if summary:
                        ui.show_summary(summary)
                except queue.Empty:
                    break

            if ui.countdown is not None:
                countdown_remaining = max(0.0, countdown_remaining - dt)
                ui.set_countdown(ui.countdown["label"], countdown_remaining)

            # ---- Avanzar replay ----
            if replay_reader is not None:
                replay_reader.update()
                # Al terminar queda congelado en el ultimo frame; el usuario sale manualmente.

            # ---- Drenar muestras al logger (solo en sesion activa real, no replay) ----
            if ui.session_active and replay_reader is None:
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

            # ---- Fuente de datos activa: replay o hardware ----
            active_reader = replay_reader if replay_reader is not None else reader

            # ---- Render 3D ----
            if replay_reader is not None:
                glClearColor(*_replay_bg, 1.0)
            else:
                glClearColor(_bg_r, _bg_g, _bg_b, 1.0)
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            glLoadIdentity()
            glTranslatef(0.0, -0.3, -5.5)

            q_now, _ = active_reader.get_imu()
            q_rel = quat_mul(q_offset, q_now)
            rw, rx, ry, rz = q_rel
            q_rel = (rw, -rx, ry, -rz)

            profile = CFG.camera_profiles.get(ui.camera_profile, {})
            q_cam = apply_camera_profile(q_rel, profile)

            glMultMatrixf(quat_to_matrix(q_cam))
            draw_axes()
            model.draw()

            # ---- HUD ----
            signals = active_reader.get_signals()
            ui.update_signals(signals)
            ctx = {
                "connected": active_reader.connected,
                "port": active_reader.port,
                "baud": active_reader.baud,
                "rate_hz": active_reader.rate_hz(),
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
        if replay_reader is not None:
            try:
                _sd.stop()
            except Exception:
                pass
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
