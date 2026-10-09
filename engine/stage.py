"""
stage.py
---------
Un "escenario" es un fondo, que ahora puede ser:
  - una imagen fija: .png / .jpg
  - un video: .mp4 / .mov / .webm / .avi / .mkv (necesita opencv-python-headless,
    ver más abajo)
  - un GIF animado: .gif (usa Pillow) -- formato viejo, ya no se usa para
    ninguno de los escenarios actuales (todos los animados pasaron a .mp4
    en V.0.40 para evitar el banding de paleta de 200 colores del GIF),
    pero el loader lo sigue soportando por si hiciera falta en el futuro.

Para agregar uno nuevo: poné el archivo en assets/stages/ y aparece solo en
la selección de escenario, sin tocar código.

DESDE V.0.40 opencv-python-headless DEJÓ DE SER OPCIONAL: los tres
escenarios animados (Box, Final Destination, Living Forest) son .mp4, así
que hace falta tenerlo instalado para que se vean animados (si falta, cada
uno cae al fondo gris de respaldo, ver requirements.txt).

OJO CON RENDIMIENTO EN LA RASPBERRY PI 3: los fondos de video/GIF se
decodifican una sola vez al cargar el escenario (todos los cuadros se
guardan en memoria y después se van mostrando en loop), así que un video
largo o en alta resolución puede tardar en cargar y usar bastante RAM.
Para la Pi 3 se recomienda: clips cortos (3-6 segundos), pocos FPS (10-15)
y, si es posible, achicar el video antes con ffmpeg, por ejemplo:

  ffmpeg -i original.mp4 -vf "fps=12,scale=480:-1" -t 5 -an escenario.mp4

DESDE V.0.44: los 3 escenarios en video que vienen con el juego (Box,
Final Destination, Living Forest) tienen DOS versiones del archivo:
  - "Box.mp4" (640x360) -- la que se usa siempre en 540p y 720p.
  - "Box_1080p.mp4" (1280x720) -- SOLO se usa si la resolución activa
    (Opciones > Resolución) es 1080p.
El costo de decodificar H.264 escala fuerte con la resolución del video
FUENTE, no tanto con a qué tamaño se lo reescala después -- por eso a
540p/720p conviene la fuente chica (mucho más rápida de decodificar, y
al reescalarla para arriba no se nota borrosa en una pantalla más chica
de todos modos) y recién a 1080p vale la pena pagar el costo de la
fuente grande para que no se note el escalado 3x de una fuente de
640x360. Bajó de ~11s a ~2.5s el total de los 3 al entrar a Elegí el
Escenario, EN 540p/720p (que es la resolución por default, "720p"); a
1080p sigue tardando como antes porque ahí se decodifica la variante
grande. Si se agrega un escenario en video nuevo y se quiere el mismo
trato, seguir esta convención de nombres (archivo base chico + variante
"_1080p" opcional al lado, mismo nombre + esa terminación antes de la
extensión) -- ver _resolve_video_source() más abajo. Si no se agrega la
variante "_1080p", el escenario simplemente usa la fuente chica también
a 1080p (se ve un poco menos nítido ahí, pero funciona igual).
"""

import glob
import os
import pygame

from engine import constants as C

IMAGE_EXTS = (".png", ".jpg", ".jpeg")
GIF_EXTS = (".gif",)
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".avi", ".mkv")
ALL_STAGE_EXTS = IMAGE_EXTS + GIF_EXTS + VIDEO_EXTS

