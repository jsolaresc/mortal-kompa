"""
ui.py
------
Barras de vida, timer, nombres, carga del especial y textos de round
(¡FIGHT!, K.O., etc).

Todos los elementos visuales de esta pantalla se pueden REEMPLAZAR poniendo
un PNG en assets/ui/ con el nombre indicado abajo. Si el archivo no existe,
el juego dibuja una versión genérica por código (así nunca se rompe):

  assets/ui/title_background.png   -> fondo de la pantalla de título
  assets/ui/title_logo.png         -> logo/título (reemplaza el texto)
  assets/ui/healthbar_frame.png    -> marco decorativo sobre la barra de vida
                                       (centro transparente para que se vea
                                       el relleno de color)
  assets/ui/timer_container.png    -> fondo detrás del número del timer
  assets/ui/ko_banner.png          -> cartel que se muestra en vez de "K.O."
  assets/ui/icon.png               -> ícono de la ventana del juego
"""

import glob
import os
import random
import pygame
from engine import constants as C
from engine.stage import Stage, ALL_STAGE_EXTS, _cover
from engine import touch as touch_mod


def round_image_corners(img, radius):
    """Devuelve una COPIA de 'img' con las 4 esquinas recortadas en
    redondo (mismo 'radius' que el marco/recuadro donde se la vaya a
    mostrar), para que la miniatura no tenga esquinas cuadradas
    asomando fuera de un contenedor con bordes redondeados (selección
    de personajes, Torre de Batalla). No modifica la imagen original."""
    img = img.convert_alpha()
    w, h = img.get_size()
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    result = img.copy()
    result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return result

UI_ASSETS_DIR = os.path.join("assets", "ui")
TITLE_BG_DIR = os.path.join(UI_ASSETS_DIR, "title_background")
BUTTON_ICON_DIR = os.path.join(UI_ASSETS_DIR, "buttons")

# Layout del HUD (con más aire entre elementos que antes). Calibrado en
# espacio base (960x540) -- C.scaled() lo lleva a la resolución real.
HUD_MARGIN = C.scaled(30)
HUD_DOTS_Y = C.scaled(14)
HUD_BAR_Y = C.scaled(36)
HUD_BAR_H = C.scaled(26)
HUD_NAME_Y = HUD_BAR_Y + HUD_BAR_H + C.scaled(16)


def _try_load(filename):
    path = os.path.join(UI_ASSETS_DIR, filename)
    if os.path.isfile(path):
        return pygame.image.load(path).convert_alpha()
    return None


def load_icon():
    """Ícono de la ventana (barra de título / taskbar). Devuelve None si no
    hay assets/ui/icon.png todavía."""
    return _try_load("icon.png")


