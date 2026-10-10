"""
main.py
--------
Punto de entrada. Ejecutá:  python3 main.py   (o hacé doble click en
Juego de Pelea.bat en Windows)

Flujo del juego:
  MENÚ DE MODOS -> [Dificultad si es CPU] -> SELECCIÓN DE PERSONAJES ->
  SELECCIÓN DE ESCENARIO -> INTRO DE ROUND -> PELEA -> RESULTADO ->
  (siguiente ronda o fin de la pelea) -> MENÚ DE MODOS

  Desde el menú de modos también se puede entrar a OPCIONES (volumen,
  pantalla completa, configurar controles).

  Durante la pelea, ENTER (teclado) o START (joystick) pausa el juego.

Controles de fábrica (podés cambiarlos en data/input_config.json o desde
Opciones > Configurar Controles):
  Jugador 1 (teclado): A/D mover, W saltar, S bloquear, J puño, K patada,
                        L especial, I ataque a distancia, ENTER pausa
  Jugador 2 (teclado): flechas mover, arriba saltar, abajo bloquear,
                        1 puño, 2 patada, 3 especial, 4 ataque a distancia
"""

import os
import sys


def _android_crash_screen(exc_type, exc, tb):
    """En el celular no hay consola: si el juego se cae, en vez de cerrarse
    en silencio muestra el error en pantalla (para sacarle captura) y lo
    guarda en crash.txt. Tocar la pantalla cierra."""
    import traceback
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        with open("crash.txt", "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        pass
    sys.__excepthook__(exc_type, exc, tb)
    try:
        import pygame as _pg
        _pg.init()
        scr = _pg.display.get_surface() or _pg.display.set_mode((0, 0), _pg.FULLSCREEN)
        w, h = scr.get_size()
        font = _pg.font.Font(None, max(18, h // 34))
        raw = ["Mortal Kompa se cayó :(  Sacale captura y mandásela a Claude."] + text.splitlines()[-22:]
        lines = []
        for ln in raw:  # partir líneas largas para que entren en pantalla
            while ln and font.size(ln)[0] > w - 24:
                cut = len(ln)
                while cut > 1 and font.size(ln[:cut])[0] > w - 24:
                    cut -= 1
                lines.append(ln[:cut])
                ln = "    " + ln[cut:]
            lines.append(ln)
        while True:
            for ev in _pg.event.get():
                if ev.type in (_pg.QUIT, _pg.FINGERDOWN, _pg.MOUSEBUTTONDOWN, _pg.KEYDOWN):
                    _pg.quit()
                    os._exit(1)
            scr.fill((25, 10, 15))
            y = 10
            for i, ln in enumerate(lines):
                col = (255, 210, 80) if i == 0 else (235, 235, 235)
                scr.blit(font.render(ln, True, col), (12, y))
                y += font.get_linesize()
            _pg.display.flip()
            _pg.time.wait(100)
    except Exception:
        os._exit(1)


if "ANDROID_ARGUMENT" in os.environ or "--crash-screen" in sys.argv:
    sys.excepthook = _android_crash_screen
import subprocess

# Si esto es un .exe armado con PyInstaller (ver mortal_kompa.spec) --
# NO corriendo "python main.py" normal -- todos los assets/data quedan
# en la carpeta real que indica sys._MEIPASS (según la versión de
# PyInstaller y la config del .spec, puede ser directo al lado del .exe
# o adentro de una subcarpeta "_internal"), pero el resto del código de
# este proyecto usa rutas relativas comunes tipo "assets/stages/..." o
# "data/characters/..." asumiendo que están al lado de main.py -- este
# chdir() hace que esas rutas relativas de siempre apunten al lugar
# correcto, sin tener que tocarlas una por una en todo el proyecto.
# Corriendo como script normal (sys.frozen no existe) esto no hace nada.
if getattr(sys, "frozen", False):
    os.chdir(sys._MEIPASS)

import pygame

from engine import constants as C
from engine import device
device.fix_android_paths(force="--android-paths" in sys.argv)
from engine.settings import load_settings, save_settings

# OJO: esto tiene que pasar ACÁ, antes de importar cualquier otro módulo
# de engine/ -- ui.py, menu.py y tower.py calculan constantes de layout
# con C.scaled() apenas se importan (una sola vez), así que si la
# resolución se fija DESPUÉS de importarlos, esos módulos quedan
# calculados para la resolución vieja. Ver C.set_resolution().
_settings = load_settings()
if device.TOUCH_UI and _settings.get("resolution") not in ("540p", "720p"):
    # en el celular no se usa 1080p (ver OptionsSubMenu.RESOLUTION_OPTIONS)
    _settings["resolution"] = "720p"
C.set_resolution(_settings.get("resolution", C.DEFAULT_RESOLUTION), aspect=device.screen_aspect())

from engine import input_manager as _input_manager_mod
from engine.input_manager import (
    load_input_config, save_input_config, build_players_input, CPUInput, PlayerInput,
    auto_assign_joysticks, build_footer, build_footer_parts,
)
from engine.character import Character
from engine.sound_manager import SoundManager
from engine.stage import Stage, list_stages, get_secret_stage
from engine.projectile import Projectile
from engine.ui import UI
from engine.menu import (
    ModeMenu, OnePlayerMenu, DifficultySelect, CharacterSelect, StageSelect,
    PauseMenu, OptionsMenu, OptionsSubMenu, OPTIONS_CATEGORIES, ControlsRemapMenu, RANDOM_SENTINEL,
    STAGE_RANDOM_SENTINEL,
    MultiplayerMenu, TournamentSizeSelect, TournamentCharacterSelect, TournamentBracketScreen,
    load_character_list, VersusEndMenu, TowerDefeatMenu,
)
from engine.tournament import TournamentBracket
from engine.tower import TowerLadder, build_opponent_order, build_final_boss_entry, Confetti
from engine.intro import IntroPlayer, VIDEO_PATH as INTRO_VIDEO_PATH
from engine import touch as touch_mod
from engine.touch import TouchControls, TouchInput
from engine.netplay import NetHost, NetClient, NetSoundManager, CombinedInput, fighter_snap, projectile_snap, camera_to_base
from engine.net_screens import HostLobby, JoinScreen, ClientSession, player_label
import random

STATE_INTRO = "intro"
STATE_MODE_MENU = "mode_menu"
STATE_ONE_PLAYER_MENU = "one_player_menu"
STATE_DIFFICULTY = "difficulty"
STATE_CHAR_SELECT = "char_select"
STATE_TOWER_INTRO = "tower_intro"
STATE_TOWER_VICTORY = "tower_victory"
STATE_STAGE_SELECT = "stage_select"
STATE_ROUND_INTRO = "round_intro"
STATE_FIGHT = "fight"
STATE_ROUND_END = "round_end"
STATE_MATCH_END = "match_end"
STATE_PAUSED = "paused"
STATE_OPTIONS = "options"
STATE_OPTIONS_SUB = "options_sub"
STATE_CONTROLS_REMAP = "controls_remap"
STATE_VERSUS_END = "versus_end"
STATE_TOWER_DEFEAT = "tower_defeat"
STATE_MULTIPLAYER_MENU = "multiplayer_menu"
STATE_TOURNAMENT_SIZE = "tournament_size"
STATE_TOURNAMENT_CHAR_SELECT = "tournament_char_select"
STATE_TOURNAMENT_BRACKET = "tournament_bracket"
STATE_TOURNAMENT_VICTORY = "tournament_victory"
# Multijugador por WiFi (ver engine/netplay.py y engine/net_screens.py)
STATE_NET_LOBBY = "net_lobby"        # anfitrión: sala de espera
STATE_NET_JOIN = "net_join"          # invitado: buscando partida
STATE_NET_CLIENT = "net_client"      # invitado: conectado (todo lo dibuja ClientSession)
STATE_NET_PICK = "net_pick"          # torneo WiFi: cada uno elige su luchador
MODE_NET_VERSUS = "net_versus"
MODE_NET_TOURNAMENT = "net_tournament"

# Estados en los que los controles táctiles son los de PELEA (joystick +
# golpes); en el resto se muestran los de menú (joystick + OK/VOLVER).
FIGHT_TOUCH_STATES = {"round_intro", "fight", "round_end"}

# Estados donde suena "música de menú" (playlist, sin loop -- cuando
# termina una canción pasa sola a otra al azar). Fuera de esta lista
# (durante la pelea en sí) la música es la del escenario, que sigue
# loopeando como siempre.
MENU_MUSIC_STATES = {
    STATE_MODE_MENU, STATE_ONE_PLAYER_MENU, STATE_DIFFICULTY, STATE_CHAR_SELECT,
    STATE_TOWER_INTRO, STATE_TOWER_VICTORY, STATE_STAGE_SELECT, STATE_MATCH_END,
    STATE_OPTIONS, STATE_OPTIONS_SUB, STATE_CONTROLS_REMAP, STATE_VERSUS_END, STATE_TOWER_DEFEAT,
    STATE_MULTIPLAYER_MENU, STATE_TOURNAMENT_SIZE, STATE_TOURNAMENT_CHAR_SELECT,
    STATE_TOURNAMENT_BRACKET, STATE_TOURNAMENT_VICTORY,
    STATE_NET_LOBBY, STATE_NET_JOIN, STATE_NET_PICK,
}

ROUND_INTRO_PAUSE = 0.35        # silencio entre "Round X"/"Muerte Súbita" y "FIGHT"
WIN_AUDIO_GAP = 0.35            # mismo silencio, pero entre anuncios de la cola de "Wins"/"Flawless Victory" (ver queue_win_audio)
ROUND_INTRO_TRAILING_PAD = 0.3  # margen después de "FIGHT" antes de que arranque la pelea de verdad
MUSIC_DIR = os.path.join("assets", "sounds", "music")

MENU_VOICES_DIR = os.path.join("assets", "sounds", "menu_voices")
MENU_VOICE_INTERVAL = 25.0  # cada cuántos segundos se tira el dado (antes: 40, y 60 antes de eso -- pedido explícito: "aumentar la frecuencia")
MENU_VOICE_CHANCE = 0.15    # probabilidad de que efectivamente suene, cada vez que se tira (antes: 0.10)
# En qué pantallas puede sonar -- afuera de esta lista, el conteo de
# MENU_VOICE_INTERVAL queda en pausa (no sigue corriendo de fondo
# mientras estás en una pelea, por ejemplo -- retoma justo donde había
# quedado la próxima vez que vuelvas a alguna de estas pantallas).
# Pedido explícito: "siempre que suene música de la carpeta music,
# deberían sonar aleatoriamente" -- antes esto era una lista aparte,
# mucho más chica, que sólo cubría 4 pantallas (Menú Principal,
# Selección de Personaje, Opciones y su submenú); ahora es EXACTAMENTE
# la misma lista que ya usa la música de menú (MENU_MUSIC_STATES, ver
# arriba) -- así, dondequiera que se agregue o saque una pantalla de
# esa lista en el futuro, las vocecitas la siguen automáticamente, sin
# tener que acordarse de tocar dos lugares.
MENU_VOICE_STATES = MENU_MUSIC_STATES


def pick_random_track(folder, exclude=None):
    """Elige un archivo de audio al azar de una carpeta (para música de
    menú y como respaldo de escenarios sin música propia). Devuelve None
    si la carpeta no existe o está vacía -- no rompe nada.

    'exclude': si se pasa (y hay más de un archivo en la carpeta), ESE
    archivo queda afuera del sorteo -- se usa para que la vocecita de
    menú no repita el mismo audio dos veces seguidas (pedido
    explícito)."""
    if not os.path.isdir(folder):
        return None
    exts = (".wav", ".ogg", ".mp3")
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(exts)]
    if exclude is not None and len(files) > 1:
        files = [f for f in files if f != exclude]
    return random.choice(files) if files else None


def find_music_track(stem):
    """Busca un tema de assets/sounds/music por nombre SIN extensión (en
    la versión de celular los .mp3 se pasaron a .ogg, ver
    tools/prepare_android.py)."""
    for ext in (".ogg", ".mp3", ".wav"):
        path = os.path.join(MUSIC_DIR, stem + ext)
        if os.path.isfile(path):
            return path
    return None


class _IdleInput:
    """Un "control" que nunca aprieta nada (ej. un invitado que se
    desconectó en medio de una pelea del torneo: su luchador se queda
    quieto)."""

    def pressed(self, action):
        return False

    def just_pressed(self, action):
        return False


IDLE_INPUT = _IdleInput()

# Estado actual del loop principal, solo para pruebas automáticas.
DEBUG = {}


def resolve_combat(attacker, defender, sound_manager):
    if attacker.attack_has_hit:
        return
    hitbox = attacker.get_active_hitbox()
    if hitbox is None:
        return
    if hitbox.colliderect(defender.get_hurtbox()):
        damage = attacker.get_damage_for_state()
        # Golpe CRÍTICO: sólo puñetazo y patada (no Especial, no a
        # distancia) -- cada uno tiene CRITICAL_HIT_CHANCE de salir
        # crítico, pegando CRITICAL_HIT_MULT de más y con su propio
        # sonido en vez del golpe normal (ver receive_hit).
        is_critical = (
            attacker.state in (C.STATE_PUNCH, C.STATE_KICK)
            and random.random() < C.CRITICAL_HIT_CHANCE
        )
        if is_critical:
            damage = damage * C.CRITICAL_HIT_MULT
        was_blocking = defender.blocking
        defender.receive_hit(damage, critical=is_critical)
        attacker.attack_has_hit = True
        # El "block" de siempre ya suena adentro de receive_hit si se
        # cubrió -- este sonido extra de "conectó el Especial" es aparte,
        # y solo si NO se cubrió (si no, sonarían los dos pisándose).
        if attacker.state == C.STATE_SPECIAL and not was_blocking:
            sound_manager.play_sfx_fallback(None, "special_hit", volume=1.0)
        if not was_blocking:
            # Voz opcional del que PEGA (ej. un grito al conectar),
            # simétrica a la de "hit" (voz del que RECIBE) -- misma
            # probabilidad baja, mismo criterio: solo si se cubrió no
            # suena ninguna de las dos (bloquear ya tiene su propio sonido).
            attacker._play_character_sound("give_hit", volume=1.0, chance=C.VOICE_LINE_CHANCE, force_chance=True)


def spawn_projectiles(attacker, defender, projectiles):
    launch = attacker.get_ranged_launch()
    if launch:
        proj = Projectile(
            launch["x"], launch["y"], launch["facing"],
            launch["damage"], launch["speed"], launch["image_paths"], launch["owner"],
            trajectory=launch["trajectory"], end_y=launch["end_y"],
            arc_height=launch["arc_height"], arc_range=launch["arc_range"],
            bounce_damping=launch["bounce_damping"], launch_vel_y=launch["launch_vel_y"],
            gravity_mult=launch["gravity_mult"], visual_y_offset=launch["visual_y_offset"],
        )
        proj.loop_channel = None
        cfg = attacker.animations_data.get(C.STATE_RANGED, {})
        if cfg.get("loop_sound"):
            # Suena en loop DESDE que se lanza HASTA que impacta o se va
            # de pantalla (ver update_projectiles) -- ej. las tijeras de
            # Sonia abriéndose/cerrando, o la pelota de Noah picando.
            path = attacker.get_character_sound_path("ranged")
            proj.loop_channel = attacker.sound_manager.play_loop(path, volume=0.8) if path else None
        projectiles.append(proj)


def update_projectiles(projectiles, p1, p2, dt=1 / 60, world_w=None):
    for proj in projectiles[:]:
        proj.update(dt, world_w=world_w)

        if proj.just_bounced:
            # sonido de "pique" propio del personaje (carpeta
            # sounds/projectile_bounce/), o el genérico si no tiene
            if not proj.owner._play_character_sound("projectile_bounce", volume=0.8):
                proj.owner.sound_manager.play_sfx_fallback(None, "projectile_bounce", volume=0.8)

        target = p2 if proj.owner is p1 else p1
        if (
            not target.knocked_out
            and proj.alive
            and proj.get_hitbox().colliderect(target.get_hurtbox())
        ):
            target.receive_hit(proj.damage, knockback=8)
            # el sonido de impacto es del personaje que TIRÓ el proyectil
            # (su celular, su pelota, lo que sea), con respaldo genérico
            if not proj.owner._play_character_sound("projectile_hit"):
                proj.owner.sound_manager.play_sfx_fallback(None, "projectile_hit", volume=0.9)
            proj.alive = False
        if not proj.alive:
            proj.owner.sound_manager.stop_loop(getattr(proj, "loop_channel", None))
            projectiles.remove(proj)


def new_fighters(p1_json, p2_json, sound_manager, stage=None):
    p1 = Character(p1_json, sound_manager)
    p2 = Character(p2_json, sound_manager)
    # Arrancan centrados en el MUNDO (no en la pantalla) -- en un
    # escenario más ancho que 16:9 (ver engine/stage.py) el mundo puede
    # ser más ancho que C.SCREEN_W, y la cámara arranca centrada en ese
    # punto medio, así que conviene que los personajes también arranquen
    # ahí (si no, en un mapa panorámico aparecerían pegados a un
    # costado en vez de en el medio de la pantalla).
    world_w = stage.world_w if stage is not None else C.LOGIC_W
    center = world_w / 2
    gap = C.LOGIC_W * 0.2  # mismo espaciado relativo de siempre (0.3/0.7 de pantalla)
    p1.x, p2.x = center - gap, center + gap
    # encararse desde ya (si no, durante la intro del round -antes de que
    # arranque handle_input()- quedaban los dos mirando para la derecha
    # por el valor default, y recién se corregía al primer input real)
    p1.facing = 1 if p2.x >= p1.x else -1
    p2.facing = 1 if p1.x >= p2.x else -1
    p1.play_voice("intro")
    p2.play_voice("intro")
    # La cámara (si hay escenario panorámico) también arranca centrada,
    # en el mismo punto medio que los personajes -- y esto hay que
    # resetearlo ACÁ, cada vez que arranca una pelea/ronda nueva (no
    # sólo una vez): si no, al pasar de una pelea a la siguiente
    # (revancha, próxima ronda del torneo, etc.) la cámara arrancaba
    # donde había quedado la ANTERIOR en vez de centrada de nuevo (ver
    # update_camera(), que necesita esta posición ya inicializada para
    # frenar a los personajes contra ella desde el primer cuadro).
    if stage is not None:
        stage.camera_x = stage.get_camera_x(center)
    return p1, p2


def start_round_intro(sound_manager, round_number, sudden_death):
    """Arranca el audio de "Round X" (o "Muerte Súbita") y calcula CUÁNDO
    tiene que sonar "FIGHT" después -- a partir de la duración REAL de
    esos clips (ver SoundManager.get_announcer_duration), no de un
    tiempo fijo a ojo. Así, si el día de mañana se reemplaza alguno de
    los audios por uno más largo o más corto, "Round X" y "FIGHT" se
    siguen escuchando bien separados, sin superponerse (bug reportado:
    con audios más largos que los de antes, "FIGHT" arrancaba a sonar
    encima del final de "Round X").

    Devuelve (duración_total_del_intro, segundo_en_que_debe_sonar_FIGHT).
    """
    round_name = "sudden_death" if sudden_death else f"round{round_number}"
    round_dur = sound_manager.get_announcer_duration(round_name)
    sound_manager.play_announcer(round_name)
    fight_dur = sound_manager.get_announcer_duration("fight")
    fight_at = round_dur + ROUND_INTRO_PAUSE
    total = fight_at + fight_dur + ROUND_INTRO_TRAILING_PAD
    fight_threshold = total - fight_at  # "FIGHT" suena cuando a round_intro_timer le queden <= esto
    return total, fight_threshold


def queue_win_audio(clip_names, initial_delay=1.05):
    """Arma una cola de anuncios para reproducir en secuencia después de
    ganar un round o la pelea entera -- ej. ["wins"] (caso normal) o
    ["wins", "flawless"] (ganó sin recibir daño: primero "Wins!", recién
    después "Flawless Victory!", nunca los dos pisados). El primero
    arranca a los 'initial_delay' segundos (tiempo para que termine de
    sonar el nombre del ganador, que ya suena aparte); los siguientes
    esperan la duración REAL del anterior (ver el bloque que consume
    win_audio_queue, más arriba) -- mismo criterio que start_round_intro
    para "Round X"/"FIGHT".

    Devuelve (win_audio_timer, win_audio_queue) para guardar en las
    variables de estado de main()."""
    return initial_delay, list(clip_names)


def win_audio_queue_duration(sound_manager, win_audio_queue, initial_delay=1.05, trailing_pad=0.5):
    """Cuánto tiene que durar como MÍNIMO la pausa de fin de round (el
    cartel de K.O./Empate en pantalla, ver round_end_timer) para que le
    dé tiempo a la cola de queue_win_audio() de terminar de sonar del
    todo -- Nombre -> Wins -> (Flawless Victory, si corresponde) --
    ANTES de que arranque el siguiente round y la corte a la mitad (bug
    reportado: se escuchaba "Flaw..." cortado de golpe). Una victoria
    normal entra de sobra en la pausa de siempre (2.8s); una Flawless
    Victory necesita bastante más, porque sonan DOS anuncios en cadena
    en vez de uno solo."""
    if not win_audio_queue:
        return 0
    total = initial_delay
    for name in win_audio_queue:
        total += sound_manager.get_announcer_duration(name) + WIN_AUDIO_GAP
    return total + trailing_pad


def restart_game(screen=None, ui=None):
    """Relanza el juego como PROCESO NUEVO (mismo intérprete, mismo
    script, mismos argumentos) y termina el actual -- la única forma
    confiable de aplicar un cambio de resolución (C.RESOLUTION), ya que
    un montón de superficies (sprites, HUD, caché de imágenes de menú)
    quedan calculadas para la resolución con la que arrancó el proceso y
    no se pueden recalcular todas "en caliente" sin bugs raros. Se llama
    justo al confirmar/salir de Opciones si la resolución elegida quedó
    distinta de la activa (ver STATE_OPTIONS en main()).

    OJO: usa subprocess.Popen (arrancar un proceso nuevo aparte) y NO
    os.execv (reemplazar el proceso actual) -- en Windows, os.execv
    arma mal la línea de comandos cuando la ruta tiene espacios (pasa
    seguido: "Mortal Kompa V0_XX" tiene espacio) y trunca el path,
    tirando un error de "no such file or directory" al querer relanzar.
    subprocess.Popen sí arma bien la línea de comandos en Windows."""
    if screen is not None and ui is not None:
        # Un cartel breve para que no se sienta como que el juego se
        # colgó justo en el instante entre cerrar este proceso y que el
        # nuevo termine de abrir (arrancar pygame + cargar todo de
        # nuevo tarda un toque).
        screen.fill(C.DARK)
        ui.draw_title(screen, "Reiniciando para aplicar la resolución...", y=C.SCREEN_H // 2)
        pygame.display.flip()
    if getattr(sys, "frozen", False):
        # Corriendo como .exe armado con PyInstaller (ver
        # mortal_kompa.spec) -- acá sys.executable ES el .exe del juego
        # directamente (no un intérprete de Python al que hay que
        # pasarle main.py como argumento), así que hay que relanzarlo
        # distinto que corriendo "python main.py" normal.
        subprocess.Popen([sys.executable] + sys.argv[1:], cwd=os.path.dirname(sys.executable))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__)] + sys.argv[1:],
            cwd=script_dir,
        )
    pygame.quit()
    sys.exit(0)


