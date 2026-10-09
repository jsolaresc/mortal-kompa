"""
touch.py
---------
Controles táctiles para Android (o para probar en PC con --touch, ver
engine/device.py).

  - Izquierda: joystick direccional. En pelea es "flotante" (aparece
    donde apoyás el dedo, en la mitad izquierda); en los menús queda
    fijo abajo a la izquierda.
  - Derecha (en pelea): Puño, Patada, Distancia, Especial y Bloqueo.
    El botón de Especial reemplaza a los 5 "pips" del HUD: arranca
    bloqueado (candado) y se va llenando con cada golpe recibido; con
    los 5 golpes se habilita (brilla).
  - Derecha (en menús): OK y VOLVER.
  - Arriba a la derecha: pausa.

Además, en los menús se puede TOCAR directamente una opción de lista,
una cara en la selección de personaje o un escenario (ver
TouchControls.taps y ui.draw_menu_list / CharacterSelect.hit_test).

Todo se dibuja sobre la pantalla REAL (más ancha que el lienzo 16:9 del
juego en un celular, ver device.logical_display_size), así que los
controles aprovechan los costados sobrantes de la pantalla.
"""

import math
import os
import time

import pygame

from engine import constants as C
from engine.input_manager import PlayerInput, ACTIONS

FONT_PATH = os.path.join("assets", "fonts", "Roboto-Black.ttf")

MODE_NONE = "none"
MODE_MENU = "menu"
MODE_FIGHT = "fight"
MODE_SPECTATE = "spectate"  # mirando una pelea ajena: solo el botón de pausa

# Colores de cada botón de pelea (relleno)
BTN_COLORS = {
    "punch": (70, 150, 235),
    "kick": (235, 90, 80),
    "ranged": (60, 190, 120),
    "special": (240, 190, 40),
    "block": (150, 150, 165),
    "confirm": (60, 190, 110),
    "cancel": (210, 80, 80),
    "start": (90, 90, 100),
}
BTN_LABELS = {
    "punch": "PUÑO",
    "kick": "PATADA",
    "ranged": "DISTANCIA",
    "special": "ESPECIAL",
    "block": "BLOQUEO",
    "confirm": "OK",
    "cancel": "VOLVER",
}

# Etiquetas para los pies de página de los menús en modo táctil (ver
# input_manager.key_label).
TOUCH_KEY_LABELS = {
    "confirm": "OK", "cancel": "VOLVER", "punch": "PUÑO", "kick": "PATADA",
    "ranged": "DISTANCIA", "special": "ESPECIAL", "block": "BLOQUEO",
    "start": "II", "left": "IZQ", "right": "DER", "up": "↑", "down": "↓",
}

# Registro de la última lista de menú dibujada (ver ui.draw_menu_list):
# [(rect_en_coordenadas_del_lienzo, indice), ...]
LIST_HITS = []


def set_list_hits(hits):
    LIST_HITS[:] = hits


def list_index_at(pos):
    for rect, idx in LIST_HITS:
        if rect.collidepoint(pos):
            return idx
    return None


