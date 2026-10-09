"""
menu.py
--------
Todas las pantallas de menú del juego:
  - ModeMenu: Jugar con CPU / 2 Jugadores / Opciones
  - DifficultySelect: 10 niveles de dificultad de la CPU
  - CharacterSelect: selección estilo "cuadrados" (Jugador 1 a la izquierda,
    Jugador 2 a la derecha, ambos eligen a la vez sobre la misma grilla)
  - StageSelect: selección de escenario (con preview animado si es GIF/video)
  - PauseMenu: pausa durante la pelea
  - OptionsMenu / ControlsRemapMenu: volumen, pantalla completa, mapeo de
    controles
"""

import glob
import json
import math
import os
import pygame

from engine import constants as C
from engine import device
from engine.ui import round_image_corners
from engine.tournament import label_picks


def load_scaled_cached(path, size, cache, radius=0):
    """Carga una imagen, la escala a 'size' y opcionalmente le redondea
    los bordes -- cacheado por (path, size, radius) en el dict 'cache'
    que le pasen (compartido entre pantallas para no repetir trabajo,
    ver _SHARED_SEL_CACHE/_SHARED_POSE_CACHE en las clases de abajo)."""
    if not path:
        return None
    key = (path, size, radius)
    if key not in cache:
        img = pygame.image.load(path).convert_alpha()
        img = pygame.transform.smoothscale(img, size)
        if radius:
            img = round_image_corners(img, radius)
        cache[key] = img
    return cache[key]
from engine.stage import (
    list_stages as _list_stage_paths,
    display_name as stage_display_name,
    Stage,
    get_secret_stage,
    load_stage_thumbnail,
)
from engine.input_manager import (
    ACTIONS, BUTTON_ACTIONS, save_input_config, build_footer, build_footer_parts,
    load_input_config, key_label,
)


# ======================================================================
# Utilidades de personajes
# ======================================================================
def _first_existing(*paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def load_character_list(include_hidden=False):
    """Devuelve una lista de dicts con toda la info de cada personaje que
    necesitan las pantallas de selección. Los personajes con "hidden":
    true en su JSON (ej. Karen, todavía no lista para la V1.0) no
    aparecen acá -- ni en el selector manual ni como rival random de la
    CPU/Torre, ambos salen de esta misma lista -- pero sus datos/sprites
    quedan intactos en el proyecto para cuando se vuelvan a activar
    (simplemente sacando ese campo del JSON)."""
    result = []
    for path in sorted(glob.glob(os.path.join(C.CHAR_DATA_DIR, "*.json"))):
        if os.path.basename(path) == "character_template.json":
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("hidden") and not include_hidden:
            continue
        folder = data.get("sprite_folder", "")
        selection = _first_existing(
            os.path.join(folder, "selection.png"),
            os.path.join(folder, "thumbnail.png"),
            os.path.join(folder, "idle", "0.png"),
        )
        pose = _first_existing(
            os.path.join(folder, "pose.png"),
            os.path.join(folder, "idle", "0.png"),
            selection,
        )
        # Casi todos los personajes usan la MISMA imagen de pose para los
        # dos lados (a la derecha se espeja para que quede "mirando hacia
        # adentro" -- ver donde se dibuja). Pero si un personaje tiene
        # ropa con texto legible (ej. Adrián, con "RACING CLUB" en el
        # buzo), espejarlo lo deja al revés -- para esos casos alcanza
        # con poner un archivo aparte "pose2.png" en su carpeta (una
        # foto DISTINTA, ya mirando para el otro lado con el texto bien)
        # y automáticamente se usa esa, sin espejar nada, del lado de
        # J2/CPU (pedido explícito: "Pose1 es para P1, Pose2 es para P2 y
        # CPU. Es el único personaje con este treatment"). El resto de
        # los personajes, que no tienen ese archivo, siguen funcionando
        # exactamente como siempre (misma imagen, espejada a la derecha).
        pose2_file = os.path.join(folder, "pose2.png")
        has_dedicated_pose2 = os.path.isfile(pose2_file)
        pose_path_p2 = pose2_file if has_dedicated_pose2 else pose
        result.append({
            "json_path": path,
            "name": data.get("name", os.path.basename(path)),
            "selection_path": selection,
            "pose_path": pose,
            "pose_path_p2": pose_path_p2,
            "pose_p2_flip": not has_dedicated_pose2,
        })
    result.sort(key=lambda c: c["name"].casefold())
    return result


# ======================================================================
# Menú de modos (Jugar con CPU / 2 Jugadores / Opciones)
# ======================================================================
class ModeMenu:
    ITEMS = ["1 Jugador", "Multijugador", "Opciones"]

    def __init__(self):
        self.index = 0
        self.done = False
        self.choice = None  # "one_player" | "multiplayer" | "options"
        # "Cancelar" acá no vuelve a ningún lado (este es el menú raíz) --
        # en cambio, dispara que se repita el video de intro (ver
        # STATE_MODE_MENU en main.py). A propósito no se muestra en el
        # pie de página (ver draw() más abajo).
        self.replay_intro = False

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ITEMS)
        elif inp.just_pressed("confirm"):
            self.choice = ["one_player", "multiplayer", "options"][self.index]
            self.done = True
        elif inp.just_pressed("cancel"):
            self.replay_intro = True

    def draw(self, surface, ui, dt=1 / 60):
        ui.draw_title_background(surface, dt)
        if not ui.draw_title_logo(surface):
            ui.draw_center_text(surface, "MORTAL KOMPA", C.YELLOW, -C.scaled(140))
        ui.draw_menu_list(surface, "", self.ITEMS, self.index, center_y=C.SCREEN_H // 2 + C.scaled(90))
        footer_cfg = load_input_config()
        exit_label = "ATRÁS" if device.TOUCH_UI else "ESC"
        ui.draw_footer_mixed(surface, build_footer_parts(footer_cfg, [("confirm", "confirmar")]) + [("text", exit_label, "salir")], C.SCREEN_H - C.scaled(30))
        version_img = ui.font_tiny.render(C.GAME_VERSION, True, C.GRAY)
        surface.blit(version_img, (C.scaled(10), C.SCREEN_H - version_img.get_height() - C.scaled(8)))


class OnePlayerMenu:
    ITEMS = ["Torre de Batalla", "Pelea contra CPU", "Volver"]

    def __init__(self):
        self.index = 0
        self.done = False
        self.cancelled = False
        self.choice = None  # "cpu" | "tower" | "back"

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ITEMS)
        elif inp.just_pressed("confirm"):
            self.choice = ["tower", "cpu", "back"][self.index]
            self.done = True
        elif inp.just_pressed("cancel"):
            self.cancelled = True

    def draw(self, surface, ui, dt=1 / 60):
        ui.draw_title_background(surface, dt)
        ui.draw_menu_list(surface, "1 JUGADOR", self.ITEMS, self.index, center_y=C.SCREEN_H // 2 + C.scaled(40))
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [("confirm", "confirmar"), ("cancel", "volver")]),
            C.SCREEN_H - C.scaled(30),
        )


