"""
Constantes globales del juego.

RESOLUCIÓN NATIVA (desde V.0.41)
---------------------------------
Todo el juego (físicas, hitboxes, HUD, menús...) está CALIBRADO a mano
sobre un lienzo de referencia de 960x540 (ver BASE_SCREEN_H). Para poder
subir la resolución nativa real (jugar en un TV grande, más nítido que
antes) SIN tener que retocar a mano cada valor en píxeles del juego
(reach, hit_offset_y, gravedad, márgenes de HUD, tamaños de fuente...),
se eligió una resolución de la tabla RESOLUTIONS de abajo y TODO se
reescala automáticamente por RES_SCALE = SCREEN_H / BASE_SCREEN_H.

Desde V.0.42 la resolución se elige en Opciones > Resolución (se guarda
en data/settings.json) en vez de acá -- este archivo solo define el
DEFAULT para la primera vez que se abre el juego. Cambiarla desde el
menú pide reiniciar (ver nota en engine/menu.py, OptionsMenu): un montón
de superficies ya escaladas (sprites, HUD, caché de imágenes de menú)
quedan calculadas para la resolución con la que arrancó el proceso, así
que no se puede cambiar "en caliente" sin reiniciar.

En la Raspberry Pi 3 puede convenir quedarse en "540p" (la resolución de
siempre) si "720p" va lento -- ver README para más notas de rendimiento.
"""

BASE_SCREEN_H = 540  # resolución de referencia con la que están calibrados reach/hitboxes/HUD/etc.

RESOLUTIONS = {
    "540p": (960, 540),    # resolución clásica (recomendada para Raspberry Pi 3 si 720p va lento)
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}
DEFAULT_RESOLUTION = "720p"  # se usa solo si data/settings.json todavía no tiene "resolution" guardado
FPS = 60


def scaled(px):
    """Convierte un valor en píxeles calibrado sobre el lienzo base
    (960x540) a la resolución real de pantalla. Usar para CUALQUIER
    posición/tamaño/margen fijo en píxeles (HUD, menús, física) que
    tenga que verse igual de proporcionado sin importar RESOLUTION."""
    return round(px * RES_SCALE)


def set_resolution(name, aspect=16 / 9):
    """Fija la resolución activa del juego. TIENE QUE LLAMARSE UNA SOLA
    VEZ, apenas arranca el proceso, ANTES de importar cualquier otro
    módulo de engine/ (ui, menu, tower, character...) -- varios de esos
    módulos calculan constantes de layout con C.scaled()/C.RES_SCALE en
    cuanto se importan (una sola vez), así que si esta función se llama
    después de que ya se importaron quedan con la resolución vieja. Por
    eso el cambio de resolución en Opciones pide reiniciar el juego en
    vez de aplicarse al toque."""
    global RESOLUTION, SCREEN_W, SCREEN_H, RES_SCALE, LOGIC_W, VIEW_PAD
    global GROUND_H, GROUND_Y, GRAVITY, PROJECTILE_GRAVITY, CHARACTER_SCALE_MULT
    if name not in RESOLUTIONS:
        name = DEFAULT_RESOLUTION
    RESOLUTION = name
    LOGIC_W, SCREEN_H = RESOLUTIONS[RESOLUTION]

    # PANTALLAS MÁS ANCHAS QUE 16:9 (celulares, ~20:9): el lienzo se
    # estira a lo ANCHO para llenar la pantalla entera (sin franjas
    # negras ni imágenes deformadas), pero la PELEA en sí sigue jugándose
    # en una ventana de 16:9 de siempre (LOGIC_W) -- lo que sobra a los
    # costados (VIEW_PAD de cada lado) solo muestra más escenario de
    # fondo. Así la jugabilidad es idéntica en cualquier pantalla (y en
    # una partida por WiFi entre celulares de distinto tamaño).
    # En PC (16:9) SCREEN_W == LOGIC_W y VIEW_PAD == 0: nada cambia.
    SCREEN_W = max(LOGIC_W, int(round(SCREEN_H * aspect / 2)) * 2)
    VIEW_PAD = (SCREEN_W - LOGIC_W) // 2

    # Factor para escalar CUALQUIER valor calibrado en el "espacio base"
    # (960x540) a la resolución real de pantalla. 960x540->1280x720 = 4/3;
    # 960x540->1920x1080 = 2x exacto. Se aplica en character.py,
    # projectile.py, ui.py, menu.py y tower.py sobre los valores que
    # vienen de JSON o están escritos como constantes de layout.
    RES_SCALE = SCREEN_H / BASE_SCREEN_H

    GROUND_H = scaled(45)            # alto de la franja de "piso" (antes 90, ahora la mitad)
    GROUND_Y = SCREEN_H - GROUND_H  # altura del piso (donde paran los pies)
    GRAVITY = 1.4 * RES_SCALE

    # Gravedad para proyectiles con trajectory="bounce" (unidad distinta a
    # la GRAVITY de arriba: esta es px/seg² real, se usa multiplicada por
    # dt en engine/projectile.py, mientras que la de arriba es un
    # incremento fijo por cuadro para saltos/K.O.).
    PROJECTILE_GRAVITY = 900 * RES_SCALE

    # Los personajes se dibujan a este porcentaje del "scale" que pida
    # cada JSON. Tocá este número acá para ajustar el tamaño de TODOS los
    # personajes de una sola vez, sin editar cada JSON (último ajuste:
    # +60%, de 0.9 a 1.44). Ya incluye RES_SCALE: así, aunque el 'scale'
    # de cada JSON esté calibrado en píxeles nativos del sprite (no
    # cambia con la resolución), el PERSONAJE renderizado en pantalla
    # mantiene el mismo tamaño relativo al lienzo sea cual sea RESOLUTION.
    CHARACTER_SCALE_MULT = 0.9 * RES_SCALE


