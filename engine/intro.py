"""
intro.py
---------
Reproductor del video de INTRO (assets/video/intro.mp4 + assets/sounds/
intro.mp3, ver main.py) al arrancar el juego.

A propósito NO usa el mismo mecanismo que los escenarios en video
(engine/stage.py, Stage._load_video) -- ese decodifica TODOS los cuadros
de una sola vez y los guarda en memoria, algo que funciona bien para un
fondo de pelea corto (unos pocos segundos, en loop) pero sería
carísimo en RAM para un video de intro de casi 40 segundos a 720p
(miles de cuadros x varios MB cada uno). Acá se decodifica DE A UN
CUADRO POR VEZ, en tiempo real, a medida que se necesita -- igual que
cualquier reproductor de video normal.

El audio (voz/música del video) se separó a un .mp3 aparte al armar
esta versión (ver el .mp4 de assets/video/, que quedó sin pista de
audio) y se reproduce con el sistema de música de siempre
(SoundManager), en paralelo al video.

SINCRONIZACIÓN CON EL AUDIO: pygame no sabe reproducir un .mp4 con
audio y video sincronizados de forma nativa (no existe un "player"
integrado como en un reproductor de video de verdad) -- por eso el
audio se separó aparte. Al ppio esto avanzaba el video contando su
PROPIO tiempo (sumando el dt del loop del juego cuadro a cuadro), en
paralelo al audio, que se reproduce con el reloj de SDL -- dos relojes
INDEPENDIENTES que se van desfasando de a poco (cualquier cuadro que
tarde un poco de más en decodificarse suma atraso, y ese atraso se va
acumulando con el correr del video, notándose cada vez más). Por eso
ahora el video se sincroniza directamente contra
pygame.mixer.music.get_pos() (el reloj del audio, mucho más preciso y
estable) en vez de llevar su propio contador de tiempo: si el video
viene atrasado respecto al audio, salta directo los cuadros que hagan
falta para alcanzarlo (sin dibujarlos), en vez de dejar que la
diferencia se siga acumulando cuadro a cuadro.
"""

import os
import pygame

from engine import constants as C

VIDEO_PATH = os.path.join("assets", "video", "intro.mp4")
AUDIO_PATH = os.path.join("assets", "sounds", "intro.mp3")

# Tope de cuadros a saltear de una sola vez para "ponerse al día" con el
# audio -- si hubiera un atraso gigante (ej. la ventana estuvo
# minimizada un rato), evita quedar decodificando cientos de cuadros de
# golpe en un solo update() (que sería, en sí mismo, otro cuelgue).
MAX_CATCHUP_FRAMES = 6


class IntroPlayer:
    def __init__(self, path=VIDEO_PATH):
        self.frame = None
        self.done = False
        self._cap = None
        self._frame_interval = 1 / 30.0
        self._video_time = 0.0  # cuánto del video ya se mostró, en segundos
        self._accum = 0.0  # solo se usa como respaldo si no hay audio activo (ver update())

        try:
            import cv2
        except ImportError:
            print(
                "[AVISO] No está instalado 'opencv-python-headless', así que no "
                "se puede reproducir el video de intro. Corré: "
                "pip3 install opencv-python-headless --break-system-packages\n"
                "Se salta directo al menú."
            )
            self.done = True
            return

        if not os.path.isfile(path):
            self.done = True
            return

        self._cv2 = cv2
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            print(f"[AVISO] No pude abrir el video de intro '{path}'.")
            self.done = True
            return

        self._cap = cap
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        self._frame_interval = 1 / fps
        self._advance_frame()  # primer cuadro ya cargado, para no arrancar con un flash negro

    def _advance_frame(self):
        ok, frame = self._cap.read()
        if not ok:
            self.done = True
            return
        cv2 = self._cv2
        frame = cv2.resize(frame, (C.SCREEN_W, C.SCREEN_H))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self.frame = pygame.image.frombuffer(frame.tobytes(), (C.SCREEN_W, C.SCREEN_H), "RGB").convert()

    def update(self, dt):
        if self.done or self._cap is None:
            return

        audio_ms = -1
        try:
            if pygame.mixer.music.get_busy():
                audio_ms = pygame.mixer.music.get_pos()
        except pygame.error:
            audio_ms = -1  # sin mezclador de audio disponible (poco común, pero no debería trabar el video)
        if audio_ms >= 0:
            # Sincronizado contra el audio: avanza tantos cuadros como
            # hagan falta para alcanzar el punto del video que le
            # corresponde a este instante del audio (puede ser 0, 1, o
            # varios si el video viene atrasado).
            target_time = audio_ms / 1000.0
            caught_up = 0
            while (
                self._video_time + self._frame_interval <= target_time
                and not self.done
                and caught_up < MAX_CATCHUP_FRAMES
            ):
                self._video_time += self._frame_interval
                self._advance_frame()
                caught_up += 1
        else:
            # Sin audio activo (no se pudo cargar el .mp3, o el volumen
            # de música está en 0 -- OJO: get_busy() sigue dando True
            # con el volumen en 0, así que esto solo pasa si el audio
            # realmente no está sonando): respaldo de siempre, avanzar
            # por el tiempo del propio loop del juego.
            self._accum += dt
            if self._accum >= self._frame_interval:
                self._accum -= self._frame_interval
                self._video_time += self._frame_interval
                self._advance_frame()

    def draw(self, surface):
        if self.frame is not None:
            surface.blit(self.frame, (0, 0))
        else:
            surface.fill(C.DARK)

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