DEFAULT_ANIM_FPS = 15
# Antes esto guardaba cada cuadro a RESOLUCIÓN DE PANTALLA COMPLETA
# (hasta 1280x720), y con el límite de 90 cuadros (~6s a 15fps) el
# video se cortaba corto siempre, sin importar cuánto durara el
# archivo fuente (bug reportado: "¿No pueden durar el largo del video
# original en bucle?"). El problema de fondo: a resolución de pantalla
# completa, un video de 160s a 15fps pesaría ~6GB SOLO ese escenario
# -- inviable en cualquier máquina, ni hablar de la Raspberry Pi 3.
#
# Ahora los cuadros se guardan MÁS CHICOS (VIDEO_STORE_W de ancho, ver
# más abajo) y se escalan para arriba recién al dibujar (ver
# AnimatedBackground.draw) -- igual que ya se hacía con la fuente
# chica (640x360) vs la variante "_1080p" para decodificar más rápido,
# pero ahora aplicado también a cuánto se GUARDA en memoria una vez
# decodificado. Con eso, un video entero de 2:40 (Final Destination)
# entra en un presupuesto razonable (~475MB a 8fps) en vez de gigas --
# y ya no hace falta cortar el clip a unos pocos segundos para que
# quepa: dura lo mismo que el archivo original, completo, en bucle.
VIDEO_STORE_W = 480
VIDEO_ANIM_FPS = 8  # más bajo que DEFAULT_ANIM_FPS -- clips largos a resolución de pantalla completa Y a 15fps no entraban en memoria
MAX_VIDEO_FRAMES = 2000  # tope de seguridad (a 8fps, ~4 minutos) -- ya no pensado para cortar el video, sólo para no colgarse con un archivo gigante por error

# Escenario secreto (referencia al "Final Destination" de Smash Bros): no
# aparece en el selector normal ni en el sorteo al azar. Se elige con un
# gesto especial (ver StageSelect en menu.py) o queda fijo en el piso
# final de la Torre (ver tower.py).
SECRET_FINAL_DESTINATION = "Final Destination"
SECRET_STAGES = {SECRET_FINAL_DESTINATION.lower()}


def list_stages(include_secret=False):
    paths = []
    for ext in ALL_STAGE_EXTS:
        paths += glob.glob(os.path.join(C.STAGES_DIR, f"*{ext}"))
    # Los archivos "*_1080p.ext" son la variante en alta resolución de un
    # video que YA está listado con su nombre normal (ver _resolve_video_source)
    # -- no son escenarios aparte, hay que sacarlos de la lista para que
    # no aparezcan duplicados en el selector.
    paths = [p for p in paths if not _is_hd_variant(p)]
    paths = sorted(paths)
    if not include_secret:
        paths = [p for p in paths if display_name(p).lower() not in SECRET_STAGES]
    return paths


