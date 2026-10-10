"""
net_screens.py
---------------
Pantallas del multijugador por WiFi (ver engine/netplay.py):

  - HostLobby: la "sala" del anfitrión (quiénes están conectados, IP para
    escribir a mano, empezar 1 vs 1 o Torneo).
  - JoinScreen: buscar partidas en la red (o escribir la IP a mano).
  - ClientSession: todo lo que ve y hace un invitado una vez conectado
    (sala, selección de personaje, pelea, bracket del torneo...). Dibuja
    lo que le manda el anfitrión y le devuelve lo que aprieta.
"""

import os
import time

import pygame

from engine import constants as C
from engine import device
from engine import touch as touch_mod
from engine.character import Character
from engine.input_manager import build_footer_parts, load_input_config
from engine.menu import (
    CharacterSelect, StageSelect, PauseMenu, VersusEndMenu, TournamentBracketScreen,
    load_character_list, RANDOM_SENTINEL,
)
from engine.netplay import (
    NetClient, SoundMirror, LocalInputTracker, apply_fighter_snap, GAME_PORT,
    camera_from_base, projectile_from_snap,
)
from engine.projectile import Projectile
from engine.stage import Stage, list_stages
from engine.tournament import TournamentBracket
from engine.tower import Confetti

LOBBY_ITEMS = ["Empezar 1 vs 1", "Empezar torneo", "Cerrar sala"]


def player_label(index):
    return f"J{index + 1}"


