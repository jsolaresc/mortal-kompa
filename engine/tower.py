"""
tower.py
----------
Modo "Torre de Batalla" (estilo la torre del Mortal Kombat de Sega
Genesis): elegís tu personaje, peleás contra todos los demás en orden
al azar, cada pelea un 5% más difícil que la anterior. Si ganás, seguís
subiendo. Si perdés, se acabó -- volvés al menú.
"""

import os
import random

import pygame

from engine import constants as C
from engine.menu import SIDE_PANEL_W

FLOOR_H = C.scaled(130)          # alto de cada "piso" de la torre en pantalla
DIFFICULTY_STEP = 1.05  # cada pelea es un 5% mas dificil que la anterior
FINAL_BOSS_DIFFICULTY_MULT = 1.20  # el jefe final es 20% mas dificil que la ultima pelea regular
CLIMB_DURATION = 1.8    # segundos que tarda la animacion de subir un piso
FLOOR_GAP = C.scaled(24)          # distancia entre el cuadrado del jugador y el del rival
BOSS_SCRATCH_DIR = os.path.join("data", "_tower_boss_cache")
# Mismo ícono de "?" que ya se usa para "Aleatorio" en la selección de
# personaje -- se reusa acá para cualquier rival de la Torre que
# TODAVÍA no se peleó (ni siquiera el actual, hasta que arranca la
# pelea): ni nombre ni silueta, cero pistas de quién es.
MYSTERY_SELECTION_PATH = os.path.join("assets", "ui", "random_selection.png")
# Pose grande de "Aleatorio" (silueta gris, ya del mismo tamaño/estilo que
# el resto del roster) -- se usa para el panel GRANDE del rival cuando
# está en misterio, en vez del cuadradito de "?" (ese queda solo para las
# miniaturas chicas de la lista).
MYSTERY_POSE_PATH = os.path.join("assets", "ui", "random_pose.png")


def build_opponent_order(all_characters, player_json_path):
    """Devuelve la lista de personajes (dicts de load_character_list, sin
    "Aleatorio") que hay que enfrentar, en orden al azar, sin repetir y
    sin incluir al propio personaje elegido."""
    real = [c for c in all_characters if c["json_path"] not in (player_json_path, None)]
    order = real[:]
    random.shuffle(order)
    return order


def _make_black_silhouette(src_path, dst_path, size=700):
    """Versión 100% negra (mismo alfa, RGB en 0) de una imagen -- para el
    jefe final: se ve la silueta pero no quién es de verdad. CACHEA en
    disco (la carpeta se llama justamente "_tower_boss_cache"): si ya
    existe, no la vuelve a generar. Antes SIEMPRE la regeneraba desde
    cero (abrir con PIL, procesar, guardar) cada vez que arrancaba una
    Torre nueva, aunque el personaje elegido como jefe fuera el mismo de
    una vez anterior -- eso era buena parte del segundo de traba
    reportado justo después de elegir personaje para la Torre."""
    if os.path.isfile(dst_path):
        return dst_path
    # Solo pygame (en Android no hay PIL): RGB -> 0, alfa intacto
    img = pygame.image.load(src_path)
    black = pygame.Surface(img.get_size(), pygame.SRCALPHA)
    black.blit(img, (0, 0))
    black.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MIN)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    pygame.image.save(black, dst_path)
    return dst_path


def build_final_boss_entry(all_characters, player_json_path):
    """El último escalón de la torre: un personaje CUALQUIERA (puede
    repetirse con algún rival ya enfrentado, menos con el propio
    jugador), pero con los sprites 100% negros y el nombre al revés --
    no se sabe quién es hasta que le ganás. 'json_path' apunta al
    personaje real (así pelea con sus animaciones/golpes de verdad),
    solo el nombre y las imágenes de la torre quedan disfrazados."""
    candidates = [c for c in all_characters if c["json_path"] != player_json_path]
    chosen = random.choice(candidates)
    reversed_name = chosen["name"][::-1].capitalize()

    slug = os.path.splitext(os.path.basename(chosen["json_path"]))[0]
    black_pose = _make_black_silhouette(
        chosen["pose_path"], os.path.join(BOSS_SCRATCH_DIR, f"{slug}_pose.png")
    )
    black_sel = _make_black_silhouette(
        chosen["selection_path"], os.path.join(BOSS_SCRATCH_DIR, f"{slug}_sel.png")
    )
    return {
        "json_path": chosen["json_path"],
        "name": reversed_name,
        "selection_path": black_sel,
        "pose_path": black_pose,
        "is_final_boss": True,
        "real_name": chosen["name"],
    }


