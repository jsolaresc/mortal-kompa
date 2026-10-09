"""
netplay.py
-----------
Multijugador por WiFi entre celulares (o PCs) en la MISMA red local.
Si no hay WiFi, alcanza con que un celular comparta datos ("Zona WiFi"
/ hotspot) y los demás se conecten a esa red: no hace falta internet.

MODELO: "anfitrión con autoridad". El celular que crea la partida
(anfitrión) corre TODO el juego de verdad (física, golpes, menús); los
demás (invitados) solo:
  1) le mandan, 60 veces por segundo, qué botones están apretando, y
  2) dibujan lo que el anfitrión les manda (posiciones, poses, vida,
     timer, proyectiles, sonidos, música...).
Así nunca hay "desincronización" entre celulares, y los invitados no
necesitan calcular nada de la pelea.

Todo va por UDP (paquetes chicos en JSON):
  - Descubrimiento: el anfitrión anuncia su partida por broadcast cada
    segundo en el puerto DISCOVERY_PORT; los invitados además preguntan
    ("¿hay alguien?") por broadcast y el anfitrión les responde directo.
    Si el router bloquea broadcast, se puede escribir la IP a mano
    (se muestra en la pantalla del anfitrión).
  - Juego: puerto GAME_PORT del anfitrión.

Si se pierde un paquete no pasa nada: cada "foto" del anfitrión trae el
estado completo, y los eventos de sonido se repiten en varias fotos
seguidas (el invitado reproduce solo los que no había escuchado).
"""

import json
import os
import socket
import time

from engine import constants as C
from engine.input_manager import ACTIONS
from engine.sound_manager import SoundManager

DISCOVERY_PORT = 47777
GAME_PORT = 47778
MAGIC = "MKOMPA1"
CLIENT_TIMEOUT = 12.0  # segundos sin noticias de un invitado -> se lo da por desconectado (cargar personajes puede tardar)
HOST_TIMEOUT = 12.0    # idem, desde el lado del invitado
ANNOUNCE_EVERY = 1.0
MAX_CLIENTS = 15
EVENTS_KEEP = 48      # cuántos eventos de sonido viajan repetidos en cada foto

ACTION_INDEX = {a: i for i, a in enumerate(ACTIONS)}


def _encode(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode(data):
    try:
        obj = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict) or obj.get("m") != MAGIC:
        return None
    return obj


def local_ips():
    """IPs IPv4 propias (sin 127.x). Prueba varias formas porque en un
    celular haciendo de hotspot sin internet el truco de "conectar a
    8.8.8.8" puede no andar."""
    from engine import device

    ips = list(device.android_local_ips())
    for probe in ("8.8.8.8", "192.168.1.1", "10.255.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127.") and ip not in ips and ip != "0.0.0.0":
                ips.append(ip)
        except OSError:
            pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def broadcast_targets():
    targets = ["255.255.255.255"]
    for ip in local_ips():
        parts = ip.split(".")
        if len(parts) == 4:
            targets.append(".".join(parts[:3] + ["255"]))
    # redes de hotspot típicas de Android (por si no pudimos ver la IP propia)
    for extra in ("192.168.43.255", "192.168.49.255"):
        if extra not in targets:
            targets.append(extra)
    return targets


def _udp_socket(port=0, broadcast=False):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if broadcast:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("", port))
    s.setblocking(False)
    return s


# ======================================================================
# Entrada remota (lo que aprieta un invitado, visto desde el anfitrión)
# ======================================================================
class RemoteInput:
    """Misma interfaz que PlayerInput (pressed/just_pressed), alimentada
    por los paquetes de un invitado. Las pulsaciones viajan como
    CONTADORES (cuántas veces se apretó cada botón desde que arrancó),
    así un toque rapidísimo nunca se pierde aunque se pierda un paquete."""

    def __init__(self):
        self.held = set()
        self._counters = [0] * len(ACTIONS)
        self._seen = None
        self._just = set()
        self.taps = []  # [(tipo, indice)] pendientes de aplicar
        self._tap_seq = 0

    def feed(self, held_bits, counters, taps):
        self.held = {a for a, i in ACTION_INDEX.items() if held_bits & (1 << i)}
        if isinstance(counters, list) and len(counters) == len(ACTIONS):
            self._counters = counters
        for t in taps or []:
            try:
                seq, kind, idx = t
            except (TypeError, ValueError):
                continue
            if seq > self._tap_seq:
                self._tap_seq = seq
                self.taps.append((kind, idx))

    def step(self):
        """Llamar UNA vez por cuadro del anfitrión."""
        if self._seen is None:
            self._seen = list(self._counters)
        self._just = {
            a for a, i in ACTION_INDEX.items() if self._counters[i] > self._seen[i]
        }
        self._seen = list(self._counters)

    def pressed(self, action):
        return action in self.held or action in self._just

    def just_pressed(self, action):
        return action in self._just

    def take_taps(self, kind):
        out = [idx for k, idx in self.taps if k == kind]
        self.taps = [t for t in self.taps if t[0] != kind]
        return out

    def clear(self):
        self.held = set()
        self._just = set()
        self.taps = []