# ======================================================================
# Sala del anfitrión
# ======================================================================
class HostLobby:
    def __init__(self):
        self.index = 0
        self.choice = None  # "versus" | "tournament" | "close"
        self.done = False
        self.message = ""
        self.message_time = 0.0

    def flash(self, text):
        self.message = text
        self.message_time = time.time()

    def update(self, inp, host):
        if host.dropped:
            self.flash(f"Se desconectó: {', '.join(host.dropped)}")
            host.dropped = []
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(LOBBY_ITEMS)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(LOBBY_ITEMS)
        elif inp.just_pressed("cancel"):
            self.choice = "close"
            self.done = True
        elif inp.just_pressed("confirm"):
            n = len(host.clients)
            if self.index == 0:
                if n < 1:
                    self.flash("Falta que se una al menos 1 jugador")
                else:
                    self.choice = "versus"
                    self.done = True
            elif self.index == 1:
                if n < 2:
                    self.flash("Para el torneo hacen falta 3 jugadores o más")
                else:
                    self.choice = "tournament"
                    self.done = True
            else:
                self.choice = "close"
                self.done = True

    def draw(self, surface, ui, host, dt=1 / 60):
        ui.draw_title_background(surface, dt)
        ui.draw_overlay(surface, alpha=150)
        ui.draw_title(surface, "SALA DE JUEGO (WiFi)", y=C.scaled(40))
        ip = host.ip_text()
        ui.draw_small_center(surface, f"IP de esta partida: {ip}", C.scaled(80))
        tip = ui.font_tiny.render(
            "Los demás: Multijugador > Unirse a partida (misma red WiFi o zona WiFi de un celular)",
            True, (200, 200, 205))
        surface.blit(tip, tip.get_rect(center=(C.SCREEN_W // 2, C.scaled(106))))

        # jugadores conectados
        names = [f"{player_label(0)}: {host.name} (vos)"] + [
            f"{player_label(i + 1)}: {c.name}" for i, c in enumerate(host.clients)
        ]
        y = C.scaled(140)
        head = ui.font_small.render(f"Jugadores ({len(names)})", True, C.YELLOW)
        surface.blit(head, head.get_rect(center=(C.SCREEN_W // 2, y)))
        y += C.scaled(28)
        cols = 1 if len(names) <= 5 else 2
        per_col = (len(names) + cols - 1) // cols
        col_w = C.scaled(300)
        for i, n in enumerate(names):
            col = i // per_col
            row = i % per_col
            cx = C.SCREEN_W // 2 + (col - (cols - 1) / 2) * col_w
            img = ui.font_tiny.render(n, True, C.WHITE)
            surface.blit(img, img.get_rect(center=(int(cx), y + row * C.scaled(22))))

        dots = "." * (1 + int(time.time() * 2) % 3)
        if not host.clients:
            w = ui.font_tiny.render(f"Esperando jugadores{dots}", True, (180, 180, 190))
            surface.blit(w, w.get_rect(center=(C.SCREEN_W // 2, y + C.scaled(24))))

        items = list(LOBBY_ITEMS)
        if len(host.clients) < 1:
            items[0] += " (faltan jugadores)"
        if len(host.clients) < 2:
            items[1] += " (3+ jugadores)"
        ui.draw_menu_list(surface, "", items, self.index, center_y=C.SCREEN_H - C.scaled(150))
        if self.message and time.time() - self.message_time < 3.5:
            m = ui.font_small.render(self.message, True, C.YELLOW)
            surface.blit(m, m.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(60))))
        cfg = load_input_config()
        ui.draw_footer_mixed(surface, build_footer_parts(cfg, [("confirm", "elegir"), ("cancel", "cerrar sala")]),
                             C.SCREEN_H - C.scaled(25))


# ======================================================================
# Buscar partida (invitado)
# ======================================================================
KEYPAD = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "0", "<", "BACK", "OK"]


class JoinScreen:
    def __init__(self, client):
        self.client = client
        self.index = 0
        self.done = False
        self.cancelled = False
        self.keypad = False
        self.kp_index = 0
        self.ip_text = ""
        self.connecting = None  # nombre/IP a la que se está conectando
        self.error = ""
        self._hosts_cache = []

    def _items(self):
        hosts = sorted(self.client.hosts.items(), key=lambda kv: kv[1]["name"])
        self._hosts_cache = hosts
        items = [f"Partida de {h['name']} ({h['n']} jug.)" + ("" if h["open"] else " - en curso") for _, h in hosts]
        items += ["Escribir IP a mano", "Volver"]
        return items

    def _start_connect(self, ip, label):
        self.error = ""
        self.connecting = label
        port = GAME_PORT
        for hip, h in self._hosts_cache:
            if hip == ip:
                port = h["port"]
        self.client.connect(ip, port)

    def update(self, inp, taps):
        c = self.client
        if self.connecting:
            if c.connected:
                self.done = True
            elif c.ended or c.connecting_timed_out():
                self.error = c.end_reason or "No respondió. ¿Están en la misma red WiFi?"
                self.connecting = None
                c.host_addr = None
                c.ended = False
            elif inp.just_pressed("cancel"):
                self.connecting = None
                c.host_addr = None
            return
        if self.keypad:
            self._update_keypad(inp, taps)
            return
        items = self._items()
        for pos in taps:
            idx = touch_mod.list_index_at(pos)
            if idx is not None:
                self.index = idx
                inp_confirm = True
                break
        else:
            inp_confirm = inp.just_pressed("confirm")
        self.index = min(self.index, len(items) - 1)
        if inp.just_pressed("up"):
            self.index = (self.index - 1) % len(items)
        elif inp.just_pressed("down"):
            self.index = (self.index + 1) % len(items)
        elif inp.just_pressed("cancel"):
            self.cancelled = True
        elif inp_confirm:
            nh = len(self._hosts_cache)
            if self.index < nh:
                ip, h = self._hosts_cache[self.index]
                self._start_connect(ip, h["name"])
            elif self.index == nh:
                self.keypad = True
                self.kp_index = 0
            else:
                self.cancelled = True

    # --- teclado numérico para escribir la IP ---
    def _key_rects(self):
        size = C.scaled(56)
        gap = C.scaled(14)
        cols = 3
        rows = 5
        total_w = cols * size + (cols - 1) * gap
        x0 = C.SCREEN_W // 2 - total_w // 2
        y0 = C.scaled(166)
        rects = []
        for i, k in enumerate(KEYPAD):
            row_w = total_w + 2 * size
            half = (row_w - gap) // 2
            if k == "BACK":
                r = pygame.Rect(x0 - size, y0 + 4 * (size + gap), half, size)
            elif k == "OK":
                r = pygame.Rect(x0 - size + half + gap, y0 + 4 * (size + gap), half, size)
            else:
                r = pygame.Rect(x0 + (i % cols) * (size + gap), y0 + (i // cols) * (size + gap), size, size)
            rects.append(r)
        return rects

    def _press_key(self, k):
        if k == "BACK":
            self.keypad = False
            self.error = ""
        elif k == "<":
            self.ip_text = self.ip_text[:-1]
        elif k == "OK":
            ip = self.ip_text.strip(".")
            parts = ip.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                self.keypad = False
                self._start_connect(ip, ip)
            else:
                self.error = "IP inválida (ej: 192.168.0.15)"
        elif len(self.ip_text) < 15:
            self.ip_text += k

    def _update_keypad(self, inp, taps):
        rects = self._key_rects()
        for pos in taps:
            for i, r in enumerate(rects):
                if r.collidepoint(pos):
                    self.kp_index = i
                    self._press_key(KEYPAD[i])
                    return
        n = len(KEYPAD)
        if inp.just_pressed("left"):
            self.kp_index = (self.kp_index - 1) % n
        elif inp.just_pressed("right"):
            self.kp_index = (self.kp_index + 1) % n
        elif inp.just_pressed("up"):
            self.kp_index = (self.kp_index - 3) % n
        elif inp.just_pressed("down"):
            self.kp_index = min(n - 1, self.kp_index + 3)
        elif inp.just_pressed("confirm"):
            self._press_key(KEYPAD[self.kp_index])
        elif inp.just_pressed("cancel"):
            self.keypad = False
            self.error = ""

    def draw(self, surface, ui, dt=1 / 60):
        ui.draw_title_background(surface, dt)
        ui.draw_overlay(surface, alpha=150)
        ui.draw_title(surface, "UNIRSE A PARTIDA", y=C.scaled(40))
        cfg = load_input_config()
        if self.connecting:
            dots = "." * (1 + int(time.time() * 2) % 3)
            ui.draw_center_text(surface, f"Conectando{dots}", C.YELLOW)
            ui.draw_small_center(surface, str(self.connecting), C.SCREEN_H // 2 + C.scaled(60))
            ui.draw_footer_mixed(surface, build_footer_parts(cfg, [("cancel", "cancelar")]), C.SCREEN_H - C.scaled(25))
            return
        if self.keypad:
            ui.draw_small_center(surface, "IP del anfitrión (aparece en su pantalla):", C.scaled(90))
            box = pygame.Rect(0, 0, C.scaled(320), C.scaled(44))
            box.center = (C.SCREEN_W // 2, C.scaled(135))
            pygame.draw.rect(surface, (30, 30, 38), box, border_radius=C.scaled(8))
            pygame.draw.rect(surface, C.YELLOW, box, width=2, border_radius=C.scaled(8))
            t = ui.font_med.render(self.ip_text + ("|" if int(time.time() * 2) % 2 else ""), True, C.WHITE)
            surface.blit(t, t.get_rect(center=box.center))
            for i, r in enumerate(self._key_rects()):
                sel = i == self.kp_index
                pygame.draw.rect(surface, (70, 70, 85) if not sel else (90, 150, 230), r, border_radius=C.scaled(8))
                label = {"<": "<", "OK": "CONECTAR", "BACK": "VOLVER"}.get(KEYPAD[i], KEYPAD[i])
                img = ui.font_small.render(label, True, C.WHITE)
                surface.blit(img, img.get_rect(center=r.center))
            if self.error:
                e = ui.font_small.render(self.error, True, C.RED)
                surface.blit(e, e.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(55))))
            ui.draw_footer_mixed(surface, build_footer_parts(cfg, [("confirm", "tecla"), ("cancel", "volver")]),
                                 C.SCREEN_H - C.scaled(25))
            return
        items = self._items()
        dots = "." * (1 + int(time.time() * 2) % 3)
        status = f"Buscando partidas en la red{dots}" if not self._hosts_cache else "Partidas encontradas:"
        ui.draw_small_center(surface, status, C.scaled(100))
        ui.draw_menu_list(surface, "", items, min(self.index, len(items) - 1), center_y=C.SCREEN_H // 2 + C.scaled(20))
        if self.error:
            e = ui.font_small.render(self.error, True, C.RED)
            surface.blit(e, e.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(60))))
        else:
            tip = ui.font_tiny.render("Tienen que estar en la misma red WiFi (o en la zona WiFi del anfitrión)", True, (190, 190, 200))
            surface.blit(tip, tip.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(60))))
        ui.draw_footer_mixed(surface, build_footer_parts(cfg, [("confirm", "unirse"), ("cancel", "volver")]),
                             C.SCREEN_H - C.scaled(25))


# ======================================================================
# Sesión del invitado
# ======================================================================
class ClientSession:
    """Corre del lado del invitado mientras está conectado. Cada cuadro:
    update() procesa la red y lo que tocó el jugador; draw() dibuja la
    "escena" que mandó el anfitrión. Cuando termina (el anfitrión cerró,
    se cortó la conexión o el jugador salió), .finished queda en True y
    .end_message explica por qué."""

    def __init__(self, client, sound_manager):
        self.client = client
        self.sm = sound_manager
        self.mirror = SoundMirror(sound_manager)
        self.tracker = LocalInputTracker()
        self.finished = False
        self.end_message = ""
        self._chars = {}  # json_path -> Character (cacheados entre peleas)
        self._stages = {}
        self._charsel = None
        self._stagesel = None
        self._pick = None  # CharacterSelect(solo) local del torneo
        self._pick_sent = None
        self._bracket = None
        self._bracket_screen = None
        self._bracket_key = None
        self._bk_applied = 0
        self._bk_phase = None
        self._confetti = None
        self._leave_menu = None
        self.my_slot = -1
        self.loading_text = None
        self.scene = None

    # --------------------------------------------------------------
    def _character(self, json_path):
        if json_path not in self._chars:
            self._chars[json_path] = Character(json_path, self.sm)
        return self._chars[json_path]

    def _stage(self, path):
        if path not in self._stages:
            self._stages = {path: Stage(path)}  # uno solo en memoria
        return self._stages[path]

    def needs_loading(self, snap):
        """Devuelve un texto de 'Cargando...' si la próxima escena
        necesita cargar algo pesado (personajes/escenario) -- para poder
        mostrar el cartel ANTES de quedarse trabado cargando."""
        if snap and snap.get("sc") == "fight":
            for j in snap.get("chars", []):
                if j not in self._chars:
                    return "Cargando personajes..."
            st = snap.get("stage")
            if st and st not in self._stages:
                return "Cargando escenario..."
        return None

    def preload(self, snap):
        if snap.get("sc") == "fight":
            for j in snap.get("chars", []):
                self._character(j)
            if snap.get("stage"):
                self._stage(snap["stage"])

    # --------------------------------------------------------------
    def leave(self):
        self.client.close()
        self.sm.stop_all_sfx()
        self.finished = True

    def update(self, dt, inp, taps):
        c = self.client
        c.poll()
        if c.ended:
            self.end_message = c.end_reason or "Se terminó la partida"
            self.client.close()
            self.finished = True
            return
        snap = c.snapshot
        if snap is None:
            return
        self.scene = snap.get("sc")
        own = snap.get("own", [])
        self.my_slot = own.index(c.my_id) if c.my_id in own else -1
        self.mirror.apply(snap.get("ev"), snap.get("mu"))

        # Menú propio para abandonar (botón Atrás en la sala / bracket)
        if self._leave_menu is not None:
            for pos in taps:
                idx = touch_mod.list_index_at(pos)
                if idx is not None:
                    self._leave_menu.index = idx
                    inp.inject("confirm")
            self._leave_menu.update(inp)
            if self._leave_menu.done:
                if self._leave_menu.choice == "menu":
                    self.end_message = ""
                    self.leave()
                    return
                self._leave_menu = None
            held = []
            self.client.send_input(held, self.tracker.counters, self.tracker.taps, pick=self._pick_sent)
            return
        if self.scene in ("lobby", "wait", "bk", "champ") and inp.just_pressed("cancel"):
            self._leave_menu = PauseMenu(net=True)
            self._leave_menu.ITEMS = ["Seguir en la partida", "Salir de la partida"]

        sc = self.scene
        if sc == "cs":
            if self._charsel is None:
                self._charsel = CharacterSelect(p2_is_cpu=False)
            for pos in taps:
                idx = self._charsel.hit_test(pos)
                if idx is not None:
                    self.tracker.add_tap("cs", idx)
        else:
            self._charsel = None if sc != "cs" else self._charsel
        if sc in ("end", "pause") or (sc == "fight" and snap.get("ov") and snap["ov"][0] in ("end", "pause")):
            for pos in taps:
                idx = touch_mod.list_index_at(pos)
                if idx is not None:
                    self.tracker.add_tap("li", idx)
        if sc == "pick":
            if self._pick is None and self._pick_sent is None:
                self._pick = CharacterSelect(solo=True)
            if self._pick is not None:
                for pos in taps:
                    idx = self._pick.hit_test(pos)
                    if idx is not None:
                        self._pick.apply_tap(0, idx)
                self._pick.update([inp, inp], dt)
                if self._pick.done:
                    self._pick_sent = self._pick.choices[0]
                    slug = os.path.splitext(os.path.basename(self._pick_sent))[0]
                    if self._pick_sent != RANDOM_SENTINEL:
                        self.sm.play(os.path.join("assets", "sounds", "announcer", "select", f"{slug}.wav"), volume=0.9)
                    self._pick = None
                elif self._pick.cancelled:
                    self._pick.cancelled = False
        else:
            self._pick = None
            if sc in ("lobby",):
                self._pick_sent = None
        if sc == "bk":
            self._update_bracket(snap, dt)
        if sc == "champ":
            if self._confetti is None:
                self._confetti = Confetti()
            self._confetti.update(dt)
            ch = self._chars.get(snap.get("json"))
            if ch:
                anim = ch.animations.get(C.STATE_WIN)
                if anim:
                    anim.update(dt)
        else:
            self._confetti = None

        held = self.tracker.update(inp)
        if self.my_slot < 0 and sc == "fight":
            held = []  # espectador: no manda movimientos (sí puede pausar, ver contadores)
        self.client.send_input(held, self.tracker.counters, self.tracker.taps, pick=self._pick_sent)

    def _update_bracket(self, snap, dt):
        bk = snap.get("bk") or {}
        seed = bk.get("seed")
        if not seed:
            return
        key = tuple(tuple(e) for e in seed)
        if key != self._bracket_key:
            chars = {c["json_path"]: c for c in load_character_list()}
            picks = []
            for json_path, label in seed:
                base = dict(chars.get(json_path) or {"json_path": json_path, "name": label,
                                                     "selection_path": None, "pose_path": None,
                                                     "pose_path_p2": None, "pose_p2_flip": True})
                base["label"] = label
                picks.append(base)
            self._bracket = TournamentBracket(picks, keep_order=True)
            self._bracket_screen = TournamentBracketScreen(self._bracket)
            self._bracket_key = key
            self._bk_applied = 0
            self._bk_phase = None
        res = bk.get("res", [])
        by_label = lambda lab: next((e for e in self._bracket.entrants if e["label"] == lab), None)
        phase = bk.get("ph")
        # aplicar resultados nuevos (en orden)
        while self._bk_applied < len(res):
            w = by_label(res[self._bk_applied])
            if w is None or self._bracket.champion is not None:
                break
            self._bracket.report_result(w)
            self._bk_applied += 1
        if phase != self._bk_phase:
            if phase in ("result", "result_done") and bk.get("rw"):
                self._bracket_screen.show_result(by_label(bk["rw"]), by_label(bk.get("rl")))
                # report_result ya se aplicó arriba solo si el anfitrión lo
                # reportó; mientras se muestra el resultado, el bracket del
                # anfitrión todavía no avanzó, igual que acá.
            elif phase in ("rising", "ready"):
                if self._bk_phase in ("result", "result_done", None):
                    self._bracket_screen.start_new_match()
            self._bk_phase = phase
        self._bracket_screen.update(dt, None)
        if phase == "ready":
            self._bracket_screen.phase = "ready"

    # --------------------------------------------------------------
    def touch_mode(self):
        if self._leave_menu is not None:
            return touch_mod.MODE_NONE
        sc = self.scene
        snap = self.client.snapshot or {}
        if sc == "fight":
            ov = snap.get("ov")
            if ov and ov[0] in ("end", "pause"):
                return touch_mod.MODE_NONE
            return touch_mod.MODE_FIGHT if self.my_slot >= 0 else touch_mod.MODE_NONE
        return touch_mod.MODE_NONE

    def special_charge(self):
        snap = self.client.snapshot or {}
        f = snap.get("f")
        if f and 0 <= self.my_slot < len(f):
            return f[self.my_slot][6]
        return 0

    def my_facing(self):
        snap = self.client.snapshot or {}
        f = snap.get("f")
        if f and 0 <= self.my_slot < len(f):
            return f[self.my_slot][2]
        return 1

    def draw(self, surface, ui, dt=1 / 60):
        snap = self.client.snapshot
        if snap is None:
            ui.draw_title_background(surface, dt)
            ui.draw_center_text(surface, "Conectado", C.YELLOW)
            ui.draw_small_center(surface, "Esperando al anfitrión...", C.SCREEN_H // 2 + C.scaled(60))
            return
        sc = snap.get("sc")
        if sc == "lobby":
            self._draw_lobby(surface, ui, snap, dt)
        elif sc == "cs":
            cs = self._charsel or CharacterSelect(p2_is_cpu=False)
            cs.cursor = list(snap.get("cur", [0, 1]))
            cs.confirmed = list(snap.get("conf", [False, False]))
            cs.choices = list(snap.get("ch", [None, None]))
            cs.touch_hint = "Sos J2 (rojo): tocá un luchador para verlo y otra vez para elegirlo"
            cs.draw(surface, ui)
        elif sc == "ss":
            if self._stagesel is None:
                self._stagesel = StageSelect(list_stages())
            self._stagesel.index = snap.get("i", 0)
            self._stagesel.touch_hint = "El anfitrión está eligiendo el escenario..."
            self._stagesel.draw(surface, ui)
            if not ui.touch_lists:
                ui.draw_touch_hint(surface, self._stagesel.touch_hint)
        elif sc == "pick":
            if self._pick is not None:
                self._pick.draw(surface, ui)
            else:
                ui.draw_screen_background(surface, ui.character_selection_background)
                ui.draw_center_text(surface, "¡Listo!", C.YELLOW)
                waiting = snap.get("waiting", [])
                msg = "Esperando a: " + ", ".join(waiting) if waiting else "Armando el torneo..."
                ui.draw_small_center(surface, msg, C.SCREEN_H // 2 + C.scaled(60))
        elif sc == "fight":
            self._draw_fight(surface, ui, snap)
        elif sc == "bk":
            if self._bracket_screen:
                self._bracket_screen.draw(surface, ui)
                nxt = snap.get("bk", {}).get("next")
                if nxt:
                    t = ui.font_tiny.render(nxt, True, C.WHITE)
                    surface.blit(t, t.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(52))))
            else:
                ui.draw_screen_background(surface, ui.character_selection_background)
        elif sc == "champ":
            surface.fill(C.DARK)
            ch = self._chars.get(snap.get("json"))
            if ch:
                ch.state = C.STATE_WIN
                ch.x, ch.y = C.LOGIC_W // 2, C.GROUND_Y
                ch.mystery = False
                ch.hit_flash_timer = 0
                ch.facing = 1
                ch.draw(surface)
            if self._confetti:
                self._confetti.draw(surface)
            ui.draw_title(surface, f"¡{snap.get('label', '').upper()} GANA EL TORNEO!", y=C.scaled(60), color=C.YELLOW)
        elif sc == "wait":
            ui.draw_title_background(surface, dt)
            ui.draw_overlay(surface, alpha=150)
            ui.draw_center_text(surface, snap.get("title", ""), C.YELLOW)
            ui.draw_small_center(surface, snap.get("text", ""), C.SCREEN_H // 2 + C.scaled(60))
        if self._leave_menu is not None:
            self._leave_menu.draw(surface, ui, frozen_frame=surface.copy())

    def _draw_lobby(self, surface, ui, snap, dt):
        ui.draw_title_background(surface, dt)
        ui.draw_overlay(surface, alpha=150)
        ui.draw_title(surface, f"SALA DE {snap.get('host', '').upper()}", y=C.scaled(40))
        players = snap.get("pl", [])
        y = C.scaled(120)
        for i, name in enumerate(players):
            me = " (vos)" if snap.get("ids", [None] * len(players))[i] == self.client.my_id else ""
            img = ui.font_small.render(f"{player_label(i)}: {name}{me}", True, C.YELLOW if me else C.WHITE)
            surface.blit(img, img.get_rect(center=(C.SCREEN_W // 2, y)))
            y += C.scaled(30)
        dots = "." * (1 + int(time.time() * 2) % 3)
        ui.draw_small_center(surface, f"Esperando que el anfitrión empiece{dots}", C.SCREEN_H - C.scaled(90))
        cfg = load_input_config()
        ui.draw_footer_mixed(surface, build_footer_parts(cfg, [("cancel", "salir")]), C.SCREEN_H - C.scaled(25))

    def _draw_fight(self, surface, ui, snap):
        chars = snap.get("chars", [])
        if len(chars) != 2:
            surface.fill(C.DARK)
            return
        p1 = self._character(chars[0])
        p2 = self._character(chars[1])
        f = snap.get("f", [])
        if len(f) == 2:
            apply_fighter_snap(p1, f[0])
            apply_fighter_snap(p2, f[1])
        cam = camera_from_base(snap.get("cam", 0))
        st = snap.get("stage")
        if st:
            self._stage(st).draw(surface, cam)
        else:
            surface.fill((40, 60, 90))
        p1.draw(surface, cam)
        p2.draw(surface, cam)
        for item in snap.get("pr", []):
            x, y, facing, path, voff = projectile_from_snap(item)
            img = Projectile._load_image(path) if path else Projectile._default_image()
            if facing == -1:
                img = pygame.transform.flip(img, True, False)
            surface.blit(img, img.get_rect(center=(x - cam + C.VIEW_PAD, y - voff)))
        hud = snap.get("hud", [C.ROUND_TIME, 0, 0])
        ui.draw_hud(surface, p1, p2, hud[0], hud[1], hud[2])
        ov = snap.get("ov")
        if ov:
            kind = ov[0]
            if kind == "center":
                ui.draw_center_text(surface, ov[1], tuple(ov[2]) if len(ov) > 2 else C.WHITE)
            elif kind == "banner":
                ui.draw_round_end_banner(surface, is_ko=ov[1], is_draw=ov[2])
            elif kind == "end":
                menu = VersusEndMenu(ov[1], net=True)
                menu.index = ov[2]
                menu.draw(surface, ui, frozen_frame=surface.copy())
            elif kind == "pause":
                menu = PauseMenu(net=True)
                menu.index = ov[1]
                menu.draw(surface, ui, frozen_frame=surface.copy())
        if self.my_slot < 0:
            t = ui.font_tiny.render("Mirando la pelea (espectador)", True, C.WHITE)
            surface.blit(t, t.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(20))))