def _is_hd_variant(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.lower().endswith("_1080p")


def _resolve_video_source(path):
    """Para un video de escenario 'Box.mp4' (la fuente chica, 640x360,
    la que se usa siempre por default), busca si existe al lado
    'Box_1080p.mp4' (la variante en alta resolución, 1280x720) -- y la
    devuelve en su lugar SOLO si la resolución activa es 1080p. A
    540p/720p una fuente de 640x360 ya se ve nítida de sobra (se achica
    o casi no se agranda) y decodifica mucho más rápido; a 1080p el
    salto de 640x360 a 1920x1080 (3x) sí se nota borroso, así que ahí
    vale la pena pagar el decode más lento a cambio de más nitidez."""
    if C.RESOLUTION != "1080p":
        return path
    base, ext = os.path.splitext(path)
    hd_path = f"{base}_1080p{ext}"
    return hd_path if os.path.isfile(hd_path) else path


def get_secret_stage(name=SECRET_FINAL_DESTINATION):
    """Devuelve la ruta del escenario secreto pedido (ej. 'Final Destination'),
    o None si no está el archivo en assets/stages/. Comparación por nombre
    mostrado, sin importar mayúsculas ni extensión (.gif/.mp4/etc)."""
    for ext in ALL_STAGE_EXTS:
        for path in glob.glob(os.path.join(C.STAGES_DIR, f"*{ext}")):
            if display_name(path).lower() == name.lower():
                return path
    return None


def find_stage_music(image_path):
    """Busca un archivo de música con el MISMO nombre que el escenario (ej:
    stage_atardecer.mp4 -> stage_atardecer.ogg/.mp3/.wav) en la misma
    carpeta assets/stages/."""
    base, _ = os.path.splitext(image_path)
    for ext in ("ogg", "mp3", "wav"):
        candidate = f"{base}.{ext}"
        if os.path.isfile(candidate):
            return candidate
    return None


MAX_WORLD_W_MULT = 6  # tope de ancho de mundo relativo a la pantalla, ver _target_world_w


def _target_world_w(src_w, src_h):
    """A partir del tamaño NATIVO de un archivo de escenario (foto, o un
    cuadro de GIF/video), calcula cuántos píxeles de MUNDO le
    corresponden a lo ancho -- escalando por altura a C.SCREEN_H y
    dejando que el aspecto real del archivo decida si el escenario
    scrollea o no (cámara estilo Mortal Kombat: la pantalla siempre
    muestra una ventana de 16:9, pero el escenario de fondo puede ser
    más panorámico -- ver Stage.get_camera_x).

    Un archivo 16:9 (misma proporción que la pantalla) da exactamente
    C.SCREEN_W -- ningún escenario "de siempre" cambia de comportamiento.
    Uno más panorámico (ej. 40:9) da un mundo más ancho que la pantalla,
    habilitando el scroll. Nunca da un mundo más angosto que la pantalla
    (un escenario más 'cuadrado' que 16:9 simplemente se estira para
    llenarla, como pasaba antes de que existiera esta cuenta)."""
    if not src_w or not src_h:
        return C.SCREEN_W
    w = round(src_w * C.SCREEN_H / src_h)
    cap = C.SCREEN_W * MAX_WORLD_W_MULT
    if w > cap:
        print(
            f"[AVISO] Un escenario pidió un mundo de {w}px de ancho (más de "
            f"{MAX_WORLD_W_MULT}x la pantalla) -- se lo recorta a {cap}px "
            f"para no gastar memoria de más."
        )
        w = cap
    return max(C.SCREEN_W, w)


def display_name(path):
    """Nombre lindo para mostrar en el selector, sin extensión ni prefijo
    'stage_'."""
    name = os.path.splitext(os.path.basename(path))[0]
    if name.lower().startswith("stage_"):
        name = name[6:]
    name = name.replace("_", " ").strip()
    if not name:
        return name
    # .title() normal converte CUALQUIER palabra a "Primera letra
    # mayúscula, resto minúscula" -- lo cual le hace mal a una sigla ya
    # en mayúsculas como "II" (numeral romano, ej. "Dust II"), que
    # terminaba mostrada como "Ii". Las palabras que YA vienen enteras
    # en mayúsculas en el nombre de archivo se dejan tal cual; el resto
    # se sigue titulando como siempre.
    words = [w if (w.isupper() and len(w) > 1) else w.title() for w in name.split(" ")]
    return " ".join(words)


# Escenarios cuyo video de origen NO cierra bien el loop (el último cuadro
# no se parece al primero, entonces se nota un "salto" feo al reiniciar).
# Para estos, en vez de repetir siempre para adelante, se reproduce en
# "ida y vuelta" (adelante, atrás, adelante, atrás...) -- así nunca hay
# un corte abrupto, el video simplemente se revierte. Comparación por
# nombre mostrado (sin mayúsculas).
#
# Pedido explícito de Joaquín: Box y Living Forest cierran bien en loop
# NORMAL hacia adelante (corte directo, sin fundido -- los archivos que
# manda ya vienen pensados para eso); Final Destination, en cambio,
# necesita el loop "boomerang" (adelante, atrás, adelante...).
PING_PONG_STAGES = {"final destination"}


class Stage:
    def __init__(self, path):
        self.image_path = path
        self.music_path = find_stage_music(path)
        self.frames = []
        self.frame_index = 0
        self.frame_timer = 0.0
        self.fps = DEFAULT_ANIM_FPS
        self.ping_pong = display_name(path).lower() in PING_PONG_STAGES
        self._direction = 1
        # Ancho del MUNDO en píxeles (puede ser más ancho que C.SCREEN_W
        # si el archivo fuente es más panorámico que 16:9, ej. un mapa
        # 40:9 -- ver _target_world_size() y get_camera_x() más abajo).
        # Por defecto, hasta que se calcule según el archivo real, es
        # igual a la pantalla (sin scroll posible).
        self.world_w = C.SCREEN_W
        # Posición X de la cámara -- la mantiene actualizada
        # main.update_camera() cuadro a cuadro (frenando a los dos
        # peleadores contra ESTA ventana, la del cuadro anterior, antes
        # de recalcularla -- ver ahí el porqué). Arranca centrada en
        # new_fighters() cuando empieza cada pelea/ronda.
        self.camera_x = 0
        # Si el video se guardó más chico que la pantalla (ver
        # VIDEO_STORE_W), acá se cachea el ÚLTIMO cuadro ya escalado
        # para arriba -- así draw() no tiene que volver a escalar en
        # cada cuadro de juego (60fps) si el video todavía sigue
        # mostrando el mismo cuadro (a 8fps, eso es la mayoría de las
        # veces).
        self._store_size = None
        self._scaled_cache_index = None
        self._scaled_cache_surf = None

        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in IMAGE_EXTS:
                raw = pygame.image.load(path).convert()
                self.world_w = _target_world_w(raw.get_width(), raw.get_height())
                self.frames = [pygame.transform.scale(raw, (self.world_w, C.SCREEN_H))]
            elif ext in GIF_EXTS:
                self.frames = self._load_gif(path)
            elif ext in VIDEO_EXTS:
                self.frames = self._load_video(path)
        except (pygame.error, OSError) as e:
            print(f"[AVISO] No pude cargar el escenario '{path}': {e}")

        if not self.frames:
            fallback = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
            fallback.fill((40, 40, 55))
            self.frames = [fallback]
            self.world_w = C.SCREEN_W

    def _load_gif(self, path):
        from PIL import Image

        frames = []
        img = Image.open(path)
        src_w, src_h = img.size
        self.world_w = _target_world_w(src_w, src_h)
        # Filtro NEAREST en vez del que usa PIL por default (BICUBIC,
        # bastante más lento) -- pero SOLO cuando el escalado a pantalla
        # es un múltiplo entero exacto (ej. 480px -> 960px, 2x limpio):
        # ahí no hay ninguna diferencia visual entre filtros (no hay
        # medios píxeles que interpolar) y se gana bastante velocidad de
        # carga. Si algún escenario nuevo viniera en otra resolución que
        # no escale entero, cae a BILINEAR (más rápido que el default de
        # PIL igual, sin verse en bloques).
        clean_2x = (self.world_w % src_w == 0) and (C.SCREEN_H % src_h == 0)
        resample = Image.NEAREST if clean_2x else Image.BILINEAR
        try:
            while True:
                frame = img.convert("RGB").resize((self.world_w, C.SCREEN_H), resample)
                surf = pygame.image.fromstring(frame.tobytes(), frame.size, "RGB")
                frames.append(surf.convert())
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        return frames

    def _load_video(self, path):
        try:
            import cv2
        except ImportError:
            print(
                f"[AVISO] '{path}' es un video, pero no está instalado 'opencv-python-headless'. "
                f"Corré: pip3 install opencv-python-headless --break-system-packages\n"
                f"Mientras tanto se usa un fondo gris de respaldo."
            )
            return []

        # A 1080p usamos la variante en alta resolución si existe (más
        # nítida, pero más lenta de decodificar) -- a 540p/720p la fuente
        # chica alcanza de sobra y carga mucho más rápido. Ver
        # _resolve_video_source() y el comentario grande al principio del
        # archivo.
        real_path = _resolve_video_source(path)
        cap = cv2.VideoCapture(real_path)
        if not cap.isOpened():
            print(f"[AVISO] No pude abrir el video '{real_path}'.")
            return []

        source_fps = cap.get(cv2.CAP_PROP_FPS) or 30
        sample_every = max(1, round(source_fps / VIDEO_ANIM_FPS))
        self.fps = source_fps / sample_every

        src_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or C.SCREEN_W
        src_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or C.SCREEN_H
        self.world_w = _target_world_w(src_w, src_h)

        # Los cuadros se GUARDAN chicos (VIDEO_STORE_W de ancho, no
        # self.world_w x C.SCREEN_H de pantalla completa) y se escalan
        # para arriba recién al dibujar (ver draw(), con cache para no
        # repetir el escalado en cada cuadro de juego si el video
        # todavía no cambió de cuadro) -- ver la nota grande junto a
        # VIDEO_STORE_W más arriba sobre por qué (un video largo entero
        # a resolución de pantalla completa no entra en memoria ni en
        # una PC, mucho menos en la Raspberry Pi 3).
        store_w = min(VIDEO_STORE_W, self.world_w)
        store_h = round(store_w * C.SCREEN_H / self.world_w)
        self._store_size = (store_w, store_h)

        frames = []
        i = 0
        while len(frames) < MAX_VIDEO_FRAMES:
            ok, frame = cap.read()
            if not ok:
                break
            if i % sample_every == 0:
                frame = cv2.resize(frame, (store_w, store_h))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                surf = pygame.image.frombuffer(frame.tobytes(), (store_w, store_h), "RGB")
                frames.append(surf.convert())
            i += 1
        cap.release()
        return frames

    def update(self, dt):
        if len(self.frames) <= 1:
            return
        self.frame_timer += dt
        step = 1.0 / self.fps
        last = len(self.frames) - 1
        while self.frame_timer >= step:
            self.frame_timer -= step
            if not self.ping_pong:
                self.frame_index = (self.frame_index + 1) % len(self.frames)
                continue
            self.frame_index += self._direction
            if self.frame_index >= last:
                self.frame_index = last
                self._direction = -1
            elif self.frame_index <= 0:
                self.frame_index = 0
                self._direction = 1

    def get_camera_x(self, target_mid_x):
        """Dado el punto que la cámara quiere centrar (normalmente el
        punto medio entre los dos personajes), devuelve la posición X
        (en píxeles de MUNDO) de la esquina izquierda de la ventana de
        cámara de C.SCREEN_W de ancho -- ya recortada para nunca mostrar
        más allá de los bordes del escenario. Si el escenario es 16:9
        normal (world_w == SCREEN_W), siempre da 0 (no hay margen para
        scrollear, se ve entero, como toda la vida)."""
        max_cam = max(0, self.world_w - C.SCREEN_W)
        cam_x = target_mid_x - C.SCREEN_W / 2
        return max(0, min(max_cam, cam_x))

    def draw(self, surface, camera_x=0):
        frame = self.frames[self.frame_index]
        if self._store_size is not None and frame.get_size() != (self.world_w, C.SCREEN_H):
            # El cuadro se guardó más chico que la pantalla (ver
            # VIDEO_STORE_W) -- hay que escalarlo para arriba antes de
            # dibujarlo. Se cachea por índice de cuadro para no volver
            # a escalar de nuevo mientras el video no cambie de cuadro
            # (el video anima mucho más lento que los 60fps del juego).
            if self._scaled_cache_index != self.frame_index:
                self._scaled_cache_surf = pygame.transform.smoothscale(frame, (self.world_w, C.SCREEN_H))
                self._scaled_cache_index = self.frame_index
            frame = self._scaled_cache_surf
        if self.world_w <= C.SCREEN_W:
            # Caso de siempre (16:9 normal): el cuadro YA mide exactamente
            # SCREEN_W, no hay nada que recortar.
            surface.blit(frame, (0, 0))
        else:
            area = pygame.Rect(int(camera_x), 0, C.SCREEN_W, C.SCREEN_H)
            surface.blit(frame, (0, 0), area=area)


class _StageThumbnail:
    """Objeto mínimo con la misma pinta que Stage para dibujar (frames +
    frame_index), usado por load_stage_thumbnail() -- no tiene .update(),
    porque el preview del selector de escenario nunca se anima (ver
    StageSelect._preview en engine/menu.py)."""

    def __init__(self, frame):
        self.frames = [frame]
        self.frame_index = 0

    def draw(self, surface):
        surface.blit(self.frames[0], (0, 0))


def _center_crop_to_screen(surface, world_w):
    """Recorta la franja central de SCREEN_W de ancho de una superficie
    de world_w de ancho -- para que la miniatura del selector muestre lo
    mismo que se va a ver apenas arranca la pelea (la cámara arranca
    centrada), en vez de achatar todo el ancho panorámico dentro de un
    recuadro 16:9 (se vería estirado/aplastado)."""
    if world_w <= C.SCREEN_W:
        return surface
    x0 = (world_w - C.SCREEN_W) // 2
    cropped = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
    cropped.blit(surface, (0, 0), area=pygame.Rect(x0, 0, C.SCREEN_W, C.SCREEN_H))
    return cropped


def load_stage_thumbnail(path):
    """Versión LIVIANA de Stage, para el selector de escenario: decodifica
    UN SOLO cuadro (el primero) en vez de los ~90 de un Stage completo,
    así que es casi instantáneo incluso para los escenarios en video --
    antes, elegir personaje y llegar a "Elegí el Escenario" se sentía
    trabado porque ahí se decodificaban LOS TRES videos enteros de una
    (uno por cada escenario, para poder mostrarlos si el jugador
    navegaba hasta ellos), aunque en el selector nunca se ven animados
    (son un cuadro fijo, ver comentario en StageSelect._preview). El
    decode COMPLETO (todos los cuadros, para que se vea animado de
    verdad durante la pelea) recién pasa una sola vez, cuando se
    CONFIRMA el escenario elegido (Stage(path) normal, en main.py).

    Si el escenario es más panorámico que 16:9 (ver _target_world_w), la
    miniatura muestra la franja CENTRAL (lo mismo que se ve apenas
    arranca la pelea, ya que la cámara arranca centrada), no todo el
    ancho estirado."""
    ext = os.path.splitext(path)[1].lower()
    frame = None
    try:
        if ext in IMAGE_EXTS:
            raw = pygame.image.load(path).convert()
            world_w = _target_world_w(raw.get_width(), raw.get_height())
            scaled = pygame.transform.scale(raw, (world_w, C.SCREEN_H))
            frame = _center_crop_to_screen(scaled, world_w)
        elif ext in GIF_EXTS:
            from PIL import Image

            img = Image.open(path)
            img.seek(0)
            world_w = _target_world_w(img.width, img.height)
            rgb = img.convert("RGB").resize((world_w, C.SCREEN_H), Image.BILINEAR)
            scaled = pygame.image.fromstring(rgb.tobytes(), rgb.size, "RGB").convert()
            frame = _center_crop_to_screen(scaled, world_w)
        elif ext in VIDEO_EXTS:
            try:
                import cv2
            except ImportError:
                frame = None
            else:
                real_path = _resolve_video_source(path)
                cap = cv2.VideoCapture(real_path)
                if cap.isOpened():
                    ok, raw_frame = cap.read()
                    if ok:
                        src_h, src_w = raw_frame.shape[:2]
                        world_w = _target_world_w(src_w, src_h)
                        raw_frame = cv2.resize(raw_frame, (world_w, C.SCREEN_H))
                        raw_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2RGB)
                        scaled = pygame.image.frombuffer(
                            raw_frame.tobytes(), (world_w, C.SCREEN_H), "RGB"
                        ).convert()
                        frame = _center_crop_to_screen(scaled, world_w)
                cap.release()
    except (pygame.error, OSError) as e:
        print(f"[AVISO] No pude generar la miniatura de '{path}': {e}")
    if frame is None:
        frame = pygame.Surface((C.SCREEN_W, C.SCREEN_H))
        frame.fill((40, 40, 55))
    return _StageThumbnail(frame)
