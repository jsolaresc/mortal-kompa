"""
input_manager.py
-----------------
Maneja entradas de teclado y de N controles (USB o Bluetooth) conectados
a través de pygame.joystick.

Cada jugador tiene un "perfil" de control con ENTRADA DUAL: teclado y
joystick pueden estar los dos configurados a la vez, y cualquiera de los
dos activa la acción -- así, si desconectás el joystick (o directamente
no lo usás), el teclado siempre sigue funcionando.
  {"keys": {...}, "joystick": {"index": 0, "buttons": {...}, "axis_x": 0, "axis_y": 1, "hat": 0}}
"joystick" es opcional (si no hay control asignado, no aparece).

Los perfiles se leen de data/input_config.json y se pueden editar sin tocar código,
o desde el propio juego en Opciones > Configurar Controles.
Para saber qué número de botón/eje corresponde a cada tecla de TU control,
usá tools/test_controller.py (ver el README).
"""

import json
import os
import random
import pygame

from engine import constants as C


DEFAULT_CONFIG_PATH = os.path.join("data", "input_config.json")

# Acciones que el juego entiende. Todo el resto del código trabaja con estos
# nombres, así que da igual si el control es un teclado, un joystick raro, o
# una IA (CPUInput más abajo).
ACTIONS = ["left", "right", "up", "down", "punch", "kick", "special", "block", "ranged", "start", "confirm", "cancel"]
BUTTON_ACTIONS = ("punch", "kick", "special", "block", "ranged", "start", "confirm", "cancel")
# 'confirm'/'cancel' son para NAVEGAR MENÚS (no para pelear): en joystick
# van por defecto a Cruz/Círculo aunque punch/kick de pelea sean otros
# botones (Cuadrado/Cruz); en teclado, si no están asignados a mano,
# caen a lo que sea punch/kick -- así ninguna config vieja se rompe.
ACTION_FALLBACK = {"confirm": "punch", "cancel": "kick"}


def _migrate_profile(profile):
    """Convierte un perfil del esquema VIEJO (teclado O joystick, nunca
    los dos) al NUEVO esquema (los dos a la vez, siempre): antes,
    desconectar el joystick te dejaba sin control porque el teclado se
    borraba al asignar uno. Ahora un perfil siempre puede tener 'keys' Y
    'joystick' -- cualquiera de las dos fuentes activa la acción."""
    if "type" not in profile:
        return profile  # ya está en el esquema nuevo
    if profile["type"] == "joystick":
        return {
            "keys": {},
            "joystick": {
                "index": profile.get("index", 0),
                "axis_x": profile.get("axis_x", 0),
                "axis_y": profile.get("axis_y", 1),
                "hat": profile.get("hat", 0),
                "deadzone": profile.get("deadzone", 0.35),
                "buttons": profile.get("buttons", {}),
            },
        }
    return {"keys": profile.get("keys", {})}


# En modo táctil (Android) los pies de página de los menús muestran los
# nombres de los botones en pantalla ("OK", "VOLVER"...) en vez de teclas
# de teclado -- ver engine/touch.py. Lo activa main.py al arrancar.
TOUCH_LABELS = None  # None | dict accion -> etiqueta

# Caché del archivo de configuración: varias pantallas de menú lo leían
# del disco en CADA cuadro (60 veces por segundo) solo para armar el pie
# de página -- en un celular eso se nota. Se invalida al guardar.
_config_cache = {}


def load_input_config(path=DEFAULT_CONFIG_PATH):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    cached = _config_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return json.loads(cached[1])
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    config = json.loads(raw)
    config["players"] = [_migrate_profile(p) for p in config["players"]]
    _config_cache[path] = (mtime, json.dumps(config))
    return config