class TouchControls:
    def __init__(self, display_size, game_rect, scale=1.0):
        self.dw, self.dh = display_size
        self.game_rect = pygame.Rect(game_rect)
        self.mode = MODE_NONE
        self.scale = scale
        self.fingers = {}  # id -> dict(pos, role, base)
        self.taps = []  # posiciones (en coordenadas del LIENZO del juego) tocadas este cuadro
        self.special_charge = 0  # 0..C.SPECIAL_HITS_REQUIRED (lo setea main/cliente)
        self.show_special = True
        self.extra_buttons = []  # (accion, label) extra en menús, ej. pausa en espectador
        self._mouse_down = False
        self._font_cache = {}
        self._surf_cache = {}
        self._layout()

    # ------------------------------------------------------------------
    def set_scale(self, scale):
        if abs(scale - self.scale) > 1e-3:
            self.scale = scale
            self._surf_cache.clear()
            self._layout()

    def _u(self, v):
        return v * self.dh / 720.0 * self.scale

    def _layout(self):
        u = self._u
        dw, dh = self.dw, self.dh
        self.joy_r = u(105)
        self.knob_r = u(48)
        self.joy_default = (max(u(150), self.game_rect.left * 0.5 + u(40)), dh - u(175))
        self.joy_default = (u(70) + self.joy_r, dh - u(60) - self.joy_r)
        # Botones de pelea: (accion, x, y, radio) -- abanico para el pulgar derecho
        self.fight_buttons = [
            ("kick", dw - u(112), dh - u(118), u(74)),
            ("punch", dw - u(272), dh - u(92), u(66)),
            ("ranged", dw - u(240), dh - u(258), u(58)),
            ("special", dw - u(92), dh - u(298), u(64)),
            ("block", dw - u(405), dh - u(150), u(50)),
        ]
        self.menu_buttons = [
            ("confirm", dw - u(120), dh - u(125), u(78)),
            ("cancel", dw - u(275), dh - u(78), u(54)),
        ]
        # pausa: centrada, justo debajo del timer (arriba a los costados
        # están las barras de vida, que ahora llegan al borde de la pantalla)
        self.pause_button = ("start", dw / 2, u(122), u(30))

    def buttons(self):
        if self.mode == MODE_FIGHT:
            return self.fight_buttons + [self.pause_button]
        if self.mode == MODE_MENU:
            return self.menu_buttons
        if self.mode == MODE_SPECTATE:
            return [self.pause_button]
        return []

    # ------------------------------------------------------------------
    def to_game(self, pos):
        return (pos[0] - self.game_rect.left, pos[1] - self.game_rect.top)

    def _button_at(self, pos, slop=1.15):
        best = None
        for action, bx, by, r in self.buttons():
            d = math.hypot(pos[0] - bx, pos[1] - by)
            if d <= r * slop and (best is None or d < best[1]):
                best = (action, d)
        return best[0] if best else None

    def _in_joy_zone(self, pos):
        x, y = pos
        if self.mode == MODE_FIGHT:
            return x < self.dw * 0.42 and y > self.dh * 0.22
        if self.mode == MODE_MENU:
            jx, jy = self.joy_default
            return math.hypot(x - jx, y - jy) <= self.joy_r * 1.5
        return False

    def _finger_down(self, fid, pos):
        btn = self._button_at(pos)
        if btn:
            self.fingers[fid] = {"pos": pos, "role": "btn", "action": btn}
            return
        if self._in_joy_zone(pos) and not any(f["role"] == "joy" for f in self.fingers.values()):
            if self.mode == MODE_FIGHT:
                r = self.joy_r
                bx = min(max(pos[0], r + self._u(10)), self.dw * 0.42)
                by = min(max(pos[1], self.dh * 0.22 + r * 0.5), self.dh - r - self._u(10))
                base = (bx, by)
            else:
                base = self.joy_default
            self.fingers[fid] = {"pos": pos, "role": "joy", "base": base}
            return
        # toque "libre" -> tap sobre el contenido (menús)
        self.fingers[fid] = {"pos": pos, "role": "tap"}
        gp = self.to_game(pos)
        if 0 <= gp[0] < self.game_rect.width and 0 <= gp[1] < self.game_rect.height:
            self.taps.append(gp)

    def _finger_move(self, fid, pos):
        f = self.fingers.get(fid)
        if not f:
            return
        f["pos"] = pos
        if f["role"] == "btn" and self.mode == MODE_FIGHT:
            # se puede "deslizar" de un botón a otro sin levantar el dedo
            btn = self._button_at(pos, slop=1.0)
            if btn and btn != "start":
                f["action"] = btn

    def _finger_up(self, fid):
        self.fingers.pop(fid, None)

    def handle_event(self, event):
        """Devuelve True si el evento era táctil (y ya se procesó)."""
        et = event.type
        if et in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            pos = (event.x * self.dw, event.y * self.dh)
            fid = ("f", event.touch_id, event.finger_id)
            if et == pygame.FINGERDOWN:
                self._finger_down(fid, pos)
            elif et == pygame.FINGERMOTION:
                self._finger_move(fid, pos)
            else:
                self._finger_up(fid)
            return True
        # En Android SDL también manda eventos de mouse "sintéticos" por
        # cada dedo -- se ignoran (ya los procesamos como FINGER*).
        if getattr(event, "touch", False):
            return True
        if et == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_down = True
            self._finger_down("mouse", event.pos)
            return True
        if et == pygame.MOUSEMOTION and self._mouse_down:
            self._finger_move("mouse", event.pos)
            return True
        if et == pygame.MOUSEBUTTONUP and event.button == 1:
            self._mouse_down = False
            self._finger_up("mouse")
            return True
        return False

    def begin_frame(self):
        """Llamar al principio de cada cuadro, ANTES de procesar eventos."""
        self.taps = []

    def release_all(self):
        self.fingers.clear()
        self._mouse_down = False

    def set_mode(self, mode):
        if mode != self.mode:
            self.mode = mode
            # los dedos que estaban apoyados sobre controles que ya no
            # existen en el modo nuevo dejan de contar
            for fid, f in list(self.fingers.items()):
                if f["role"] in ("btn", "joy"):
                    f["role"] = "dead"

    # ------------------------------------------------------------------
    def state(self):
        """Estado de acciones mantenidas (dict accion->bool)."""
        st = {a: False for a in ACTIONS}
        for f in self.fingers.values():
            if f["role"] == "btn":
                st[f["action"]] = True
            elif f["role"] == "joy":
                bx, by = f["base"]
                dx = (f["pos"][0] - bx) / self.joy_r
                dy = (f["pos"][1] - by) / self.joy_r
                if self.mode == MODE_FIGHT:
                    st["right"] = dx > 0.38
                    st["left"] = dx < -0.38
                    st["up"] = dy < -0.55
                    st["down"] = dy > 0.55
                else:
                    # menú: una sola dirección dominante (más preciso)
                    if max(abs(dx), abs(dy)) > 0.45:
                        if abs(dx) > abs(dy):
                            st["right" if dx > 0 else "left"] = True
                        else:
                            st["down" if dy > 0 else "up"] = True
        return st

    # ------------------------------------------------------------------
    # Dibujo
    # ------------------------------------------------------------------
    def _font(self, size):
        size = max(8, int(size))
        if size not in self._font_cache:
            if os.path.isfile(FONT_PATH):
                self._font_cache[size] = pygame.font.Font(FONT_PATH, size)
            else:
                self._font_cache[size] = pygame.font.SysFont("arial", size, bold=True)
        return self._font_cache[size]

    def _circle_surface(self, r, color, alpha, ring=None):
        key = ("c", int(r), color, alpha, ring)
        if key not in self._surf_cache:
            ss = 3  # supersampling para bordes suaves
            R = int(r * ss)
            s = pygame.Surface((2 * R + 4, 2 * R + 4), pygame.SRCALPHA)
            pygame.draw.circle(s, (*color, alpha), (R + 2, R + 2), R)
            if ring:
                rc, rw = ring
                pygame.draw.circle(s, rc, (R + 2, R + 2), R, width=max(1, int(rw * ss)))
            s = pygame.transform.smoothscale(s, (int(2 * r) + 2, int(2 * r) + 2))
            self._surf_cache[key] = s
        return self._surf_cache[key]

    def _blit_center(self, surface, img, center):
        surface.blit(img, img.get_rect(center=(int(center[0]), int(center[1]))))

    def _glyph(self, action, r, color=(255, 255, 255)):
        """Ícono simple dibujado a mano para cada botón (cacheado)."""
        key = ("g", action, int(r), color)
        if key in self._surf_cache:
            return self._surf_cache[key]
        ss = 4
        size = int(r * 1.3 * ss)
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size / 2
        k = size / 100.0
        col = (*color, 255)

        def P(x, y):
            return (c + x * k, c + y * k)

        if action == "punch":
            # puño: palma redondeada + 4 nudillos + pulgar
            pygame.draw.rect(s, col, pygame.Rect(P(-30, -14), (60 * k, 46 * k)), border_radius=int(14 * k))
            for i in range(4):
                pygame.draw.circle(s, col, P(-22 + i * 14.7, -18), 10 * k)
            pygame.draw.rect(s, col, pygame.Rect(P(-38, 0), (22 * k, 14 * k)), border_radius=int(7 * k))
            for i in range(3):
                x = -15 + i * 14.7
                pygame.draw.line(s, (0, 0, 0, 90), P(x + 7, -24), P(x + 7, -6), max(1, int(3 * k)))
        elif action == "kick":
            # bota
            pts = [P(-16, -40), P(8, -40), P(8, 8), P(36, 14), P(40, 30), P(-20, 30), P(-20, 14)]
            pygame.draw.polygon(s, col, pts)
            pygame.draw.rect(s, col, pygame.Rect(P(-22, 26), (64 * k, 10 * k)), border_radius=int(4 * k))
        elif action == "ranged":
            # objeto volando con estelas
            pygame.draw.circle(s, col, P(20, 0), 20 * k)
            for i, yy in enumerate((-14, 0, 14)):
                pygame.draw.line(s, col, P(-40 + i * 6, yy), P(-6, yy), max(2, int(7 * k)))
        elif action == "special":
            # estrella de 5 puntas
            pts = []
            for i in range(10):
                ang = -math.pi / 2 + i * math.pi / 5
                rad = 40 if i % 2 == 0 else 17
                pts.append(P(rad * math.cos(ang), rad * math.sin(ang)))
            pygame.draw.polygon(s, col, pts)
        elif action == "block":
            # escudo
            pts = [P(-30, -36), P(30, -36), P(30, 0), P(0, 40), P(-30, 0)]
            pygame.draw.polygon(s, col, pts)
            pygame.draw.polygon(s, (0, 0, 0, 80), [P(-18, -26), P(0, -26), P(0, 26), P(-18, 2)])
        elif action == "start":
            pygame.draw.rect(s, col, pygame.Rect(P(-22, -28), (15 * k, 56 * k)), border_radius=int(3 * k))
            pygame.draw.rect(s, col, pygame.Rect(P(7, -28), (15 * k, 56 * k)), border_radius=int(3 * k))
        elif action == "lock":
            pygame.draw.rect(s, col, pygame.Rect(P(-26, -4), (52 * k, 40 * k)), border_radius=int(6 * k))
            pygame.draw.circle(s, col, P(0, -6), 20 * k, width=max(2, int(8 * k)))
            pygame.draw.circle(s, (0, 0, 0, 120), P(0, 14), 6 * k)
        elif action == "confirm":
            pygame.draw.lines(s, col, False, [P(-30, 2), P(-8, 24), P(32, -22)], max(3, int(13 * k)))
        elif action == "cancel":
            pygame.draw.line(s, col, P(-24, -24), P(24, 24), max(3, int(12 * k)))
            pygame.draw.line(s, col, P(24, -24), P(-24, 24), max(3, int(12 * k)))
        out = pygame.transform.smoothscale(s, (size // ss, size // ss))
        self._surf_cache[key] = out
        return out

    def _pressed_actions(self):
        return {f["action"] for f in self.fingers.values() if f["role"] == "btn"}

    # ------------------------------------------------------------------
    # "Caras" de los botones: PNG editables en assets/ui/touch/ (ver
    # TOUCH_FACES más abajo). Si un PNG no existe, se dibuja por código
    # (el mismo diseño con el que se generaron los PNG de fábrica, ver
    # render_default_face / tools/export_touch_buttons.py).
    # ------------------------------------------------------------------
    def render_default_face(self, name, r):
        """Dibujo de fábrica de cada botón, opaco, de radio r."""
        size = int(2 * r) + 4
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        c = (size / 2, size / 2)
        ring_w = max(2, int(r * 0.045))
        if name == "joystick_base":
            disk = self._circle_surface(r, (20, 20, 28), 200, ring=((255, 255, 255, 220), ring_w))
            s.blit(disk, disk.get_rect(center=c))
            for ang in (0, 90, 180, 270):
                a = math.radians(ang)
                cx = c[0] + math.cos(a) * r * 0.78
                cy = c[1] + math.sin(a) * r * 0.78
                sz = r * 0.095
                pts = [
                    (cx + math.cos(a) * sz, cy + math.sin(a) * sz),
                    (cx + math.cos(a + 2.4) * sz, cy + math.sin(a + 2.4) * sz),
                    (cx + math.cos(a - 2.4) * sz, cy + math.sin(a - 2.4) * sz),
                ]
                pygame.draw.polygon(s, (255, 255, 255, 230), pts)
            return s
        if name == "joystick_knob":
            disk = self._circle_surface(r, (235, 235, 240), 255, ring=((40, 40, 50, 230), ring_w))
            s.blit(disk, disk.get_rect(center=c))
            return s
        if name == "special_locked":
            color, glyph, label, gcol = (95, 95, 105), "lock", None, (230, 230, 235)
        elif name == "special":
            color, glyph, label, gcol = BTN_COLORS["special"], "special", BTN_LABELS["special"], (40, 30, 0)
        elif name == "pause":
            color, glyph, label, gcol = BTN_COLORS["start"], "start", None, (255, 255, 255)
        else:
            color, glyph, label, gcol = BTN_COLORS.get(name, (120, 120, 130)), name, BTN_LABELS.get(name), (255, 255, 255)
        disk = self._circle_surface(r, color, 255, ring=((255, 255, 255, 235), ring_w))
        s.blit(disk, disk.get_rect(center=c))
        g = self._glyph(glyph, r * (0.62 if glyph == "lock" else 0.75), gcol)
        s.blit(g, g.get_rect(center=(c[0], c[1] - (r * 0.12 if label else 0))))
        if label:
            t = self._font(r * 0.24).render(label, True, gcol)
            s.blit(t, t.get_rect(center=(c[0], c[1] + r * 0.55)))
        return s

    def _face(self, name, r, alpha=255):
        """Superficie lista para dibujar del botón 'name' con radio r."""
        r = max(4, int(r))
        key = ("face", name, r, alpha)
        surf = self._surf_cache.get(key)
        if surf is not None:
            return surf
        base_key = ("face", name, r, 255)
        base = self._surf_cache.get(base_key)
        if base is None:
            path = os.path.join(TOUCH_DIR, f"{name}.png")
            base = None
            if os.path.isfile(path):
                try:
                    img = pygame.image.load(path).convert_alpha()
                    w, h = img.get_size()
                    f = (2 * r) / max(w, h)
                    base = pygame.transform.smoothscale(img, (max(1, int(w * f)), max(1, int(h * f))))
                except pygame.error:
                    base = None
            if base is None:
                base = self.render_default_face(name, r)
            self._surf_cache[base_key] = base
        if alpha >= 255:
            return base
        surf = base.copy()
        surf.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        self._surf_cache[key] = surf
        return surf

    def draw(self, surface):
        if self.mode == MODE_NONE:
            return
        pressed = self._pressed_actions()

        if self.mode == MODE_SPECTATE:
            for action, bx, by, r in self.buttons():
                self._blit_center(surface, self._face("pause", r, 170), (bx, by))
            return

        # --- joystick ---
        joy = next((f for f in self.fingers.values() if f["role"] == "joy"), None)
        if joy:
            base = joy["base"]
            dx, dy = joy["pos"][0] - base[0], joy["pos"][1] - base[1]
            d = math.hypot(dx, dy)
            lim = self.joy_r * 0.85
            if d > lim:
                dx, dy = dx * lim / d, dy * lim / d
            knob = (base[0] + dx, base[1] + dy)
            alpha_base, alpha_knob = 150, 220
        else:
            base = self.joy_default
            knob = base
            alpha_base, alpha_knob = 95, 120
        self._blit_center(surface, self._face("joystick_base", self.joy_r, alpha_base), base)
        self._blit_center(surface, self._face("joystick_knob", self.knob_r, alpha_knob), knob)

        # --- botones ---
        for action, bx, by, r in self.buttons():
            is_pressed = action in pressed
            if action == "special" and self.mode == MODE_FIGHT and self.show_special:
                self._draw_special(surface, bx, by, r, is_pressed)
                continue
            name = "pause" if action == "start" else action
            rr = r * (0.93 if is_pressed else 1.0)
            self._blit_center(surface, self._face(name, rr, 240 if is_pressed else 165), (bx, by))

    def _disc(self, name):
        """(dx, dy, radio) del disco principal del PNG, en fracciones del radio
        del botón. Mide el ancho/alto opaco en los ejes que cruzan el centro."""
        key = ("disc", name)
        if key in self._surf_cache:
            return self._surf_cache[key]
        res = (0.0, 0.0, 1.0)
        path = os.path.join(TOUCH_DIR, f"{name}.png")
        try:
            img = pygame.image.load(path)
            w, h = img.get_size()
            cx, cy = w // 2, h // 2
            for _ in range(3):
                xs = [x for x in range(w) if img.get_at((x, cy)).a > 40]
                ys = [y for y in range(h) if img.get_at((cx, y)).a > 40]
                if not xs or not ys:
                    break
                cx, cy = (xs[0] + xs[-1]) // 2, (ys[0] + ys[-1]) // 2
            half = max(w, h) / 2
            rad = min(xs[-1] - xs[0], ys[-1] - ys[0]) / 2
            res = ((cx - w / 2) / half, (cy - h / 2) / half, rad / half)
        except (pygame.error, OSError, NameError, UnboundLocalError):
            pass
        self._surf_cache[key] = res
        return res

    def _draw_special(self, surface, bx, by, r, is_pressed):
        req = C.SPECIAL_HITS_REQUIRED
        charge = max(0, min(req, self.special_charge))
        ready = charge >= req
        u = self._u
        rr = r * (0.93 if is_pressed else 1.0)
        # se mide el círculo real del PNG (las llamas que sobresalen no cuentan)
        ox, oy, fr = self._disc("special" if ready else "special_locked")
        cx, cy = bx + ox * rr, by + oy * rr
        disc_r = fr * rr
        width = max(3, int(u(5)))
        if ready:
            pulse = 0.5 + 0.5 * math.sin(time.time() * 7)
            glow = self._circle_surface(disc_r + width + u(4 + 3 * pulse), (255, 220, 60), int(60 + 50 * pulse))
            self._blit_center(surface, glow, (cx, cy))
        if ready:
            face = self._face("special", rr, 245 if is_pressed else 215)
        else:
            face = self._face("special_locked", rr, 165)
        # desbloqueado: el aro va DETRÁS del PNG (no corta los pinchos);
        # bloqueado: encima, para que se vea bien la carga
        if not ready:
            self._blit_center(surface, face, (bx, by))
        self._draw_charge_ring(surface, cx, cy, disc_r, width, charge, req)
        if ready:
            self._blit_center(surface, face, (bx, by))

    def _draw_charge_ring(self, surface, cx, cy, disc_r, width, charge, req):
        """Aro de 5 segmentos pegado al borde del disco del ícono."""
        r_in = disc_r + self._u(1)
        r_out = r_in + width
        gap = 0.10
        seg = (2 * math.pi) / req
        n = 20
        for i in range(req):
            a0 = -math.pi / 2 + i * seg + gap / 2  # arranca arriba, sentido horario
            a1 = a0 + seg - gap
            pts = [(cx + r_out * math.cos(a0 + (a1 - a0) * k / n), cy + r_out * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]
            pts += [(cx + r_in * math.cos(a1 - (a1 - a0) * k / n), cy + r_in * math.sin(a1 - (a1 - a0) * k / n)) for k in range(n + 1)]
            col = (255, 215, 50) if i < charge else (55, 55, 65)
            pygame.draw.polygon(surface, col, pts)
            pygame.draw.aalines(surface, col, True, pts)

# Botones editables (assets/ui/touch/<nombre>.png). Cualquier tamaño:
# se escalan solos al tamaño del botón (cuadrados, con transparencia).
TOUCH_DIR = os.path.join("assets", "ui", "touch")
TOUCH_FACES = [
    "punch", "kick", "ranged", "block", "special", "special_locked", "pause",
    "joystick_base", "joystick_knob",
]


class TouchInput(PlayerInput):
    """Como PlayerInput (teclado + joystick físico, que siguen andando:
    sirven para un control Bluetooth en el celular o para probar en PC),
    pero sumando los controles táctiles."""

    def __init__(self, profile, touch):
        super().__init__(profile)
        self.touch = touch

    def update(self, keys_pressed):
        super().update(keys_pressed)
        for a, v in self.touch.state().items():
            if v:
                self.state[a] = True
        self._apply_injected()