class CombinedInput:
    """Varias entradas a la vez (ej. anfitrión + invitado controlando el
    mismo menú de fin de pelea): cualquiera que apriete, vale."""

    def __init__(self, *inputs):
        self.inputs = [i for i in inputs if i is not None]

    def pressed(self, action):
        return any(i.pressed(action) for i in self.inputs)

    def just_pressed(self, action):
        return any(i.just_pressed(action) for i in self.inputs)


# ======================================================================
# Sonido que además "graba" lo que suena (para mandárselo a los invitados)
# ======================================================================
class _LoopHandle:
    __slots__ = ("channel", "id")

    def __init__(self, channel, loop_id):
        self.channel = channel
        self.id = loop_id


class NetSoundManager(SoundManager):
    """SoundManager normal que, si 'recording' está activo (somos
    anfitrión de una partida en red), anota cada sonido que reproduce
    para que los invitados lo reproduzcan también."""

    def __init__(self):
        super().__init__()
        self.recording = False
        self.events = []
        self._ev_seq = 0
        self._loop_seq = 0
        self._mute_record = 0
        # Estado de la música (va en cada foto, no como evento: así un
        # invitado que se une a mitad de camino igual queda sincronizado)
        self.music_state = [None, 0.55, True, "menu", 0, False]

    def _rec(self, *ev):
        if self.recording and not self._mute_record:
            self._ev_seq += 1
            self.events.append([self._ev_seq, *ev])
            if len(self.events) > EVENTS_KEEP:
                del self.events[: len(self.events) - EVENTS_KEEP]

    def recent_events(self):
        return list(self.events)

    def play(self, path, volume=1.0):
        self._rec("p", path, round(volume, 3))
        super().play(path, volume)

    def play_announcer(self, name, volume=1.0):
        self._rec("a", name, round(volume, 3))
        self._mute_record += 1
        try:
            super().play_announcer(name, volume)
        finally:
            self._mute_record -= 1

    def play_raw(self, path, volume):
        self._rec("r", path, round(volume, 3))
        super().play_raw(path, volume)

    def play_loop(self, path, volume=1.0):
        ch = super().play_loop(path, volume)
        self._loop_seq += 1
        self._rec("lp", self._loop_seq, path, round(volume, 3))
        return _LoopHandle(ch, self._loop_seq)

    def stop_loop(self, channel):
        if isinstance(channel, _LoopHandle):
            self._rec("ls", channel.id)
            super().stop_loop(channel.channel)
        else:
            super().stop_loop(channel)

    def play_music(self, path, volume=0.55, loop=True, category="menu"):
        super().play_music(path, volume, loop, category)
        if path and os.path.isfile(path):
            self.music_state = [path, volume, loop, category, self.music_state[4] + 1, False]

    def stop_music(self):
        super().stop_music()
        self.music_state = [None, 0.55, True, "menu", self.music_state[4] + 1, False]

    def pause_music(self):
        super().pause_music()
        self.music_state[5] = True

    def unpause_music(self):
        super().unpause_music()
        self.music_state[5] = False

    def pause_all_sfx(self):
        self._rec("pa")
        super().pause_all_sfx()

    def unpause_all_sfx(self):
        self._rec("ua")
        super().unpause_all_sfx()

    def stop_all_sfx(self):
        self._rec("sa")
        super().stop_all_sfx()