def apply_display_mode(settings):
    if device.TOUCH_UI:
        # Ventana con el ASPECTO REAL de la pantalla del celular (más
        # ancha que 16:9): el juego se dibuja centrado en su lienzo de
        # siempre y los costados quedan para los controles táctiles (ver
        # main() -> present()).
        size = (C.SCREEN_W, C.SCREEN_H)  # ya tiene el aspecto real de la pantalla (ver C.set_resolution)
        if device.IS_ANDROID:
            return pygame.display.set_mode(size, pygame.FULLSCREEN | pygame.SCALED)
        return pygame.display.set_mode(size, pygame.RESIZABLE | pygame.SCALED)
    if settings.get("fullscreen"):
        try:
            return pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), pygame.FULLSCREEN | pygame.SCALED)
        except pygame.error as e:
            print(f"[AVISO] No se pudo activar pantalla completa ({e}); uso modo ventana.")
            settings["fullscreen"] = False
    # RESIZABLE + SCALED: la ventana se puede agrandar/maximizar a mano
    # (arrastrando el borde o con el botón de maximizar), y pygame
    # escala todo el contenido automáticamente -- el resto del código
    # sigue dibujando siempre sobre la resolución lógica elegida en
    # C.RESOLUTION (ver engine/constants.py), no hace falta cambiar nada
    # más acá.
    return pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), pygame.RESIZABLE | pygame.SCALED)