class TowerLadder:
    """Maneja el estado (piso actual, dificultad) y la animación visual
    de la torre subiendo entre pelea y pelea."""

    # Compartida entre corridas de la Torre (se crea un TowerLadder nuevo
    # cada vez que se entra), por la misma razón que _SHARED_SEL_CACHE en
    # CharacterSelect -- evita recargar y reescalar las poses grandes de
    # cada rival de nuevo en cada intento.
    _SHARED_POSE_CACHE = {}

    def __init__(self, player_entry, opponents, starting_difficulty, final_boss_entry=None):
        self.player_entry = player_entry
        self.opponents = list(opponents)  # lista ordenada al azar, index 0 = primer rival
        self.final_boss_index = None
        if final_boss_entry is not None:
            self.final_boss_index = len(self.opponents)
            self.opponents.append(final_boss_entry)
        self.total_floors = len(self.opponents)
        self.floor = 0  # cuantas peleas ya gano (0 = a punto de pelear la primera)
        self.difficulty = float(starting_difficulty)
        self.cleared = False  # gano toda la torre
        self._pose_cache = self._SHARED_POSE_CACHE

        # animacion de "subir": arranca en 0 y sube hasta mostrar el piso actual
        self.scroll_y = 0.0
        self._scroll_start = 0.0
        self._scroll_target = 0.0
        self._anim_t = 0.0
        self.anim_done = False
        self.start_climb()

    @property
    def current_opponent(self):
        if self.floor >= self.total_floors:
            return None
        return self.opponents[self.floor]

    @property
    def fighting_final_boss(self):
        return self.final_boss_index is not None and self.floor == self.final_boss_index

    def register_win(self):
        """Se llama cuando el jugador gana la pelea contra el piso actual.
        Devuelve True si todavia quedan pisos, False si completo la torre."""
        self.floor += 1
        if self.floor == self.final_boss_index:
            # el jefe final no sigue la escalada normal del 5%: es 20%
            # mas dificil que la ULTIMA pelea regular (la de recien)
            self.difficulty = self.difficulty * FINAL_BOSS_DIFFICULTY_MULT
        else:
            self.difficulty = self.difficulty * DIFFICULTY_STEP
        if self.floor >= self.total_floors:
            self.cleared = True
            return False
        self.start_climb()
        return True

    def start_climb(self):
        self._scroll_start = self.scroll_y
        self._scroll_target = self.floor * FLOOR_H
        self._anim_t = 0.0
        self.anim_done = False

    def update(self, dt):
        if self.anim_done:
            return
        self._anim_t += dt
        t = min(1.0, self._anim_t / CLIMB_DURATION)
        eased = 1 - (1 - t) ** 3  # ease-out cubico, arranca rapido y frena suave
        self.scroll_y = self._scroll_start + (self._scroll_target - self._scroll_start) * eased
        if t >= 1.0:
            self.scroll_y = self._scroll_target
            self.anim_done = True

    def _load_pose(self, path, size):
        if not path:
            return None
        key = (path, size)
        if key not in self._pose_cache:
            if not os.path.isfile(path):
                return None
            img = pygame.image.load(path).convert_alpha()
            self._pose_cache[key] = pygame.transform.smoothscale(img, size)
        return self._pose_cache[key]

    POSE_SIZE = SIDE_PANEL_W  # mismo tamaño que en la selección de personajes (2 Jugadores)

    def _display_info(self, entry, revealed):
        """Nombre/imagen a mostrar para un rival de la torre. Se revela
        (nombre real + foto real) para CUALQUIER piso, ya sea ya
        superado, el actual, o uno que todavía falta -- el único caso
        que se oculta como "???" y el ícono de "Aleatorio" es el jefe
        final, en CUALQUIER momento (ni siquiera cuando le toca pelear:
        recién se revela al empezar la pelea de verdad, ver
        STATE_ROUND_INTRO en main.py)."""
        if revealed:
            return entry["name"], entry["selection_path"], entry.get("pose_path")
        return "???", MYSTERY_SELECTION_PATH, MYSTERY_POSE_PATH

    def draw(self, surface, ui, char_select_helper):
        """char_select_helper: instancia de CharacterSelect ya creada,
        se usa solo para reutilizar su cache de imagenes (_load_scaled)."""
        ui.draw_screen_background(surface, ui.tower_background)
        base_y = C.SCREEN_H - C.scaled(110)  # altura en pantalla del piso actual

        # --- Pose grande del jugador, bien a la izquierda ---
        pose = self._load_pose(self.player_entry.get("pose_path"), (self.POSE_SIZE, self.POSE_SIZE))
        if pose:
            surface.blit(pose, pose.get_rect(midbottom=(C.scaled(130), C.SCREEN_H - C.scaled(30))))

        player_cx = C.scaled(320)
        rivals_cx = player_cx + C.scaled(100) + FLOOR_GAP  # pegado al del jugador (24px de separación)
        cell_size = C.scaled(100)
        thumb_size = C.scaled(92)

        # --- Columna de rivales: se van desplazando hacia arriba ---
        for i, entry in enumerate(self.opponents):
            y = base_y - i * FLOOR_H + self.scroll_y
            if y < -FLOOR_H or y > C.SCREEN_H + FLOOR_H:
                continue
            rect = pygame.Rect(0, 0, cell_size, cell_size)
            rect.center = (rivals_cx, int(y))
            already_beaten = i < self.floor
            is_final_floor = self.final_boss_index is not None and i == self.final_boss_index
            revealed = not is_final_floor
            name, selection_path, _ = self._display_info(entry, revealed)
            img = char_select_helper._load_scaled(selection_path, (thumb_size, thumb_size), char_select_helper._sel_cache, radius=C.scaled(10))

            # El marco/borde ES el color (celeste para el jugador,
            # amarillo para el rival del piso actual, gris para el
            # resto) -- la imagen queda un poco más chica que la
            # celda (thumb_size < cell_size) para que ese color se vea
            # alrededor, como un borde. Antes se dibujaba un fondo
            # gris fijo y, ENCIMA, un anillo de color aparte -- dos
            # bordes superpuestos (bug reportado: "los personajes de
            # la torre tienen doble borde gris... debería ser solo el
            # interno, seleccionándose amarillo el CPU").
            color = (240, 200, 50) if i == self.floor else (90, 90, 100)
            cell_surf = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
            pygame.draw.rect(cell_surf, color, cell_surf.get_rect(), border_radius=C.scaled(10))
            if img:
                cell_surf.blit(img, img.get_rect(center=(cell_size // 2, cell_size // 2)))
            if already_beaten:
                cell_surf.set_alpha(76)  # 100 - 70% = 30% de opacidad
            surface.blit(cell_surf, rect.topleft)

            txt_color = (120, 120, 125) if already_beaten else (230, 230, 230)
            txt = ui.font_small.render(name, True, txt_color)
            surface.blit(txt, txt.get_rect(midleft=(rect.right + C.scaled(16), rect.centery)))

        # --- Columna del jugador: sube EN PARALELO, a la misma altura que
        # el rival actual (mismo scroll_y, mismo índice de piso) ---
        player_y = base_y - self.floor * FLOOR_H + self.scroll_y
        prect = pygame.Rect(0, 0, cell_size, cell_size)
        prect.center = (player_cx, int(player_y))
        pimg = char_select_helper._load_scaled(self.player_entry["selection_path"], (thumb_size, thumb_size), char_select_helper._sel_cache, radius=C.scaled(10))
        # El marco ES el celeste (nunca doble borde gris+celeste -- ver
        # nota arriba, mismo bug reportado): la imagen queda un poco
        # más chica que la celda para que el celeste se vea alrededor.
        pygame.draw.rect(surface, (80, 170, 240), prect, border_radius=C.scaled(10))
        if pimg:
            surface.blit(pimg, pimg.get_rect(center=prect.center))
        ptxt = ui.font_small.render(self.player_entry["name"], True, (230, 230, 230))
        surface.blit(ptxt, ptxt.get_rect(midtop=(prect.centerx, prect.bottom + C.scaled(8))))

        # velo arriba/abajo para que los pisos aparezcan/desaparezcan suave
        fade_h = C.scaled(70)
        top_fade = pygame.Surface((C.SCREEN_W, fade_h), pygame.SRCALPHA)
        for yy in range(fade_h):
            alpha = int(255 * (1 - yy / fade_h))
            pygame.draw.line(top_fade, (*C.DARK, alpha), (0, yy), (C.SCREEN_W, yy))
        surface.blit(top_fade, (0, 0))

        # --- Info de texto + pose grande del rival: columna derecha ---
        text_x = C.scaled(800)
        if self.floor < self.total_floors:
            piso_txt = "FINAL" if self.fighting_final_boss else f"PISO {self.floor + 1} DE {self.total_floors}"
            ui.draw_title(surface, piso_txt, y=C.scaled(40), x=C.scaled(130), size=C.scaled(30))  # -20% (38 -> 30)

            rival_entry = self.current_opponent
            # El rival ACTUAL se revela (nombre y pose reales), salvo que
            # sea el jefe final -- a ese no se lo muestra ni cuando le
            # toca pelear, se guarda la sorpresa para la pelea en sí.
            rival_name, _, rival_pose_path = self._display_info(rival_entry, revealed=not self.fighting_final_boss)
            # "Rival:" a la mitad de tamaño, pegado (12px) al nombre (que
            # SÍ mantiene el tamaño grande)
            label = ui.font_med.render("Rival:", True, C.YELLOW)  # ~50% de font_big
            label_y = C.scaled(90)
            surface.blit(label, label.get_rect(center=(text_x, label_y)))
            name_txt = ui.font_big.render(rival_name, True, C.YELLOW)
            name_y = label_y + label.get_height() // 2 + C.scaled(12) + name_txt.get_height() // 2
            surface.blit(name_txt, name_txt.get_rect(center=(text_x, name_y)))

            # misma pose y mismo tamaño que el jugador, ANCLADA POR LOS
            # PIES a la misma altura (antes usaba un anclaje distinto,
            # relativo al texto de arriba, y quedaban a alturas distintas)
            # -- espejada para que quede mirando hacia la izquierda (hacia
            # el jugador), igual que el panel de J2 en la pantalla de 2
            # Jugadores.
            rival_pose = self._load_pose(rival_pose_path, (self.POSE_SIZE, self.POSE_SIZE))
            if rival_pose:
                rival_pose = pygame.transform.flip(rival_pose, True, False)
                pose_rect = rival_pose.get_rect(midbottom=(text_x, C.SCREEN_H - C.scaled(30)))
                surface.blit(rival_pose, pose_rect)
        from engine.input_manager import load_input_config, build_footer_parts
        footer_cfg = load_input_config()
        ui.draw_footer_mixed(surface, build_footer_parts(footer_cfg, [("confirm", "continuar")]), C.SCREEN_H - C.scaled(30))


class Confetti:
    """Lluvia de confeti simple para la pantalla de victoria de la torre."""

    COLORS = [(240, 90, 90), (90, 200, 240), (250, 210, 60), (120, 220, 130), (200, 120, 240)]

    def __init__(self, count=90):
        self.particles = []
        for _ in range(count):
            self.particles.append(self._new_particle(random.uniform(-C.SCREEN_H, 0)))

    def _new_particle(self, y=None):
        return {
            "x": random.uniform(0, C.SCREEN_W),
            "y": y if y is not None else random.uniform(-C.scaled(40), -C.scaled(10)),
            "vy": random.uniform(C.scaled(70), C.scaled(180)),
            "vx": random.uniform(-C.scaled(30), C.scaled(30)),
            "size": random.uniform(C.scaled(5), C.scaled(11)),
            "color": random.choice(self.COLORS),
            "spin": random.uniform(0, 360),
            "spin_speed": random.uniform(-220, 220),
        }

    def update(self, dt):
        for p in self.particles:
            p["y"] += p["vy"] * dt
            p["x"] += p["vx"] * dt
            p["spin"] += p["spin_speed"] * dt
            if p["y"] > C.SCREEN_H + C.scaled(20):
                p.update(self._new_particle())

    def draw(self, surface):
        for p in self.particles:
            s = pygame.Surface((p["size"], p["size"] * 0.6), pygame.SRCALPHA)
            s.fill(p["color"])
            rotated = pygame.transform.rotate(s, p["spin"])
            surface.blit(rotated, rotated.get_rect(center=(p["x"], p["y"])))