class SoundMirror:
    """Del lado del invitado: reproduce los eventos de sonido y la música
    que manda el anfitrión."""

    def __init__(self, sound_manager):
        self.sm = sound_manager
        self.last_seq = None
        self.loops = {}
        self.music_nonce = None
        self.music_paused = False

    def apply(self, events, music):
        if events:
            if self.last_seq is None:
                # recién conectados: no reproducir lo que ya pasó
                self.last_seq = max(e[0] for e in events)
            for ev in events:
                seq = ev[0]
                if seq <= self.last_seq:
                    continue
                self.last_seq = seq
                self._play(ev[1], ev[2:])
        elif self.last_seq is None:
            self.last_seq = 0
        if music:
            path, vol, loop, cat, nonce, paused = music
            if nonce != self.music_nonce:
                self.music_nonce = nonce
                if path:
                    self.sm.play_music(path, vol, loop, cat)
                else:
                    self.sm.stop_music()
                self.music_paused = False
            if paused != self.music_paused:
                self.music_paused = paused
                if paused:
                    self.sm.pause_music()
                else:
                    self.sm.unpause_music()

    def _play(self, kind, args):
        sm = self.sm
        try:
            if kind == "p":
                sm.play(args[0], args[1])
            elif kind == "a":
                sm.play_announcer(args[0], args[1])
            elif kind == "r":
                sm.play_raw(args[0], args[1])
            elif kind == "lp":
                self.loops[args[0]] = sm.play_loop(args[1], args[2])
            elif kind == "ls":
                sm.stop_loop(self.loops.pop(args[0], None))
            elif kind == "pa":
                sm.pause_all_sfx()
            elif kind == "ua":
                sm.unpause_all_sfx()
            elif kind == "sa":
                sm.stop_all_sfx()
                self.loops.clear()
        except Exception as e:  # nunca romper por un sonido
            print(f"[AVISO] sonido remoto: {e}")


# ======================================================================
# Anfitrión
# ======================================================================
class ClientConn:
    def __init__(self, cid, addr, name):
        self.id = cid
        self.addr = addr
        self.name = name
        self.last_seen = time.time()
        self.input = RemoteInput()
        self.last_in_seq = -1
        self.pick = None  # elección de personaje (torneo)


class NetHost:
    def __init__(self, name):
        self.name = name
        self.sock = _udp_socket(GAME_PORT, broadcast=True)
        try:
            self.disc = _udp_socket(DISCOVERY_PORT, broadcast=True)
        except OSError:
            self.disc = None
        self.clients = []
        self._next_id = 1
        self.open = True  # se aceptan invitados nuevos
        self._last_announce = 0.0
        self.dropped = []  # nombres de invitados que se cayeron (para avisar en pantalla)
        self.snap_seq = 0
        self._targets = broadcast_targets()
        self._targets_time = time.time()

    def ip_text(self):
        now = time.time()
        if now - getattr(self, "_ip_time", 0) > 3.0:
            self._ip_time = now
            ips = local_ips()
            self._ip_cache = ", ".join(ips[:2]) if ips else "(sin red)"
        return self._ip_cache

    def close(self):
        msg = _encode({"m": MAGIC, "t": "end"})
        for _ in range(3):
            for c in self.clients:
                try:
                    self.sock.sendto(msg, c.addr)
                except OSError:
                    pass
        for s in (self.sock, self.disc):
            try:
                if s:
                    s.close()
            except OSError:
                pass

    def client_by_id(self, cid):
        return next((c for c in self.clients if c.id == cid), None)

    def kick(self, client):
        try:
            self.sock.sendto(_encode({"m": MAGIC, "t": "end"}), client.addr)
        except OSError:
            pass
        if client in self.clients:
            self.clients.remove(client)

    def _announce_packet(self):
        return _encode({"m": MAGIC, "t": "ann", "name": self.name, "port": GAME_PORT,
                        "open": self.open, "n": len(self.clients) + 1})

    def poll(self):
        now = time.time()
        # anuncio periódico por broadcast
        if now - self._last_announce >= ANNOUNCE_EVERY:
            self._last_announce = now
            if now - self._targets_time > 10:
                self._targets = broadcast_targets()
                self._targets_time = now
            pkt = self._announce_packet()
            for t in self._targets:
                try:
                    self.sock.sendto(pkt, (t, DISCOVERY_PORT))
                except OSError:
                    pass
        # preguntas de descubrimiento
        if self.disc:
            while True:
                try:
                    data, addr = self.disc.recvfrom(2048)
                except (BlockingIOError, OSError):
                    break
                msg = _decode(data)
                if msg and msg.get("t") == "probe":
                    reply_port = int(msg.get("port", DISCOVERY_PORT))
                    try:
                        self.sock.sendto(self._announce_packet(), (addr[0], reply_port))
                    except OSError:
                        pass
        # paquetes de juego
        while True:
            try:
                data, addr = self.sock.recvfrom(4096)
            except (BlockingIOError, OSError):
                break
            msg = _decode(data)
            if not msg:
                continue
            t = msg.get("t")
            client = next((c for c in self.clients if c.addr == addr), None)
            if t == "probe":
                try:
                    self.sock.sendto(self._announce_packet(), addr)
                except OSError:
                    pass
            elif t == "hello":
                if client is None:
                    if not self.open or len(self.clients) >= MAX_CLIENTS:
                        self.sock.sendto(_encode({"m": MAGIC, "t": "reject",
                                                  "why": "La partida ya empezó"}), addr)
                        continue
                    client = ClientConn(self._next_id, addr, str(msg.get("name", "Invitado"))[:18])
                    self._next_id += 1
                    self.clients.append(client)
                client.last_seen = now
                self.sock.sendto(_encode({"m": MAGIC, "t": "welcome", "id": client.id,
                                          "host": self.name}), addr)
            elif client is None:
                continue
            elif t == "in":
                client.last_seen = now
                seq = msg.get("s", 0)
                if seq > client.last_in_seq:
                    client.last_in_seq = seq
                    client.input.feed(msg.get("h", 0), msg.get("c"), msg.get("tp"))
                pick = msg.get("pick")
                if pick is not None:
                    client.pick = pick
            elif t == "bye":
                self.clients.remove(client)
                self.dropped.append(client.name)
        # timeouts
        for c in list(self.clients):
            if now - c.last_seen > CLIENT_TIMEOUT:
                self.clients.remove(c)
                self.dropped.append(c.name)
        for c in self.clients:
            c.input.step()

    def send(self, snap):
        self.snap_seq += 1
        snap["m"] = MAGIC
        snap["t"] = "snap"
        snap["s"] = self.snap_seq
        data = _encode(snap)
        for c in self.clients:
            try:
                self.sock.sendto(data, c.addr)
            except OSError:
                pass