# OJO: NO se escala acá (ver character.py, self.jump_power) -- se
# multiplica por RES_SCALE junto con cualquier override de "jump_power"
# que traiga el JSON de un personaje, para no aplicar el factor dos veces.
JUMP_POWER_DEFAULT = -25        # un poco más de salto = más margen para esquivar en el aire

set_resolution(DEFAULT_RESOLUTION)

# Techo de tamaño PROPIO para la animación de K.O. Un personaje tirado en
# el piso, de cuerpo entero, mide en ancho más o menos lo mismo que mide
# de alto parado (es una persona acostada) -- eso es real y no hay que
# "corregirlo". Pero si ese ancho no tiene límite, en una pantalla de
# SCREEN_W px angosta (hay que dejar lugar para el otro personaje, la
# barra de vida, etc.) el K.O. puede terminar viéndose gigante. Este
# porcentaje limita cuánto ancho de pantalla puede ocupar como máximo la
# animación de K.O. de CUALQUIER personaje; si se pasa, se reescala SOLO
# esa animación puntual (no afecta su tamaño en el resto del juego).
KO_MAX_WIDTH_FRAC = 0.4

ROUND_TIME = 60                # segundos por round
ROUNDS_TO_WIN = 2               # al mejor de 3

SPECIAL_HITS_REQUIRED = 5       # golpes que hay que RECIBIR para poder usar el especial
SPECIAL_DAMAGE_MULT = 1.10      # el Especial pega un 10% más que el 'damage' de su JSON

# Golpe crítico: SÓLO para puñetazo y patada (no Especial, no a distancia)
# -- cada uno tiene esta probabilidad de salir crítico, pegando ese %
# de más y sonando con un efecto de sonido propio, bien distinto del
# golpe normal (ver Character.receive_hit / resolve_combat en main.py).
CRITICAL_HIT_CHANCE = 0.02      # 2% de posibilidades por golpe
CRITICAL_HIT_MULT = 1.30        # 30% más de daño cuando sale crítico

# Si un personaje tiene VARIOS audios asignados a una misma acción (lista en
# vez de un solo archivo en el JSON), cada uno tiene esta probabilidad
# independiente de sonar cada vez que se dispara esa acción.
SOUND_RANDOM_CHANCE = 0.10
# probabilidad de que ADEMÁS del golpe físico (que siempre suena) también
# se escuche una voz propia del personaje reaccionando ("¡ay!", etc.)
VOICE_LINE_CHANCE = 0.05

# Colores UI
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (220, 40, 40)
GREEN = (40, 200, 90)
YELLOW = (240, 200, 40)
GRAY = (60, 60, 60)
DARK = (20, 20, 24)

# Estados posibles de un personaje (nombre de carpeta / clave de animación)
STATE_IDLE = "idle"
STATE_WALK = "walk"
STATE_JUMP = "jump"
STATE_PUNCH = "punch"
STATE_KICK = "kick"
STATE_SPECIAL = "special"
STATE_RANGED = "ranged"
STATE_RANGED_CROUCH = "ranged_crouch"  # ataque a distancia agachado, para pegarle bajo a un rival agachado/chico (ver character.py)
STATE_CROUCH = "crouch"
STATE_BLOCK = "block"
STATE_BLOCK_CROUCH = "block_crouch"
STATE_KO = "ko"
STATE_WIN = "win"

ATTACK_STATES = (STATE_PUNCH, STATE_KICK, STATE_SPECIAL, STATE_RANGED, STATE_RANGED_CROUCH)

# Carpetas
CHAR_DATA_DIR = "data/characters"
CHAR_ASSETS_DIR = "assets/characters"
STAGES_DIR = "assets/stages"
FONTS_DIR = "assets/fonts"
SETTINGS_PATH = "data/settings.json"

# Modos de juego
MODE_CPU = "cpu"
MODE_VERSUS = "versus"
MODE_TOWER = "tower"
MODE_TOURNAMENT = "tournament"

# Versión del juego, mostrada abajo a la izquierda en la pantalla de
# inicio (ModeMenu). Subila manualmente en cada entrega según el
# progreso: V.0.1, V.0.2... hasta V.1.0 cuando estén todos los assets
# visuales listos para el primer release.
GAME_VERSION = "V.1.3"