def save_input_config(config, path=DEFAULT_CONFIG_PATH):
    _config_cache.pop(path, None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class PlayerInput:
    """Traduce el estado crudo del teclado/joystick a acciones del juego.
    Lee AMBAS fuentes a la vez (si el perfil las tiene configuradas):
    cualquiera de las dos que esté apretada activa la acción. Así, si
    tenés un joystick asignado pero lo desconectás (o directamente no lo
    usás), el teclado sigue funcionando siempre -- nunca te quedás sin
    control."""

    def __init__(self, profile):
        self.profile = profile
        self.joystick = None
        joy_cfg = profile.get("joystick")
        if joy_cfg:
            idx = joy_cfg.get("index", 0)
            if idx < pygame.joystick.get_count():
                self.joystick = pygame.joystick.Joystick(idx)
                self.joystick.init()

        # estado actual y del frame anterior (para detectar "apenas apretado")
        self.state = {a: False for a in ACTIONS}
        self.prev_state = dict(self.state)
        self._injected = set()

    def inject(self, action):
        """Simula que 'action' se acaba de apretar en este cuadro (toques
        directos sobre una opción de menú, botón Atrás de Android, etc.).
        Si se llama ANTES de update() vale para ese update; si se llama
        después, vale para lo que queda de este cuadro."""
        self._injected.add(action)
        self.state[action] = True
        self.prev_state[action] = False

    def end_frame(self):
        self._injected = set()

    def _apply_injected(self):
        for a in self._injected:
            self.state[a] = True
            self.prev_state[a] = False
        self._injected = set()

    def update(self, keys_pressed):
        self.prev_state = dict(self.state)
        new_state = {a: False for a in ACTIONS}

        # --- Teclado (si el perfil tiene teclas asignadas) ---
        kmap = self.profile.get("keys", {})
        for action in ACTIONS:
            key_name = kmap.get(action) or kmap.get(ACTION_FALLBACK.get(action, ""))
            try:
                if key_name and keys_pressed[pygame.key.key_code(key_name)]:
                    new_state[action] = True
            except (ValueError, TypeError):
                pass

        # --- Joystick (si el perfil tiene uno asignado Y sigue conectado) ---
        joy_cfg = self.profile.get("joystick")
        if joy_cfg and self.joystick is not None:
            btns = joy_cfg.get("buttons", {})
            axis_x = joy_cfg.get("axis_x", 0)
            axis_y = joy_cfg.get("axis_y", 1)
            hat_index = joy_cfg.get("hat", None)
            deadzone = joy_cfg.get("deadzone", 0.35)

            left = right = up = down = False

            if axis_x is not None and axis_x < self.joystick.get_numaxes():
                ax = self.joystick.get_axis(axis_x)
                left = ax < -deadzone
                right = ax > deadzone
            if axis_y is not None and axis_y < self.joystick.get_numaxes():
                ay = self.joystick.get_axis(axis_y)
                up = ay < -deadzone
                down = ay > deadzone

            if hat_index is not None and self.joystick.get_numhats() > hat_index:
                hx, hy = self.joystick.get_hat(hat_index)
                if hx != 0:
                    left, right = hx < 0, hx > 0
                if hy != 0:
                    up, down = hy > 0, hy < 0  # en la mayoría de los hats, +1 = arriba

            new_state["left"] = new_state["left"] or left
            new_state["right"] = new_state["right"] or right
            new_state["up"] = new_state["up"] or up
            new_state["down"] = new_state["down"] or down

            for action in BUTTON_ACTIONS:
                btn_index = btns.get(action)
                if btn_index is None:
                    btn_index = btns.get(ACTION_FALLBACK.get(action, ""))
                if (
                    btn_index is not None
                    and btn_index < self.joystick.get_numbuttons()
                    and self.joystick.get_button(btn_index) == 1
                ):
                    new_state[action] = True

        self.state = new_state
        if type(self) is PlayerInput:
            self._apply_injected()

    def pressed(self, action):
        """True mientras se mantiene apretado."""
        return self.state.get(action, False)

    def just_pressed(self, action):
        """True solo en el frame en que se apretó (evita repetir el golpe sin soltar)."""
        return self.state.get(action, False) and not self.prev_state.get(action, False)


class CPUInput:
    """Un 'control' fantasma manejado por reglas simples, para el modo un
    jugador contra la máquina. Implementa la misma interfaz que PlayerInput
    (pressed/just_pressed), así que Character no necesita saber si lo maneja
    una persona o la IA.

    Se usa de dos formas distintas según la pantalla:
      - think_select(...) en la selección de personajes (elige y confirma)
      - think_fight(...) durante la pelea (decide movimientos)
    """

    LEVELS = 10  # dificultad de 1 (muy fácil) a 10 (muy difícil) -- para
    # la Torre de Batalla se puede pasar más de 10 (ver engine/tower.py):
    # cada parámetro interno tiene su propio techo real más alto, así que
    # seguir subiendo más allá de "imposible" sigue notándose.

    def __init__(self, difficulty=5):
        self.difficulty = max(1, difficulty)
        d = (self.difficulty - 1) / (self.LEVELS - 1)  # 0..1 en dificultad normal, puede pasar de 1
        self.reaction_time = max(0.03, 0.45 - 0.38 * d)     # segundos entre decisiones
        self.aggression = min(0.98, 0.15 + 0.55 * d)        # probabilidad de atacar al estar en rango
        self.block_chance = min(0.97, 0.05 + 0.75 * d)      # probabilidad de bloquear un ataque entrante
        self.mistake_chance = max(0.0, 0.35 - 0.32 * d)     # probabilidad de "distraerse" y no reaccionar

        self.state = {a: False for a in ACTIONS}
        self.prev_state = dict(self.state)
        self._timer = 0.0
        self._select_index = 0
        self._select_timer = random.uniform(0.4, 1.2)
        self._select_confirmed = False
        # anti-spam: si viene comiendo golpes seguidos sin contraatacar
        # (típico de un jugador machacando siempre el mismo botón), se
        # pone mucho más defensiva hasta que logra pegar de vuelta
        self._last_health = None
        self._consecutive_hits_taken = 0
        self.force_defend = False  # ver Character.handle_input

    def pressed(self, action):
        return self.state.get(action, False)

    def just_pressed(self, action):
        return self.state.get(action, False) and not self.prev_state.get(action, False)

    def _reset_state(self):
        self.prev_state = dict(self.state)
        self.state = {a: False for a in ACTIONS}

    # ------------------------------------------------------------------
    def think_select(self, dt, num_characters):
        """Simula el uso del menú de selección de personaje: se mueve un
        rato y después confirma."""
        self._reset_state()
        if self._select_confirmed or num_characters <= 0:
            return
        self._select_timer -= dt
        if self._select_timer <= 0:
            if random.random() < 0.7:
                self._select_index = (self._select_index + random.choice([-1, 1])) % num_characters
                self.state["right" if random.random() < 0.5 else "left"] = True
                self._select_timer = random.uniform(0.25, 0.6)
            else:
                self.state["confirm"] = True
                self._select_confirmed = True

    # ------------------------------------------------------------------
    def think_fight(self, dt, me, opponent):
        """Decide qué hacer durante la pelea, mirando la posición y el
        estado del rival. La decisión (moverse, bloquear, etc.) queda
        SOSTENIDA hasta la próxima vez que le toque decidir (cada
        reaction_time) -- antes se resetreaba a "nada" en cada frame y solo
        quedaba en True el frame exacto de la decisión, así que bloquear o
        moverse se veía como un parpadeo/glitch en vez de algo sostenido."""
        self.prev_state = dict(self.state)  # para detectar flancos (just_pressed), siempre al dia
        self._timer -= dt
        if self._timer > 0:
            return  # entre decisiones, se deja el estado tal cual (sostenido)
        self._timer = self.reaction_time

        # anti-spam: si veníamos comiendo golpes seguidos (típico de un
        # jugador machacando siempre el mismo botón) sin lograr pegar de
        # vuelta, contamos la racha -- se resetea apenas la CPU conecta
        # un golpe propio.
        if self._last_health is not None and me.health < self._last_health:
            self._consecutive_hits_taken += 1
        if me.state in ("punch", "kick", "special", "ranged") and me.attack_has_hit:
            self._consecutive_hits_taken = max(0, self._consecutive_hits_taken - 1)
        self._last_health = me.health

        self.state = {a: False for a in ACTIONS}  # recien aca arranca una decision nueva
        self.force_defend = False

        if random.random() < self.mistake_chance:
            return  # esta vez "no reacciona"

        distance = abs(opponent.x - me.x)
        # Distancias calibradas en el lienzo base (960x540, ver
        # C.RES_SCALE) igual que reach/hitboxes en character.py -- sin
        # esto, a una resolución más alta que la base (720p/1080p, que
        # es lo que corre HOY por default) la CPU juzgaba las distancias
        # como si la pantalla siguiera siendo la de 540p de siempre,
        # quedando más corta de reflejos de lo que la dificultad elegida
        # debería dar.
        melee_range = C.scaled(90)             # alcance real de golpes cuerpo a cuerpo (reach de personajes: 65-115)
        ranged_engage_range = C.scaled(420)     # hasta acá vale la pena tirar un ataque a distancia
        block_melee_range = C.scaled(150)       # qué tan cerca hace falta estar para que un golpe cuerpo a cuerpo entrante sea agarrable
        panic_retreat_range = C.scaled(200)

        opponent_melee_attacking = opponent.state in ("punch", "kick", "special")
        opponent_ranged_attacking = opponent.state == "ranged"

        # Con 3+ golpes seguidos sin contraatacar (típico contra un
        # jugador que machaca siempre el mismo botón), la prioridad deja
        # de ser "reaccionar a un ataque que veo activo ahora mismo" y
        # pasa a ser "cubrirme SIEMPRE que esté cerca, casi no atacar,
        # hasta lograr pegar de vuelta" -- si no, entre una decisión y la
        # otra el rival puede estar en la mitad de un golpe sin que la
        # CPU lo esté mirando justo en ese instante, y como sigue siendo
        # agresiva igual, termina intercambiando golpes en vez de cubrirse.
        panicking = self._consecutive_hits_taken >= 3
        if panicking:
            if distance < panic_retreat_range:
                self.state["block"] = True
                self.force_defend = True  # puede cancelar un ataque propio a mitad de camino
                # de vez en cuando arriesga un contragolpe rápido si lo tiene muy encima
                if distance < melee_range and random.random() < 0.2:
                    self.state["block"] = False
                    self.force_defend = False
                    self.state["punch" if random.random() < 0.6 else "kick"] = True
            else:
                # Lejos Y en racha de golpes recibidos: lo más probable
                # es que el rival esté pegando con ataques A DISTANCIA
                # (contra esos, retroceder no sirve de nada -- siguen
                # alcanzando igual). Antes acá SIEMPRE retrocedía, así
                # que contra un rival que solo usaba ranged terminaba
                # empujada hasta la punta del mapa sin poder hacer nada
                # (bug reportado). Ahora se acerca para cerrar distancia
                # y volver a estar en rango de bloquear/contragolpear.
                self.state["right" if opponent.x > me.x else "left"] = True
            return

        # Bloquear si el rival tiene un golpe cuerpo a cuerpo en rango de
        # llegar, O si está en medio de un ataque A DISTANCIA (esos hay
        # que poder bloquearlos sin importar la distancia -- son
        # justamente para pegar de lejos; antes acá se exigía estar a
        # menos de 150px para considerar bloquear CUALQUIER ataque,
        # entrante, así que un ranged tirado desde lejos nunca se
        # bloqueaba ni en la dificultad más alta -- bug reportado).
        threat = (opponent_melee_attacking and distance < block_melee_range) or opponent_ranged_attacking
        if threat and random.random() < self.block_chance:
            self.state["block"] = True
            return

        if distance <= melee_range:
            # cuerpo a cuerpo: atacar según agresividad (o, si no, quizás retroceder)
            if random.random() < self.aggression:
                choice = random.random()
                if choice < 0.45:
                    self.state["punch"] = True
                elif choice < 0.8:
                    self.state["kick"] = True
                elif choice < 0.92 and me.hits_taken_since_special >= 5:
                    self.state["special"] = True
                else:
                    self.state["ranged"] = True
            elif random.random() < 0.3:
                self.state["left" if opponent.x > me.x else "right"] = True
        elif distance <= ranged_engage_range:
            # media distancia: buena oportunidad para un ataque a
            # distancia (antes la CPU NUNCA atacaba desde acá -- la única
            # rama de ataque de todo el método estaba adentro de "cuerpo
            # a cuerpo", así que un ranged solo podía salir por azar
            # estando ya pegada al rival, algo que casi nunca pasaba --
            # bug reportado: "nunca vi que tire ataques ranged"),
            # si no, seguir acercándose para rematar cuerpo a cuerpo.
            if random.random() < self.aggression * 0.8:
                self.state["ranged"] = True
            else:
                self.state["right" if opponent.x > me.x else "left"] = True
                if random.random() < 0.03 * (self.difficulty / self.LEVELS):
                    self.state["up"] = True
        else:
            # lejos de verdad: acercarse (con algo de salto ocasional para variar)
            self.state["right" if opponent.x > me.x else "left"] = True
            if random.random() < 0.03 * (self.difficulty / self.LEVELS):
                self.state["up"] = True


def build_players_input(config):
    """Crea un PlayerInput por cada perfil definido en input_config.json"""
    return [PlayerInput(profile) for profile in config["players"]]


JOYSTICK_ICON_BY_INDEX = {
    # mismo criterio posicional que DEFAULT_JOYSTICK_BUTTONS: el archivo
    # de ícono que corresponde a CADA POSICIÓN del mando, sea cual sea la
    # marca conectada.
    0: "cross.png", 1: "circle.png", 2: "square.png", 3: "triangle.png",
    4: "l1.png", 5: "r1.png", 6: "share.png", 7: "options.png",
}


def key_icon(config, action, player_index=0):
    """Si 'action' está atada a un botón de joystick con ícono conocido
    (ver JOYSTICK_ICON_BY_INDEX), devuelve el nombre de archivo del
    ícono (ej. 'square.png'). Si el jugador usa teclado, o el botón no
    tiene ícono conocido, devuelve None (hay que mostrar texto).

    Mismo respaldo que key_label para 'confirm'/'cancel' (ver
    ACTION_FALLBACK): si no tienen un botón propio asignado, se fijan en
    el de 'punch'/'kick'."""
    if TOUCH_LABELS is not None:
        return None
    try:
        profile = config["players"][player_index]
    except (KeyError, IndexError, TypeError):
        return None
    joy_cfg = profile.get("joystick")
    if not joy_cfg:
        return None
    btns = joy_cfg.get("buttons", {})
    btn = btns.get(action)
    if btn is None:
        btn = btns.get(ACTION_FALLBACK.get(action, ""))
    return JOYSTICK_ICON_BY_INDEX.get(btn)


def build_footer_parts(config, parts, player_index=0):
    """Como build_footer, pero para usar con ui.draw_footer_mixed: en vez
    de un string, devuelve una lista de piezas ('icon', archivo, desc) o
    ('text', etiqueta, desc) -- así el footer puede mostrar el ícono de
    botón real (PlayStation) en vez de la palabra 'BOTÓN 2', tanto para
    controles de PlayStation como de Xbox (misma posición física)."""
    out = []
    for action, desc in parts:
        if action in ACTIONS:
            icon = key_icon(config, action, player_index)
            if icon:
                out.append(("icon", icon, desc))
            else:
                out.append(("text", key_label(config, action, player_index), desc))
        else:
            out.append(("text", action, desc))
    return out


def build_footer(config, parts, player_index=0):
    """Arma un texto de instrucciones tipo 'J confirmar | K volver' usando
    la tecla/botón REAL asignado a cada acción (en vez del nombre fijo
    'PUÑO'/'PATADA' de siempre). 'parts' es una lista de tuplas
    (accion_o_texto_libre, descripcion) -- si el primer elemento no es
    una acción conocida (ej. '↑/↓' para moverse), se usa tal cual."""
    pieces = []
    for action, desc in parts:
        if action in ACTIONS:
            pieces.append(f"{key_label(config, action, player_index)} {desc}")
        else:
            pieces.append(f"{action} {desc}")
    return "   |   ".join(pieces)


def key_label(config, action, player_index=0):
    """Devuelve un texto cortito para mostrar en pantalla qué tecla/botón
    real está asignado a 'action' para ese jugador (según su config
    actual) -- ej. 'J', 'ESPACIO', 'BOTÓN 0'. Si no encuentra nada,
    devuelve el nombre de la acción en mayúsculas como respaldo (nunca
    rompe la pantalla).

    'confirm'/'cancel' son acciones DE MENÚ que casi nunca están
    asignadas a una tecla propia (ver ACTION_FALLBACK más arriba): en la
    práctica funcionan con la tecla de 'punch'/'kick' respectivamente.
    Por eso ACÁ TAMBIÉN hay que aplicar ese mismo respaldo -- si no, el
    cartelito del pie de página termina mostrando el texto literal
    "CANCEL" como si esa fuera la tecla a apretar (no existe tal tecla),
    en vez de la tecla real que sí hace algo (bug reportado: "dice
    CANCEL en el pie pero no anda")."""
    if TOUCH_LABELS is not None:
        return TOUCH_LABELS.get(action, action.upper())
    try:
        profile = config["players"][player_index]
    except (KeyError, IndexError, TypeError):
        return action.upper()

    fallback_action = ACTION_FALLBACK.get(action)

    joy_cfg = profile.get("joystick")
    if joy_cfg:
        btns = joy_cfg.get("buttons", {})
        btn = btns.get(action)
        if btn is None and fallback_action:
            btn = btns.get(fallback_action)
        if btn is not None:
            return f"BOTÓN {btn}"

    keys = profile.get("keys", {})
    key_name = keys.get(action)
    if key_name is None and fallback_action:
        key_name = keys.get(fallback_action)
    if key_name is None:
        return action.upper()
    # nombres de pygame para teclas especiales, más cortos/prolijos en pantalla
    NICE_NAMES = {
        "return": "ENTER", "space": "ESPACIO", "left": "◄", "right": "►",
        "up": "▲", "down": "▼", "left shift": "SHIFT", "right shift": "SHIFT",
    }
    return NICE_NAMES.get(key_name, key_name.upper())


DEFAULT_JOYSTICK_BUTTONS = {
    # Se mapea por POSICIÓN FÍSICA en el mando, no por marca: en (casi)
    # todos los joysticks reconocidos por SDL2/pygame (PS3/PS4/Xbox
    # 360/One), el botón de ABAJO es el índice 0, el de la DERECHA el 1,
    # el de la IZQUIERDA el 2 y el de ARRIBA el 3 -- así que usar estos
    # índices ya da Cruz/Círculo/Cuadrado/Triángulo en un control de
    # PlayStation, y A/B/X/Y en la MISMA posición física en uno de Xbox,
    # sin tener que detectar la marca del control para nada.
    "kick": 0,      # abajo: Cruz (PS) / A (Xbox)
    "ranged": 1,    # derecha: Círculo (PS) / B (Xbox)
    "punch": 2,     # izquierda: Cuadrado (PS) / X (Xbox)
    "special": 3,   # arriba: Triángulo (PS) / Y (Xbox)
    "block": 5,     # R1 (PS) / RB (Xbox)
    "start": 7,     # Options (PS) / Menu (Xbox)
    # navegación de menús, INDEPENDIENTE de los botones de pelea de arriba
    "confirm": 0,   # Cruz (PS) / A (Xbox)
    "cancel": 1,    # Círculo (PS) / B (Xbox)
}


def auto_assign_joysticks(config):
    """Si hay 1 o 2 controles conectados y todavía no se les asignó nada
    a mano, los suma automáticamente para Jugador 1 / Jugador 2, ADEMÁS
    del teclado -- nunca lo reemplaza (entrada dual: cualquiera de los
    dos sirve en todo momento, así que desconectar el joystick nunca te
    deja sin control). Con una asignación de botones estándar, editable
    después desde Opciones > Configurar Controles. NO toca un perfil que
    el jugador ya haya configurado con un joystick a propósito.

    Devuelve True si cambió algo (para saber si conviene reconstruir los
    PlayerInput y guardar la config)."""
    pygame.joystick.init()
    count = pygame.joystick.get_count()
    if count == 0:
        return False

    used_indices = {
        p["joystick"]["index"] for p in config["players"] if p.get("joystick")
    }

    changed = False
    joy_i = 0
    for player_profile in config["players"]:
        if player_profile.get("joystick"):
            continue  # ya tiene un control asignado (a mano o antes), no tocar
        while joy_i in used_indices and joy_i < count:
            joy_i += 1
        if joy_i >= count:
            break  # no quedan controles libres para este jugador
        player_profile["joystick"] = {
            "index": joy_i,
            "axis_x": 0,
            "axis_y": 1,
            "hat": 0,
            "deadzone": 0.35,
            "buttons": dict(DEFAULT_JOYSTICK_BUTTONS),
        }
        player_profile.setdefault("keys", {})  # el teclado se mantiene intacto
        used_indices.add(joy_i)
        joy_i += 1
        changed = True
    return changed


def list_connected_joysticks():
    """Utilidad para debug: devuelve nombres e índices de joysticks conectados."""
    pygame.joystick.init()
    out = []
    for i in range(pygame.joystick.get_count()):
        j = pygame.joystick.Joystick(i)
        j.init()
        out.append((i, j.get_name(), j.get_numbuttons(), j.get_numaxes(), j.get_numhats()))
    return out