# ======================================================================
# Invitado
# ======================================================================
class NetClient:
    def __init__(self, name):
        self.name = name
        self.sock = _udp_socket(0, broadcast=True)
        self.port = self.sock.getsockname()[1]
        try:
            self.disc = _udp_socket(DISCOVERY_PORT, broadcast=True)
        except OSError:
            self.disc = None
        self.hosts = {}  # ip -> {"name", "port", "seen", "open", "n"}
        self.host_addr = None
        self.my_id = None
        self.host_name = ""
        self.connected = False
        self.ended = False
        self.end_reason = ""
        self.snapshot = None
        self._last_snap_seq = -1
        self._last_probe = 0.0
        self._last_hello = 0.0
        self._hello_started = 0.0
        self.last_host_msg = time.time()
        self._in_seq = 0
        self._targets = broadcast_targets()

    def close(self):
        if self.host_addr:
            for _ in range(3):
                try:
                    self.sock.sendto(_encode({"m": MAGIC, "t": "bye"}), self.host_addr)
                except OSError:
                    pass
        for s in (self.sock, self.disc):
            try:
                if s:
                    s.close()
            except OSError:
                pass

    def connect(self, ip, port=GAME_PORT):
        self.host_addr = (ip, port)
        self.connected = False
        self._hello_started = time.time()
        self._last_hello = 0.0
        self.end_reason = ""
        self.ended = False

    def connecting_timed_out(self):
        return self.host_addr and not self.connected and time.time() - self._hello_started > 6.0

    def _handle(self, msg, addr):
        t = msg.get("t")
        if t == "ann":
            self.hosts[addr[0]] = {
                "name": msg.get("name", "?"), "port": int(msg.get("port", GAME_PORT)),
                "seen": time.time(), "open": msg.get("open", True), "n": msg.get("n", 1),
            }
            return
        if not self.host_addr or addr[0] != self.host_addr[0]:
            return
        self.last_host_msg = time.time()
        if t == "welcome":
            self.connected = True
            self.my_id = msg.get("id")
            self.host_name = msg.get("host", "")
        elif t == "reject":
            self.ended = True
            self.end_reason = msg.get("why", "No se pudo entrar")
        elif t == "end":
            self.ended = True
            self.end_reason = "El anfitrión cerró la partida"
        elif t == "snap":
            seq = msg.get("s", 0)
            if seq > self._last_snap_seq:
                self._last_snap_seq = seq
                self.snapshot = msg

    def poll(self):
        now = time.time()
        if not self.host_addr and now - self._last_probe > 1.0:
            # preguntar "¿hay alguien?" por broadcast
            self._last_probe = now
            pkt = _encode({"m": MAGIC, "t": "probe", "port": self.port})
            for t in self._targets:
                try:
                    self.sock.sendto(pkt, (t, DISCOVERY_PORT))
                except OSError:
                    pass
        if self.host_addr and not self.connected and now - self._last_hello > 0.4:
            self._last_hello = now
            try:
                self.sock.sendto(_encode({"m": MAGIC, "t": "hello", "name": self.name}), self.host_addr)
            except OSError:
                pass
        for s in (self.sock, self.disc):
            if not s:
                continue
            while True:
                try:
                    data, addr = s.recvfrom(65536)
                except (BlockingIOError, OSError):
                    break
                msg = _decode(data)
                if msg:
                    self._handle(msg, addr)
        # hosts que dejaron de anunciarse
        for ip in list(self.hosts):
            if now - self.hosts[ip]["seen"] > 4.0:
                del self.hosts[ip]
        if self.connected and now - self.last_host_msg > HOST_TIMEOUT:
            self.ended = True
            self.end_reason = "Se perdió la conexión con el anfitrión"

    def send_input(self, held, counters, taps, pick=None):
        if not (self.host_addr and self.connected):
            return
        self._in_seq += 1
        bits = 0
        for a in held:
            bits |= 1 << ACTION_INDEX[a]
        pkt = {"m": MAGIC, "t": "in", "s": self._in_seq, "h": bits, "c": counters, "tp": taps}
        if pick is not None:
            pkt["pick"] = pick
        try:
            self.sock.sendto(_encode(pkt), self.host_addr)
        except OSError:
            pass


