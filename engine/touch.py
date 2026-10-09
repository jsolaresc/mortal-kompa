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
        self.pause_button = ("start", dw - u(48), u(46), u(34))

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

    def draw(self, surface):
        if self.mode == MODE_NONE:
            return
        pressed = self._pressed_actions()
        u = self._u

        if self.mode == MODE_SPECTATE:
            for action, bx, by, r in self.buttons():
                self._blit_center(surface, self._circle_surface(r, BTN_COLORS["start"], 150, ring=((255, 255, 255, 170), u(3))), (bx, by))
                self._blit_center(surface, self._glyph(action, r * 0.75), (bx, by))
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
            alpha_base, alpha_knob = 90, 200
        else:
            base = self.joy_default
            knob = base
            alpha_base, alpha_knob = 55, 110
        self._blit_center(surface, self._circle_surface(self.joy_r, (20, 20, 28), alpha_base, ring=((255, 255, 255, 120), u(3))), base)
        # flechitas de dirección en el aro
        arrow_col = (255, 255, 255, 150)
        for ang in (0, 90, 180, 270):
            a = math.radians(ang)
            cx = base[0] + math.cos(a) * self.joy_r * 0.78
            cy = base[1] + math.sin(a) * self.joy_r * 0.78
            sz = u(10)
            pts = [
                (cx + math.cos(a) * sz, cy + math.sin(a) * sz),
                (cx + math.cos(a + 2.4) * sz, cy + math.sin(a + 2.4) * sz),
                (cx + math.cos(a - 2.4) * sz, cy + math.sin(a - 2.4) * sz),
            ]
            pygame.draw.polygon(surface, arrow_col, pts)
        self._blit_center(surface, self._circle_surface(self.knob_r, (235, 235, 240), alpha_knob, ring=((40, 40, 50, 180), u(2))), knob)

        # --- botones ---
        for action, bx, by, r in self.buttons():
            is_pressed = action in pressed
            color = BTN_COLORS.get(action, (120, 120, 130))
            if action == "special" and self.mode == MODE_FIGHT and self.show_special:
                self._draw_special(surface, bx, by, r, is_pressed)
                continue
            alpha = 230 if is_pressed else 150
            rr = r * (0.93 if is_pressed else 1.0)
            self._blit_center(surface, self._circle_surface(rr, color, alpha, ring=((255, 255, 255, 170), u(3))), (bx, by))
            g = self._glyph(action, rr * 0.75)
            self._blit_center(surface, g, (bx, by - (rr * 0.12 if action not in ("start",) else 0)))
            label = BTN_LABELS.get(action)
            if label and action != "start":
                f = self._font(rr * 0.24)
                t = f.render(label, True, (255, 255, 255))
                self._blit_center(surface, t, (bx, by + rr * 0.55))

    def _draw_special(self, surface, bx, by, r, is_pressed):
        req = C.SPECIAL_HITS_REQUIRED
        charge = max(0, min(req, self.special_charge))
        ready = charge >= req
        u = self._u
        if ready:
            pulse = 0.5 + 0.5 * math.sin(time.time() * 7)
            glow = self._circle_surface(r * (1.18 + 0.06 * pulse), (255, 220, 60), int(70 + 60 * pulse))
            self._blit_center(surface, glow, (bx, by))
            color = BTN_COLORS["special"]
            alpha = 240 if is_pressed else 210
        else:
            color = (95, 95, 105)
            alpha = 150
        rr = r * (0.93 if is_pressed else 1.0)
        self._blit_center(surface, self._circle_surface(rr, color, alpha, ring=((255, 255, 255, 120), u(3))), (bx, by))
        # aro de carga: 5 segmentos
        ring_r = rr + u(7)
        rect = pygame.Rect(0, 0, ring_r * 2, ring_r * 2)
        rect.center = (int(bx), int(by))
        gap = 0.12
        seg = (2 * math.pi) / req
        for i in range(req):
            start = math.pi / 2 - (i + 1) * seg + gap / 2
            end = math.pi / 2 - i * seg - gap / 2
            filled = i < charge
            col = (255, 215, 50) if filled else (60, 60, 70)
            pygame.draw.arc(surface, col, rect, start, end, max(3, int(u(7))))
        if ready:
            g = self._glyph("special", rr * 0.75, (40, 30, 0))
        else:
            g = self._glyph("lock", rr * 0.62, (230, 230, 235))
        self._blit_center(surface, g, (bx, by - rr * 0.1))
        f = self._font(rr * 0.24)
        txt = BTN_LABELS["special"] if ready else f"{charge}/{req}"
        t = f.render(txt, True, (40, 30, 0) if ready else (255, 255, 255))
        self._blit_center(surface, t, (bx, by + rr * 0.55))


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