def draw_arena_background(screen, stage, camera_x=0):
    if stage:
        stage.draw(screen, camera_x)
    else:
        screen.fill((40, 60, 90))
        pygame.draw.rect(screen, (50, 40, 30), (0, C.GROUND_Y, C.SCREEN_W, C.SCREEN_H - C.GROUND_Y))


def compute_camera_x(stage, p1_x, p2_x):
    """Posición X (en píxeles de MUNDO) de la esquina izquierda de la
    ventana de cámara -- 0 si no hay escenario o es 16:9 normal (no hay
    margen para scrollear). Ver Stage.get_camera_x/Stage.world_w."""
    if stage is None:
        return 0
    return stage.get_camera_x((p1_x + p2_x) / 2)


def clamp_fighters_to_camera(camera_x, *fighters):
    """Evita que los personajes salgan de la ventana de cámara actual
    (C.SCREEN_W de ancho) -- en un escenario más ancho que 16:9 (ver
    engine/stage.py), si se separan más de lo que entra en pantalla esto
    los frena antes de salir de cuadro, en vez de dejar que intenten
    mostrar más ancho del que la cámara puede abarcar."""
    margin = C.scaled(20)
    lo, hi = camera_x + margin, camera_x + C.LOGIC_W - margin
    for f in fighters:
        f.clamp_x(lo, hi)


def update_camera(stage, p1, p2):
    """Frena a los dos peleadores DENTRO de la ventana de cámara del
    cuadro ANTERIOR (stage.camera_x, que este mismo método deja
    guardada ahí para la próxima vez) y RECIÉN DESPUÉS calcula la
    cámara nueva a partir de esas posiciones ya frenadas.

    El orden importa: antes se calculaba la cámara nueva primero (a
    partir de las posiciones de este cuadro, que ya podían incluir el
    paso que un jugador acababa de dar) y se frenaba a los personajes
    recién después -- así que un jugador QUIETO se terminaba
    "empujando" igual apenas el OTRO daba un paso lo bastante grande
    hacia un rincón: ese paso, sin frenar todavía, alcanzaba a
    separarlos más de lo que entra en una pantalla, la cuenta de la
    cámara se quedaba sin ningún lugar válido por ese único cuadro, y
    en ese instante puntual el que estaba quieto se corría igual (bug
    reportado, reproducido con un jugador fijo y el otro caminando
    varios cuadros seguidos hacia el borde del mundo).

    Frenando PRIMERO contra la ventana de la cámara YA existente (la
    del cuadro anterior, que por definición ya entraban los dos ahí --
    invariante que este mismo método mantiene siempre), ningún jugador
    puede llegar a separarse del otro más de lo que la pantalla
    permite -- así que al calcular la cámara nueva SIEMPRE hay un lugar
    válido, sin excepción, y el que se quedó quieto nunca se mueve ni
    un píxel."""
    clamp_fighters_to_camera(stage.camera_x, p1, p2)
    stage.camera_x = compute_camera_x(stage, p1.x, p2.x)
    return stage.camera_x