class LocalInputTracker:
    """Del lado del invitado: arma el paquete de entrada a partir de su
    TouchInput local (botones mantenidos + contadores de pulsaciones +
    toques directos sobre menús)."""

    def __init__(self):
        self.counters = [0] * len(ACTIONS)
        self.taps = []  # [seq, tipo, indice] (se reenvían varias veces)
        self._tap_seq = 0

    def update(self, inp):
        held = [a for a in ACTIONS if inp.pressed(a)]
        for a in ACTIONS:
            if inp.just_pressed(a):
                self.counters[ACTION_INDEX[a]] += 1
        return held

    def add_tap(self, kind, idx):
        self._tap_seq += 1
        self.taps.append([self._tap_seq, kind, idx])
        self.taps = self.taps[-6:]


# ======================================================================
# Fotos (snapshots) de la pelea
# ======================================================================
# Las posiciones viajan en "unidades base" (lienzo de 960x540, ver
# C.RES_SCALE): así un celular a 720p y otro a 540p ven exactamente lo
# mismo, cada uno a su propia resolución.
def _to_base(v):
    return round(v / C.RES_SCALE, 2)


def _from_base(v):
    return v * C.RES_SCALE


def fighter_snap(f):
    anim = f.animations.get(f.state)
    return [
        _to_base(f.x), _to_base(f.y), f.facing, f.state, anim.index if anim else 0,
        round(f.health, 2), f.hits_taken_since_special, f.name, bool(f.mystery),
        f.hit_flash_timer > 0,
    ]


def apply_fighter_snap(f, s):
    (x, y, f.facing, state, idx, f.health, f.hits_taken_since_special,
     f.name, f.mystery, flash) = s
    f.x, f.y = _from_base(x), _from_base(y)
    f.state = state
    anim = f.animations.get(state)
    if anim and anim.frames:
        anim.index = max(0, min(idx, len(anim.frames) - 1))
    f.hit_flash_timer = 0.1 if flash else 0.0


def projectile_snap(p):
    paths = getattr(p, "frame_paths", None) or [None]
    path = paths[p.frame_index % len(paths)] if paths else None
    return [_to_base(p.x), _to_base(p.y), p.facing, path, _to_base(p.visual_y_offset)]


def camera_to_base(cam):
    return _to_base(cam)


def camera_from_base(cam):
    return _from_base(cam)


def projectile_from_snap(item):
    x, y, facing, path, voff = item
    return _from_base(x), _from_base(y), facing, path, _from_base(voff)