class UI:
    # Fuente Black (peso 900, la variable más pesada/imponente de la
    # familia) empaquetada directo en el proyecto -- así se ve IGUAL en
    # cualquier máquina (Windows/Mac/Linux/Raspberry Pi) sin depender de
    # qué fuentes tenga instaladas el sistema. Si por algún motivo el
    # archivo no está, cae a una negrita real del sistema, y como último
    # recurso a la negrita "sintética" de pygame (bold=True) -- nunca
    # rompe.
    BUNDLED_FONT = os.path.join(UI_ASSETS_DIR, "..", "fonts", "Roboto-Black.ttf")
    TITLE_FONT_CANDIDATES = [
        BUNDLED_FONT,
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
    ]

    @classmethod
    def _load_title_font(cls, size):
        for path in cls.TITLE_FONT_CANDIDATES:
            if os.path.isfile(path):
                return pygame.font.Font(path, size)
        return pygame.font.SysFont("arial", size, bold=True)

    def __init__(self):
        # Todo el texto de la interfaz (menús, títulos, marcadores,
        # pie de página) usa la misma familia Black -- antes era Arial
        # con negrita sintética, se ve mucho menos marcada a estos
        # tamaños.
        # Tamaños calibrados en espacio base (960x540) -- C.scaled() los
        # lleva a la resolución real para que el texto se vea igual de
        # grande en relación a la pantalla, sea cual sea C.RESOLUTION
        # (importante para que se lea bien de lejos en un TV grande).
        self.font_big = self._load_title_font(C.scaled(64))
        self.font_med = self._load_title_font(C.scaled(30))
        self.font_small = self._load_title_font(C.scaled(20))
        self.font_tiny = self._load_title_font(C.scaled(15))
        self.font_footer = self._load_title_font(C.scaled(16))  # -20% de font_small (20px), para textos de instrucciones
        # Fuente Bold real, más grande, solo para TÍTULOS de pantalla
        # (menús, "PISO X DE Y", etc.) -- que se vean imponentes de verdad.
        self.font_title = self._load_title_font(C.scaled(38))
        self._title_font_cache = {}
        self._icon_cache = {}
        self._scaled_cache = {}  # (id_imagen, tamaño) -> superficie ya escalada (HUD)
        # En la versión táctil (Android) los 5 "pips" de carga del
        # Especial NO se dibujan en el HUD: los reemplaza el propio botón
        # de Especial, que se va llenando (ver engine/touch.py).
        self.show_special_pips = True
        # Versión táctil: listas de menú con opciones más grandes, cada una
        # en su propia "pastilla" para tocarla directo con el dedo, y sin
        # pies de página de teclas (ver _draw_touch_list / draw_footer_mixed).
        self.touch_lists = False
        self._list_font = None

        # Assets editables (None si el usuario todavía no los reemplazó)
        # Fondo de título: si hay archivos en assets/ui/title_background/
        # (pueden ser imágenes, GIFs o videos, mezclados), se elige UNO AL
        # AZAR por partida -- reusa la misma carga que los escenarios, así
        # que soporta lo mismo (si hay uno solo, obviamente siempre se ve
        # ese). Si la carpeta no existe o está vacía, cae al viejo
        # title_background.png único, y si tampoco existe, fondo oscuro liso.
        self.title_bg_anim = self._load_random_title_background()
        self.title_background = None if self.title_bg_anim else _try_load("title_background.png")
        self.title_logo = _try_load("title_logo.png")
        # healthbar_frame.png y timer_container.png: el tamaño final en
        # pantalla de estos dos NO depende de su tamaño nativo (se
        # estiran siempre a la medida ya calculada de la barra de vida y
        # del timer, ver draw_health_bar/draw_hud más abajo) -- por eso,
        # a diferencia de los "pips" un poco más abajo, achicar/agrandar
        # el archivo fuente no rompe nada ni pide tocar código: un PNG
        # más grande de fuente (están al doble del lienzo base, 1920x1080,
        # no 960x540 -- mismo motivo que los pips) simplemente le da más
        # detalle a pygame.transform.smoothscale para resolver hacia
        # abajo, y se ve más nítido en 1080p sin perder nada en 720p/540p.
        self.healthbar_frame = _try_load("healthbar_frame.png")
        self.timer_container = _try_load("timer_container.png")
        self.ko_banner = _try_load("ko_banner.png")
        # Fondos editables de las pantallas de selección de personaje y
        # de la Torre de Batalla -- antes eran gris liso siempre, ahora
        # si existe el archivo se usa, si no, cae al gris de antes (nunca
        # rompe si todavía no lo reemplazaron).
        self.character_selection_background = _try_load("character_selection_background.png")
        self.tower_background = _try_load("tower_background.png")
        # Pantalla de carga (mientras se decodifica el video de un
        # escenario, ver draw_loading_screen más abajo). Poné acá
        # "loading.png" (o más adelante un GIF animado, mismo sistema
        # que title_background) para reemplazar el fondo oscuro liso +
        # texto "Cargando..." de por defecto.
        self.loading_background = _try_load("loading.png")

        # Puntitos de ronda ganada y de golpes para el special, como PNG
        # editables (para que se puedan re-skinear sin tocar código). Si
        # alguno no está, se sigue dibujando el circulito de toda la vida
        # como respaldo -- nunca rompe.
        #
        # El PNG fuente está diseñado al DOBLE del lienzo base (1920x1080,
        # no 960x540) -- a propósito, para que en 1080p se dibuje casi 1
        # a 1 (nítido) y en 720p/540p se achique por código (una imagen
        # de más resolviéndose hacia ABAJO siempre se ve mejor que una
        # chica estirada hacia arriba). Antes el PNG SÍ estaba pensado a
        # escala base (960x540) y se multiplicaba por C.RES_SCALE directo
        # -- en 1080p (RES_SCALE=2) eso terminaba estirando al doble un
        # archivo ya de por sí chico (16x16/14x14), y se veía borroso
        # (bug reportado: "los PNG del HUD están algo chicos... al
        # escalar a 1080p no se ven bien"). Por eso acá se usa
        # RES_SCALE/2 -- para terminar en el MISMO tamaño en pantalla de
        # siempre, pero resolviendo desde una fuente más grande.
        def _scale_pip(img):
            if img is None:
                return None
            w, h = img.get_size()
            new_size = (max(1, round(w * C.RES_SCALE / 2)), max(1, round(h * C.RES_SCALE / 2)))
            return pygame.transform.smoothscale(img, new_size)

        self.round_pip_filled = _scale_pip(_try_load("round_pip_filled.png"))
        self.round_pip_empty = _scale_pip(_try_load("round_pip_empty.png"))
        self.special_pip_empty = _scale_pip(_try_load("special_pip_empty.png"))
        self.special_pip_filled = _scale_pip(_try_load("special_pip_filled.png"))
        self.special_pip_ready = _scale_pip(_try_load("special_pip_ready.png"))

    def _scaled(self, image, size):
        """smoothscale cacheado: varias piezas del HUD/fondos se
        reescalaban en CADA cuadro (60 veces por segundo) aunque el
        tamaño nunca cambia -- en un celular eso pesa bastante."""
        key = (id(image), size)
        surf = self._scaled_cache.get(key)
        if surf is None:
            surf = pygame.transform.smoothscale(image, size)
            self._scaled_cache[key] = surf
        return surf

    def _covered(self, image):
        """Fondo de pantalla completa SIN deformar: cubre todo el lienzo
        (aunque la pantalla sea más ancha que 16:9) recortando lo que
        sobra. Cacheado."""
        key = (id(image), "cover", C.SCREEN_W, C.SCREEN_H)
        surf = self._scaled_cache.get(key)
        if surf is None:
            surf = _cover(image, C.SCREEN_W, C.SCREEN_H, anchor_y=0.5)
            self._scaled_cache[key] = surf
        return surf

    def draw_screen_background(self, surface, image):
        """Dibuja 'image' (ya escalada a pantalla completa) de fondo, o
        el gris liso de siempre si todavía no existe ese archivo."""
        if image:
            surface.blit(self._covered(image), (0, 0))
        else:
            surface.fill(C.DARK)

    def draw_loading_screen(self, surface, text="Cargando..."):
        """Pantalla que se muestra justo antes de un trabajo que tarda
        (decodificar el video de un escenario, por ejemplo) para que no
        se sienta como que el juego se colgó. Usa assets/ui/loading.png
        si existe (poné ahí tu propio GIF/placeholder más adelante);
        si no, fondo oscuro liso + el texto."""
        self.draw_screen_background(surface, self.loading_background)
        self.draw_title(surface, text, y=C.SCREEN_H // 2)

    # ------------------------------------------------------------------
    def draw_health_bar(self, surface, x, y, width, height, ratio, flip=False):
        pygame.draw.rect(surface, C.BLACK, (x - 3, y - 3, width + 6, height + 6), border_radius=6)
        pygame.draw.rect(surface, C.GRAY, (x, y, width, height), border_radius=4)
        fill_w = int(width * max(0, ratio))
        color = C.GREEN if ratio > 0.5 else (C.YELLOW if ratio > 0.2 else C.RED)
        if flip:
            fill_rect = (x + width - fill_w, y, fill_w, height)
        else:
            fill_rect = (x, y, fill_w, height)
        pygame.draw.rect(surface, color, fill_rect, border_radius=4)

        if self.healthbar_frame:
            pad = C.scaled(10)
            frame_rect = pygame.Rect(x - pad, y - pad, width + pad * 2, height + pad * 2)
            scaled = self._scaled(self.healthbar_frame, frame_rect.size)
            surface.blit(scaled, frame_rect.topleft)

    def _draw_round_pip(self, surface, cx, cy, won):
        img = self.round_pip_filled if won else self.round_pip_empty
        if img:
            rect = img.get_rect(center=(cx, cy))
            surface.blit(img, rect)
        else:
            color = C.YELLOW if won else C.GRAY
            pygame.draw.circle(surface, color, (cx, cy), 6)

    def draw_special_pips(self, surface, x, y, hits_taken, required, align_right=False):
        """5 puntitos que se van llenando con los golpes recibidos; cuando
        están todos llenos, el especial está listo para usarse."""
        r = C.scaled(5)
        gap = C.scaled(18)  # separación entre puntitos (antes 14 -- pedido explícito: "separar ligeramente los special pips, 4px bastan")
        ready = hits_taken >= required
        for i in range(required):
            cx = x + i * gap if not align_right else x - (required - 1 - i) * gap
            filled = i < hits_taken
            img = self.special_pip_ready if ready else (self.special_pip_filled if filled else self.special_pip_empty)
            if img:
                rect = img.get_rect(center=(cx, y))
                surface.blit(img, rect)
            else:
                color = C.YELLOW if ready else (C.WHITE if filled else C.GRAY)
                pygame.draw.circle(surface, color, (cx, y), r)
                pygame.draw.circle(surface, C.BLACK, (cx, y), r, width=1)

    def draw_hud(self, surface, p1, p2, time_left, p1_wins, p2_wins):
        margin = HUD_MARGIN
        bar_w = C.SCREEN_W // 2 - margin - C.scaled(90)

        self.draw_health_bar(surface, margin, HUD_BAR_Y, bar_w, HUD_BAR_H, p1.health / p1.max_health, flip=False)
        self.draw_health_bar(
            surface, C.SCREEN_W - margin - bar_w, HUD_BAR_Y, bar_w, HUD_BAR_H,
            p2.health / p2.max_health, flip=True,
        )

        name1 = self.font_small.render(p1.name, True, C.WHITE)
        name2 = self.font_small.render(p2.name, True, C.WHITE)
        surface.blit(name1, (margin, HUD_NAME_Y))
        surface.blit(name2, (C.SCREEN_W - margin - name2.get_width(), HUD_NAME_Y))

        # Los 5 puntitos de special van en el MISMO renglón que el
        # nombre, pero en la otra punta de la barra de vida (si van
        # debajo del nombre se chocan con el texto). Para P1 (barra a la
        # izquierda) quedan pegados al borde DERECHO de su barra; para
        # P2 (barra a la derecha) quedan pegados al borde IZQUIERDO --
        # en los dos casos, lejos del nombre.
        pip_y = HUD_NAME_Y + name1.get_height() // 2
        pip_edge = C.scaled(3)
        if self.show_special_pips:
            self.draw_special_pips(
                surface, margin + bar_w - pip_edge, pip_y,
                p1.hits_taken_since_special, C.SPECIAL_HITS_REQUIRED, align_right=True,
            )
            self.draw_special_pips(
                surface, C.SCREEN_W - margin - bar_w + pip_edge, pip_y,
                p2.hits_taken_since_special, C.SPECIAL_HITS_REQUIRED,
            )

        # Rounds ganados (puntitos), separados del resto arriba de todo
        dot_margin, dot_gap = C.scaled(10), C.scaled(20)
        for i in range(C.ROUNDS_TO_WIN):
            self._draw_round_pip(surface, margin + dot_margin + i * dot_gap, HUD_DOTS_Y, i < p1_wins)
            self._draw_round_pip(surface, C.SCREEN_W - margin - dot_margin - i * dot_gap, HUD_DOTS_Y, i < p2_wins)

        if self.timer_container:
            cont = self._scaled(self.timer_container, (C.scaled(86), C.scaled(56)))
            rect = cont.get_rect(center=(C.SCREEN_W // 2, HUD_BAR_Y + HUD_BAR_H // 2))
            surface.blit(cont, rect)

        timer_text = self.font_med.render(str(max(0, int(time_left))), True, C.WHITE)
        trect = timer_text.get_rect(center=(C.SCREEN_W // 2, HUD_BAR_Y + HUD_BAR_H // 2))
        surface.blit(timer_text, trect)

    # ------------------------------------------------------------------
    def _load_random_title_background(self):
        """Busca imágenes/GIFs/videos en assets/ui/title_background/ y
        devuelve uno elegido al azar ya cargado (reusando Stage, que sabe
        leer los 3 formatos), o None si la carpeta no existe/está vacía."""
        if not os.path.isdir(TITLE_BG_DIR):
            return None
        candidates = []
        for ext in ALL_STAGE_EXTS:
            candidates += glob.glob(os.path.join(TITLE_BG_DIR, f"*{ext}"))
        if not candidates:
            return None
        chosen = random.choice(candidates)
        try:
            return Stage(chosen)
        except (pygame.error, OSError) as e:
            print(f"[AVISO] No pude cargar el fondo de título '{chosen}': {e}")
            return None

    def draw_title_background(self, surface, dt=1 / 60):
        if self.title_bg_anim:
            self.title_bg_anim.update(dt)
            self.title_bg_anim.draw(surface)
        elif self.title_background:
            surface.blit(self._covered(self.title_background), (0, 0))
        else:
            surface.fill(C.DARK)

    def draw_title_logo(self, surface):
        """Devuelve True si dibujó un logo propio (para que el llamador no
        dibuje también el texto de reemplazo)."""
        if self.title_logo:
            rect = self.title_logo.get_rect(center=(C.SCREEN_W // 2, 110))
            surface.blit(self.title_logo, rect)
            return True
        return False

    def draw_round_end_banner(self, surface, is_ko, is_draw=False):
        if is_draw:
            self.draw_center_text(surface, "EMPATE", C.YELLOW)
        elif is_ko and self.ko_banner:
            rect = self.ko_banner.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H // 2))
            surface.blit(self.ko_banner, rect)
        else:
            self.draw_center_text(surface, "K.O." if is_ko else "TIEMPO", C.RED)

    # ------------------------------------------------------------------
    def draw_center_text(self, surface, text, color=C.WHITE, y_offset=0):
        img = self.font_big.render(text, True, color)
        rect = img.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H // 2 + y_offset))
        surface.blit(img, rect)

    def draw_title(self, surface, text, y=40, color=None, x=None, size=None):
        """Título de pantalla (menús, 'SELECCIONÁ TU LUCHADOR', 'PISO X DE
        Y'...), con la fuente Bold real -- para que se vea imponente de
        verdad, no la negrita sintética de los textos comunes. Por
        defecto centrado en toda la pantalla; con 'x' se puede centrar
        sobre otra columna en particular, y con 'size' usar otro tamaño
        que el estándar (38px). Lleva una sombra negra suave (para que
        se siga leyendo bien incluso sobre fondos claros o con detalle,
        ya que estos títulos no siempre tienen una franja sólida atrás)."""
        color = color if color is not None else C.YELLOW
        x = x if x is not None else C.SCREEN_W // 2
        font = self.font_title
        if size is not None and size != 38:
            if size not in self._title_font_cache:
                self._title_font_cache[size] = self._load_title_font(size)
            font = self._title_font_cache[size]
        shadow = font.render(text, True, C.BLACK)
        shadow.set_alpha(140)
        offset = max(1, C.scaled(2))
        surface.blit(shadow, shadow.get_rect(center=(x + offset, y + offset)))
        img = font.render(text, True, color)
        surface.blit(img, img.get_rect(center=(x, y)))

    def draw_small_center(self, surface, text, y):
        img = self.font_small.render(text, True, C.WHITE)
        rect = img.get_rect(center=(C.SCREEN_W // 2, y))
        surface.blit(img, rect)

    def draw_footer(self, surface, text, y):
        """Como draw_small_center, pero con la fuente de instrucciones
        (20% más chica) -- para las líneas tipo 'J confirmar | K volver'."""
        img = self.font_footer.render(text, True, C.WHITE)
        rect = img.get_rect(center=(C.SCREEN_W // 2, y))
        surface.blit(img, rect)

    def _load_button_icon(self, filename, height=20):
        """Carga (con caché) un ícono de assets/ui/buttons/, escalado a
        una altura fija manteniendo proporción. None si no existe."""
        key = (filename, height)
        if key not in self._icon_cache:
            path = os.path.join(BUTTON_ICON_DIR, filename)
            if not os.path.isfile(path):
                self._icon_cache[key] = None
            else:
                img = pygame.image.load(path).convert_alpha()
                scale = height / img.get_height()
                new_size = (max(1, int(img.get_width() * scale)), height)
                self._icon_cache[key] = pygame.transform.smoothscale(img, new_size)
        return self._icon_cache[key]

    def draw_footer_mixed(self, surface, parts, y):
        """Como draw_footer, pero soporta mezclar íconos de botón reales
        (PNG) con texto en la misma línea -- 'parts' es una lista de
        ('icon', archivo, descripción) o ('text', etiqueta, descripción),
        ver input_manager.build_footer_parts(). Arma toda la línea y la
        centra como un conjunto."""
        if self.touch_lists:
            # Versión táctil: no hay teclas que explicar. Solo se deja una
            # ayuda cuando la pantalla se "toca para seguir".
            for kind, content, desc in parts:
                if content in ("OK",) and desc in ("continuar", "pelear"):
                    self.draw_touch_hint(surface, f"Tocá la pantalla para {desc}", y)
                    break
            return
        SEP = "   |   "
        pieces = []  # lista de superficies ya renderizadas, en orden
        icon_h = 20
        for i, (kind, content, desc) in enumerate(parts):
            if i > 0:
                pieces.append(self.font_footer.render(SEP, True, C.GRAY))
            icon = self._load_button_icon(content, icon_h) if kind == "icon" else None
            if icon:
                pieces.append(icon)
            else:
                label = content if kind == "text" else content.upper()
                pieces.append(self.font_footer.render(label, True, C.WHITE))
            pieces.append(self.font_footer.render(f" {desc}", True, C.WHITE))

        total_w = sum(p.get_width() for p in pieces)
        x = C.SCREEN_W // 2 - total_w // 2
        max_h = max((p.get_height() for p in pieces), default=0)
        for p in pieces:
            surface.blit(p, (x, y - max_h // 2 + (max_h - p.get_height()) // 2))
            x += p.get_width()

    def draw_overlay(self, surface, alpha=170):
        """Capa semitransparente oscura, para pantallas de pausa/opciones
        sobre el juego."""
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, alpha))
        surface.blit(overlay, (0, 0))

    def draw_menu_list(self, surface, title, items, selected_index, center_y=None, extra_lines=None):
        """Lista vertical simple para menúes (pausa, opciones, modos...).
        'items' es una lista de strings ya formateados (con su valor si
        corresponde, ej: 'Volumen música: 70%')."""
        center_y = center_y or C.SCREEN_H // 2
        if self.touch_lists:
            return self._draw_touch_list(surface, title, items, selected_index, center_y, extra_lines)
        start_y = center_y - (len(items) - 1) * 22

        # el título va SIEMPRE pegado arriba de la lista real (no a una
        # distancia fija de center_y) -- así nunca se pisan aunque la
        # lista tenga más o menos items. Si viene vacío, no se dibuja
        # nada pero la lista NO se mueve (sigue calculada desde center_y).
        if title:
            self.draw_title(surface, title, y=start_y - 55)

        hits = []
        for i, text in enumerate(items):
            color = C.YELLOW if i == selected_index else C.WHITE
            prefix = "> " if i == selected_index else "   "
            img = self.font_small.render(prefix + text, True, color)
            surface.blit(img, img.get_rect(center=(C.SCREEN_W // 2, start_y + i * 44)))
            hit = pygame.Rect(0, 0, max(img.get_width() + 80, 360), 44)
            hit.center = (C.SCREEN_W // 2, start_y + i * 44)
            hits.append((hit, i))
        # para poder TOCAR directamente una opción (versión táctil)
        touch_mod.set_list_hits(hits)

        if extra_lines:
            y = start_y + len(items) * 44 + 20
            for line in extra_lines:
                img = self.font_tiny.render(line, True, C.GRAY)
                surface.blit(img, img.get_rect(center=(C.SCREEN_W // 2, y)))
                y += 20

    # ------------------------------------------------------------------
    # Versión táctil
    # ------------------------------------------------------------------
    TOUCH_ROW_PITCH = 46   # espacio base (960x540) entre opciones
    TOUCH_ROW_H = 40       # alto base de cada "pastilla"

    def touch_list_height(self, count):
        return C.scaled(self.TOUCH_ROW_PITCH) * count

    def _draw_touch_list(self, surface, title, items, selected_index, center_y, extra_lines=None):
        if self._list_font is None:
            self._list_font = self._load_title_font(C.scaled(23))
        pitch = C.scaled(self.TOUCH_ROW_PITCH)
        row_h = C.scaled(self.TOUCH_ROW_H)
        start_y = center_y - (len(items) - 1) * pitch / 2
        if title:
            self.draw_title(surface, title, y=int(start_y - pitch / 2 - C.scaled(28)))
        imgs = []
        for i, text in enumerate(items):
            color = C.YELLOW if i == selected_index else C.WHITE
            imgs.append(self._list_font.render(text, True, color))
        pill_w = max([C.scaled(300)] + [im.get_width() + C.scaled(70) for im in imgs])
        pill_w = min(pill_w, C.SCREEN_W - C.scaled(40))
        hits = []
        radius = row_h // 2
        for i, img in enumerate(imgs):
            cy = int(start_y + i * pitch)
            rect = pygame.Rect(0, 0, pill_w, row_h)
            rect.center = (C.SCREEN_W // 2, cy)
            bg = pygame.Surface(rect.size, pygame.SRCALPHA)
            sel = i == selected_index
            pygame.draw.rect(bg, (0, 0, 0, 165), bg.get_rect(), border_radius=radius)
            pygame.draw.rect(bg, (240, 200, 40, 230) if sel else (255, 255, 255, 90), bg.get_rect(),
                             width=max(2, C.scaled(2)), border_radius=radius)
            surface.blit(bg, rect.topleft)
            surface.blit(img, img.get_rect(center=rect.center))
            hit = rect.inflate(C.scaled(10), pitch - row_h)
            hits.append((hit, i))
        touch_mod.set_list_hits(hits)
        if extra_lines:
            y = int(start_y + len(items) * pitch)
            for line in extra_lines:
                img = self.font_tiny.render(line, True, C.GRAY)
                surface.blit(img, img.get_rect(center=(C.SCREEN_W // 2, y)))
                y += C.scaled(20)
        return hits

    def draw_touch_hint(self, surface, text, y=None):
        """Línea de ayuda para la versión táctil (reemplaza a los pies de
        página con teclas)."""
        y = y if y is not None else C.SCREEN_H - C.scaled(25)
        img = self.font_footer.render(text, True, (230, 230, 235))
        bg = img.get_rect(center=(C.SCREEN_W // 2, y)).inflate(C.scaled(24), C.scaled(10))
        box = pygame.Surface(bg.size, pygame.SRCALPHA)
        pygame.draw.rect(box, (0, 0, 0, 140), box.get_rect(), border_radius=bg.height // 2)
        surface.blit(box, bg.topleft)
        surface.blit(img, img.get_rect(center=(C.SCREEN_W // 2, y)))

    def draw_round_button(self, surface, center, radius, text, color=(60, 60, 72)):
        """Botón redondo simple para tocar (versión táctil). Devuelve su rect."""
        r = int(radius)
        circ = pygame.Surface((2 * r, 2 * r), pygame.SRCALPHA)
        pygame.draw.circle(circ, (*color, 220), (r, r), r)
        pygame.draw.circle(circ, (255, 255, 255, 140), (r, r), r, width=max(2, C.scaled(2)))
        rect = circ.get_rect(center=(int(center[0]), int(center[1])))
        surface.blit(circ, rect)
        img = self.font_med.render(text, True, C.WHITE)
        surface.blit(img, img.get_rect(center=rect.center))
        return rect

    def draw_pill_button(self, surface, center, text, min_w=None, color=(60, 160, 90)):
        """Botón alargado (ej. "ELEGIR") para la versión táctil."""
        if self._list_font is None:
            self._list_font = self._load_title_font(C.scaled(23))
        img = self._list_font.render(text, True, C.WHITE)
        h = C.scaled(self.TOUCH_ROW_H)
        w = max(min_w or C.scaled(200), img.get_width() + C.scaled(60))
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (int(center[0]), int(center[1]))
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (*color, 230), bg.get_rect(), border_radius=h // 2)
        pygame.draw.rect(bg, (255, 255, 255, 150), bg.get_rect(), width=max(2, C.scaled(2)), border_radius=h // 2)
        surface.blit(bg, rect.topleft)
        surface.blit(img, img.get_rect(center=rect.center))
        return rect