def main():
    # Le pide a SDL que, al estirar la resolución nativa elegida (ver
    # C.RESOLUTION en engine/constants.py -- 720p por defecto desde
    # V.0.41, antes 540p) a la ventana o pantalla completa (más grande,
    # ej. una tele en 1080p/4K), use un filtro SUAVE ("linear") en vez
    # del que usa por default ("nearest", vecino más cercano -- bloques
    # duros, se nota mucho en pantallas grandes tipo tele). Esto es
    # aparte de C.RESOLUTION: agrandar C.RESOLUTION hace que el juego
    # RENDERICE más nítido de entrada (menos trabajo de escalado para
    # SDL); este filtro suaviza lo que quede de estirado hasta el
    # tamaño real de la ventana/tele. No pesa más para la CPU -- el
    # estirado lo hace la placa de video igual, la única diferencia es
    # CÓMO interpola los píxeles de más. Tiene que ir ANTES de
    # pygame.init() para que SDL lo tome.
    os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "1")

    if device.IS_ANDROID:
        # sin esto, SDL además de los eventos FINGER* manda clicks de
        # mouse "de mentira" por cada dedo (se ignoran igual, ver touch.py)
        os.environ.setdefault("SDL_TOUCH_MOUSE_EVENTS", "0")
    pygame.init()
    pygame.joystick.init()
    device.android_setup()
    # Cursor del mouse SIEMPRE oculto -- tanto en pantalla completa como
    # en ventana (pedido explícito) -- el juego se juega con
    # teclado/joystick, así que no hace falta verlo nunca. (En PC con
    # --touch sí se muestra: el mouse hace de dedo.)
    pygame.mouse.set_visible(device.TOUCH_SIM and not device.IS_ANDROID)

    settings = _settings  # ya cargado arriba, antes de fijar C.RESOLUTION (ver comentario)

    # El ícono se carga y se aplica ANTES de crear la ventana (antes de
    # apply_display_mode) a propósito -- pygame.display.set_icon() no
    # necesita .convert_alpha() para funcionar (no hace falta que ya
    # exista una pantalla), y aplicándolo ANTES de que se cree la
    # ventana evita que Windows le muestre al usuario, aunque sea un
    # instante, el ícono genérico de Python en la barra de tareas antes
    # de cambiar al de Mortal Kompa -- se nota más de lo normal
    # reiniciando el juego solo (ver restart_game, al cambiar de
    # resolución), porque ahí se abre una ventana nueva de cero.
    icon_path = os.path.join("assets", "ui", "icon.png")
    if os.path.isfile(icon_path):
        try:
            pygame.display.set_icon(pygame.image.load(icon_path))
        except pygame.error:
            pass

    display = apply_display_mode(settings)
    device.force_landscape()

    # 'screen' es el lienzo del juego (C.SCREEN_W x C.SCREEN_H, 16:9) --
    # todo el juego dibuja ahí como siempre. En PC es directamente la
    # ventana; en la versión táctil es una superficie aparte que después
    # se copia centrada en la pantalla real (más ancha), con los
    # controles táctiles dibujados encima (ver present()).
    touch = None
    if device.TOUCH_UI:
        screen = pygame.Surface((C.SCREEN_W, C.SCREEN_H)).convert()
        game_x = (display.get_width() - C.SCREEN_W) // 2
        touch = TouchControls(display.get_size(), (game_x, 0, C.SCREEN_W, C.SCREEN_H),
                              scale=settings.get("touch_scale", 1.0))
        _input_manager_mod.TOUCH_LABELS = touch_mod.TOUCH_KEY_LABELS
    else:
        screen = display
        game_x = 0

    def present(with_touch=True):
        """Muestra el cuadro: copia el lienzo del juego a la pantalla real
        (si son distintos) y dibuja los controles táctiles encima."""
        if screen is not display:
            if game_x > 0:
                # solo las franjas de los costados (el centro lo tapa el lienzo)
                display.fill((0, 0, 0), (0, 0, game_x, C.SCREEN_H))
                display.fill((0, 0, 0), (game_x + C.SCREEN_W, 0, display.get_width() - game_x - C.SCREEN_W, C.SCREEN_H))
            display.blit(screen, (game_x, 0))
            if touch is not None and with_touch:
                touch.draw(display)
        pygame.display.flip()

    pygame.display.set_caption("Mortal Kompa")
    clock = pygame.time.Clock()
    ui = UI()
    if device.TOUCH_UI:
        ui.show_special_pips = False  # los reemplaza el botón de Especial táctil
        ui.touch_lists = True         # menús con opciones grandes para tocar directo
    # NetSoundManager = SoundManager de siempre, que además puede "grabar"
    # lo que suena para mandárselo a los invitados de una partida WiFi.
    sound_manager = NetSoundManager()
    sound_manager.apply_settings(settings)
    # El tema fijo de apertura ("Mortal_Kompa_Remix") ya NO arranca acá
    # -- ahora lo primero que se ve/escucha es el video de intro (con su
    # propio audio, ver más abajo), y ese tema recién arranca al llegar
    # al menú principal por primera vez (ver STATE_INTRO). Después de
    # una pelea (o volviendo al menú desde cualquier lado) sigue siendo
    # aleatorio como siempre, ver pick_random_track() en el resto del
    # archivo.

    config = load_input_config()
    if auto_assign_joysticks(config):
        save_input_config(config)

    def build_inputs():
        built = build_players_input(config)
        if touch is not None:
            # J1 = pantalla táctil (+ teclado/joystick, que siguen andando)
            built[0] = TouchInput(config["players"][0], touch)
        return built

    inputs = build_inputs()
    last_joystick_count = pygame.joystick.get_count()

    # La intro en video no viene en la versión de celular (pesa mucho) --
    # si el archivo no está, se arranca directo en el menú principal.
    has_intro = os.path.isfile(INTRO_VIDEO_PATH) and not device.IS_ANDROID
    if has_intro:
        state = STATE_INTRO
        intro_player = IntroPlayer()
        if not intro_player.done:
            sound_manager.play_music(os.path.join("assets", "sounds", "intro.mp3"), volume=0.7, loop=False)
    else:
        state = STATE_MODE_MENU
        intro_player = None
        remix_track = find_music_track("Mortal_Kompa_Remix")
        sound_manager.play_music(remix_track or pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
    mode_menu = ModeMenu()
    difficulty_select = None
    char_select = None
    stage_select = None
    options_menu = None
    options_submenu = None
    controls_remap = None
    pause_menu = None
    versus_end_menu = None
    state_before_pause = None
    pause_just_entered = False
    mode_menu_just_entered = False
    frozen_frame = None

    game_mode = C.MODE_VERSUS
    cpu_difficulty = 5
    cpu_input = None

    p1 = p2 = None
    stage = None
    stage_paths = list_stages()
    p1_json = p2_json = None
    options_return_state = STATE_MODE_MENU
    tower = None
    one_player_menu = None
    tower_defeat_menu = None
    tower_result = None
    confetti = None
    multiplayer_menu = None
    tournament_size_select = None
    tournament_char_select = None
    tournament = None
    tournament_bracket_screen = None
    tournament_match = None
    tournament_pending_result = None
    tournament_champion_char = None
    p1_is_random = p2_is_random = False
    projectiles = []
    round_time_left = C.ROUND_TIME
    p1_wins = p2_wins = 0
    round_number = 1
    round_end_timer = 0
    round_intro_timer = 0
    round_intro_fight_played = True  # True hasta que arranque el siguiente intro de round (ver STATE_ROUND_INTRO)
    round_intro_fight_threshold = 0  # a round_intro_timer le tienen que quedar <= esto para que suene "FIGHT" -- ver start_round_intro()
    round_winner = None
    sudden_death = False
    match_winner_text = ""
    win_audio_timer = None
    win_audio_queue = []  # cola de anuncios pendientes (ver queue_win_audio y el bloque que la consume)
    menu_voice_timer = MENU_VOICE_INTERVAL  # ver MENU_VOICE_* más arriba
    last_menu_voice = None  # último audio de menu_voices/ que sonó -- para no repetirlo dos veces seguidas

    # --- Multijugador por WiFi ---
    net_host = None          # NetHost si somos anfitrión
    net_client = None        # NetClient si somos invitado (buscando / conectado)
    host_lobby = None
    join_screen = None
    client_session = None
    net_owners = [0, 0]      # dueño de cada peleador: 0 = este celular, si no, id del invitado
    net_pick_select = None   # CharacterSelect(solo) del anfitrión en el torneo WiFi
    net_host_pick = None
    net_bk_results = []      # ganadores reportados del torneo WiFi (para que los invitados copien el bracket)
    pause_input = None       # quién maneja el menú de pausa / fin de pelea en red
    toast_text = ""          # cartelito temporal (ej. "se desconectó X")
    toast_until = 0.0
    app_paused = False       # Android: app en segundo plano

    def toast(text, seconds=3.5):
        nonlocal toast_text, toast_until
        toast_text = text
        toast_until = pygame.time.get_ticks() / 1000.0 + seconds

    def net_input_for(owner):
        """Entrada que maneja a un peleador según quién es su dueño."""
        if owner == 0 or net_host is None:
            return inputs[0]
        cl = net_host.client_by_id(owner)
        return cl.input if cl else IDLE_INPUT

    def fighter_inputs():
        if game_mode in (MODE_NET_VERSUS, MODE_NET_TOURNAMENT):
            return [net_input_for(net_owners[0]), net_input_for(net_owners[1])]
        return [inputs[0], inputs[1]]

    def remote_fighter_inputs():
        if net_host is None:
            return []
        return [net_host.client_by_id(o).input for o in net_owners
                if o != 0 and net_host.client_by_id(o) is not None]

    def go_net_lobby(message=None):
        nonlocal state, host_lobby, game_mode, projectiles, pause_menu
        sound_manager.stop_all_sfx()
        host_lobby = HostLobby()
        if message:
            host_lobby.flash(message)
        net_host.open = True
        game_mode = C.MODE_VERSUS
        inputs[1] = build_inputs()[1]
        projectiles = []
        pause_menu = None
        sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
        state = STATE_NET_LOBBY

    def close_net_host():
        nonlocal net_host
        if net_host is not None:
            net_host.close()
            net_host = None
        sound_manager.recording = False

    def build_host_snapshot():
        """La "foto" que el anfitrión les manda a los invitados en este
        cuadro (ver engine/netplay.py y ClientSession en net_screens.py)."""
        snap = {
            "ev": sound_manager.recent_events(),
            "mu": sound_manager.music_state,
            "own": list(net_owners),
        }
        fight_like = state in (STATE_ROUND_INTRO, STATE_FIGHT, STATE_ROUND_END, STATE_VERSUS_END) or (
            state == STATE_PAUSED and state_before_pause == STATE_FIGHT
        )
        if state == STATE_NET_LOBBY:
            snap.update(sc="lobby", host=net_host.name,
                        pl=[net_host.name] + [c.name for c in net_host.clients],
                        ids=[0] + [c.id for c in net_host.clients])
        elif state == STATE_CHAR_SELECT and char_select is not None:
            snap.update(sc="cs", cur=list(char_select.cursor), conf=list(char_select.confirmed),
                        ch=list(char_select.choices))
        elif state == STATE_STAGE_SELECT and stage_select is not None:
            snap.update(sc="ss", i=stage_select.index)
        elif state == STATE_NET_PICK:
            snap.update(sc="pick", waiting=[player_label(i + 1) for i, cl in enumerate(net_host.clients) if cl.pick is None]
                        + ([player_label(0)] if net_host_pick is None else []))
        elif fight_like and p1 is not None and p2 is not None:
            if state == STATE_ROUND_INTRO:
                ov = ["center", "MUERTE SÚBITA" if sudden_death else f"ROUND {round_number}", list(C.WHITE)]
            elif state == STATE_ROUND_END:
                ov = ["banner", bool(p1.knocked_out or p2.knocked_out), round_winner is None]
            elif state == STATE_VERSUS_END:
                ov = ["end", versus_end_menu.winner_name, versus_end_menu.index]
            elif state == STATE_PAUSED:
                ov = ["pause", pause_menu.index]
            else:
                ov = None
            snap.update(
                sc="fight",
                stage=stage.image_path if stage else None,
                cam=camera_to_base(stage.camera_x) if stage else 0,
                chars=[p1_json, p2_json],
                f=[fighter_snap(p1), fighter_snap(p2)],
                pr=[projectile_snap(pr) for pr in projectiles],
                hud=[round(max(0, round_time_left), 2), p1_wins, p2_wins],
                ov=ov,
            )
        elif state == STATE_TOURNAMENT_BRACKET and tournament is not None:
            scr = tournament_bracket_screen
            nxt = ""
            m = tournament.current_match()
            if m and scr.phase in ("rising", "ready"):
                nxt = f"Próxima pelea: {m[0]['label']} vs {m[1]['label']}"
            snap.update(sc="bk", bk={
                "seed": [[e["json_path"], e["label"]] for e in tournament.seeded],
                "res": list(net_bk_results),
                "ph": scr.phase,
                "rw": scr.result_winner["label"] if scr.result_winner else None,
                "rl": scr.result_loser["label"] if scr.result_loser else None,
                "next": nxt,
            })
        elif state == STATE_TOURNAMENT_VICTORY and tournament is not None and tournament.champion:
            snap.update(sc="champ", json=tournament.champion["json_path"], label=tournament.champion["label"])
        else:
            snap.update(sc="wait", title="Un momento...", text="El anfitrión está en otra pantalla")
        return snap

    running = True
    while running:
        # OJO: clock.tick() sin límite podía devolver un dt gigante
        # (varios SEGUNDOS) justo después de un cuadro que hizo trabajo
        # pesado de forma sincrónica (ej. decodificar el video de un
        # escenario recién elegido, antes de entrar a STATE_ROUND_INTRO)
        # -- eso hacía que "round_intro_timer -= dt" saltara de golpe
        # mucho más de la cuenta en un solo cuadro, disparando "FIGHT"
        # casi en el mismo instante que "Round X" (bug reportado: se
        # pisaban SOLO en el Round 1 de una pelea nueva, nunca en el
        # Round 2/3 de la misma pelea, porque solo al arrancar una pelea
        # nueva se decodifica un escenario de cero justo antes). Un dt
        # gigante de un solo cuadro también podía hacer que la física
        # "atravesara" cosas en vez de chocarlas. Se lo topea a un
        # máximo razonable (unos 3 cuadros a 60fps) -- de sobra para que
        # ningún cuadro normal se vea afectado, pero sin permitir saltos
        # gigantes tras una pausa/carga real.
        dt = min(clock.tick(C.FPS) / 1000.0, 3.0 / C.FPS)
        keys_pressed = pygame.key.get_pressed()

        # Detección "en caliente": si se conecta/desconecta un control,
        # lo toma solo (reemplaza el teclado, nunca a la CPU si está
        # jugando en ese momento).
        joystick_count_now = pygame.joystick.get_count()
        if joystick_count_now != last_joystick_count:
            last_joystick_count = joystick_count_now
            if auto_assign_joysticks(config):
                save_input_config(config)
                fresh_inputs = build_players_input(config)
                for i in range(len(inputs)):
                    if not isinstance(inputs[i], CPUInput):
                        inputs[i] = fresh_inputs[i]

        # Si terminó la canción de menú (no loopea a propósito) y seguimos
        # en una pantalla de menú, pasa sola a otra al azar -- antes se
        # quedaba repitiendo la misma para siempre.
        #
        # OJO: 'is_music_playing()' da False tanto si no hay nada sonando
        # COMO si la música está en PAUSA (pygame no los distingue) -- así
        # que si entramos a Opciones desde la pausa de una pelea (la
        # música del escenario está pausada, no parada), este chequeo NO
        # debe pisarla con una del menú, o al reanudar la pelea se perdía
        # para siempre (quedaba sonando la de menú en su lugar).
        # Si entramos a Opciones (o a cualquiera de sus sub-pantallas)
        # desde una pelea en pausa, no hay que arrancar música de menú
        # por encima de la música del escenario, que sigue sonando de
        # fondo (pausada) -- por eso este chequeo cubre las 3 pantallas
        # del flujo de Opciones, no solo el hub.
        paused_from_fight = (
            state in (STATE_OPTIONS, STATE_OPTIONS_SUB, STATE_CONTROLS_REMAP)
            and options_return_state == STATE_PAUSED
        )
        if state in MENU_MUSIC_STATES and not sound_manager.is_music_playing() and not paused_from_fight:
            sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)

        # "Nombre" ya sonó al ganar el round (o la pelea entera); a los N
        # segundos arranca esta COLA de anuncios (ver queue_win_audio) --
        # "Wins!" siempre, y si encima fue sin recibir daño, "Flawless
        # Victory!" justo después (nunca los dos juntos/pisados: cada uno
        # espera a que termine el anterior según su duración real).
        if win_audio_timer is not None:
            win_audio_timer -= dt
            if win_audio_timer <= 0:
                if win_audio_queue:
                    name = win_audio_queue.pop(0)
                    sound_manager.play_announcer(name)
                    if win_audio_queue:
                        win_audio_timer = sound_manager.get_announcer_duration(name) + WIN_AUDIO_GAP
                    else:
                        win_audio_timer = None
                else:
                    win_audio_timer = None

        # Vocecitas random de menú (Principal, Selección de Personaje,
        # Ajustes): cada MENU_VOICE_INTERVAL segundos, MENU_VOICE_CHANCE
        # de probabilidad de que suene una al azar de assets/sounds/
        # menu_voices/ -- mismo espíritu que los sonidos random de los
        # personajes, no algo que suene todo el tiempo. Afuera de esas
        # pantallas el conteo queda en pausa (ver MENU_VOICE_STATES).
        if state in MENU_VOICE_STATES:
            menu_voice_timer -= dt
            if menu_voice_timer <= 0:
                menu_voice_timer = MENU_VOICE_INTERVAL
                if random.random() < MENU_VOICE_CHANCE:
                    # 'exclude=last_menu_voice': para que nunca suene el
                    # mismo audio dos veces seguidas (pedido explícito).
                    clip = pick_random_track(MENU_VOICES_DIR, exclude=last_menu_voice)
                    if clip:
                        sound_manager.play(clip)
                        last_menu_voice = clip

        DEBUG["state"] = state
        DEBUG["client_scene"] = client_session.scene if client_session is not None else None
        DEBUG["client_ov"] = ((net_client.snapshot or {}).get("ov") or [None])[0] if (net_client is not None and client_session is not None) else None
        if touch is not None:
            touch.begin_frame()
            touch.set_scale(settings.get("touch_scale", 1.0))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if touch is not None and touch.handle_event(event):
                continue
            # --- Android: la app pasa a segundo plano / vuelve ---
            if event.type in (getattr(pygame, "APP_WILLENTERBACKGROUND", -1), getattr(pygame, "WINDOWFOCUSLOST", -1) if device.IS_ANDROID else -2):
                if not app_paused:
                    app_paused = True
                    sound_manager.pause_music()
                    sound_manager.pause_all_sfx()
                    if touch is not None:
                        touch.release_all()
                    # pelea local (no WiFi): se pausa sola
                    if state == STATE_FIGHT and game_mode not in (MODE_NET_VERSUS, MODE_NET_TOURNAMENT):
                        state_before_pause = STATE_FIGHT
                        pause_menu = PauseMenu()
                        frozen_frame = screen.copy()
                        state = STATE_PAUSED
                        pause_just_entered = True
                continue
            if event.type in (getattr(pygame, "APP_DIDENTERFOREGROUND", -1), getattr(pygame, "WINDOWFOCUSGAINED", -1) if device.IS_ANDROID else -2):
                if app_paused:
                    app_paused = False
                    if state != STATE_PAUSED:
                        sound_manager.unpause_music()
                        sound_manager.unpause_all_sfx()
                continue
            # --- botón "Atrás" de Android (y ESC en PC con --touch) ---
            if event.type == pygame.KEYDOWN and event.key == getattr(pygame, "K_AC_BACK", -1):
                if state == STATE_MODE_MENU:
                    running = False
                elif state in (STATE_FIGHT, STATE_ROUND_INTRO, STATE_ROUND_END) or (state == STATE_NET_CLIENT and touch is not None and touch.mode == touch_mod.MODE_FIGHT):
                    inputs[0].inject("start")
                else:
                    inputs[0].inject("cancel")
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if state in (STATE_MODE_MENU,):
                    running = False
            if state == STATE_INTRO and event.type in (pygame.KEYDOWN, pygame.JOYBUTTONDOWN):
                # Cualquier tecla/botón salta la intro -- a propósito no
                # pasa por el sistema de "acciones" de siempre (no hace
                # falta saber CUÁL tecla, cualquiera sirve para saltar).
                intro_player.done = True
            if state == STATE_CONTROLS_REMAP and controls_remap and controls_remap.waiting:
                if event.type in (pygame.KEYDOWN, pygame.JOYBUTTONDOWN):
                    controls_remap.handle_raw_event(event)

        for i, inp in enumerate(inputs):
            if not isinstance(inp, PlayerInput):
                continue  # CPU / invitado remoto: se actualizan aparte
            inp.update(keys_pressed)

        # Red: recibir lo que mandaron los invitados (o el anfitrión)
        if net_host is not None:
            net_host.poll()
            if net_host.dropped and state != STATE_NET_LOBBY:
                gone = ", ".join(net_host.dropped)
                net_host.dropped = []
                if game_mode == MODE_NET_VERSUS and not any(net_host.client_by_id(o) for o in net_owners if o != 0):
                    go_net_lobby(f"Se desconectó: {gone}")
                elif state in (STATE_NET_PICK,) and not net_host.clients:
                    go_net_lobby(f"Se desconectó: {gone}")
                else:
                    toast(f"Se desconectó: {gone}")

        # Toques directos sobre la pantalla (versión táctil): opciones de
        # lista, caras de la selección de personaje, escenarios...
        taps = touch.taps if touch is not None else []
        tap_handler = {STATE_DIFFICULTY: difficulty_select, STATE_OPTIONS_SUB: options_submenu}.get(state)
        if taps and tap_handler is not None and hasattr(tap_handler, "handle_tap"):
            taps = [pos for pos in taps if not tap_handler.handle_tap(pos)]
        if taps and state in (
            STATE_MODE_MENU, STATE_ONE_PLAYER_MENU, STATE_MULTIPLAYER_MENU, STATE_OPTIONS,
            STATE_OPTIONS_SUB, STATE_PAUSED, STATE_VERSUS_END, STATE_TOWER_DEFEAT, STATE_NET_LOBBY,
        ):
            for pos in taps:
                idx = touch_mod.list_index_at(pos)
                if idx is None:
                    continue
                menu_obj = {
                    STATE_MODE_MENU: mode_menu, STATE_ONE_PLAYER_MENU: one_player_menu,
                    STATE_MULTIPLAYER_MENU: multiplayer_menu, STATE_OPTIONS: options_menu,
                    STATE_OPTIONS_SUB: options_submenu, STATE_PAUSED: pause_menu,
                    STATE_VERSUS_END: versus_end_menu if state == STATE_VERSUS_END else None,
                    STATE_TOWER_DEFEAT: tower_defeat_menu, STATE_NET_LOBBY: host_lobby,
                }.get(state)
                if menu_obj is not None:
                    menu_obj.index = idx
                    inputs[0].inject("confirm")
                break
        if taps and state == STATE_CHAR_SELECT and char_select:
            for pos in taps:
                idx = char_select.hit_test(pos)
                if idx is not None:
                    char_select.apply_tap(0, idx)
        if taps and state == STATE_STAGE_SELECT and stage_select:
            for pos in taps:
                stage_select.apply_tap(stage_select.hit_test(pos))
        if taps and state == STATE_NET_PICK and net_pick_select:
            for pos in taps:
                idx = net_pick_select.hit_test(pos)
                if idx is not None:
                    net_pick_select.apply_tap(0, idx)
        if taps and state == STATE_TOURNAMENT_BRACKET and tournament_bracket_screen and tournament_bracket_screen.phase in ("ready", "result"):
            inputs[0].inject("confirm")
        if taps and state in (STATE_TOURNAMENT_VICTORY, STATE_TOWER_VICTORY, STATE_TOWER_INTRO):
            inputs[0].inject("confirm")
        # toques de los invitados sobre la selección de personaje / menús
        if net_host is not None:
            for cl in net_host.clients:
                slot = net_owners.index(cl.id) if cl.id in net_owners else None
                for idx in cl.input.take_taps("cs"):
                    if state == STATE_CHAR_SELECT and char_select and slot is not None:
                        char_select.apply_tap(slot, idx)
                for idx in cl.input.take_taps("li"):
                    if slot is None:
                        continue
                    if state == STATE_PAUSED and pause_menu:
                        pause_menu.index = idx
                        pause_menu.done = True
                        pause_menu.choice = pause_menu.CHOICES[idx] if idx < len(pause_menu.CHOICES) else None
                    elif state == STATE_VERSUS_END:
                        versus_end_menu.index = idx
                        cl.input._just.add("confirm")

        p2_is_cpu = isinstance(inputs[1], CPUInput)
        if p2_is_cpu and state == STATE_CHAR_SELECT and char_select:
            inputs[1].think_select(dt, len(char_select.characters))
        if p2_is_cpu and state == STATE_FIGHT and p1 and p2:
            inputs[1].think_fight(dt, p2, p1)

        # Pausa: se puede pausar desde la pelea con el jugador humano (slot 0)
        # -- en una partida WiFi, también cualquiera de los dos peleadores
        # desde su celular (y el menú de pausa lo manejan todos ellos).
        net_match = game_mode in (MODE_NET_VERSUS, MODE_NET_TOURNAMENT)
        pausers = [inputs[0]] + (remote_fighter_inputs() if net_match else [])
        if state == STATE_FIGHT and any(i.just_pressed("start") for i in pausers):
            state_before_pause = STATE_FIGHT
            pause_menu = PauseMenu(net=net_match)
            pause_input = CombinedInput(*pausers) if net_match else inputs[0]
            frozen_frame = screen.copy()
            state = STATE_PAUSED
            pause_just_entered = True
            sound_manager.pause_music()
            sound_manager.pause_all_sfx()

        # ------------------------------------------------------------
        if state == STATE_INTRO:
            intro_player.update(dt)
            intro_player.draw(screen)
            # A propósito NO se dibuja ningún pie de página acá -- ni
            # "toque cualquier tecla para saltear" ni nada (pedido
            # explícito: que esos controles queden sin explicar en
            # pantalla).
            if intro_player.done:
                intro_player.close()
                sound_manager.stop_music()  # corta el audio de la intro si seguía sonando (la saltearon a mitad de camino)
                remix_track = find_music_track("Mortal_Kompa_Remix")
                sound_manager.play_music(remix_track or pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
                mode_menu = ModeMenu()
                # La MISMA tecla/botón que saltea la intro (ver el
                # bloque de eventos, más arriba) también queda marcada
                # como "recién apretada" para inputs[0] en este mismo
                # cuadro -- sin este freno, el menú la vuelve a
                # interpretar como un "confirmar" propio y entra directo
                # a la primera opción resaltada (bug reportado: saltear
                # con J terminaba entrando a "1 Jugador" solo). Mismo
                # truco que ya se usa al entrar a Pausa (pause_just_entered).
                mode_menu_just_entered = True
                state = STATE_MODE_MENU

        # ------------------------------------------------------------
        elif state == STATE_MODE_MENU:
            if mode_menu_just_entered:
                mode_menu_just_entered = False
            else:
                mode_menu.update(inputs[0])
            mode_menu.draw(screen, ui, dt)
            if mode_menu.replay_intro and not has_intro:
                mode_menu.replay_intro = False
            elif mode_menu.replay_intro:
                intro_player = IntroPlayer()
                if not intro_player.done:
                    sound_manager.stop_music()
                    sound_manager.play_music(os.path.join("assets", "sounds", "intro.mp3"), volume=0.7, loop=False)
                    state = STATE_INTRO
                else:
                    mode_menu.replay_intro = False  # no hay video para mostrar, seguir como si nada
            elif mode_menu.done:
                if mode_menu.choice == "one_player":
                    one_player_menu = OnePlayerMenu()
                    state = STATE_ONE_PLAYER_MENU
                elif mode_menu.choice == "multiplayer":
                    multiplayer_menu = MultiplayerMenu()
                    state = STATE_MULTIPLAYER_MENU
                elif mode_menu.choice == "options":
                    options_menu = OptionsMenu()
                    options_return_state = STATE_MODE_MENU
                    state = STATE_OPTIONS
                mode_menu = ModeMenu()

        elif state == STATE_MULTIPLAYER_MENU:
            multiplayer_menu.update(inputs[0])
            multiplayer_menu.draw(screen, ui, dt)
            if multiplayer_menu.cancelled:
                state = STATE_MODE_MENU
            elif multiplayer_menu.done:
                if multiplayer_menu.choice == "host":
                    try:
                        net_host = NetHost(device.device_name())
                    except OSError as e:
                        net_host = None
                        toast(f"No se pudo crear la partida: {e}")
                    if net_host is not None:
                        sound_manager.recording = True
                        go_net_lobby()
                elif multiplayer_menu.choice == "join":
                    try:
                        net_client = NetClient(device.device_name())
                        join_screen = JoinScreen(net_client)
                        state = STATE_NET_JOIN
                    except OSError as e:
                        net_client = None
                        toast(f"No se pudo usar la red: {e}")
                elif multiplayer_menu.choice == "versus":
                    game_mode = C.MODE_VERSUS
                    inputs[1] = build_players_input(config)[1]
                    char_select = CharacterSelect(p2_is_cpu=False)
                    state = STATE_CHAR_SELECT
                elif multiplayer_menu.choice == "tournament":
                    tournament_size_select = TournamentSizeSelect()
                    state = STATE_TOURNAMENT_SIZE
                else:
                    state = STATE_MODE_MENU
                multiplayer_menu = MultiplayerMenu()

        # ------------------------------------------------------------
        # Multijugador WiFi
        # ------------------------------------------------------------
        elif state == STATE_NET_LOBBY:
            host_lobby.update(inputs[0], net_host)
            host_lobby.draw(screen, ui, net_host, dt)
            if host_lobby.done:
                if host_lobby.choice == "close":
                    close_net_host()
                    multiplayer_menu = MultiplayerMenu()
                    state = STATE_MULTIPLAYER_MENU
                elif host_lobby.choice == "versus":
                    opponent = net_host.clients[0]
                    net_owners = [0, opponent.id]
                    net_host.open = False
                    game_mode = MODE_NET_VERSUS
                    inputs[1] = opponent.input
                    opponent.input.clear()
                    char_select = CharacterSelect(p2_is_cpu=False)
                    state = STATE_CHAR_SELECT
                elif host_lobby.choice == "tournament":
                    net_host.open = False
                    for cl in net_host.clients:
                        cl.pick = None
                    net_pick_select = CharacterSelect(solo=True)
                    net_host_pick = None
                    net_owners = [0, 0]
                    state = STATE_NET_PICK
                    host_lobby = HostLobby()

        elif state == STATE_NET_PICK:
            if net_host_pick is None:
                net_pick_select.update([inputs[0], inputs[0]], dt)
                if net_pick_select.cancelled:
                    go_net_lobby()
                elif net_pick_select.done:
                    net_host_pick = net_pick_select.choices[0]
                    if net_host_pick != RANDOM_SENTINEL:
                        slug = os.path.splitext(os.path.basename(net_host_pick))[0]
                        sound_manager.play(os.path.join("assets", "sounds", "announcer", "select", f"{slug}.wav"), volume=0.9)
            if state == STATE_NET_PICK:
                if net_host_pick is None:
                    net_pick_select.draw(screen, ui)
                else:
                    ui.draw_screen_background(screen, ui.character_selection_background)
                    ui.draw_center_text(screen, "¡Listo!", C.YELLOW)
                    waiting = [player_label(i + 1) for i, cl in enumerate(net_host.clients) if cl.pick is None]
                    ui.draw_small_center(screen, ("Esperando a: " + ", ".join(waiting)) if waiting else "Armando el torneo...", C.SCREEN_H // 2 + C.scaled(60))
                if net_host_pick is not None and all(cl.pick is not None for cl in net_host.clients):
                    all_chars = load_character_list()
                    by_json = {c["json_path"]: c for c in all_chars}
                    picks = []
                    owners = [(0, net_host_pick)] + [(cl.id, cl.pick) for cl in net_host.clients]
                    for n, (owner, choice) in enumerate(owners):
                        entry = by_json.get(choice) or random.choice(all_chars)
                        picks.append({**entry, "owner": owner, "label": f"{entry['name']} · {player_label(n)}"})
                    tournament = TournamentBracket(picks)
                    net_bk_results = []
                    tournament_bracket_screen = TournamentBracketScreen(tournament)
                    game_mode = MODE_NET_TOURNAMENT
                    state = STATE_TOURNAMENT_BRACKET

        elif state == STATE_NET_JOIN:
            net_client.poll()
            join_screen.update(inputs[0], taps)
            join_screen.draw(screen, ui, dt)
            if join_screen.cancelled:
                net_client.close()
                net_client = None
                multiplayer_menu = MultiplayerMenu()
                state = STATE_MULTIPLAYER_MENU
            elif join_screen.done:
                sound_manager.stop_music()
                client_session = ClientSession(net_client, sound_manager)
                state = STATE_NET_CLIENT

        elif state == STATE_NET_CLIENT:
            client_session.update(dt, inputs[0], taps)
            if not client_session.finished:
                loading = client_session.needs_loading(net_client.snapshot)
                if loading:
                    ui.draw_loading_screen(screen, loading)
                    present(with_touch=False)
                    client_session.preload(net_client.snapshot)
                client_session.draw(screen, ui, dt)
                if touch is not None:
                    touch.special_charge = client_session.special_charge()
                DEBUG["my_facing"] = client_session.my_facing()
            if client_session.finished:
                msg = client_session.end_message
                client_session = None
                net_client = None
                sound_manager.stop_all_sfx()
                sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
                multiplayer_menu = MultiplayerMenu()
                state = STATE_MULTIPLAYER_MENU
                if msg:
                    toast(msg)

        elif state == STATE_TOURNAMENT_SIZE:
            tournament_size_select.update(inputs[0])
            tournament_size_select.draw(screen, ui)
            if tournament_size_select.cancelled:
                state = STATE_MULTIPLAYER_MENU
            elif tournament_size_select.done:
                tournament_char_select = TournamentCharacterSelect(tournament_size_select.count)
                state = STATE_TOURNAMENT_CHAR_SELECT

        elif state == STATE_TOURNAMENT_CHAR_SELECT:
            prev_pick_count = len(tournament_char_select.picks)
            tournament_char_select.update(inputs[0])
            tournament_char_select.draw(screen, ui)
            if len(tournament_char_select.picks) > prev_pick_count:
                # Anuncia el nombre BASE siempre (aunque el "Personajes
                # elegidos" de al lado ya diga "Ana 4", el locutor sigue
                # diciendo "Ana" a secas -- no existe un audio "Ana 4.wav").
                chosen = tournament_char_select.picks[-1]
                slug = os.path.splitext(os.path.basename(chosen["json_path"]))[0]
                sound_manager.play(os.path.join("assets", "sounds", "announcer", "select", f"{slug}.wav"), volume=0.9)
            if tournament_char_select.cancelled:
                tournament_size_select = TournamentSizeSelect()
                state = STATE_TOURNAMENT_SIZE
            elif tournament_char_select.done:
                tournament = TournamentBracket(tournament_char_select.picks)
                tournament_bracket_screen = TournamentBracketScreen(tournament)
                game_mode = C.MODE_TOURNAMENT
                state = STATE_TOURNAMENT_BRACKET

        elif state == STATE_TOURNAMENT_BRACKET:
            bracket_input = inputs[0]
            if game_mode == MODE_NET_TOURNAMENT:
                upcoming = tournament.current_match()
                if upcoming:
                    owners_next = [e.get("owner", 0) for e in upcoming]
                    remotes_next = [net_host.client_by_id(o).input for o in owners_next
                                    if o != 0 and net_host.client_by_id(o)]
                    bracket_input = CombinedInput(inputs[0], *remotes_next)
                    # alguien se desconectó antes de su pelea: pierde por abandono
                    missing = [o != 0 and net_host.client_by_id(o) is None for o in owners_next]
                    if tournament_bracket_screen.phase == "ready" and any(missing):
                        w_idx = 1 if missing[0] else 0
                        tournament_pending_result = (upcoming[w_idx], upcoming[1 - w_idx])
                        if tournament.is_final_match():
                            tournament.report_result(upcoming[w_idx])
                            net_bk_results.append(upcoming[w_idx]["label"])
                            confetti = Confetti()
                            tournament_champion_char = Character(upcoming[w_idx]["json_path"], sound_manager)
                            tournament_champion_char.set_state(C.STATE_WIN, force=True)
                            tournament_champion_char.x, tournament_champion_char.y = C.LOGIC_W // 2, C.GROUND_Y
                            state = STATE_TOURNAMENT_VICTORY
                        else:
                            tournament_bracket_screen.show_result(upcoming[w_idx], upcoming[1 - w_idx])
                        toast("Ganó por abandono del rival")
            tournament_bracket_screen.update(dt, bracket_input)
            tournament_bracket_screen.draw(screen, ui)
            if state != STATE_TOURNAMENT_BRACKET:
                pass
            elif tournament_bracket_screen.phase == "ready" and bracket_input.just_pressed("confirm"):
                match = tournament.current_match()
                tournament_match = match
                p1_json = match[0]["json_path"]
                p2_json = match[1]["json_path"]
                if game_mode == MODE_NET_TOURNAMENT:
                    net_owners = [match[0].get("owner", 0), match[1].get("owner", 0)]
                else:
                    inputs[1] = build_players_input(config)[1]
                if tournament.is_final_match():
                    # la final del torneo siempre es en Final Destination,
                    # igual que la pelea contra el jefe final de la Torre
                    stage_path = get_secret_stage() or (random.choice(stage_paths) if stage_paths else None)
                else:
                    stage_path = random.choice(stage_paths) if stage_paths else None
                ui.draw_loading_screen(screen)
                present(with_touch=False)
                stage = Stage(stage_path) if stage_path else None
                music = stage.music_path if stage else None
                if music:
                    sound_manager.play_music(music, category="stage")
                elif not sound_manager.is_music_playing():
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), category="stage")
                p1, p2 = new_fighters(p1_json, p2_json, sound_manager, stage=stage)
                p1_is_random = p2_is_random = False
                projectiles = []
                p1_wins = p2_wins = 0
                round_number = 1
                sudden_death = False
                round_time_left = C.ROUND_TIME
                sound_manager.stop_all_sfx()  # corta cualquier audio colgado (ej. "X avanza" del bracket) antes de que arranque "Round 1"
                round_intro_timer, round_intro_fight_threshold = start_round_intro(sound_manager, round_number, sudden_death)
                round_intro_fight_played = False
                state = STATE_ROUND_INTRO
            elif tournament_bracket_screen.phase == "result_done":
                winner_entrant, loser_entrant = tournament_pending_result
                finished = tournament.report_result(winner_entrant)
                net_bk_results.append(winner_entrant["label"])
                if finished:
                    confetti = Confetti()
                    tournament_champion_char.x = C.LOGIC_W // 2  # centrado, ver pedido explícito
                    state = STATE_TOURNAMENT_VICTORY
                else:
                    tournament_bracket_screen.start_new_match()

        elif state == STATE_TOURNAMENT_VICTORY:
            confetti.update(dt)
            tournament_champion_char.animations[C.STATE_WIN].update(dt)
            screen.fill(C.DARK)
            tournament_champion_char.draw(screen)
            confetti.draw(screen)
            # Pedido explícito: sacar el fondo gris pleno que iba acá
            # atrás (pygame.draw.rect con C.DARK, franja completa de
            # arriba) -- tapaba cuadros de la pose WIN cuando el
            # personaje festeja con los brazos bien arriba, ya que el
            # personaje se dibuja ANTES que esa franja. El título solo
            # (sin panel opaco detrás) ya se lee bien, igual que en
            # "RONDA 1"/"FINAL" del bracket.
            champ_label = tournament.champion["label"] if (game_mode == MODE_NET_TOURNAMENT and tournament.champion) else tournament_champion_char.name
            ui.draw_title(screen, f"¡{champ_label.upper()} GANA EL TORNEO!", y=C.scaled(60), color=C.YELLOW)
            ui.draw_footer_mixed(screen, build_footer_parts(config, [("confirm", "continuar")]), C.SCREEN_H - C.scaled(30))
            if inputs[0].just_pressed("confirm"):
                sound_manager.stop_all_sfx()
                if game_mode == MODE_NET_TOURNAMENT:
                    go_net_lobby()
                else:
                    state = STATE_MODE_MENU

        elif state == STATE_ONE_PLAYER_MENU:
            one_player_menu.update(inputs[0])
            one_player_menu.draw(screen, ui, dt)
            if one_player_menu.cancelled:
                state = STATE_MODE_MENU
            elif one_player_menu.done:
                if one_player_menu.choice == "cpu":
                    game_mode = C.MODE_CPU
                    difficulty_select = DifficultySelect()
                    state = STATE_DIFFICULTY
                elif one_player_menu.choice == "tower":
                    game_mode = C.MODE_TOWER
                    difficulty_select = DifficultySelect()
                    state = STATE_DIFFICULTY
                else:
                    state = STATE_MODE_MENU

        elif state == STATE_DIFFICULTY:
            difficulty_select.update(inputs[0])
            difficulty_select.draw(screen, ui)
            if difficulty_select.cancelled:
                # Objeto NUEVO, no el viejo -- el de antes ya tenía
                # ".done = True" desde que se lo eligió para LLEGAR
                # hasta acá (con "cpu"/"tower" en .choice), y esa bandera
                # nunca se resetea sola. Si se reutilizara tal cual,
                # STATE_ONE_PLAYER_MENU la vería en True apenas se entra
                # (antes de procesar ningún input nuevo) y rebotaría
                # directo de vuelta para acá en el mismo instante -- eso
                # era el "titileo" reportado al intentar volver.
                one_player_menu = OnePlayerMenu()
                state = STATE_ONE_PLAYER_MENU
            elif difficulty_select.done:
                cpu_difficulty = difficulty_select.level
                if game_mode == C.MODE_TOWER:
                    char_select = CharacterSelect(solo=True)
                else:
                    inputs[1] = CPUInput(cpu_difficulty)
                    char_select = CharacterSelect(p2_is_cpu=True)
                state = STATE_CHAR_SELECT

        elif state == STATE_OPTIONS:
            options_menu.update(inputs[0])
            options_menu.draw(screen, ui)
            if options_menu.done:
                if options_menu.choice is None:
                    state = options_return_state
                else:
                    rows, title = OPTIONS_CATEGORIES[options_menu.choice]
                    options_submenu = OptionsSubMenu(settings, rows, title)
                    state = STATE_OPTIONS_SUB

        elif state == STATE_OPTIONS_SUB:
            options_submenu.update(inputs[0])
            options_submenu.draw(screen, ui)
            if options_submenu.fullscreen_changed:
                if not device.TOUCH_UI:
                    display = apply_display_mode(settings)
                    screen = display
                options_submenu.fullscreen_changed = False
            sound_manager.apply_settings(settings)
            if options_submenu.open_controls_player is not None:
                controls_remap = ControlsRemapMenu(config, initial_player=options_submenu.open_controls_player)
                state = STATE_CONTROLS_REMAP
                options_submenu.open_controls_player = None
            elif options_submenu.done:
                save_settings(settings)
                if settings.get("resolution", C.RESOLUTION) != C.RESOLUTION and not device.TOUCH_UI:
                    restart_game(screen, ui)  # no vuelve de acá -- reemplaza el proceso
                options_menu = OptionsMenu()  # vuelve al hub, no al juego -- ver options_return_state para eso
                state = STATE_OPTIONS

        elif state == STATE_CONTROLS_REMAP:
            controls_remap.update(inputs[0])
            controls_remap.draw(screen, ui)
            if controls_remap.done:
                inputs = build_inputs()
                state = STATE_OPTIONS_SUB

        elif state == STATE_CHAR_SELECT:
            # lo ya anunciado se guarda en el propio select: los toques
            # confirman ANTES de llegar acá (ver taps más arriba), así que
            # comparar contra el estado de este mismo cuadro no alcanza
            prev_confirmed = getattr(char_select, "_announced", [False, False])
            real_inputs = [inputs[0], inputs[1]]
            char_select.update(real_inputs, dt)
            char_select.draw(screen, ui)
            for p_idx in (0, 1):
                if char_select.confirmed[p_idx] and not prev_confirmed[p_idx]:
                    chosen = char_select.choices[p_idx]
                    # si eligió "Aleatorio", no decimos el nombre -- arruinaría la sorpresa
                    if chosen and chosen != RANDOM_SENTINEL:
                        slug = os.path.splitext(os.path.basename(chosen))[0]
                        sound_manager.play(os.path.join("assets", "sounds", "announcer", "select", f"{slug}.wav"), volume=0.9)
            char_select._announced = list(char_select.confirmed)
            if char_select.cancelled:
                if game_mode == MODE_NET_VERSUS:
                    go_net_lobby()
                else:
                    state = STATE_MODE_MENU
            elif char_select.done:
                real_choices = [c["json_path"] for c in char_select.characters if c["json_path"] != RANDOM_SENTINEL]
                p1_json = char_select.choices[0]
                p1_is_random = p1_json == RANDOM_SENTINEL
                if p1_is_random:
                    p1_json = random.choice(real_choices)

                if game_mode == C.MODE_TOWER:
                    all_chars = load_character_list()
                    player_entry = next(c for c in all_chars if c["json_path"] == p1_json)
                    opponents = build_opponent_order(all_chars, p1_json)
                    final_boss = build_final_boss_entry(all_chars, p1_json)
                    tower = TowerLadder(player_entry, opponents, cpu_difficulty, final_boss_entry=final_boss)
                    state = STATE_TOWER_INTRO
                else:
                    p2_json = char_select.choices[1]
                    p2_is_random = p2_json == RANDOM_SENTINEL
                    if p2_is_random:
                        p2_json = random.choice(real_choices)
                    stage_select = StageSelect(stage_paths)
                    state = STATE_STAGE_SELECT

        elif state == STATE_TOWER_INTRO:
            tower.update(dt)
            tower.draw(screen, ui, char_select)
            if tower.anim_done and inputs[0].just_pressed("confirm"):
                p2_json = tower.current_opponent["json_path"]
                p2_is_random = False
                inputs[1] = CPUInput(tower.difficulty)
                # Cartel de carga ANTES de decodificar el escenario (unas
                # décimas de segundo a un par de segundos según el
                # escenario que toque) -- si no, quedaba una pantalla
                # congelada sin ningún indicio de que está pasando algo
                # (bug reportado: "tarda mucho... y no se ve nada").
                ui.draw_loading_screen(screen)
                present(with_touch=False)
                if tower.fighting_final_boss:
                    # la pelea final de la Torre siempre ocurre en el
                    # escenario secreto, no en uno al azar
                    tower_stage_path = get_secret_stage() or (random.choice(stage_paths) if stage_paths else None)
                else:
                    tower_stage_path = random.choice(stage_paths) if stage_paths else None
                stage = Stage(tower_stage_path) if tower_stage_path else None
                music = stage.music_path if stage else None
                if music:
                    sound_manager.play_music(music, category="stage")
                elif not sound_manager.is_music_playing():
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), category="stage")
                p1, p2 = new_fighters(p1_json, p2_json, sound_manager, stage=stage)
                if p1_is_random:
                    p1.enter_mystery()
                if tower.fighting_final_boss:
                    # el jefe final: pelea con sus animaciones/golpes reales,
                    # pero se ve y se llama disfrazado toda la pelea (nunca
                    # se revela, a diferencia del "Aleatorio" del jugador)
                    p2.mystery = True
                    p2.name = tower.current_opponent["name"]
                projectiles = []
                p1_wins = p2_wins = 0
                round_number = 1
                sudden_death = False
                round_time_left = C.ROUND_TIME
                # corta cualquier audio que haya quedado sonando (la voz
                # de "Wins" de la selección de personaje, por ejemplo) --
                # si no, se pisaba con el "Round 1" de acá abajo.
                sound_manager.stop_all_sfx()
                round_intro_timer, round_intro_fight_threshold = start_round_intro(sound_manager, round_number, sudden_death)
                round_intro_fight_played = False
                state = STATE_ROUND_INTRO

        elif state == STATE_STAGE_SELECT:
            stage_select.update(inputs[0], dt)
            stage_select.draw(screen, ui)
            if stage_select.cancelled:
                char_select = CharacterSelect(p2_is_cpu=isinstance(inputs[1], CPUInput))
                state = STATE_CHAR_SELECT
            elif stage_select.done:
                chosen_path = stage_select.choice
                if chosen_path == STAGE_RANDOM_SENTINEL:
                    # el mismo "stage_paths" que ve el selector (sin el
                    # secreto, ver list_stages) es el pool del sorteo --
                    # así "Aleatorio" nunca termina llevando sin querer
                    # al escenario secreto, que se guarda para quien
                    # sepa el gesto de Smash Bros a propósito.
                    chosen_path = random.choice(stage_paths) if stage_paths else None
                # Mismo cartel de carga que en la Torre -- acá es donde
                # se decodifica el video ANIMADO completo por primera vez
                # (el selector solo usaba una miniatura de un cuadro, ver
                # load_stage_thumbnail en engine/stage.py).
                ui.draw_loading_screen(screen)
                present(with_touch=False)
                stage = Stage(chosen_path) if chosen_path else None
                music = stage.music_path if stage else None
                if music:
                    sound_manager.play_music(music, category="stage")
                elif not sound_manager.is_music_playing():
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), category="stage")
                # si el escenario no tiene música propia Y ya está sonando
                # algo de la playlist, lo dejamos seguir en vez de cambiar
                p1, p2 = new_fighters(p1_json, p2_json, sound_manager, stage=stage)
                if p1_is_random:
                    p1.enter_mystery()
                if p2_is_random:
                    p2.enter_mystery()
                projectiles = []
                p1_wins = p2_wins = 0
                round_number = 1
                sudden_death = False
                round_time_left = C.ROUND_TIME
                # corta cualquier audio que haya quedado sonando (la voz
                # de "Wins" de la selección de personaje, por ejemplo) --
                # si no, se pisaba con el "Round 1" de acá abajo.
                sound_manager.stop_all_sfx()
                round_intro_timer, round_intro_fight_threshold = start_round_intro(sound_manager, round_number, sudden_death)
                round_intro_fight_played = False
                state = STATE_ROUND_INTRO

        elif state == STATE_ROUND_INTRO:
            if stage:
                stage.update(dt)
            camera_x = update_camera(stage, p1, p2)
            draw_arena_background(screen, stage, camera_x)
            p1.draw(screen, camera_x)
            p2.draw(screen, camera_x)
            ui.draw_hud(screen, p1, p2, round_time_left, p1_wins, p2_wins)
            ui.draw_center_text(screen, "MUERTE SÚBITA" if sudden_death else f"ROUND {round_number}", C.WHITE)

            round_intro_timer -= dt
            if not round_intro_fight_played and round_intro_timer <= round_intro_fight_threshold:
                sound_manager.play_announcer("fight")
                round_intro_fight_played = True
            if round_intro_timer <= 0:
                p1.reveal()
                if not (game_mode == C.MODE_TOWER and tower.fighting_final_boss):
                    p2.reveal()
                state = STATE_FIGHT

        elif state == STATE_FIGHT:
            round_time_left -= dt

            fi = fighter_inputs()
            p1.handle_input(fi[0], p2.x)
            p2.handle_input(fi[1], p1.x)
            p1.physics_update(dt)
            p2.physics_update(dt)

            camera_x = update_camera(stage, p1, p2)

            resolve_combat(p1, p2, sound_manager)
            resolve_combat(p2, p1, sound_manager)
            spawn_projectiles(p1, p2, projectiles)
            spawn_projectiles(p2, p1, projectiles)
            update_projectiles(projectiles, p1, p2, dt, world_w=stage.world_w if stage else None)

            if stage:
                stage.update(dt)
            draw_arena_background(screen, stage, camera_x)
            p1.draw(screen, camera_x)
            p2.draw(screen, camera_x)
            for proj in projectiles:
                proj.draw(screen, camera_x)
            ui.draw_hud(screen, p1, p2, round_time_left, p1_wins, p2_wins)

            time_up = round_time_left <= 0
            someone_ko = p1.knocked_out or p2.knocked_out
            if time_up or someone_ko:
                round_winner = None
                if p1.knocked_out and not p2.knocked_out:
                    p2_wins += 1
                    round_winner = p2
                elif p2.knocked_out and not p1.knocked_out:
                    p1_wins += 1
                    round_winner = p1
                else:
                    if p1.health > p2.health:
                        p1_wins += 1
                        round_winner = p1
                    elif p2.health > p1.health:
                        p2_wins += 1
                        round_winner = p2
                if round_winner:
                    round_winner.set_state(C.STATE_WIN, force=True)
                    winner_slug = os.path.splitext(
                        os.path.basename(p1_json if round_winner is p1 else p2_json)
                    )[0]
                    # "Nombre" al toque, y 1.05s después "Wins!" -- y si
                    # no perdió ni un punto de vida en todo el round,
                    # justo a continuación "Flawless Victory!" también
                    # (orden: Nombre -> Wins -> Flawless Victory). MISMA
                    # cola que al ganar la pelea entera (ver
                    # STATE_ROUND_END más abajo), pero acá suena al final
                    # de CADA round individual.
                    sound_manager.play(
                        os.path.join("assets", "sounds", "announcer", "select", f"{winner_slug}.wav"),
                        volume=1.0,
                    )
                    if round_winner.health >= round_winner.max_health:
                        # ni un solo punto de vida perdido en todo el round
                        # (ni golpes conectados, ni chip damage bloqueando)
                        win_audio_timer, win_audio_queue = queue_win_audio(["wins", "flawless"])
                    else:
                        win_audio_timer, win_audio_queue = queue_win_audio(["wins"])
                else:
                    sound_manager.play_announcer("draw")
                    win_audio_queue = []
                projectiles = []
                # 2.8s de siempre, salvo que la cola de audio (Nombre ->
                # Wins -> Flawless Victory) necesite más para terminar de
                # sonar entera -- si no, "Flawless Victory" quedaba
                # cortado a la mitad cuando arrancaba el siguiente round.
                round_end_timer = max(2.8, win_audio_queue_duration(sound_manager, win_audio_queue))
                state = STATE_ROUND_END

        elif state == STATE_ROUND_END:
            if stage:
                stage.update(dt)
            p1.physics_update(dt)
            p2.physics_update(dt)
            camera_x = update_camera(stage, p1, p2)
            draw_arena_background(screen, stage, camera_x)
            p1.draw(screen, camera_x)
            p2.draw(screen, camera_x)
            ui.draw_hud(screen, p1, p2, max(0, round_time_left), p1_wins, p2_wins)
            ui.draw_round_end_banner(screen, is_ko=(p1.knocked_out or p2.knocked_out), is_draw=(round_winner is None))

            round_end_timer -= dt
            if round_end_timer <= 0:
                if p1_wins >= C.ROUNDS_TO_WIN or p2_wins >= C.ROUNDS_TO_WIN:
                    winner_char = p1 if p1_wins > p2_wins else p2
                    winner_json = p1_json if winner_char is p1 else p2_json
                    match_winner_text = f"¡{winner_char.name.upper()} GANA LA PELEA!"
                    winner_char.play_win_voice()
                    winner_slug = os.path.splitext(os.path.basename(winner_json))[0]
                    # reutiliza el MISMO audio del nombre que ya suena al elegir
                    # personaje (no hace falta grabar "Ana" Y "Ana wins" aparte)
                    sound_manager.play(os.path.join("assets", "sounds", "announcer", "select", f"{winner_slug}.wav"), volume=1.0)
                    win_audio_timer, win_audio_queue = queue_win_audio(["wins"])  # el de fin de PELEA siempre es solo "Wins!" (el "Flawless" es por round, ver STATE_FIGHT)
                    # cortar la música del escenario (todavía sonando, loopeando) y
                    # pasar a la de menú, SIEMPRE -- antes solo lo hacía si no sonaba
                    # nada, pero la del escenario sigue activa en este momento
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)

                    if game_mode in (C.MODE_VERSUS, MODE_NET_VERSUS):
                        winner_char.set_state(C.STATE_WIN, force=True)
                        versus_end_menu = VersusEndMenu(winner_char.name, net=(game_mode == MODE_NET_VERSUS))
                        state = STATE_VERSUS_END
                    elif game_mode == C.MODE_TOWER:
                        if winner_char is p1:
                            has_more = tower.register_win()
                            tower_result = "advance" if has_more else "cleared"
                            state = STATE_MATCH_END
                        else:
                            tower_result = "defeat"
                            tower_defeat_menu = TowerDefeatMenu(tower.floor, tower.total_floors)
                            state = STATE_TOWER_DEFEAT
                    elif game_mode in (C.MODE_TOURNAMENT, MODE_NET_TOURNAMENT):
                        winner_char.set_state(C.STATE_WIN, force=True)
                        winner_entrant = tournament_match[0] if winner_char is p1 else tournament_match[1]
                        loser_entrant = tournament_match[1] if winner_char is p1 else tournament_match[0]
                        if tournament.is_final_match():
                            # Directo a "X GANA EL TORNEO" -- sin el
                            # cartelito de "avanza" de en medio, que no
                            # tiene sentido para la última pelea (no hay
                            # ningún "próximo cruce" al que avanzar).
                            tournament.report_result(winner_entrant)
                            net_bk_results.append(winner_entrant["label"])
                            confetti = Confetti()
                            tournament_champion_char = winner_char
                            tournament_champion_char.x = C.LOGIC_W // 2  # centrado, ver pedido explícito
                            state = STATE_TOURNAMENT_VICTORY
                        else:
                            tournament_pending_result = (winner_entrant, loser_entrant)
                            tournament_bracket_screen.show_result(winner_entrant, loser_entrant)
                            state = STATE_TOURNAMENT_BRACKET
                    else:
                        state = STATE_MATCH_END
                    round_end_timer = 4
                else:
                    # corta cualquier audio que haya quedado sonando del
                    # round recién terminado (la voz de "Win" del
                    # personaje, o el "Nombre... Wins!" de más abajo) --
                    # si no, se pisaba con el "Round X" del round que
                    # arranca ahora (bug reportado: "no se llega a
                    # escuchar el 1" de "Round 1").
                    sound_manager.stop_all_sfx()
                    round_number += 1
                    round_time_left = C.ROUND_TIME
                    p1, p2 = new_fighters(p1_json, p2_json, sound_manager, stage=stage)
                    if p1_is_random:
                        p1.enter_mystery()
                    if game_mode == C.MODE_TOWER and tower.fighting_final_boss:
                        # new_fighters() crea personajes NUEVOS para cada
                        # round (vida/posición de cero) -- el disfraz del
                        # jefe final no sobrevive esa recreación solo, hay
                        # que volver a aplicarlo cada vez o a partir del
                        # round 2 se ve/nombra con su identidad real.
                        p2.mystery = True
                        p2.name = tower.current_opponent["name"]
                    elif game_mode == C.MODE_VERSUS and p2_is_random:
                        p2.enter_mystery()
                    if round_winner is None and p1_wins == 1 and p2_wins == 1:
                        # empate estando 1 a 1 (el round decisivo también
                        # empató) -> muerte súbita: ambos arrancan con 1%
                        # de vida, el primer golpe que conecte define todo
                        sudden_death = True
                        p1.health = max(1, round(p1.max_health * 0.01))
                        p2.health = max(1, round(p2.max_health * 0.01))
                    else:
                        sudden_death = False
                    round_intro_timer, round_intro_fight_threshold = start_round_intro(sound_manager, round_number, sudden_death)
                    round_intro_fight_played = False
                    state = STATE_ROUND_INTRO

        elif state == STATE_VERSUS_END:
            if stage:
                stage.update(dt)
            p1.physics_update(dt)
            p2.physics_update(dt)
            camera_x = update_camera(stage, p1, p2)
            draw_arena_background(screen, stage, camera_x)
            p1.draw(screen, camera_x)
            p2.draw(screen, camera_x)
            frozen = screen.copy()
            if game_mode == MODE_NET_VERSUS:
                versus_end_menu.update(CombinedInput(inputs[0], *remote_fighter_inputs()))
            else:
                versus_end_menu.update(inputs[0])
            versus_end_menu.draw(screen, ui, frozen_frame=frozen)
            if versus_end_menu.done:
                if versus_end_menu.choice == "rematch":
                    # SIEMPRE cambia a la música del escenario (o una de
                    # menú si no tiene propia) -- sin condicional de por
                    # medio, para que no quede sonando la de menú por error
                    music = stage.music_path if stage else None
                    sound_manager.stop_all_sfx()  # corta la voz de "Win" del ganador anterior, si seguía sonando
                    sound_manager.play_music(music or pick_random_track(MUSIC_DIR), category="stage" if music else "menu")
                    p1, p2 = new_fighters(p1_json, p2_json, sound_manager, stage=stage)
                    projectiles = []
                    p1_wins = p2_wins = 0
                    round_number = 1
                    round_time_left = C.ROUND_TIME
                    sudden_death = False
                    round_intro_timer, round_intro_fight_threshold = start_round_intro(sound_manager, round_number, sudden_death)
                    round_intro_fight_played = False
                    state = STATE_ROUND_INTRO
                elif versus_end_menu.choice == "recharacter":
                    sound_manager.stop_all_sfx()  # corta la voz de "Win" del ganador anterior, si seguía sonando
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
                    char_select = CharacterSelect(p2_is_cpu=False)
                    state = STATE_CHAR_SELECT
                elif game_mode == MODE_NET_VERSUS:
                    go_net_lobby()
                else:
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
                    sound_manager.stop_all_sfx()
                    state = STATE_MODE_MENU

        elif state == STATE_MATCH_END:
            screen.fill(C.DARK)
            ui.draw_center_text(screen, match_winner_text, C.YELLOW)
            if game_mode == C.MODE_TOWER:
                if tower_result == "advance":
                    msg = "¡Llegaste a la pelea FINAL!" if tower.fighting_final_boss else f"Avanza al piso {tower.floor + 1} de {tower.total_floors}"
                    ui.draw_small_center(screen, msg, C.SCREEN_H // 2 + C.scaled(60))
                elif tower_result == "cleared":
                    ui.draw_small_center(screen, "¡COMPLETASTE LA TORRE DE BATALLA!", C.SCREEN_H // 2 + C.scaled(60))
            else:
                ui.draw_small_center(screen, "Volviendo al menú...", C.SCREEN_H // 2 + C.scaled(60))
            round_end_timer -= dt
            if round_end_timer <= 0:
                if game_mode == C.MODE_TOWER and tower_result == "cleared":
                    p1.set_state(C.STATE_WIN, force=True)
                    p1.x, p1.y = C.LOGIC_W // 2, C.GROUND_Y
                    confetti = Confetti()
                    state = STATE_TOWER_VICTORY
                elif game_mode == C.MODE_TOWER and tower_result == "advance":
                    sound_manager.stop_all_sfx()  # corta la voz de "Win" del piso anterior, si seguía sonando
                    state = STATE_TOWER_INTRO
                else:
                    sound_manager.stop_all_sfx()
                    state = STATE_MODE_MENU

        elif state == STATE_TOWER_DEFEAT:
            tower_defeat_menu.update(inputs[0])
            tower_defeat_menu.draw(screen, ui)
            if tower_defeat_menu.done:
                if tower_defeat_menu.choice == "retry":
                    # misma pelea (mismo piso, mismo rival, misma dificultad
                    # que tenía ANTES de perder -- no vuelve a bajar de nivel)
                    sound_manager.stop_all_sfx()  # corta la voz de "Win" del rival, si seguía sonando
                    state = STATE_TOWER_INTRO
                else:
                    sound_manager.stop_all_sfx()
                    state = STATE_MODE_MENU

        elif state == STATE_TOWER_VICTORY:
            confetti.update(dt)
            p1.animations[C.STATE_WIN].update(dt)
            screen.fill(C.DARK)
            p1.draw(screen)
            confetti.draw(screen)
            ui.draw_title(screen, "¡COMPLETASTE LA TORRE DE BATALLA!", y=C.scaled(60), color=C.YELLOW)
            ui.draw_small_center(screen, f"{p1.name} le ganó a los {tower.total_floors} rivales", y=C.scaled(100))
            ui.draw_footer_mixed(screen, build_footer_parts(config, [("confirm", "continuar")]), C.SCREEN_H - C.scaled(30))
            if inputs[0].just_pressed("confirm"):
                sound_manager.stop_all_sfx()
                state = STATE_MODE_MENU

        elif state == STATE_PAUSED:
            if pause_just_entered:
                pause_just_entered = False
            elif not pause_menu.done:
                pause_menu.update(pause_input or inputs[0])
            pause_menu.draw(screen, ui, frozen_frame=frozen_frame)
            if pause_menu.done and net_host is not None and pause_menu.choice == "menu":
                sound_manager.unpause_all_sfx()
                go_net_lobby("Partida abandonada")
            elif pause_menu.done:
                if pause_menu.choice == "resume":
                    sound_manager.unpause_music()
                    sound_manager.unpause_all_sfx()
                    state = state_before_pause
                elif pause_menu.choice == "options":
                    options_menu = OptionsMenu()
                    options_return_state = STATE_PAUSED
                    pause_menu.done = False
                    pause_menu.choice = None
                    state = STATE_OPTIONS
                else:
                    sound_manager.unpause_all_sfx()
                    sound_manager.play_music(pick_random_track(MUSIC_DIR), volume=0.5, loop=False)
                    sound_manager.stop_all_sfx()
                    state = STATE_MODE_MENU

        # --- Partida WiFi (anfitrión): mandar la "foto" de este cuadro ---
        if net_host is not None:
            try:
                net_host.send(build_host_snapshot())
            except Exception as e:  # nunca cortar el juego por la red
                print(f"[AVISO] red: {e}")

        # --- Controles táctiles: qué set mostrar ---
        if touch is not None:
            if state == STATE_NET_CLIENT and client_session is not None:
                touch.set_mode(client_session.touch_mode())
            elif state in FIGHT_TOUCH_STATES:
                local_fighter = (
                    game_mode not in (MODE_NET_VERSUS, MODE_NET_TOURNAMENT) or 0 in net_owners
                )
                touch.set_mode(touch_mod.MODE_FIGHT if local_fighter else touch_mod.MODE_SPECTATE)
                if p1 is not None:
                    mine = p1
                    if game_mode in (MODE_NET_VERSUS, MODE_NET_TOURNAMENT) and net_owners[0] != 0:
                        mine = p2
                    touch.special_charge = mine.hits_taken_since_special
                    DEBUG["my_facing"] = mine.facing
            else:
                # menús: sin joystick ni botones, se toca directo la opción
                touch.set_mode(touch_mod.MODE_NONE)

        # cartelito temporal (avisos de red, etc.)
        if toast_text and pygame.time.get_ticks() / 1000.0 < toast_until:
            img = ui.font_small.render(toast_text, True, C.WHITE)
            box = img.get_rect(center=(C.SCREEN_W // 2, C.SCREEN_H - C.scaled(85)))
            bg = box.inflate(C.scaled(30), C.scaled(16))
            pygame.draw.rect(screen, (20, 20, 26), bg, border_radius=C.scaled(10))
            pygame.draw.rect(screen, C.YELLOW, bg, width=2, border_radius=C.scaled(10))
            screen.blit(img, box)

        present()
        if isinstance(inputs[0], PlayerInput):
            inputs[0].end_frame()

    close_net_host()
    if net_client is not None:
        net_client.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