class DifficultySelect:
    def __init__(self):
        self.level = 5
        self.done = False
        self.cancelled = False

    def update(self, inp):
        if inp.just_pressed("left"):
            self.level = max(1, self.level - 1)
        elif inp.just_pressed("right"):
            self.level = min(10, self.level + 1)
        elif inp.just_pressed("confirm"):
            self.done = True
        elif inp.just_pressed("cancel"):
            self.cancelled = True

    def handle_tap(self, pos):
        """Versión táctil: botones − / + y ELEGIR (ver draw)."""
        for key, rect in getattr(self, "_hits", {}).items():
            if rect.collidepoint(pos):
                if key == "minus":
                    self.level = max(1, self.level - 1)
                elif key == "plus":
                    self.level = min(10, self.level + 1)
                elif key == "ok":
                    self.done = True
                return True
        return False

    def draw(self, surface, ui):
        surface.fill(C.DARK)
        ui.draw_small_center(surface, "DIFICULTAD DE LA CPU", C.SCREEN_H // 2 - C.scaled(90))
        big = ui.font_big.render(str(self.level), True, C.YELLOW)
        surface.blit(big, big.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H // 2)))
        if ui.touch_lists:
            etiqueta = ["Muy fácil", "Fácil", "Fácil", "Normal-", "Normal", "Normal+",
                        "Difícil", "Difícil", "Muy difícil", "Imposible"][self.level - 1]
            ui.draw_small_center(surface, etiqueta, C.SCREEN_H // 2 + C.scaled(60))
            r = C.scaled(34)
            self._hits = {
                "minus": ui.draw_round_button(surface, (C.SCREEN_W // 2 - C.scaled(130), C.SCREEN_H // 2), r, "−"),
                "plus": ui.draw_round_button(surface, (C.SCREEN_W // 2 + C.scaled(130), C.SCREEN_H // 2), r, "+"),
                "ok": ui.draw_pill_button(surface, (C.SCREEN_W // 2, C.SCREEN_H // 2 + C.scaled(130)), "ELEGIR"),
            }
            return
        etiqueta = ["Muy fácil", "Fácil", "Fácil", "Normal-", "Normal", "Normal+",
                    "Difícil", "Difícil", "Muy difícil", "Imposible"][self.level - 1]
        ui.draw_small_center(surface, etiqueta, C.SCREEN_H // 2 + C.scaled(60))
        footer_cfg = load_input_config()
        left_l, right_l = key_label(footer_cfg, "left"), key_label(footer_cfg, "right")
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [(f"{left_l}/{right_l}", "cambiar"), ("confirm", "confirmar"), ("cancel", "volver")]),
            C.SCREEN_H - C.scaled(40),
        )


class MultiplayerMenu:
    # En el celular (o probando la versión táctil) solo tiene sentido el
    # juego por WiFi: en un mismo celular no entran dos jugadores. En PC
    # quedan también los modos locales de siempre (2 controles).
    if device.TOUCH_UI:
        ITEMS = ["Crear partida (WiFi)", "Unirse a partida (WiFi)", "Volver"]
        CHOICES = ["host", "join", "back"]
    else:
        ITEMS = ["2 Jugadores", "Torneo", "Crear partida (WiFi)", "Unirse a partida (WiFi)", "Volver"]
        CHOICES = ["versus", "tournament", "host", "join", "back"]

    def __init__(self):
        self.index = 0
        self.done = False
        self.cancelled = False
        self.choice = None  # "versus" | "tournament" | "host" | "join" | "back"

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ITEMS)
        elif inp.just_pressed("confirm"):
            self.choice = self.CHOICES[self.index]
            self.done = True
        elif inp.just_pressed("cancel"):
            self.cancelled = True

    def draw(self, surface, ui, dt=1 / 60):
        ui.draw_title_background(surface, dt)
        ui.draw_menu_list(surface, "MULTIJUGADOR", self.ITEMS, self.index, center_y=C.SCREEN_H // 2 + C.scaled(40))
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [("confirm", "confirmar"), ("cancel", "volver")]),
            C.SCREEN_H - C.scaled(30),
        )


class TournamentSizeSelect:
    MIN_PLAYERS = 3
    MAX_PLAYERS = 16

    def __init__(self):
        self.count = 8
        self.done = False
        self.cancelled = False

    def update(self, inp):
        if inp.just_pressed("left"):
            self.count = max(self.MIN_PLAYERS, self.count - 1)
        elif inp.just_pressed("right"):
            self.count = min(self.MAX_PLAYERS, self.count + 1)
        elif inp.just_pressed("confirm"):
            self.done = True
        elif inp.just_pressed("cancel"):
            self.cancelled = True

    def draw(self, surface, ui):
        surface.fill(C.DARK)
        ui.draw_small_center(surface, "¿CUÁNTOS JUGADORES?", C.SCREEN_H // 2 - C.scaled(90))
        big = ui.font_big.render(str(self.count), True, C.YELLOW)
        surface.blit(big, big.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H // 2)))
        footer_cfg = load_input_config()
        left_l, right_l = key_label(footer_cfg, "left"), key_label(footer_cfg, "right")
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [(f"{left_l}/{right_l}", "cambiar"), ("confirm", "confirmar"), ("cancel", "volver")]),
            C.SCREEN_H - C.scaled(40),
        )




# ======================================================================
# Selección de personajes: cuadrados seleccionables + arte de pose a los
# costados (estilo Marvel vs Capcom / KOF), P1 y P2 eligen a la vez.
# ======================================================================
P1_COLOR = (80, 170, 240)
P2_COLOR = (240, 80, 90)
CPU_COLOR = (240, 200, 50)  # mismo amarillo que ya usa el rival actual en la Torre de Batalla

RANDOM_SENTINEL = "__random__"

# Área disponible para la grilla en pantalla (lo que queda libre entre los
# paneles de pose de cada jugador, el título de arriba y las instrucciones
# de abajo). El tamaño de celda se calcula para que la grilla entre
# siempre entera ahí, sea cual sea la cantidad de personajes.
# Calibrado en espacio base (960x540) -- C.scaled() lo lleva a la
# resolución real (ver C.RESOLUTION).
GRID_AREA_TOP = C.scaled(70)
GRID_AREA_BOTTOM_MARGIN = C.scaled(95)   # deja lugar a "J1: nombre" / instrucciones
SIDE_PANEL_W = C.scaled(286)  # 260 * 1.10 -- las poses se veían chicas, +10%
SIDE_MARGIN = C.scaled(20)
GRID_SIDE_GAP = C.scaled(20)
GRID_CELL_MIN = C.scaled(34)
GRID_CELL_MAX = C.scaled(120)
GRID_GAP = C.scaled(10)
# Borde/marco alrededor de cada selection.png (el margen gris que se ve
# asomando entre la imagen y el recuadro) -- ~30% más chico que antes,
# pedido explícito. Un solo valor compartido por las 3 pantallas que
# usan este mismo esquema (Selección de Personajes, Torneo, Escenarios).
SEL_FRAME_PAD = C.scaled(8) * 0.7

# Grilla de escenarios: celdas 16:9 (no cuadradas como las de personaje)
# y con lugar reservado para el nombre escrito debajo de cada miniatura.
STAGE_GRID_TOP = C.scaled(70)
STAGE_GRID_BOTTOM_MARGIN = C.scaled(55)
STAGE_GRID_SIDE_MARGIN = C.scaled(40)
STAGE_GRID_GAP = C.scaled(18)
STAGE_CELL_MIN_W = C.scaled(160)
STAGE_CELL_MAX_W = C.scaled(420)
STAGE_LABEL_GAP = C.scaled(6)
STAGE_LABEL_H = C.scaled(24)


class CharacterSelect:
    # Caché de miniaturas COMPARTIDA entre TODAS las instancias (se
    # crea un CharacterSelect nuevo cada vez que se entra a esta
    # pantalla, incluso yendo a la Torre -- antes cada instancia tenía
    # su propia caché vacía, así que las miniaturas de los personajes
    # se volvían a cargar y redondear los bordes desde cero cada vez,
    # aportando a la traba reportada justo después de elegir personaje
    # para la Torre). Vive mientras dure el proceso del juego.
    _SHARED_SEL_CACHE = {}
    _SHARED_POSE_CACHE = {}

    def __init__(self, p2_is_cpu=False, solo=False):
        self.characters = load_character_list() + [{
            "json_path": RANDOM_SENTINEL,
            "name": "Aleatorio",
            "selection_path": os.path.join("assets", "ui", "random_selection.png"),
            "pose_path": os.path.join("assets", "ui", "random_pose.png"),
            "pose_path_p2": os.path.join("assets", "ui", "random_pose.png"),
            "pose_p2_flip": True,
        }]
        self.p2_is_cpu = p2_is_cpu
        self.solo = solo  # True: solo elige J1 (para Torre de Batalla), sin panel/cursor de J2
        self.cursor = [0, 0]
        self.confirmed = [False, False]
        self.choices = [None, None]
        self.done = False
        self.cancelled = False

        n = len(self.characters)
        avail_w = C.SCREEN_W - 2 * (SIDE_MARGIN + SIDE_PANEL_W + GRID_SIDE_GAP)
        avail_h = C.SCREEN_H - GRID_AREA_TOP - GRID_AREA_BOTTOM_MARGIN
        self.cell_size, self.cols, self.rows = self._compute_grid(n, avail_w, avail_h)

        self._sel_cache = self._SHARED_SEL_CACHE
        self._pose_cache = self._SHARED_POSE_CACHE

        # celda inicial distinta para cada jugador si hay lugar
        if n > 1:
            self.cursor[1] = 1

    @staticmethod
    def _compute_grid(n, avail_w, avail_h, gap=GRID_GAP):
        """Elige cantidad de columnas/filas y tamaño de celda que MAXIMIZA
        el tamaño de celda sin salirse del área disponible. Menos
        personajes -> menos columnas necesarias -> celdas más grandes
        (hasta el tope GRID_CELL_MAX). Más personajes -> se acomodan solos
        en más columnas/filas con celdas más chicas, pero siempre adentro
        de la pantalla."""
        if n <= 0:
            return GRID_CELL_MAX, 1, 1
        best = None
        for cols in range(1, n + 1):
            rows = math.ceil(n / cols)
            cell_w = (avail_w - (cols - 1) * gap) / cols
            cell_h = (avail_h - (rows - 1) * gap) / rows
            cell = min(cell_w, cell_h)
            if cell <= 0:
                continue
            if best is None or cell > best[0]:
                best = (cell, cols, rows)
        cell, cols, rows = best or (GRID_CELL_MIN, 1, n)
        cell = max(GRID_CELL_MIN, min(GRID_CELL_MAX, cell))
        return cell, cols, rows

    def _load_scaled(self, path, size, cache, radius=0):
        return load_scaled_cached(path, size, cache, radius)

    def cell_rects(self):
        """Rectángulos (en el lienzo) de cada casillero de la grilla --
        mismos cálculos que draw(). Para tocar una cara directamente."""
        cell = self.cell_size
        gap = GRID_GAP
        grid_w = self.cols * cell + (self.cols - 1) * gap
        grid_h = self.rows * cell + (self.rows - 1) * gap
        area_h = C.SCREEN_H - GRID_AREA_TOP - GRID_AREA_BOTTOM_MARGIN
        start_x = C.SCREEN_W // 2 - grid_w // 2
        start_y = GRID_AREA_TOP + max(0, (area_h - grid_h) // 2)
        rects = []
        for i in range(len(self.characters)):
            x = start_x + (i % self.cols) * (cell + gap)
            y = start_y + (i // self.cols) * (cell + gap)
            rects.append(pygame.Rect(int(x), int(y), int(cell), int(cell)))
        return rects

    def hit_test(self, pos):
        for i, r in enumerate(self.cell_rects()):
            if r.collidepoint(pos):
                return i
        return None

    def apply_tap(self, p, idx):
        """Toque directo sobre la cara 'idx' por el jugador 'p': si ya
        estaba marcada, confirma; si no, mueve el cursor ahí."""
        if idx is None or not (0 <= idx < len(self.characters)):
            return False
        if self.confirmed[p]:
            return False
        if self.cursor[p] == idx:
            self.confirmed[p] = True
            self.choices[p] = self.characters[idx]["json_path"]
        else:
            self.cursor[p] = idx
        self._check_done()
        return True

    def _check_done(self):
        if self.solo:
            if self.confirmed[0]:
                self.done = True
        elif all(self.confirmed):
            self.done = True

    def update(self, inputs, dt):
        if not self.characters:
            return
        n = len(self.characters)

        # Para volver atrás (cancelar toda la selección), sólo importa
        # si J1 ya confirmó o no -- si J2 es la CPU, su elección
        # automática NO debería bloquearle a J1 la posibilidad de
        # volver (bug reportado: "no puedo volver atrás si la CPU ya
        # eligió su personaje"). Entre 2 jugadores humanos, en cambio,
        # se sigue pidiendo que NINGUNO de los dos haya confirmado
        # todavía (no tiene sentido que un jugador le cancele al otro
        # una elección ya hecha).
        cancel_ok = not self.confirmed[0] if self.p2_is_cpu else not any(self.confirmed)
        if cancel_ok and inputs[0].just_pressed("cancel"):
            self.cancelled = True
            return

        for p in (0, 1):
            if self.solo and p == 1:
                continue
            inp = inputs[p]
            if self.confirmed[p]:
                # ya confirmó: con "cancel" puede deshacer su elección y
                # volver a elegir (antes no había forma de deseleccionar,
                # ni con teclado ni con joystick)
                if inp.just_pressed("cancel"):
                    self.confirmed[p] = False
                    self.choices[p] = None
                continue
            if inp.just_pressed("right"):
                self.cursor[p] = (self.cursor[p] + 1) % n
            elif inp.just_pressed("left"):
                self.cursor[p] = (self.cursor[p] - 1) % n
            elif inp.just_pressed("down"):
                self.cursor[p] = (self.cursor[p] + self.cols) % n
            elif inp.just_pressed("up"):
                self.cursor[p] = (self.cursor[p] - self.cols) % n
            if inp.just_pressed("confirm"):
                self.confirmed[p] = True
                self.choices[p] = self.characters[self.cursor[p]]["json_path"]

        if self.solo:
            if self.confirmed[0]:
                self.done = True
        elif all(self.confirmed):
            self.done = True

    def draw(self, surface, ui):
        ui.draw_screen_background(surface, ui.character_selection_background)
        if not self.characters:
            ui.draw_center_text(surface, "No hay personajes en data/characters/", C.RED)
            return

        # Cuando J2 es la CPU (1 Jugador vs CPU), usa amarillo en vez
        # de rojo para todo lo suyo -- mismo amarillo que ya identifica
        # al rival en la Torre de Batalla (pedido explícito: "mismo
        # color que CPU de Torre de batalla... Recuadro, círculo de
        # selección y 'CPU' en amarillo").
        p2_color = CPU_COLOR if self.p2_is_cpu else P2_COLOR

        # --- Grilla central (tamaño de celda calculado en __init__ para
        # que siempre entre completa en pantalla) ---
        cell = self.cell_size
        gap = GRID_GAP
        grid_w = self.cols * cell + (self.cols - 1) * gap
        grid_h = self.rows * cell + (self.rows - 1) * gap
        area_top = GRID_AREA_TOP
        area_h = C.SCREEN_H - GRID_AREA_TOP - GRID_AREA_BOTTOM_MARGIN
        start_x = C.SCREEN_W // 2 - grid_w // 2
        start_y = area_top + max(0, (area_h - grid_h) // 2)

        for i, char in enumerate(self.characters):
            col = i % self.cols
            row = i // self.cols
            x = start_x + col * (cell + gap)
            y = start_y + row * (cell + gap)
            rect = pygame.Rect(int(x), int(y), int(cell), int(cell))

            p1_here = self.cursor[0] == i
            p2_here = (not self.solo) and self.cursor[1] == i
            # El marco/borde ES el que cambia de color al elegido de
            # P1/P2 (antes se dejaba el marco gris de siempre y se le
            # dibujaba un anillo de color ENCIMA -- quedaban los dos
            # superpuestos). Solo cuando P1 y P2 coinciden en la MISMA
            # celda hace falta mostrar los dos colores a la vez.
            if p1_here and p2_here:
                # Mismo tamaño de celda de siempre -- antes esto se
                # dibujaba con dos anillos INFLADOS (más grandes que la
                # celda), así que apenas P2 se movía a otro casillero, el
                # de P1 "se achicaba" de golpe volviendo a su tamaño
                # normal (bug reportado). Ahora se parte el mismo marco
                # al medio, mitad para cada color -- SIN cambiar nunca el
                # tamaño de la celda.
                pygame.draw.rect(surface, P1_COLOR, rect, border_radius=C.scaled(8))
                right_half = pygame.Rect(rect.centerx, rect.y, rect.width - rect.width // 2, rect.height)
                pygame.draw.rect(
                    surface, p2_color, right_half,
                    border_top_right_radius=C.scaled(8), border_bottom_right_radius=C.scaled(8),
                )
            else:
                frame_color = P1_COLOR if p1_here else (p2_color if p2_here else (45, 45, 52))
                pygame.draw.rect(surface, frame_color, rect, border_radius=C.scaled(8))

            img = self._load_scaled(char["selection_path"], (int(cell - SEL_FRAME_PAD), int(cell - SEL_FRAME_PAD)), self._sel_cache, radius=C.scaled(8))
            if img:
                surface.blit(img, img.get_rect(center=rect.center))

            dot_off, dot_r = C.scaled(14), C.scaled(10)
            if self.choices[0] == char["json_path"] and self.confirmed[0]:
                pygame.draw.circle(surface, P1_COLOR, (rect.left + dot_off, rect.top + dot_off), dot_r)
            if self.choices[1] == char["json_path"] and self.confirmed[1] and not self.solo:
                pygame.draw.circle(surface, p2_color, (rect.right - dot_off, rect.top + dot_off), dot_r)

        # --- Panel de pose, Jugador 1 (izquierda) ---
        idx1 = self.characters.index(next(c for c in self.characters if c["json_path"] == self.choices[0])) \
            if self.choices[0] else self.cursor[0]
        pose1 = self._load_scaled(self.characters[idx1]["pose_path"], (SIDE_PANEL_W, SIDE_PANEL_W), self._pose_cache)
        if pose1:
            surface.blit(pose1, (SIDE_MARGIN, C.SCREEN_H // 2 - SIDE_PANEL_W // 2))

        # --- Panel de pose, Jugador 2 (derecha, mirando hacia la izquierda) ---
        # (no se dibuja en modo solo -- Torre de Batalla, solo elige J1)
        if not self.solo:
            idx2 = self.characters.index(next(c for c in self.characters if c["json_path"] == self.choices[1])) \
                if self.choices[1] else self.cursor[1]
            char2 = self.characters[idx2]
            pose2 = self._load_scaled(char2["pose_path_p2"], (SIDE_PANEL_W, SIDE_PANEL_W), self._pose_cache)
            if pose2:
                if char2["pose_p2_flip"]:
                    pose2 = pygame.transform.flip(pose2, True, False)
                surface.blit(pose2, (C.SCREEN_W - SIDE_MARGIN - SIDE_PANEL_W, C.SCREEN_H // 2 - SIDE_PANEL_W // 2))
            p2_label = "CPU" if self.p2_is_cpu else f"J2: {self.characters[idx2]['name']}"
            t2 = ui.font_small.render(p2_label, True, p2_color)
            surface.blit(t2, (C.SCREEN_W - C.scaled(40) - t2.get_width(), C.SCREEN_H // 2 + C.scaled(240)))

        title_top = "ELEGÍ TU LUCHADOR" if self.solo else ("SELECCIONÁ PERSONAJE" + ("S" if not self.p2_is_cpu else ""))
        ui.draw_title(surface, title_top, y=C.scaled(25))
        font = ui.font_small
        t1 = font.render(f"J1: {self.characters[idx1]['name']}", True, P1_COLOR)
        surface.blit(t1, (C.scaled(40), C.SCREEN_H // 2 + C.scaled(240)))

        footer_cfg = load_input_config()
        footer = build_footer_parts(footer_cfg, [("confirm", "confirmar"), ("cancel", "volver (J1)")])
        ui.draw_footer_mixed(surface, footer, C.SCREEN_H - C.scaled(25))
        if ui.touch_lists:
            ui.draw_touch_hint(surface, getattr(self, "touch_hint", None) or "Tocá un luchador para verlo y otra vez para elegirlo")


# ======================================================================
# Torneo: elegir los N personajes, uno a la vez (mismo J1 elige todos)
# ======================================================================
TOURNAMENT_LIST_W = C.scaled(230)


class TournamentCharacterSelect:
    _SHARED_SEL_CACHE = CharacterSelect._SHARED_SEL_CACHE
    _SHARED_POSE_CACHE = CharacterSelect._SHARED_POSE_CACHE

    def __init__(self, total_slots):
        self.characters = load_character_list()
        self.total_slots = total_slots
        self.picks = []  # lista de dicts (de load_character_list), uno por lugar del torneo -- pueden repetirse
        self.cursor = 0
        self.done = False
        self.cancelled = False
        self._sel_cache = self._SHARED_SEL_CACHE
        self._pose_cache = self._SHARED_POSE_CACHE

        n = len(self.characters)
        avail_w = C.SCREEN_W - 2 * SIDE_MARGIN - SIDE_PANEL_W - GRID_SIDE_GAP - TOURNAMENT_LIST_W - GRID_SIDE_GAP
        avail_h = C.SCREEN_H - GRID_AREA_TOP - GRID_AREA_BOTTOM_MARGIN
        self.cell_size, self.cols, self.rows = CharacterSelect._compute_grid(n, avail_w, avail_h)

    def update(self, inp):
        if not self.characters:
            return
        n = len(self.characters)
        if inp.just_pressed("cancel"):
            if self.picks:
                self.picks.pop()  # deshace la última elección, para poder corregir sin tener que cancelar todo
            else:
                self.cancelled = True
            return
        if inp.just_pressed("right"):
            self.cursor = (self.cursor + 1) % n
        elif inp.just_pressed("left"):
            self.cursor = (self.cursor - 1) % n
        elif inp.just_pressed("down"):
            self.cursor = (self.cursor + self.cols) % n
        elif inp.just_pressed("up"):
            self.cursor = (self.cursor - self.cols) % n
        elif inp.just_pressed("confirm"):
            self.picks.append(self.characters[self.cursor])
            if len(self.picks) >= self.total_slots:
                self.done = True

    def draw(self, surface, ui):
        ui.draw_screen_background(surface, ui.character_selection_background)
        if not self.characters:
            ui.draw_center_text(surface, "No hay personajes en data/characters/", C.RED)
            return

        cell = self.cell_size
        gap = GRID_GAP
        grid_w = self.cols * cell + (self.cols - 1) * gap
        grid_h = self.rows * cell + (self.rows - 1) * gap
        area_top = GRID_AREA_TOP
        area_h = C.SCREEN_H - GRID_AREA_TOP - GRID_AREA_BOTTOM_MARGIN
        # la grilla queda centrada en el espacio ENTRE el panel de pose
        # (izquierda) y la lista de elegidos (derecha), no en toda la pantalla
        grid_area_left = SIDE_MARGIN + SIDE_PANEL_W + GRID_SIDE_GAP
        grid_area_right = C.SCREEN_W - SIDE_MARGIN - TOURNAMENT_LIST_W - GRID_SIDE_GAP
        start_x = grid_area_left + max(0, (grid_area_right - grid_area_left - grid_w) // 2)
        start_y = area_top + max(0, (area_h - grid_h) // 2)

        for i, char in enumerate(self.characters):
            col = i % self.cols
            row = i // self.cols
            x = start_x + col * (cell + gap)
            y = start_y + row * (cell + gap)
            rect = pygame.Rect(int(x), int(y), int(cell), int(cell))
            frame_color = P1_COLOR if self.cursor == i else (45, 45, 52)
            img = load_scaled_cached(char["selection_path"], (int(cell - SEL_FRAME_PAD), int(cell - SEL_FRAME_PAD)), self._sel_cache, radius=C.scaled(8))
            pygame.draw.rect(surface, frame_color, rect, border_radius=C.scaled(8))
            if img:
                surface.blit(img, img.get_rect(center=rect.center))

        # --- Panel de pose (izquierda), igual que en Torre de Batalla ---
        pose = load_scaled_cached(self.characters[self.cursor]["pose_path"], (SIDE_PANEL_W, SIDE_PANEL_W), self._pose_cache)
        if pose:
            surface.blit(pose, (SIDE_MARGIN, C.SCREEN_H // 2 - SIDE_PANEL_W // 2))

        # --- Lista de "Personajes elegidos" (derecha) ---
        list_x = C.SCREEN_W - SIDE_MARGIN - TOURNAMENT_LIST_W
        list_title = ui.font_small.render("Personajes elegidos", True, C.WHITE)
        surface.blit(list_title, (list_x, GRID_AREA_TOP))
        row_h = min(C.scaled(28), (C.SCREEN_H - GRID_AREA_TOP - GRID_AREA_BOTTOM_MARGIN - list_title.get_height()) / max(1, self.total_slots))
        # Etiquetados en vivo (ej. "Ana", "Ana 2", "Ana 3") -- mismo
        # criterio que se usa después para el bracket en sí (ver
        # label_picks en engine/tournament.py), para que ya se vea acá
        # la numeración final antes de terminar de elegir a todos.
        labeled_picks = label_picks(self.picks)
        for i in range(self.total_slots):
            y = GRID_AREA_TOP + list_title.get_height() + C.scaled(10) + i * row_h
            if i < len(labeled_picks):
                text = f"{i + 1}. {labeled_picks[i]['label']}"
                color = C.WHITE
            else:
                text = f"{i + 1}. _ _ _"
                color = (110, 110, 118)
            t = ui.font_tiny.render(text, True, color)
            surface.blit(t, (list_x, int(y)))

        title = f"ELEGIR LUCHADOR {len(self.picks) + 1}"
        ui.draw_title(surface, title, y=C.scaled(25))

        footer_cfg = load_input_config()
        footer = build_footer_parts(footer_cfg, [("confirm", "confirmar"), ("cancel", "deshacer/volver")])
        ui.draw_footer_mixed(surface, footer, C.SCREEN_H - C.scaled(25))


# ======================================================================
# Torneo: pantalla del bracket (peleas + animación de subida/caída)
# ======================================================================
def _build_slot_structure(leaf_count):
    """Simula, en SLOTS abstractos (números, todavía sin asignar a
    ningún peleador real), la estructura COMPLETA del bracket de punta
    a punta -- qué par de slots se cruza en cada partido de cada ronda,
    quién tiene bye, y a qué slot nuevo sube el que gane, ronda por
    ronda, hasta llegar a un solo slot (el campeón).

    Como el sorteo es al azar UNA SOLA VEZ, al armar el torneo (ver
    tournament.py) -- de ahí en más el ganador del partido 1 de cada
    ronda siempre juega contra el ganador del partido 2, y así
    sucesivamente, sin volver a sortearse -- esta estructura es 100%
    determinística a partir de la cantidad de peleadores: se puede
    calcular acá UNA SOLA VEZ, de entrada, y usar SIEMPRE la misma
    (mismas posiciones, mismas líneas) para dibujar el bracket en
    cualquier ronda del torneo (pedido explícito: "unificar los
    brackets a lo largo de todo el torneo" -- antes, antes de darse
    cuenta de que el sorteo no era al azar en cada ronda, no había
    forma de saber de antemano con quién iba a cruzarse cada uno, así
    que la Ronda 1 no podía mostrar de entrada el árbol completo).

    Los primeros 'leaf_count' slots (0 a leaf_count-1) son los
    peleadores originales de la Ronda 1, EN EL MISMO ORDEN en que
    arman sus partidos de verdad (ver TournamentBracketScreen, donde
    se los asigna a partir de bracket.matches/bracket.bye) -- de ahí
    para arriba son todos slots "derivados" (el ganador de tal
    partido). El bye de cada ronda (si hay) siempre entra AL FINAL de
    la lista de la ronda siguiente -- se empareja con el ganador del
    ÚLTIMO partido de esta ronda, nunca con el del primero (tiene que
    coincidir exactamente con tournament.py, que arma el orden de la
    misma manera -- ver ahí el porqué, con capturas de referencia).

    Devuelve una lista de rondas; cada ronda es {"pairs": [(slotA,
    slotB), ...], "bye": slot_o_None, "winner_slots": [...]} (mismo
    orden que 'pairs' -- a qué slot nuevo sube el ganador de cada
    partido)."""
    level = list(range(leaf_count))
    rounds = []
    next_id = leaf_count
    while len(level) > 1:
        slots = list(level)
        bye_slot = slots.pop() if len(slots) % 2 == 1 else None
        pairs = [(slots[i], slots[i + 1]) for i in range(0, len(slots), 2)]
        winner_slots = [next_id + i for i in range(len(pairs))]
        rounds.append({"pairs": pairs, "bye": bye_slot, "winner_slots": winner_slots})
        next_id += len(pairs)
        level = winner_slots + ([bye_slot] if bye_slot is not None else [])
    return rounds


class TournamentBracketScreen:
    _SHARED_SEL_CACHE = CharacterSelect._SHARED_SEL_CACHE
    _SHARED_POSE_CACHE = CharacterSelect._SHARED_POSE_CACHE

    RISE_DURATION = 0.8       # cuánto tarda en "subir" la pelea actual al centro
    RESULT_DURATION = 1.8     # cuánto se ve el resultado (el perdedor "cae") antes de poder seguir

    def __init__(self, bracket):
        self.bracket = bracket
        self._sel_cache = self._SHARED_SEL_CACHE
        self._pose_cache = self._SHARED_POSE_CACHE
        self.phase = "rising"  # "rising" -> "ready" -> "result" -> "result_done"
        self.anim_t = 0.0
        self.result_winner = None
        self.result_loser = None
        # Como el sorteo es al azar UNA SOLA VEZ (al armar el torneo --
        # ver tournament.py) y de ahí en más el bracket queda fijo (el
        # ganador del partido 1 juega contra el ganador del partido 2,
        # etc.), TODA la estructura del árbol -- qué cruce con qué, en
        # cualquier ronda futura -- se puede calcular de entrada, una
        # sola vez, y usar SIEMPRE la misma para dibujar el bracket
        # completo en cualquier ronda del torneo (pedido explícito:
        # "unificar los brackets a lo largo de todo el torneo"). El
        # tamaño de cada tarjeta y el alto de cada "nivel" también
        # quedan FIJOS de punta a punta. Escala sola tanto para 3 como
        # para 16 jugadores.
        self._slot_structure = _build_slot_structure(len(self.bracket.entrants))
        self._geo = self._compute_layout_geometry()
        self._slot_positions = self._compute_slot_positions()

    def _compute_layout_geometry(self):
        n_rounds = len(self._slot_structure)
        # El tamaño de cada cuadradito y la separación entre partidos
        # son SIEMPRE los mismos, sea cual sea el torneo -- el árbol
        # ocupa el ancho que necesite, centrado en la pantalla (pedido
        # explícito, con capturas de referencia: "Los brackets son
        # siempre iguales... el árbol ocupa lo que necesite").
        card_size = C.scaled(40)
        pair_gap = card_size * 0.62
        branch_gap = card_size * 0.55

        # PERO sólo hasta cierto punto: con muchos partidos en la Ronda
        # 1 (10+ jugadores) ese ancho fijo terminaba siendo tan grande
        # que tapaba casi entera la pose de los dos personajes a los
        # costados (bug reportado: "está tapando casi todo pose.png de
        # ambos personajes"). Se calcula acá cuánto ancho pediría la
        # Ronda 1 (la fila con más partidos, así que la más ancha de
        # todo el torneo) con el tamaño de siempre, y si eso pisaría
        # más del 20% del panel de cada pose, se achica el cuadradito
        # (y todo lo que depende de él) lo justo y necesario para que
        # nunca tape más que eso -- torneos chicos y medianos ni lo
        # notan (les sobra lugar de sobra), sólo entra a achicar a
        # partir de donde hace falta. Ojo: el panel de cada pose ya se
        # corre un poco hacia afuera de su posición "de libro" (ver
        # 'push' en _draw_pose) -- si acá no se cuenta ese lugar extra
        # que ese corrimiento ya regala, el cálculo queda de más
        # estricto de lo necesario y el cuadradito termina más chico
        # de lo que en realidad hace falta (bug reportado: "ahora está
        # demasiado chico... está medio ilegible").
        n_matches_r1 = len(self.bracket.matches)
        has_bye_r1 = self.bracket.bye is not None
        entries_r1 = n_matches_r1 + (1 if has_bye_r1 else 0)
        match_half_w = pair_gap + card_size * 0.5
        bye_half_w = card_size * 0.5
        natural_w = match_half_w * 2 * n_matches_r1 + (bye_half_w * 2 if has_bye_r1 else 0) + branch_gap * max(0, entries_r1 - 1)

        push = C.scaled(70)
        max_pose_overlap = SIDE_PANEL_W * 0.20
        budget_w = (C.SCREEN_W - 2 * SIDE_MARGIN - 2 * SIDE_PANEL_W) + 2 * push + 2 * max_pose_overlap
        if natural_w > budget_w > 0:
            scale = budget_w / natural_w
            card_size *= scale
            pair_gap = card_size * 0.62
            branch_gap = card_size * 0.55

        center_top = C.scaled(100)
        center_bottom = C.SCREEN_H - C.scaled(110)

        # Una fila por cada ronda que hace falta jugar, más una fila
        # extra fija (la de las tarjetas de la Ronda 1, el punto de
        # partida) -- usando SIEMPRE el mismo presupuesto vertical
        # total (no todo el alto disponible), así que un torneo con
        # más rondas (16 jugadores, 4 rondas) no termina con un árbol
        # más alto que uno con menos rondas (3 jugadores, 2 rondas) --
        # los personajes de las capturas de referencia se ven todos a
        # una altura pareja, no cada vez más arriba cuanto más grande
        # el torneo.
        total_rows = n_rounds + 1
        total_tree_height = C.scaled(330)
        row_h = total_tree_height / total_rows

        return {
            "center_top": center_top, "center_bottom": center_bottom,
            "row_h": row_h,
            "card_size": card_size, "pair_gap": pair_gap, "branch_gap": branch_gap,
        }

    def start_new_match(self):
        self.phase = "rising"
        self.anim_t = 0.0
        self.result_winner = None
        self.result_loser = None

    def show_result(self, winner, loser):
        self.phase = "result"
        self.anim_t = 0.0
        self.result_winner = winner
        self.result_loser = loser

    def _compute_slot_positions(self):
        """Ubica, UNA SOLA VEZ, la posición (x, y) de CADA slot del
        árbol completo -- desde las hojas (Ronda 1) hasta el campeón --
        usando siempre la MISMA geometría fija (self._geo), y arma de
        una vez TODAS las líneas que conectan esos slots entre sí, en
        el mismo recorrido (para el caso del bye hace falta tener a
        mano la posición de ANTES y la de DESPUÉS de cada ronda a la
        vez -- guardarlas por separado, en dos pasadas distintas,
        pisaba la de antes con la de después). Como la estructura
        entera ya se conoce de entrada (ver _build_slot_structure),
        esto se calcula antes de jugarse un solo partido y NUNCA se
        vuelve a tocar en todo el torneo -- se dibujan SIEMPRE
        completas, en cualquier ronda (pedido explícito: "la Ronda 1
        ni siquiera tiene las líneas de los brackets... unificar los
        brackets a lo largo de todo el torneo"). Lo único que cambia
        ronda a ronda son las TARJETAS que se ponen encima (ver
        _draw_bracket), nunca estas líneas."""
        g = self._geo
        card_size, pair_gap = g["card_size"], g["pair_gap"]
        branch_gap = g["branch_gap"]
        center_bottom, row_h = g["center_bottom"], g["row_h"]

        b = self.bracket
        n_matches = len(b.matches)
        has_bye = b.bye is not None
        leaf_y = center_bottom - row_h * 0.5

        # Ancho fijo por partido (tarjetas bien juntas, como dos
        # rivales de verdad) y un margen fijo entre partidos distintos
        # -- SIEMPRE los mismos, sea cual sea el torneo. El árbol
        # entero se centra en la mitad de la pantalla (no del área
        # disponible entre las poses) y ocupa el ancho que le haga
        # falta -- si necesita más lugar que el que dejan las poses en
        # su posición de siempre, son las POSES las que se corren hacia
        # afuera (ver draw()), nunca el árbol el que se aprieta (bug
        # reportado, con capturas: "se superponen los jugadores").
        match_half_w = pair_gap + card_size * 0.5
        entries = n_matches + (1 if has_bye else 0)
        bye_half_w = card_size * 0.5
        total_w = match_half_w * 2 * n_matches + (bye_half_w * 2 if has_bye else 0) + branch_gap * max(0, entries - 1)
        cursor_x = C.SCREEN_W * 0.5 - total_w * 0.5

        positions = {}
        for m in range(n_matches):
            slot_cx = cursor_x + match_half_w
            cursor_x += match_half_w * 2 + branch_gap
            positions[2 * m] = (slot_cx - pair_gap, leaf_y)
            positions[2 * m + 1] = (slot_cx + pair_gap, leaf_y)
        if has_bye:
            slot_cx = cursor_x + bye_half_w
            positions[2 * n_matches] = (slot_cx, leaf_y)

        lines = []
        # Guarda, para cada slot, la posición que tuvo en el momento
        # EXACTO en que se creó (ganador recién subido, o bye recién
        # pasado de largo) -- 'positions' se sigue actualizando ronda
        # a ronda (hace falta el valor más nuevo para calcular los
        # cruces de más arriba), pero un slot "ganador" puede, más
        # adelante, terminar recibiendo ÉL MISMO un bye en una ronda
        # posterior (pasa de largo sin pelear) -- y ahí 'positions' se
        # le pisa con la posición de ESA ronda futura. Si al dibujar la
        # ronda en la que ese slot se creó se usara 'positions'
        # directo, se mostraba mal ubicado (con la posición de una
        # ronda que todavía ni había pasado) -- bug encontrado: dos
        # peleadores de ramas distintas con tarjetas exactamente
        # superpuestas.
        self._winner_slot_positions = {}
        # Lo mismo para el bye: guarda la posición de ANTES y de
        # DESPUÉS de CADA ronda en la que le tocó (puede pasar de largo
        # varias rondas seguidas).
        self._bye_round_positions = {}
        min_gap = card_size * 1.05
        cur_y = leaf_y
        for round_idx, rnd in enumerate(self._slot_structure):
            next_y = cur_y - row_h

            # PRIMERA pasada: calcula dónde "querría" caer cada slot
            # nuevo de esta fila (el punto medio de sus dos padres, o
            # la misma x de siempre si es un bye que pasa de largo) sin
            # ubicar nada todavía. Como un bye puede terminar
            # cruzándose de nuevo más adelante con el ganador de OTRO
            # partido bien lejano en el árbol, sus dos posiciones
            # promediadas pueden coincidir, por pura coincidencia
            # numérica, con la de un slot de otra rama -- ver segunda
            # pasada, que separa a los que piden un lugar demasiado
            # parecido antes de dibujar nada (bug encontrado: dos
            # peleadores de ramas distintas con tarjetas exactamente
            # superpuestas).
            raw = []
            for (slot_a, slot_b), new_slot in zip(rnd["pairs"], rnd["winner_slots"]):
                ax, _ay = positions[slot_a]
                bx, _by = positions[slot_b]
                raw.append((new_slot, (ax + bx) * 0.5))
            if rnd["bye"] is not None:
                old_x, _old_y = positions[rnd["bye"]]
                raw.append((rnd["bye"], old_x))

            raw.sort(key=lambda t: t[1])
            resolved = {}
            prev_x = None
            for slot_id, x in raw:
                if prev_x is not None and x - prev_x < min_gap:
                    x = prev_x + min_gap
                resolved[slot_id] = x
                prev_x = x

            for (slot_a, slot_b), new_slot in zip(rnd["pairs"], rnd["winner_slots"]):
                ax, ay = positions[slot_a]
                bx, by = positions[slot_b]
                nx = resolved[new_slot]
                positions[new_slot] = (nx, next_y)
                self._winner_slot_positions[new_slot] = (nx, next_y)
                # SIN hueco reservado para una tarjeta que todavía no
                # existe: el tramo va exactamente de un nivel al
                # siguiente (desde la altura real del hijo hasta la
                # altura real del padre), no hasta "justo antes" de
                # donde iría la tarjeta -- antes, si esa tarjeta
                # TODAVÍA no estaba decidida (ej. toda la Ronda 1, o
                # cualquier ronda futura), ese hueco quedaba vacío,
                # sin nada dibujado ahí (bug reportado: "se ven
                # espacios vacíos cuando la línea debería ser
                # completa"). Ahora el trazo es SIEMPRE continuo, de
                # punta a punta del árbol entero, exista o no exista
                # todavía la tarjeta en el medio -- cuando la tarjeta
                # aparece (al decidirse ese cruce), se dibuja ENCIMA
                # del tramo de línea que pasa por ahí (las tarjetas se
                # pintan después -- ver draw()), tapando esa parte
                # nada más, como corresponde.
                top_of_children = ay
                bottom_of_parent = next_y
                merge_y = bottom_of_parent + (top_of_children - bottom_of_parent) * 0.65
                lines.append(((ax, top_of_children), (ax, merge_y)))
                lines.append(((bx, top_of_children), (bx, merge_y)))
                lines.append(((ax, merge_y), (bx, merge_y)))
                lines.append((((ax + bx) * 0.5, merge_y), (nx, bottom_of_parent)))
            if rnd["bye"] is not None:
                old_x, old_y = positions[rnd["bye"]]
                new_x = resolved[rnd["bye"]]
                positions[rnd["bye"]] = (new_x, next_y)
                # El bye no dibuja ninguna línea propia acá -- no hubo
                # ningún cruce real esta ronda, así que no hay nada que
                # conectar "de abajo hacia arriba" (la única línea que
                # sí le corresponde es la del PRÓXIMO cruce real que
                # tenga, y esa la dibuja el partido de esa ronda,
                # usando ya esta posición actualizada) -- pedido
                # explícito: el bye se muestra una sola vez, arriba.
                self._bye_round_positions[round_idx] = (old_x, old_y, new_x, next_y)
            cur_y = next_y

        self._fixed_lines = lines
        return positions

    def update(self, dt, inp):
        self.anim_t += dt
        if self.phase == "rising" and self.anim_t >= self.RISE_DURATION:
            self.phase = "ready"
        elif self.phase == "result":
            confirmed = inp is not None and inp.just_pressed("confirm")
            if confirmed or self.anim_t >= self.RESULT_DURATION:
                self.phase = "result_done"

    def _card(self, surface, ui, entrant, center, color, size, dim=False, alpha=None):
        """Dibuja la tarjeta (selection.png + borde de color).

        'dim': para los peleadores ELIMINADOS (perdieron su cruce) --
        en vez de bajarle la opacidad a la tarjeta entera (que dejaba
        traslucir, por transparencia, el trazo del bracket dibujado
        atrás -- bug reportado: "se ven las líneas detrás de los que
        tienen opacidad baja"), la tarjeta se dibuja SIEMPRE entera y
        opaca (tapa la línea de atrás por completo, como corresponde)
        y recién ENCIMA, si 'dim' es True, se le pone un velo negro
        semitransparente -- misma sensación de "apagado", pero sin
        que se filtre nada por detrás. Pedido explícito: "podría
        reemplazarse con el recuadro al 100% y un recuadro negro al
        50% por encima. Eso lo simplificaría".

        'alpha': sólo para la animación de "cae y se desvanece" del
        perdedor en la pantalla de resultado (ver draw(), fase
        "result") -- ahí SÍ hace falta un degradé numérico continuo
        (no un apagado fijo) y no hay ningún trazo de fondo detrás que
        se pueda filtrar, así que ese caso puntual sigue usando la
        transparencia real de siempre."""
        # El radio de las esquinas es TAMBIÉN un porcentaje del tamaño
        # de la tarjeta, no un valor fijo -- por la misma razón que el
        # borde (ver nota más abajo): con un radio fijo, el cuadradito
        # chico de un torneo grande quedaba con las esquinas
        # desproporcionadamente redondeadas (casi un círculo) en vez
        # de mantener la misma proporción que el cuadradito grande
        # (bug reportado: "16 jugadores parece casi circular, 8
        # jugadores parece más cuadrado"). Con un TOPE máximo (igual
        # que el borde, ver más abajo): sin tope, la tarjeta grande de
        # la pantalla "personaje avanza" (card_size mucho más grande
        # que las del bracket) terminaba con las esquinas exageradas.
        radius = max(2, min(round(size * 0.15), C.scaled(14)))
        rect = pygame.Rect(0, 0, size, size)
        rect.center = center
        img = load_scaled_cached(entrant["selection_path"], (size, size), self._sel_cache, radius=radius)
        card = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(card, (35, 35, 42, 255), card.get_rect(), border_radius=radius)
        if img:
            card.blit(img, img.get_rect(center=(size // 2, size // 2)))
        # El borde es un PORCENTAJE del tamaño de la tarjeta, no un
        # valor fijo -- con un valor fijo, cuando el torneo tiene
        # muchos partidos y el cuadradito se achica (ver
        # _compute_layout_geometry), el borde seguía teniendo siempre
        # el mismo grosor de siempre -- y terminaba viéndose
        # desproporcionadamente grueso en relación a lo chico que
        # había quedado el cuadradito (bug reportado: "el borde gris
        # es demasiado grande respecto a la elección de personaje...
        # se ve mucho más grande en relación cuando hay muchos
        # cuadrados"). Con un porcentaje, el borde se achica junto con
        # la tarjeta, en la misma proporción siempre -- pero CON UN
        # TOPE máximo: el mismo porcentaje que se ve bien en las
        # tarjetas chicas del bracket (37 a 53px) se volvía un borde
        # grueso de más en la tarjeta grande de la pantalla "personaje
        # avanza" (card_size bastante más grande) -- bug reportado:
        # "quedó con los bordes... muy gruesos". El tope mantiene el
        # mismo grosor fino que ya se veía bien en selección de
        # personaje y en los brackets, sin importar cuán grande sea la
        # tarjeta.
        border_w = max(2, min(round(size * 0.065), C.scaled(6)))
        border = pygame.Surface((size + border_w * 2, size + border_w * 2), pygame.SRCALPHA)
        pygame.draw.rect(border, (*color, 255), border.get_rect(), width=border_w, border_radius=radius + border_w)
        if alpha is not None and alpha < 255:
            card.set_alpha(alpha)
            border.set_alpha(alpha)
        surface.blit(card, card.get_rect(center=center))
        surface.blit(border, border.get_rect(center=center))
        if dim:
            overlay = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (0, 0, 0, 130), overlay.get_rect(), border_radius=radius)
            surface.blit(overlay, overlay.get_rect(center=center))

    def _draw_pose(self, surface, ui, entrant, side, y_offset=0):
        """Pose grande del luchador a un costado (izquierda o derecha).
        Se corre un poco hacia afuera de su posición de siempre --
        el PNG de 700x700 tiene de sobra alrededor del personaje, así
        que no se pierde nada al recortarse un poco (pedido explícito,
        con capturas de referencia). No hace falta correrla más que
        eso para "esquivar" el árbol del bracket: los brackets y
        selection.png se dibujan DESPUÉS (ver draw()) y quedan siempre
        por encima de la pose, así que un torneo grande simplemente
        tapa un poco más de la pose -- no hay que perseguir el ancho
        exacto del árbol acá."""
        pose = load_scaled_cached(entrant["pose_path"], (SIDE_PANEL_W, SIDE_PANEL_W), self._pose_cache)
        y = C.SCREEN_H // 2 - SIDE_PANEL_W // 2 + y_offset
        push = C.scaled(70)
        if side == "left":
            x = SIDE_MARGIN - push
        else:
            x = C.SCREEN_W - SIDE_MARGIN - SIDE_PANEL_W + push
            # Mismo caso especial que en CharacterSelect: si el
            # personaje tiene una foto aparte para el lado derecho (ej.
            # Adrián, con texto legible en la ropa que quedaría al
            # revés si sólo se espejara la de siempre), se usa ESA, sin
            # espejar nada.
            pose = load_scaled_cached(entrant["pose_path_p2"], (SIDE_PANEL_W, SIDE_PANEL_W), self._pose_cache)
            if pose and entrant["pose_p2_flip"]:
                pose = pygame.transform.flip(pose, True, False)
        if pose:
            surface.blit(pose, (x, y))
        color = P1_COLOR if side == "left" else P2_COLOR
        prefix = "J1" if side == "left" else "J2"
        name_txt = ui.font_small.render(f"{prefix}: {entrant['label']}", True, color)
        # Misma posición EXACTA que "J1: nombre" en la pantalla de 2
        # Jugadores (no relativa al panel de pose, que no coincidía --
        # bug reportado: "los nombres siguen apareciendo arriba" -- y
        # tampoco se mueve con la animación de "subida" de la pose, para
        # que quede fijo como en esa pantalla).
        name_y = C.SCREEN_H // 2 + C.scaled(240)
        if side == "left":
            name_x = C.scaled(40)
        else:
            name_x = C.SCREEN_W - C.scaled(40) - name_txt.get_width()
        surface.blit(name_txt, (name_x, name_y))

    def _draw_bracket(self, surface, ui):
        """Bracket en el medio: como la estructura COMPLETA del árbol
        ya se conoce de entrada (el sorteo es al azar una sola vez, al
        armar el torneo -- ver tournament.py y _build_slot_structure),
        las LÍNEAS son SIEMPRE las mismas, de punta a punta, en
        cualquier ronda -- se calcularon una sola vez al arrancar (ver
        self._fixed_lines en __init__/_compute_slot_positions) y acá
        sólo se dibujan, nunca se recalculan (pedido explícito: "Solo
        tienen que moverse los personajes, NO las líneas de fondo" /
        "unificar los brackets a lo largo de todo el torneo").

        Lo único que cambia ronda a ronda son las TARJETAS: cada
        peleador tiene su slot fijo de entrada (ver
        _compute_slot_positions); a medida que se van jugando los
        partidos (reales, de self.bracket.history y de la ronda
        actual), su tarjeta aparece en el slot de arriba que le
        corresponda -- nunca antes de tiempo (no se puede saber quién
        gana antes de jugar), pero la POSICIÓN de ese slot ya estaba
        dibujada desde la Ronda 1.

        TODOS los cuadraditos miden SIEMPRE lo mismo -- se calculó una
        sola vez al arrancar (ver self._geo).

        Las TARJETAS (selection.png) se devuelven en una lista para
        que quien llama las pinte recién después de las poses, y así
        queden por ENCIMA de ellas (pedido explícito: "pose.png
        debería ir por detrás de selection.png")."""
        b = self.bracket
        g = self._geo
        card_size = g["card_size"]
        line_color = (150, 150, 158)
        positions = self._slot_positions
        pending_cards = []

        for p1, p2 in self._fixed_lines:
            pygame.draw.line(surface, line_color, p1, p2, 2)

        # Asigna cada peleador a su slot: primero la Ronda 1 (las hojas,
        # siempre conocidas de entrada), después cada ronda YA jugada
        # (self.bracket.history, en orden), y por último la ronda
        # actual (que puede estar a mitad de jugarse).
        n_matches_r1 = len(b.matches) if not b.history else len(b.history[0]["matches"])
        r1_matches = b.history[0]["matches"] if b.history else b.matches
        r1_bye = b.history[0]["bye"] if b.history else b.bye
        slot_entrant = {}
        for i, (a, bb) in enumerate(r1_matches):
            slot_entrant[2 * i] = a
            slot_entrant[2 * i + 1] = bb
        if r1_bye is not None:
            slot_entrant[2 * n_matches_r1] = r1_bye

        rounds_seq = []
        for rnd in b.history:
            rounds_seq.append({
                "matches": rnd["matches"], "bye": rnd["bye"],
                "results": rnd["results"], "match_index": len(rnd["matches"]),
                "is_current": False,
            })
        rounds_seq.append({
            "matches": b.matches, "bye": b.bye,
            "results": b.round_results, "match_index": b.match_index,
            "is_current": True,
        })

        for round_idx, round_data in enumerate(rounds_seq):
            struct = self._slot_structure[round_idx]
            results = round_data["results"]
            match_index = round_data["match_index"]
            is_current = round_data["is_current"]

            for i, (slot_a, slot_b) in enumerate(struct["pairs"]):
                a = slot_entrant.get(slot_a)
                bb = slot_entrant.get(slot_b)
                if a is None or bb is None:
                    continue  # esta ronda todavía no se sabe quién llega hasta acá
                ax, ay = positions[slot_a]
                bx, by = positions[slot_b]
                decided = i < match_index
                is_active = is_current and i == match_index
                new_slot = struct["winner_slots"][i]
                # OJO: 'positions[new_slot]' puede haber sido pisada por
                # una ronda MÁS ADELANTE (si este mismo slot terminó
                # además recibiendo un bye más arriba) -- para dibujar
                # ESTA ronda hace falta la posición que tuvo en el
                # momento en que se creó, no la más nueva (ver
                # self._winner_slot_positions en _compute_slot_positions
                # -- bug encontrado: dos peleadores de ramas distintas
                # con tarjetas exactamente superpuestas).
                nx, ny = self._winner_slot_positions[new_slot]

                if decided:
                    # 'results' viene en orden [ganador partido 0,
                    # ganador partido 1, ..., bye?] -- el bye (si hay)
                    # va SIEMPRE al final, nunca adelante (ver
                    # tournament.py) -- así que el ganador del partido
                    # 'i' es simplemente results[i], sin ningún offset.
                    winner = results[i]
                    loser = bb if winner is a else a
                    # el que PIERDE se apaga (queda frozen ahí, con el
                    # velo negro encima -- ver _card) -- el que GANA se
                    # mantiene SIEMPRE al 100%, tanto acá (de dónde
                    # vino) como de nuevo arriba, en su slot nuevo --
                    # antes el ganador TAMBIÉN se atenuaba acá abajo,
                    # como si hubiese perdido algo, lo cual no tenía
                    # sentido (bug reportado: "deberían opacarse los
                    # que pierden y mantenerse al 100% los que ganan").
                    pending_cards.append((loser, (ax if loser is a else bx, ay), (90, 90, 100), card_size, True))
                    pending_cards.append((winner, (ax if winner is a else bx, ay), (120, 120, 128), card_size, False))
                    pending_cards.append((winner, (nx, ny), (120, 120, 128), card_size, False))
                    slot_entrant[new_slot] = winner
                else:
                    color_a = P1_COLOR if is_active else (90, 90, 100)
                    color_b = P2_COLOR if is_active else (90, 90, 100)
                    pending_cards.append((a, (ax, ay), color_a, card_size, False))
                    pending_cards.append((bb, (bx, by), color_b, card_size, False))

            if struct["bye"] is not None:
                bye_entrant = slot_entrant.get(struct["bye"])
                if bye_entrant is not None and round_idx in self._bye_round_positions:
                    _old_x, _old_y, new_x, new_y = self._bye_round_positions[round_idx]
                    # El bye se muestra UNA SOLA VEZ, arriba, en la
                    # ronda en la que arranca a jugar -- no "peleó"
                    # nada esta ronda (no hay ningún cruce real), así
                    # que no correspondía mostrarlo también abajo, como
                    # si hubiese estado esperando ahí solo -- pedido
                    # explícito: "el bye no tiene que aparecer dos
                    # veces: solo arriba, en la ronda que empieza él".
                    pending_cards.append((bye_entrant, (new_x, new_y), (140, 140, 148), card_size, False))

        # Pedido explícito: ya no hace falta el cartel "fulano: ya pasó
        # de ronda" -- una vez que el bye se ve una sola vez, arriba,
        # en su lugar correcto del árbol (y no como si estuviera
        # esperando abajo, solo), se entiende con sólo mirar el cuadro,
        # sin necesidad de aclararlo aparte con texto.

        return pending_cards

    def draw(self, surface, ui):
        ui.draw_screen_background(surface, ui.character_selection_background)
        b = self.bracket
        title = "FINAL" if b.is_final_match() else f"RONDA {b.round_number}"
        ui.draw_title(surface, title, y=C.scaled(30))

        if self.phase == "result" or self.phase == "result_done":
            # Se ve la pelea que acaba de terminar: el ganador se queda
            # resaltado, el perdedor "cae" con la opacidad bajando --
            # mismo lenguaje visual que un rival ya superado en la Torre
            # de Batalla.
            cx = C.SCREEN_W // 2
            card_y = C.scaled(320)
            card_size = C.scaled(150)
            gap = C.scaled(230)
            fall_t = min(1.0, self.anim_t / self.RESULT_DURATION)
            loser_y = card_y + int(fall_t * C.scaled(90))
            loser_alpha = max(60, 255 - int(fall_t * 195))
            self._card(surface, ui, self.result_winner, (cx, card_y), (120, 120, 128), card_size)
            self._card(surface, ui, self.result_loser, (cx + gap, loser_y), (90, 90, 100), card_size, alpha=loser_alpha)
            win_txt = ui.font_med.render(f"{self.result_winner['label']} avanza", True, C.YELLOW)
            surface.blit(win_txt, win_txt.get_rect(center=(cx, card_y + card_size // 2 + C.scaled(50))))
            footer_cfg = load_input_config()
            ui.draw_footer_mixed(surface, build_footer_parts(footer_cfg, [("confirm", "continuar")]), C.SCREEN_H - C.scaled(30))
            return

        match = b.current_match()
        if match is None:
            return
        a, c = match

        rise_progress = min(1.0, self.anim_t / self.RISE_DURATION) if self.phase == "rising" else 1.0
        eased = 1 - (1 - rise_progress) ** 3  # ease-out: arranca rápido, frena suave (mismo criterio que la Torre)
        rise_offset = int((1 - eased) * C.scaled(120))  # las poses "suben" desde abajo al entrar a la pelea

        # Bracket bien grande, apoyado a la altura del piso (donde están
        # los pies de las poses) y subiendo casi hasta arriba de todo.
        # Se dibuja en TRES capas, en este orden -- pedido explícito:
        # "pose.png debería ir por detrás de selection.png":
        #   1) las LÍNEAS del árbol (bien al fondo)
        #   2) las poses grandes de los personajes (tapan las líneas
        #      donde se cruzan -- antes tapaban TAMBIÉN las tarjetitas
        #      selection.png del bracket, bug reportado con captura)
        #   3) las tarjetitas selection.png del bracket, siempre por
        #      ENCIMA de las poses, nunca tapadas por ellas.
        pending_cards = self._draw_bracket(surface, ui)

        # Pedido explícito: sacar el "VS" del medio -- no encontraba una
        # posición que no terminara tapando algo según la ronda, y sin
        # el "VS" el color de cada cuadradito (celeste/rojo, resaltado
        # solo el que está en juego ahora) ya deja bien claro cuál es la
        # pelea actual.
        self._draw_pose(surface, ui, a, "left", y_offset=rise_offset)
        self._draw_pose(surface, ui, c, "right", y_offset=rise_offset)

        for entrant, pos, color, size, dim in pending_cards:
            self._card(surface, ui, entrant, pos, color, size, dim=dim)

        footer_cfg = load_input_config()
        if self.phase == "ready":
            ui.draw_footer_mixed(surface, build_footer_parts(footer_cfg, [("confirm", "pelear")]), C.SCREEN_H - C.scaled(30))


# ======================================================================
# Selección de escenario
# ======================================================================
STAGE_RANDOM_SENTINEL = "__random_stage__"


class StageSelect:
    # Misma idea que CharacterSelect._SHARED_SEL_CACHE: se crea una
    # StageSelect nueva cada vez que se entra a esta pantalla, así que
    # sin caché compartida las miniaturas se recargarían y redondearían
    # de cero cada vez.
    _SHARED_THUMB_CACHE = {}

    def __init__(self, stage_paths):
        # Orden fijo pedido explícitamente (no alfabético): arriba
        # Aleatorio, Dust II, Living Forest, World Tournament; abajo
        # Claypole, Emilio Mitre, Luna Park, Remedios. Cualquier
        # escenario nuevo que se agregue más adelante y no esté en esta
        # lista cae al final, en orden alfabético (para que nunca
        # "desaparezca" de la grilla por no haberse acordado de sumarlo acá).
        FIXED_ORDER = ["Dust II", "Living Forest", "World Tournament", "Claypole", "Emilio Mitre", "Luna Park", "Remedios"]
        fixed_order_lower = [n.lower() for n in FIXED_ORDER]
        def _sort_key(p):
            name = stage_display_name(p)
            try:
                return (0, fixed_order_lower.index(name.lower()))
            except ValueError:
                return (1, name.lower())
        real = sorted(stage_paths, key=_sort_key)
        self.stages = [{
            "path": STAGE_RANDOM_SENTINEL,
            "name": "Aleatorio",
            "thumb_path": os.path.join("assets", "ui", "random_stage_selection.png"),
        }] + [
            {"path": p, "name": stage_display_name(p), "thumb_path": p}
            for p in real
        ]
        self.index = 0
        self.done = False
        self.choice = None
        self.cancelled = False
        self._thumb_cache = self._SHARED_THUMB_CACHE

        n = len(self.stages)
        avail_w = C.SCREEN_W - 2 * STAGE_GRID_SIDE_MARGIN
        avail_h = C.SCREEN_H - STAGE_GRID_TOP - STAGE_GRID_BOTTOM_MARGIN
        self.cell_w, self.cols, self.rows = self._compute_grid(n, avail_w, avail_h)

    @staticmethod
    def _compute_grid(n, avail_w, avail_h, gap=STAGE_GRID_GAP):
        """Misma idea que CharacterSelect._compute_grid (elegir columnas/
        filas que MAXIMIZAN el tamaño de celda sin salirse de la
        pantalla), pero con celdas 16:9 en vez de cuadradas, y
        descontando el lugar del nombre escrito debajo de cada una."""
        if n <= 0:
            return STAGE_CELL_MAX_W, 1, 1
        best = None
        for cols in range(1, n + 1):
            rows = math.ceil(n / cols)
            cell_w_from_width = (avail_w - (cols - 1) * gap) / cols
            row_h = (avail_h - (rows - 1) * gap) / rows
            cell_h_from_height = row_h - STAGE_LABEL_GAP - STAGE_LABEL_H
            cell_w_from_height = cell_h_from_height * 16 / 9
            cell_w = min(cell_w_from_width, cell_w_from_height)
            if cell_w <= 0:
                continue
            if best is None or cell_w > best[0]:
                best = (cell_w, cols, rows)
        cell_w, cols, rows = best or (STAGE_CELL_MIN_W, 1, n)
        cell_w = max(STAGE_CELL_MIN_W, min(STAGE_CELL_MAX_W, cell_w))
        return cell_w, cols, rows

    def _thumb(self, entry, size, radius=0):
        key = (entry["thumb_path"], size, radius)
        if key not in self._thumb_cache:
            still = load_stage_thumbnail(entry["thumb_path"])
            img = pygame.transform.smoothscale(still.frames[0], size)
            if radius:
                img = round_image_corners(img, radius)
            self._thumb_cache[key] = img
        return self._thumb_cache[key]

    def cell_rects(self):
        cell_w = self.cell_w
        cell_h = cell_w * 9 / 16
        gap = STAGE_GRID_GAP
        grid_w = self.cols * cell_w + (self.cols - 1) * gap
        row_h = cell_h + STAGE_LABEL_GAP + STAGE_LABEL_H
        grid_h = self.rows * row_h + (self.rows - 1) * gap
        area_h = C.SCREEN_H - STAGE_GRID_TOP - STAGE_GRID_BOTTOM_MARGIN
        start_x = C.SCREEN_W // 2 - grid_w // 2
        start_y = STAGE_GRID_TOP + max(0, (area_h - grid_h) // 2)
        rects = []
        for i in range(len(self.stages)):
            x = start_x + (i % self.cols) * (cell_w + gap)
            y = start_y + (i // self.cols) * (row_h + gap)
            rects.append(pygame.Rect(int(x), int(y), int(cell_w), int(row_h)))
        return rects

    def hit_test(self, pos):
        for i, r in enumerate(self.cell_rects()):
            if r.collidepoint(pos):
                return i
        return None

    def apply_tap(self, idx):
        if idx is None or not (0 <= idx < len(self.stages)):
            return
        if self.index == idx:
            self.choice = self.stages[idx]["path"]
            self.done = True
        else:
            self.index = idx

    def update(self, inp, dt=0.0):
        if not self.stages:
            self.done = True
            self.choice = None
            return
        n = len(self.stages)
        if inp.just_pressed("right"):
            self.index = (self.index + 1) % n
        elif inp.just_pressed("left"):
            self.index = (self.index - 1) % n
        elif inp.just_pressed("down"):
            self.index = (self.index + self.cols) % n
        elif inp.just_pressed("up"):
            self.index = (self.index - self.cols) % n
        elif inp.just_pressed("confirm"):
            self.choice = self.stages[self.index]["path"]
            self.done = True
        elif inp.just_pressed("start"):
            # Gesto secreto de siempre (ENTER en teclado / botón Menú-
            # Select en joystick): no importa qué escenario esté
            # resaltado, manda directo a Final Destination -- guiño a
            # Smash Bros. Si por algún motivo no está el archivo, no
            # hace nada raro: sigue como si nada (fallback silencioso).
            secret = get_secret_stage()
            if secret:
                self.choice = secret
                self.done = True
        elif inp.just_pressed("cancel"):
            self.cancelled = True

    def draw(self, surface, ui):
        ui.draw_screen_background(surface, ui.character_selection_background)
        ui.draw_title(surface, "ELEGÍ EL ESCENARIO", y=C.scaled(35))
        if not self.stages:
            ui.draw_center_text(surface, "No hay escenarios en assets/stages/", C.RED)
            return

        cell_w = self.cell_w
        cell_h = cell_w * 9 / 16
        gap = STAGE_GRID_GAP
        grid_w = self.cols * cell_w + (self.cols - 1) * gap
        row_h = cell_h + STAGE_LABEL_GAP + STAGE_LABEL_H
        grid_h = self.rows * row_h + (self.rows - 1) * gap
        area_h = C.SCREEN_H - STAGE_GRID_TOP - STAGE_GRID_BOTTOM_MARGIN
        start_x = C.SCREEN_W // 2 - grid_w // 2
        start_y = STAGE_GRID_TOP + max(0, (area_h - grid_h) // 2)

        radius = C.scaled(8)
        for i, entry in enumerate(self.stages):
            col = i % self.cols
            row = i // self.cols
            x = start_x + col * (cell_w + gap)
            y = start_y + row * (row_h + gap)
            rect = pygame.Rect(int(x), int(y), int(cell_w), int(cell_h))

            # Mismo marco que Selección de Personajes/Torneo (antes esta
            # pantalla no tenía ninguno -- la miniatura ocupaba el
            # recuadro entero): se achica un poco la miniatura para que
            # asome el marco alrededor, y ESE marco es el que cambia de
            # color al elegido, sin dibujar un anillo aparte encima.
            pad_h = SEL_FRAME_PAD * (cell_h / cell_w)  # mismo recorte proporcional, respeta el 16:9
            img = self._thumb(entry, (int(cell_w - SEL_FRAME_PAD), int(cell_h - pad_h)), radius=radius)
            frame_color = P1_COLOR if self.index == i else (45, 45, 52)
            pygame.draw.rect(surface, frame_color, rect, border_radius=radius)
            if img:
                surface.blit(img, img.get_rect(center=rect.center))

            label = ui.font_tiny.render(entry["name"], True, C.WHITE)
            surface.blit(label, label.get_rect(centerx=rect.centerx, top=rect.bottom + STAGE_LABEL_GAP))

        footer_cfg = load_input_config()
        footer = build_footer_parts(footer_cfg, [("confirm", "confirmar"), ("cancel", "volver")])
        ui.draw_footer_mixed(surface, footer, C.SCREEN_H - C.scaled(25))
        if ui.touch_lists:
            ui.draw_touch_hint(surface, getattr(self, "touch_hint", None) or "Tocá un escenario para marcarlo y otra vez para elegirlo")


# ======================================================================
# Pausa
# ======================================================================
class PauseMenu:
    ITEMS = ["Reanudar", "Opciones", "Volver a Inicio"]
    CHOICES = ["resume", "options", "menu"]

    def __init__(self, net=False):
        self.index = 0
        self.done = False
        self.choice = None  # "resume" | "options" | "menu"
        if net:
            # partida por WiFi: sin Opciones (la pelea sigue "viva" en
            # los otros celulares mientras tanto)
            self.ITEMS = ["Reanudar", "Abandonar partida"]
            self.CHOICES = ["resume", "menu"]

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ITEMS)
        elif inp.just_pressed("confirm") or inp.just_pressed("start"):
            self.choice = self.CHOICES[self.index]
            self.done = True

    def draw(self, surface, ui, frozen_frame=None):
        if frozen_frame:
            surface.blit(frozen_frame, (0, 0))
        ui.draw_overlay(surface)
        ui.draw_menu_list(surface, "PAUSA", self.ITEMS, self.index)
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [("confirm", "confirmar")]),
            C.SCREEN_H - C.scaled(30),
        )


class VersusEndMenu:
    """Pantalla de fin de pelea en modo 2 Jugadores: nada de cartel de
    texto ni vuelta automática al menú -- se queda en la escena con el
    ganador festejando, y da 3 opciones."""

    ITEMS = ["Pelear de nuevo", "Cambiar personajes", "Volver a Inicio"]

    def __init__(self, winner_name, net=False):
        self.winner_name = winner_name
        if net:
            self.ITEMS = ["Pelear de nuevo", "Cambiar personajes", "Volver a la sala"]
        self.index = 0
        self.done = False
        self.choice = None  # "rematch" | "recharacter" | "menu"

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ITEMS)
        elif inp.just_pressed("confirm") or inp.just_pressed("start"):
            self.choice = ["rematch", "recharacter", "menu"][self.index]
            self.done = True

    def draw(self, surface, ui, frozen_frame=None):
        if frozen_frame:
            surface.blit(frozen_frame, (0, 0))
        ui.draw_overlay(surface, alpha=140)
        ui.draw_title(surface, f"¡{self.winner_name.upper()} GANA LA PELEA!", y=C.scaled(70))
        ui.draw_menu_list(surface, "", self.ITEMS, self.index, center_y=C.SCREEN_H // 2 + C.scaled(60))
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [("confirm", "confirmar")]),
            C.SCREEN_H - C.scaled(25),
        )


# ======================================================================
class TowerDefeatMenu:
    """Pantalla al perder en la Torre de Batalla: da la opción de
    reintentar la MISMA pelea (mismo rival, misma dificultad) en vez de
    mandarte directo al menú."""

    ITEMS = ["Reintentar", "Volver al menú"]

    def __init__(self, floor, total_floors):
        self.floor = floor
        self.total_floors = total_floors
        self.index = 0
        self.done = False
        self.choice = None  # "retry" | "menu"

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ITEMS)
        elif inp.just_pressed("confirm") or inp.just_pressed("start"):
            self.choice = ["retry", "menu"][self.index]
            self.done = True

    def draw(self, surface, ui):
        surface.fill(C.DARK)
        ui.draw_title(surface, "DERROTA", y=C.scaled(70), color=C.RED)
        ui.draw_small_center(surface, f"Piso {self.floor + 1} de {self.total_floors}", C.SCREEN_H // 2 - C.scaled(40))
        ui.draw_menu_list(surface, "", self.ITEMS, self.index, center_y=C.SCREEN_H // 2 + C.scaled(60))
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [("confirm", "confirmar")]),
            C.SCREEN_H - C.scaled(25),
        )


# ======================================================================
# Opciones (volumen + pantalla completa + entrada a Configurar Controles)
# ======================================================================
class OptionsMenu:
    """Menú HUB de Opciones: elegís una categoría (Sonido/Gráficos/
    Controles) y ahí adentro está cada ajuste puntual -- ver
    OptionsSubMenu más abajo, que es el que realmente los muestra."""

    ROWS = ["sound", "graphics", "back"] if device.TOUCH_UI else ["sound", "graphics", "controls", "back"]
    LABELS = {
        "sound": "Sonido",
        "graphics": "Pantalla" if device.TOUCH_UI else "Gráficos",
        "controls": "Controles",
        "back": "Volver",
    }

    def __init__(self):
        self.index = 0
        self.done = False
        self.choice = None  # "sound" | "graphics" | "controls" | None (None = volver del todo)

    def update(self, inp):
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.ROWS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.ROWS)
        elif inp.just_pressed("confirm"):
            row = self.ROWS[self.index]
            self.done = True
            self.choice = None if row == "back" else row
        elif inp.just_pressed("cancel"):
            self.done = True
            self.choice = None

    def draw(self, surface, ui):
        surface.fill(C.DARK)
        items = [self.LABELS[k] for k in self.ROWS]
        ui.draw_menu_list(surface, "OPCIONES", items, self.index, center_y=C.SCREEN_H // 2 - C.scaled(10))
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [("confirm", "confirmar"), ("cancel", "volver")]),
            C.SCREEN_H - C.scaled(30),
        )


# Qué fila de OptionsSubMenu.LABELS entra en cada categoría del hub
# (OptionsMenu) -- así main.py solo necesita saber el nombre de la
# categoría elegida para armar el submenú correspondiente.
OPTIONS_CATEGORIES = {
    "sound": (["music_volume", "stage_music_volume", "sfx_volume", "announcer_volume"], "SONIDO"),
    "graphics": (["resolution", "touch_scale"], "PANTALLA") if device.TOUCH_UI else (["resolution", "fullscreen"], "GRÁFICOS"),
    "controls": (["controls_p1", "controls_p2", "controls_swap"], "CONTROLES"),
}


class OptionsSubMenu:
    """Una categoría puntual de Opciones (Sonido / Gráficos / Controles),
    con la misma lógica de ajuste que tenía el menú de Opciones de una
    sola pantalla de antes -- solo que ahora cada instancia muestra
    nada más que las filas de SU categoría (rows), pasadas desde
    main.py según lo que se eligió en el OptionsMenu (hub)."""

    LABELS = {
        "music_volume": "Volumen música",
        "stage_music_volume": "Volumen música de escenario",
        "sfx_volume": "Volumen efectos",
        "announcer_volume": "Volumen presentador",
        "resolution": "Resolución",
        "fullscreen": "Pantalla completa",
        "controls_p1": "Controles J1",
        "controls_p2": "Controles J2",
        "controls_swap": "Invertir joysticks J1/J2",
        "touch_scale": "Tamaño de botones",
        "back": "Volver",
    }
    # Mismo orden que C.RESOLUTIONS -- ciclar con izquierda/derecha recorre esta lista.
    # En el celular no se ofrece 1080p (pesa mucho y en una pantalla
    # chica no se nota la diferencia).
    RESOLUTION_OPTIONS = ["540p", "720p"] if device.TOUCH_UI else ["540p", "720p", "1080p"]

    def __init__(self, settings, rows, title):
        self.settings = settings
        self.rows = list(rows) + ["back"]
        self.title = title
        self.index = 0
        self.done = False
        self.open_controls_player = None  # None | 0 | 1
        self.fullscreen_changed = False
        self.message = ""  # feedback breve (ej. tras invertir joysticks) -- se limpia solo al moverse

    def _adjust(self, key, direction):
        if key == "fullscreen":
            self.settings["fullscreen"] = not self.settings["fullscreen"]
            self.fullscreen_changed = True
        elif key == "resolution":
            opts = self.RESOLUTION_OPTIONS
            cur = self.settings.get("resolution", C.RESOLUTION)
            idx = opts.index(cur) if cur in opts else opts.index(C.RESOLUTION)
            self.settings["resolution"] = opts[(idx + direction) % len(opts)]
            if device.TOUCH_UI and self.settings["resolution"] != C.RESOLUTION:
                self.message = "Se aplica la próxima vez que abras el juego"
            else:
                self.message = ""
        elif key == "touch_scale":
            cur = self.settings.get("touch_scale", 1.0)
            self.settings["touch_scale"] = round(min(1.4, max(0.7, cur + direction * 0.1)), 2)
        else:
            self.settings[key] = round(min(1.0, max(0.0, self.settings[key] + direction * 0.1)), 2)

    def _swap_joysticks(self):
        """Intercambia el joystick físico asignado a J1 con el de J2 (con
        UN solo click, en vez de tener que rehacer botón por botón la
        reasignación de cada acción en las dos pantallas de 'Configurar
        Controles' -- pedido explícito: 'quiero que el P1 sea el 2 y
        viceversa'). Sólo mueve el 'joystick' (índice + mapeo de
        botones de ESE control) -- las teclas de teclado de cada
        jugador, si tiene, quedan donde estaban."""
        config = load_input_config()
        players = config["players"]
        joy0 = players[0].get("joystick")
        joy1 = players[1].get("joystick")
        if joy0 is not None:
            players[1]["joystick"] = joy0
        else:
            players[1].pop("joystick", None)
        if joy1 is not None:
            players[0]["joystick"] = joy1
        else:
            players[0].pop("joystick", None)
        save_input_config(config)
        if joy0 is None and joy1 is None:
            self.message = "No hay ningún joystick asignado todavía"
        else:
            self.message = "¡Listo! J1 y J2 invirtieron sus joysticks"

    def update(self, inp):
        row = self.rows[self.index]
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(self.rows)
            self.message = ""
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(self.rows)
            self.message = ""
        elif inp.just_pressed("left"):
            if row not in ("controls_p1", "controls_p2", "controls_swap", "back"):
                self._adjust(row, -1)
        elif inp.just_pressed("right"):
            if row not in ("controls_p1", "controls_p2", "controls_swap", "back"):
                self._adjust(row, 1)
        elif inp.just_pressed("confirm"):
            if row == "fullscreen":
                self._adjust(row, 1)
            elif row == "controls_p1":
                self.open_controls_player = 0
            elif row == "controls_p2":
                self.open_controls_player = 1
            elif row == "controls_swap":
                self._swap_joysticks()
            elif row == "back":
                self.done = True
        elif inp.just_pressed("cancel"):
            self.done = True

    def _row_text(self, key):
        label = self.LABELS[key]
        if key == "fullscreen":
            return f"{label}: {'Sí' if self.settings['fullscreen'] else 'No'}"
        if key == "resolution":
            value = self.settings.get("resolution", C.RESOLUTION)
            return f"{label}: {value}"
        if key == "touch_scale":
            return f"{label}: {int(round(self.settings.get('touch_scale', 1.0) * 100))}%"
        if key in ("controls_p1", "controls_p2", "controls_swap", "back"):
            return label
        return f"{label}: {int(self.settings[key] * 100)}%"

    def handle_tap(self, pos):
        """Versión táctil: botones − / + al costado de cada fila ajustable."""
        for (row_idx, direction), rect in getattr(self, "_adj_hits", {}).items():
            if rect.collidepoint(pos):
                self.index = row_idx
                self._adjust(self.rows[row_idx], direction)
                return True
        return False

    def draw(self, surface, ui):
        surface.fill(C.DARK)
        items = [self._row_text(k) for k in self.rows]
        hits = ui.draw_menu_list(surface, self.title, items, self.index, center_y=C.SCREEN_H // 2 - C.scaled(10))
        self._adj_hits = {}
        if ui.touch_lists and hits:
            r = C.scaled(19)
            for rect, i in hits:
                if self.rows[i] in ("controls_p1", "controls_p2", "controls_swap", "back", "fullscreen"):
                    continue
                cy = rect.centery
                self._adj_hits[(i, -1)] = ui.draw_round_button(surface, (rect.left - r - C.scaled(4), cy), r, "−")
                self._adj_hits[(i, 1)] = ui.draw_round_button(surface, (rect.right + r + C.scaled(4), cy), r, "+")
        if self.message:
            msg_img = ui.font_small.render(self.message, True, C.YELLOW)
            surface.blit(msg_img, msg_img.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H // 2 + C.scaled(110))))
        footer_cfg = load_input_config()
        left_l, right_l = key_label(footer_cfg, "left"), key_label(footer_cfg, "right")
        ui.draw_footer_mixed(
            surface,
            build_footer_parts(footer_cfg, [(f"{left_l}/{right_l}", "ajustar"), ("confirm", "confirmar"), ("cancel", "volver")]),
            C.SCREEN_H - C.scaled(30),
        )


class ControlsRemapMenu:
    """Reasigna teclas/botones. Elegís jugador, elegís acción, apretás
    PUÑO y la próxima tecla/botón que toques queda asignada."""

    def __init__(self, input_config, initial_player=0):
        self.config = input_config
        self.player = initial_player
        self.index = 0
        self.waiting = False
        self.done = False
        self.message = ""

    def current_profile(self):
        return self.config["players"][self.player]

    def update(self, inp):
        if self.waiting:
            return  # se resuelve por evento crudo, ver handle_raw_event
        if inp.just_pressed("left") or inp.just_pressed("right"):
            self.player = 1 - self.player
        elif inp.just_pressed("up"):
            self.index = (self.index - 1) % len(ACTIONS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(ACTIONS)
        elif inp.just_pressed("confirm"):
            self.waiting = True
            self.message = f"Presioná una tecla/botón para '{ACTIONS[self.index]}'..."
        elif inp.just_pressed("cancel"):
            save_input_config(self.config)
            self.done = True

    def handle_raw_event(self, event):
        """Se llama desde main.py con los eventos crudos de pygame mientras
        self.waiting es True, para capturar la próxima tecla o botón.
        Asigna SIN borrar la otra fuente (teclado y joystick conviven)."""
        if not self.waiting:
            return
        profile = self.current_profile()
        action = ACTIONS[self.index]
        if event.type == pygame.KEYDOWN:
            key_name = pygame.key.name(event.key)
            profile.setdefault("keys", {})[action] = key_name
            self.waiting = False
            self.message = f"'{action}' asignado a la tecla '{key_name}'"
        elif event.type == pygame.JOYBUTTONDOWN:
            joy_cfg = profile.get("joystick")
            if not joy_cfg or joy_cfg.get("index") != event.joy:
                joy_cfg = {"index": event.joy, "axis_x": 0, "axis_y": 1,
                           "hat": 0, "deadzone": 0.35, "buttons": {}}
                profile["joystick"] = joy_cfg
            joy_cfg.setdefault("buttons", {})[action] = event.button
            self.waiting = False
            self.message = f"'{action}' asignado al botón {event.button} del control"

    def draw(self, surface, ui):
        surface.fill(C.DARK)
        ui.draw_small_center(surface, f"CONFIGURAR CONTROLES - JUGADOR {self.player + 1}", C.scaled(40))
        profile = self.current_profile()
        joy_cfg = profile.get("joystick")
        tipo = f"Teclado + Joystick #{joy_cfg['index']}" if joy_cfg else "Solo teclado"
        ui.draw_small_center(surface, f"Entradas activas: {tipo}", C.scaled(70))

        start_y = C.scaled(120)
        row_h = C.scaled(28)
        for i, action in enumerate(ACTIONS):
            color = C.YELLOW if i == self.index else C.WHITE
            key_bound = profile.get("keys", {}).get(action, "-")
            btn = joy_cfg.get("buttons", {}).get(action) if joy_cfg else None
            joy_bound = f"botón {btn}" if btn is not None else "-"
            prefix = "> " if i == self.index else "   "
            text = f"{prefix}{action:10s} : teclado {key_bound}  |  joystick {joy_bound}"
            img = ui.font_small.render(text, True, color)
            surface.blit(img, (C.SCREEN_W // 2 - C.scaled(260), start_y + i * row_h))

        if self.waiting:
            ui.draw_overlay(surface, alpha=120)
            ui.draw_center_text(surface, self.message, C.YELLOW)
            ui.draw_small_center(surface, "(tocá una tecla o un botón de joystick)", C.SCREEN_H // 2 + C.scaled(50))
        else:
            left_l, right_l = key_label(self.config, "left", 0), key_label(self.config, "right", 0)
            ui.draw_footer_mixed(
                surface,
                build_footer_parts(self.config, [
                    (f"{left_l}/{right_l}", "cambiar jugador"), ("↑/↓", "elegir acción"),
                    ("confirm", "reasignar"), ("cancel", "guardar y volver"),
                ]),
                C.SCREEN_H - C.scaled(25),
            )
