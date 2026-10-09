"""
character.py
-------------
Define la clase Character: carga sus sprites y sonidos desde un JSON,
maneja física simple (correr, saltar, gravedad) y la máquina de estados
de combate (idle, walk, jump, punch, kick, special, block, hit, ko).

CÓMO FUNCIONAN LAS ANIMACIONES
Cada animación (idle, walk, punch, ...) es una carpeta con imágenes PNG
llamadas 0.png, 1.png, 2.png... (los frames, en orden). El juego las
carga todas y las va mostrando según los FPS configurados en el JSON
del personaje.
"""

import glob
import json
import os
import random
import pygame

from engine import constants as C


class Animation:
    def __init__(self, frames, fps, loop=True):
        self.frames = frames  # lista de Surface
        self.fps = max(1, fps)
        self.loop = loop
        self.timer = 0.0
        self.index = 0
        self.finished = False

    def reset(self):
        self.timer = 0.0
        self.index = 0
        self.finished = False

    def update(self, dt):
        if self.finished or not self.frames:
            return
        self.timer += dt
        frame_duration = 1.0 / self.fps
        while self.timer >= frame_duration:
            self.timer -= frame_duration
            self.index += 1
            if self.index >= len(self.frames):
                if self.loop:
                    self.index = 0
                else:
                    self.index = len(self.frames) - 1
                    self.finished = True

    def current_frame(self):
        if not self.frames:
            return None
        return self.frames[self.index]


def _load_frames(folder, colorkey_magenta=True):
    """Carga todas las imágenes numeradas de una carpeta como frames."""
    if not os.path.isdir(folder):
        return []
    paths = sorted(
        glob.glob(os.path.join(folder, "*.png")),
        key=lambda p: int("".join(filter(str.isdigit, os.path.basename(p))) or 0),
    )
    frames = []
    for p in paths:
        img = pygame.image.load(p).convert_alpha()
        frames.append(img)
    return frames


def _cap_ko_frame_size(frames):
    """Techo de tamaño propio para la animación de K.O. (ver
    C.KO_MAX_WIDTH_FRAC en constants.py). Un personaje tirado en el piso
    mide de ancho lo mismo que medía de alto parado -- eso es real y a
    propósito NO se toca en el resto del motor (ver README, sección
    Noah). Lo que SÍ hacemos acá es evitar que ese ancho (o, en los
    frames donde todavía no terminó de caer, el alto) se pase de un
    máximo razonable en pantalla, midiendo el contenido real (bounding
    box, sin márgenes transparentes) de los frames YA escalados con el
    'scale' del personaje. Si ninguno se pasa, no se toca nada. Si
    alguno se pasa, se reescala SOLO la animación de K.O. por un factor
    parejo (mantiene la proporción entre frames) -- el resto de las
    animaciones del personaje quedan intactas."""
    max_w = int(C.LOGIC_W * C.KO_MAX_WIDTH_FRAC)
    max_h = C.GROUND_Y - C.scaled(10)
    biggest_w = 0
    biggest_h = 0
    for f in frames:
        bbox = f.get_bounding_rect(min_alpha=10)
        w = bbox.width if bbox.width > 0 else f.get_width()
        h = bbox.height if bbox.height > 0 else f.get_height()
        biggest_w = max(biggest_w, w)
        biggest_h = max(biggest_h, h)
    if biggest_w == 0 or biggest_h == 0:
        return frames
    factor = min(1.0, max_w / biggest_w, max_h / biggest_h)
    if factor >= 0.999:
        return frames
    return [
        pygame.transform.smoothscale(
            f, (max(1, int(f.get_width() * factor)), max(1, int(f.get_height() * factor)))
        )
        for f in frames
    ]


# Animaciones donde el personaje debería medir siempre lo mismo "de pie"
# (aunque se mueva un brazo o una pierna, el torso/cabeza quedan a la
# misma altura que en idle). A propósito NO incluye crouch/block_crouch/ko:
# ahí el cambio de altura es real (agachado, cayéndose) y normalizarlas
# arruinaría esas poses.
STANDING_ANIMS = {
    C.STATE_IDLE, C.STATE_WALK, C.STATE_JUMP, C.STATE_PUNCH,
    C.STATE_KICK, C.STATE_SPECIAL, C.STATE_RANGED, C.STATE_BLOCK,
}

# block_crouch es la misma pose que crouch (agachado) más los puños en
# guardia -- debería medir lo mismo que crouch, no lo mismo que idle (de
# pie). Se normaliza aparte, contra la altura de crouch en vez de idle.
# ranged_crouch (tirar un proyectil agachado) NO entra acá a propósito:
# el brazo extendido tirando el proyectil confunde la detección
# automática por ancho de cabeza de forma inconsistente entre personajes
# (probado y descartado -- daba resultados dispares según el personaje).
# Se calibra a mano con "extra_scale" en el JSON de cada uno, midiendo el
# ANCHO DEL TORSO (más estable que la cabeza para esta pose puntual, ver
# charla con Claude) contra su propio idle.
CROUCH_ANIMS = {C.STATE_BLOCK_CROUCH}


def _max_bbox_height(frames):
    best = 0
    for f in frames:
        bbox = f.get_bounding_rect(min_alpha=10)
        h = bbox.height if bbox.height > 0 else f.get_height()
        best = max(best, h)
    return best


def _head_pixel_width(frame, top_frac=0.12):
    """Ancho en píxeles del contenido dentro del primer 'top_frac' de la
    altura del bounding box (aproximadamente la cabeza). Sirve como
    referencia de zoom de cámara INDEPENDIENTE de la pose: la cabeza de
    una persona no cambia de tamaño real entre estar parado o agachado,
    así que si su ancho en píxeles difiere entre dos hojas del mismo
    personaje, es porque la cámara estaba más cerca/lejos en una que en
    la otra -- a diferencia de la altura total (que SÍ cambia con la
    pose, agachado o no), esto no se confunde con una pose real."""
    if not frame:
        return 0
    bbox = frame.get_bounding_rect(min_alpha=10)
    if bbox.height == 0:
        return 0
    band_h = max(1, int(bbox.height * top_frac))
    band = frame.subsurface(pygame.Rect(bbox.x, bbox.y, bbox.width, band_h))
    band_bbox = band.get_bounding_rect(min_alpha=10)
    return band_bbox.width


class Character:
    def __init__(self, json_path, sound_manager):
        with open(json_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

        self.name = self.data.get("name", "Sin nombre")
        self.sprite_folder = self.data["sprite_folder"]
        self.scale = self.data.get("scale", 2) * C.CHARACTER_SCALE_MULT
        self.max_health = self.data.get("health", 100)
        self.health = self.max_health
        # walk_speed/jump_power vienen del JSON calibrados en el lienzo
        # base (960x540, ver C.RES_SCALE) -- se escalan ACÁ, una sola vez,
        # tanto el valor propio del personaje como el default, para que
        # no importa la resolución activa se sientan igual de rápidos/
        # saltarines en relación al tamaño de pantalla.
        self.walk_speed = self.data.get("walk_speed", 4) * C.RES_SCALE
        self.jump_power = self.data.get("jump_power", C.JUMP_POWER_DEFAULT) * C.RES_SCALE
        self.sounds = self.data.get("sounds", {})
        self.sound_manager = sound_manager
        self._sound_pools = self._build_sound_pools()
        self.projectile_frame_paths = self._resolve_projectile_frames()

        self.animations_data = self.data.get("animations", {})
        self.animations = {}
        self._load_all_animations()

        # Física / posición
        self.x = 0
        self.y = C.GROUND_Y
        self.vel_x = 0
        self.vel_y = 0
        self.facing = 1  # 1 = derecha, -1 = izquierda
        self.on_ground = True

        # Combate
        self.state = C.STATE_IDLE
        self.blocking = False
        self.hitstun_timer = 0.0
        self.attack_has_hit = False  # para no pegar 2 veces en el mismo ataque
        self._special_miss_checked = False  # para no repetir el sonido de "erró" en el mismo Especial
        # Qué mantenía apretado en el último handle_input() -- para que,
        # cuando un ataque termina (dentro de physics_update, ver más
        # abajo), se pueda volver DIRECTO a crouch/block en vez de pasar
        # siempre por "idle" primero (aunque siguiera agachado/cubriendo
        # todo el tiempo). Ese paso de más por "idle" duraba un cuadro
        # entero -- se veía como un parpadeo (bug reportado).
        self._down_held = False
        self._block_held = False
        self.knocked_out = False
        self.hit_flash_timer = 0.0

        # "Aleatorio": mientras self.mystery es True, se dibuja como
        # silueta negra y el nombre se ve como "???" (ver enter_mystery/reveal)
        self.mystery = False
        self._real_name = self.name

        # Física del K.O. (caída + rebote contra el piso)
        self.ko_bounces = 0
        self.ko_max_bounces = 2
        self.ko_settled = False

        # Especial con "carga" por golpes recibidos
        self.hits_taken_since_special = 0

        # Ataque a distancia: para no lanzar más de un proyectil por ataque
        self.projectile_spawned = False

        # Hitbox/hurtbox base (se ajusta según el sprite y el escalado global)
        self.body_w = int(90 * C.CHARACTER_SCALE_MULT)
        self.body_h = int(260 * C.CHARACTER_SCALE_MULT)

    # ------------------------------------------------------------------
    # Carga de recursos
    # ------------------------------------------------------------------
    def _load_all_animations(self):
        if not os.path.isdir(self.sprite_folder):
            print(
                f"[AVISO] '{self.name}': no encontré la carpeta de sprites "
                f"'{self.sprite_folder}'. Revisá que 'sprite_folder' en su .json "
                f"apunte EXACTAMENTE (mayúsculas/tildes incluidas) al nombre real "
                f"de la carpeta dentro de assets/characters/. Se va a mostrar un "
                f"rectángulo de color en su lugar."
            )

        # Techo de tamaño: si con el 'scale' pedido (JSON x CHARACTER_SCALE_MULT)
        # el personaje quedaría más alto que la pantalla estando parado quieto,
        # se reduce automáticamente para que no se le corte la cabeza. Usamos
        # la altura del CONTENIDO visible (bounding box de píxeles no
        # transparentes), no la altura del lienzo del PNG: varios packs de
        # sprites dejan mucho margen transparente arriba/abajo del personaje
        # (para poder animar saltos, por ejemplo), y medir el lienzo completo
        # lo achicaba mucho más de lo necesario.
        idle_frames = _load_frames(os.path.join(self.sprite_folder, C.STATE_IDLE))
        idle_ref_h = _max_bbox_height(idle_frames) if idle_frames else 0
        idle_head_w = _head_pixel_width(idle_frames[0]) if idle_frames else 0

        # 'crouch' y 'block_crouch' SÍ deberían medir menos que 'idle' (es
        # una pose agachada, real) -- por eso no usamos su altura total
        # para detectar zoom raro, como con las animaciones "de pie"
        # (la altura CAMBIA con la pose, a propósito). En cambio medimos
        # el ancho de la cabeza (que no cambia diga lo que diga la pose)
        # contra la de 'idle': si difiere, es la cámara más cerca/lejos
        # en esa hoja puntual, no una pose distinta -- y ESO sí lo
        # corregimos, preservando cuánto se agacha de verdad.
        crouch_frames = _load_frames(os.path.join(self.sprite_folder, C.STATE_CROUCH))
        crouch_head_w = _head_pixel_width(crouch_frames[0]) if crouch_frames else 0
        crouch_zoom_factor = 1.0
        if idle_head_w and crouch_head_w:
            crouch_zoom_factor = idle_head_w / crouch_head_w
            if abs(crouch_zoom_factor - 1.0) > 0.05:
                print(
                    f"[AVISO] '{self.name}': la animación 'crouch' se ve tomada "
                    f"con otro zoom de cámara que 'idle' (cabeza {crouch_zoom_factor:.2f}x). "
                    f"Se corrigió el zoom manteniendo la pose agachada real."
                )

        # OJO: se probó la misma técnica de 'ancho de cabeza' para 'win'
        # (mataba dos pájaros: la altura SÍ cambia de verdad ahí -- brazos
        # arriba festejando, a veces un saltito -- así que tampoco vale
        # forzarla a medir lo mismo que idle como a una animación "de
        # pie" común). Pero da resultados igual de poco confiables que
        # con K.O. (factores de 0.2x-0.4x, imposibles): con los brazos
        # arriba, lo más alto del cuadro pasa a ser la MANO, no la
        # cabeza, así que la banda "de arriba" mide ancho de puño en vez
        # de ancho de cabeza. Por eso 'win' tampoco se autocorrige acá --
        # si una hoja puntual sale mal, se ajusta a mano con
        # "extra_scale", mirando el renderizado al lado de otro
        # personaje ya calibrado (mismo criterio que K.O.).

        # 'ko' tiene el mismo problema posible que 'crouch': su ALTURA sí
        # cambia de verdad (se va cayendo), así que tampoco se puede usar
        # para detectar zoom raro -- pero la hoja completa puede venir
        # grabada con la cámara mucho más lejos/cerca que 'idle' de
        # entrada (pasa cuando cada animación se generó por separado), y
        # eso SÍ hay que corregirlo o el K.O. sale gigante o diminuto
        # comparado con el resto del personaje. Se mide con el frame 0
        # (recién empieza a caer, todavía casi parado, cabeza bien visible).
        # OJO: a diferencia de 'crouch' (pose de arrodillarse, bastante
        # estable entre personajes), el K.O. es una caída dinámica y en
        # muchos personajes el primer cuadro YA arranca inclinado hacia
        # adelante -- ahí la banda de "ancho de cabeza" mide el hombro/la
        # capucha en vez de la cabeza real y da una corrección falsa (se
        # probó y da resultados inconsistentes incluso comparando cuadros
        # cercanos entre sí). Por eso NO se autocorrige el zoom de K.O.
        # por esta vía; si una hoja de K.O. puntual sale mal, se ajusta a
        # mano con "extra_scale" en su config (ver constants/README).
        if idle_ref_h:
            max_h = C.GROUND_Y - C.scaled(10)
            if idle_ref_h * self.scale > max_h:
                capped = max_h / idle_ref_h
                print(
                    f"[AVISO] '{self.name}': con scale={self.scale:.2f} no entraba "
                    f"parado en la pantalla (quedaba más alto que {max_h}px). Se "
                    f"ajustó automáticamente a scale={capped:.2f}. Si lo querés más "
                    f"grande igual, subí SCREEN_H en engine/constants.py."
                )
                self.scale = capped

        for anim_name, cfg in self.animations_data.items():
            folder = os.path.join(self.sprite_folder, anim_name)
            frames = _load_frames(folder)
            if os.path.isdir(self.sprite_folder) and not frames:
                print(
                    f"[AVISO] '{self.name}': la animación '{anim_name}' no tiene "
                    f"frames en '{folder}' (esperaba archivos 0.png, 1.png, ...)."
                )

            # "ranged_crouch": a diferencia de TODAS las otras animaciones
            # (que vienen de una sola foto/toma por cuadro pero con la
            # cámara relativamente estable entre cuadros), estas 4 hojas
            # tienen la distancia de cámara bastante inconsistente ENTRE
            # CUADROS de la MISMA animación -- eso hace que el
            # personaje "cambie de tamaño" visiblemente cuadro a cuadro
            # durante la propia animación (bug reportado; con "ranged"
            # de pie pasa lo mismo a nivel de píxeles pero se nota mucho
            # menos). El ajuste de más abajo (extra_scale/local_factor)
            # es un solo número por ANIMACIÓN, se aplica IGUAL a los 4
            # cuadros, así que no alcanza para esto -- hace falta
            # normalizar cuadro por cuadro, acá, antes de esa parte.
            #
            # OJO: la primera versión de esto medía la altura TOTAL del
            # recuadro de cada cuadro (de la punta más alta a los pies).
            # Rompía justo en los cuadros donde el puño de guardia queda
            # LEVANTADO POR ENCIMA DE LA CABEZA (los primeros de la
            # animación, antes de estirar el brazo para tirar): ahí "la
            # punta más alta" es el puño, no la cabeza, así que esos
            # cuadros medían de más y la normalización los achicaba de
            # más -- el cuerpo real quedaba más chico que en los cuadros
            # 3 y 4 en vez de igual (bug reportado, con capturas).
            #
            # Por eso ahora se mide "de la CABEZA a los pies" en cada
            # cuadro, no "de la punta más alta a los pies": se busca fila
            # por fila desde arriba hasta encontrar dónde el ancho del
            # contenido se acerca al ancho de cabeza típico de este
            # personaje (un puño es mucho más angosto que una cabeza) --
            # esa fila es la cabeza de verdad, ignorando cualquier puño
            # levantado por encima. El ancho de cabeza de referencia sale
            # del cuadro ACTIVO (el que suelta el proyectil, con el brazo
            # ya estirado hacia adelante y no hacia arriba -- ahí la
            # cabeza SÍ es la punta más alta, así que medirla ahí es
            # confiable).
            if anim_name == C.STATE_RANGED_CROUCH and frames:
                active_frames_list = cfg.get("active_frames") or [len(frames) - 1]
                active_idx = min(active_frames_list[0], len(frames) - 1)
                ref_bbox = frames[active_idx].get_bounding_rect(min_alpha=10)
                ref_band_h = max(1, int(ref_bbox.height * 0.08))
                ref_head_w = frames[active_idx].subsurface(
                    pygame.Rect(ref_bbox.x, ref_bbox.y, ref_bbox.width, ref_band_h)
                ).get_bounding_rect(min_alpha=10).width

                def _body_height(frame, head_w_ref):
                    bbox = frame.get_bounding_rect(min_alpha=10)
                    threshold = head_w_ref * 0.7
                    head_top = 0
                    for y in range(bbox.height):
                        row = frame.subsurface(pygame.Rect(bbox.x, bbox.y + y, bbox.width, 1))
                        if row.get_bounding_rect(min_alpha=10).width >= threshold:
                            head_top = y
                            break
                    return bbox.height - head_top

                if ref_head_w > 0:
                    ref_body_h = _body_height(frames[active_idx], ref_head_w)
                    if ref_body_h > 0:
                        normalized = []
                        for f in frames:
                            fbh = _body_height(f, ref_head_w)
                            if fbh > 0 and fbh != ref_body_h:
                                factor = ref_body_h / fbh
                                f = pygame.transform.smoothscale(
                                    f,
                                    (max(1, round(f.get_width() * factor)), max(1, round(f.get_height() * factor))),
                                )
                            normalized.append(f)
                        frames = normalized

            # Corrección de "zoom" inconsistente entre hojas: si esta
            # animación viene de una hoja generada con otro nivel de
            # acercamiento de cámara que la de idle (pasa seguido cuando
            # cada animación se generó por separado con IA), el personaje
            # se ve más grande o más chico solo en esa animación aunque el
            # 'scale' del personaje sea uno solo. Para las animaciones
            # "de pie" (ver STANDING_ANIMS), medimos el pico de altura de
            # ESTA hoja y la reescalamos para que coincida con la de idle
            # -- se corrige un factor por hoja entera, así que las
            # proporciones DENTRO de la animación (ej: un frame agachado
            # de jump sigue más bajo que uno estirado) no se tocan.
            local_factor = 1.0
            ref_h = None
            ref_name = None
            if anim_name in STANDING_ANIMS and anim_name != C.STATE_IDLE and idle_ref_h:
                ref_h, ref_name = idle_ref_h, "idle"
            if ref_h and frames:
                anim_h = _max_bbox_height(frames)
                if anim_h > 0:
                    local_factor = ref_h / anim_h
                    if abs(local_factor - 1.0) > 0.05:
                        print(
                            f"[AVISO] '{self.name}': la animación '{anim_name}' tenía "
                            f"otro nivel de zoom que '{ref_name}' (factor {local_factor:.2f}). "
                            f"Se corrigió automáticamente para que mida lo mismo que "
                            f"'{ref_name}'."
                        )
            elif anim_name == C.STATE_CROUCH:
                local_factor = crouch_zoom_factor
            elif anim_name in CROUCH_ANIMS and frames:
                # Mismo criterio que 'crouch': corregimos el zoom de cámara
                # por ancho de cabeza contra idle, no la altura total.
                anim_head_w = _head_pixel_width(frames[0])
                if idle_head_w and anim_head_w:
                    local_factor = idle_head_w / anim_head_w
                    if abs(local_factor - 1.0) > 0.05:
                        print(
                            f"[AVISO] '{self.name}': la animación '{anim_name}' se ve "
                            f"tomada con otro zoom de cámara que 'idle' (cabeza "
                            f"{local_factor:.2f}x). Se corrigió el zoom manteniendo la "
                            f"pose real."
                        )

            # Ajuste manual opcional por animación (JSON: "extra_scale"),
            # para retoques finos ("este KO se ve un poco chico") sin
            # tocar el 'scale' general del personaje ni el resto de sus
            # animaciones.
            extra_scale = cfg.get("extra_scale", 1.0)

            total_scale = self.scale * local_factor * extra_scale
            if total_scale != 1:
                frames = [
                    pygame.transform.smoothscale(
                        f, (max(1, int(f.get_width() * total_scale)), max(1, int(f.get_height() * total_scale)))
                    )
                    for f in frames
                ]
            if anim_name == C.STATE_KO and frames:
                frames = _cap_ko_frame_size(frames)
            self.animations[anim_name] = Animation(
                frames, cfg.get("fps", 8), cfg.get("loop", True)
            )

        # Compatibilidad: si el personaje no tiene 'crouch' o 'block_crouch'
        # propios (personajes viejos, o nuevos sin ese arte todavía), se usa
        # la animación más parecida que sí tenga, en vez de romper.
        if C.STATE_CROUCH not in self.animations or not self.animations[C.STATE_CROUCH].frames:
            fallback = self.animations.get(C.STATE_BLOCK) or self.animations.get(C.STATE_IDLE)
            if fallback:
                self.animations[C.STATE_CROUCH] = fallback
        if C.STATE_BLOCK_CROUCH not in self.animations or not self.animations[C.STATE_BLOCK_CROUCH].frames:
            fallback = self.animations.get(C.STATE_CROUCH) or self.animations.get(C.STATE_BLOCK)
            if fallback:
                self.animations[C.STATE_BLOCK_CROUCH] = fallback
        if C.STATE_WIN not in self.animations or not self.animations[C.STATE_WIN].frames:
            fallback = self.animations.get(C.STATE_IDLE)
            if fallback:
                self.animations[C.STATE_WIN] = fallback

    # ------------------------------------------------------------------
    # Cambio de estado
    # ------------------------------------------------------------------
    def set_state(self, new_state, force=False):
        if self.knocked_out and not force:
            return
        if self.state == new_state and not force:
            return
        # No interrumpir un ataque a mitad de animación
        if self.state in C.ATTACK_STATES and not self.animations[self.state].finished and not force:
            return

        self.state = new_state
        if new_state in self.animations:
            self.animations[new_state].reset()
        self.attack_has_hit = False
        self.projectile_spawned = False
        if new_state == C.STATE_SPECIAL:
            self._special_miss_checked = False

        if new_state == C.STATE_WIN:
            # Si justo cuando ganó la ronda venía caminando (o con
            # cualquier impulso encima), que no siga arrastrándose solo
            # contra un borde del escenario durante toda la animación de
            # festejo -- se cancela el movimiento y queda festejando
            # clavado en el lugar exacto donde ganó.
            self.vel_x = 0
            self.vel_y = 0

        # Sonidos automáticos de "silbido" del golpe al arrancar la animación
        # (el sonido de IMPACTO se dispara aparte, en receive_hit, porque
        # depende de si conecta o no).
        sound_key = {
            C.STATE_PUNCH: "punch",
            C.STATE_KICK: "kick",
            C.STATE_SPECIAL: "special",
        }.get(new_state)
        if sound_key:
            self._play_character_sound(sound_key)
        if new_state in (C.STATE_RANGED, C.STATE_RANGED_CROUCH):
            # Si el proyectil de este personaje suena en loop mientras
            # está en pantalla (ver 'loop_sound' en el JSON, y
            # spawn_projectiles en main.py), ESE es su sonido -- acá no
            # se dispara nada más, o sonarían los dos pisándose.
            loop_cfg = self.animations_data.get(new_state, {})
            if not loop_cfg.get("loop_sound"):
                if not self._play_character_sound("ranged", volume=0.8):
                    self.sound_manager.play_sfx_fallback(None, "throw", volume=0.8)

    SOUND_EXTENSIONS = (".wav", ".ogg", ".mp3")

    def _build_sound_pools(self):
        """Arma, para cada acción, la lista de archivos de audio que le
        corresponden. Por defecto, auto-detecta CUALQUIER archivo de audio
        adentro de assets/characters/<nombre>/sounds/<acción>/ (así como
        las animaciones: soltás archivos ahí y listo, sin tocar el JSON).
        Si el JSON define esa clave explícitamente (string o lista), esa
        declaración GANA y se usa en vez de la carpeta -- para los casos
        raros en que necesites apuntar a otro lado."""
        pools = {}

        sounds_root = os.path.join(self.sprite_folder, "sounds")
        if os.path.isdir(sounds_root):
            for entry in sorted(os.listdir(sounds_root)):
                subdir = os.path.join(sounds_root, entry)
                if not os.path.isdir(subdir):
                    continue  # no es una carpeta de acción (podría ser un .wav suelto viejo)
                files = sorted(
                    os.path.join(subdir, f)
                    for f in os.listdir(subdir)
                    if f.lower().endswith(self.SOUND_EXTENSIONS)
                )
                if files:
                    pools[entry] = files

        for key, value in self.sounds.items():
            if key.startswith("_") or not value:
                continue  # saltear comentarios ("_comentario": "...")
            paths = value if isinstance(value, list) else [value]
            pools[key] = [os.path.join(self.sprite_folder, p) for p in paths]

        return pools

    def _resolve_projectile_frames(self):
        """Rutas de imagen para el proyectil. Prioridad:
        carpeta 'projectile/' con SUBCARPETAS (0/, 1/, 2/...) -> cada
        subcarpeta es un objeto distinto con sus propios cuadros de giro
        (ej. Omar: llave, pinza, destornillador -- cada tiro elige una
        AL AZAR y esa gira volando, ver 'random_spin' en
        get_ranged_launch) -> carpeta 'projectile/' con archivos sueltos
        (uno o más = animación de giro de UN solo objeto, sin variantes)
        -> 'projectile_image' de siempre (un solo archivo, compatibilidad
        con personajes viejos) -> ninguno (el Projectile usa su bolita
        amarilla de respaldo)."""
        folder = os.path.join(self.sprite_folder, "projectile")
        if os.path.isdir(folder):
            def sort_key(fname):
                stem = os.path.splitext(fname)[0]
                return (0, int(stem)) if stem.isdigit() else (1, fname)

            subdirs = sorted(
                (d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))),
                key=sort_key,
            )
            if subdirs:
                groups = []
                for d in subdirs:
                    sub = os.path.join(folder, d)
                    files = sorted(
                        (f for f in os.listdir(sub) if f.lower().endswith((".png", ".jpg", ".jpeg"))),
                        key=sort_key,
                    )
                    paths = [os.path.join(sub, f) for f in files]
                    if paths:
                        groups.append(paths)
                if groups:
                    return groups

            files = sorted(
                (f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg", ".jpeg"))),
                key=sort_key,
            )
            paths = [os.path.join(folder, f) for f in files]
            if paths:
                return paths

        single = self.data.get("projectile_image")
        if single:
            path = os.path.join(self.sprite_folder, single)
            if os.path.isfile(path):
                return [path]
        return []

    def play_voice(self, key):
        self._play_character_sound(key)

    def enter_mystery(self):
        """Se llama cuando este personaje fue elegido con 'Aleatorio': se
        dibuja como silueta negra y el nombre se ve como '???' hasta que
        arranca la pelea de verdad (reveal())."""
        self.mystery = True
        self.name = "???"

    def reveal(self):
        """Se llama justo cuando empieza la pelea (fin de la intro del
        round): vuelve a mostrar al personaje real."""
        if self.mystery:
            self.mystery = False
            self.name = self._real_name

    def play_win_voice(self):
        """Se llama UNA vez cuando este personaje gana la pelea (no un
        round, la pelea completa). Si hay varios audios de 'win', elige uno
        al azar (a diferencia de golpes/hits, acá SIEMPRE suena alguno si
        hay algo cargado, no tiene sentido que la victoria quede en
        silencio por mala suerte)."""
        paths = [p for p in self._sound_pools.get("win", []) if os.path.isfile(p)]
        if paths:
            self.sound_manager.play(random.choice(paths), volume=1.0)

    def get_character_sound_path(self, key):
        """Devuelve UNA ruta de audio propia del personaje para 'key' (al
        azar si hay varias), o None si no tiene. A diferencia de
        _play_character_sound, no reproduce nada -- para casos donde hace
        falta la ruta en sí (ej. sonido de proyectil en loop, manejado
        por canal aparte en main.py)."""
        paths = [p for p in self._sound_pools.get(key, []) if os.path.isfile(p)]
        return random.choice(paths) if paths else None

    def _play_character_sound(self, key, volume=1.0, chance=None, force_chance=False):
        """Reproduce el/los audio(s) propios del personaje para 'key' (ver
        _build_sound_pools). Por defecto: UN solo archivo -> suena
        siempre; VARIOS archivos -> cada uno tiene una probabilidad
        independiente ('chance', SOUND_RANDOM_CHANCE=10% si no se
        especifica) de sonar, así que puede sonar 0, 1 o más en un mismo
        golpe. Con force_chance=True, esa probabilidad se aplica AUNQUE
        haya un solo archivo (para voces tipo 'grito al recibir un golpe',
        que no queremos que suenen el 100% de las veces). Devuelve True
        si sonó algo."""
        paths = self._sound_pools.get(key)
        if not paths:
            return False
        use_chance = chance if chance is not None else C.SOUND_RANDOM_CHANCE
        played_any = False
        for full_path in paths:
            always = len(paths) == 1 and not force_chance
            if always or random.random() < use_chance:
                if os.path.isfile(full_path):
                    self.sound_manager.play(full_path, volume)
                    played_any = True
        return played_any

    # ------------------------------------------------------------------
    # Lógica por frame
    # ------------------------------------------------------------------
    def handle_input(self, inp, opponent_x):
        if self.knocked_out:
            return

        # Excepción puntual: la IA en "modo pánico" (ver CPUInput) puede
        # cancelar su propio ataque a mitad de camino para cubrirse, algo
        # que un jugador normal no puede hacer -- si no, quedaba
        # atrapada terminando un golpe propio mientras comía otro más.
        if getattr(inp, "force_defend", False) and self.on_ground:
            self.blocking = True
            self.vel_x = 0
            self.set_state(C.STATE_BLOCK, force=True)
            return

        # Mientras se está atacando, no se puede mover/cambiar acción
        busy = self.state in C.ATTACK_STATES and not self.animations[self.state].finished

        # Se registra SIEMPRE (incluso ocupado atacando) -- lo usa
        # physics_update() para saber a qué volver apenas termine el
        # ataque, sin pasar por "idle" de más si seguía agachado/cubriendo.
        self._down_held = inp.pressed("down") and self.on_ground
        self._block_held = inp.pressed("block") and self.on_ground

        self.blocking = False

        if not busy:
            if inp.just_pressed("punch"):
                self.set_state(C.STATE_PUNCH)
                return
            if inp.just_pressed("kick"):
                self.set_state(C.STATE_KICK)
                return
            if inp.just_pressed("ranged"):
                # Agachado + a distancia = tirar desde abajo (pega más
                # bajo, para alcanzar a un rival agachado). Solo para
                # personajes que tengan la animación "ranged_crouch"
                # definida -- si no la tienen, se comporta exactamente
                # como siempre (tira de pie, sin importar si estaba
                # agachado un instante antes).
                if (
                    inp.pressed("down")
                    and self.on_ground
                    and C.STATE_RANGED_CROUCH in self.animations_data
                ):
                    self.set_state(C.STATE_RANGED_CROUCH)
                else:
                    self.set_state(C.STATE_RANGED)
                return
            if inp.just_pressed("special"):
                if self.hits_taken_since_special >= C.SPECIAL_HITS_REQUIRED:
                    self.hits_taken_since_special = 0
                    self.set_state(C.STATE_SPECIAL)
                # si todavía no está cargado, se ignora el input (no hace nada)
                return

            guard = inp.pressed("block") and self.on_ground
            crouch = inp.pressed("down") and self.on_ground

            if guard and crouch:
                self.blocking = True
                self.set_state(C.STATE_BLOCK_CROUCH)
                self.vel_x = 0
            elif guard:
                # cubrirse de pie: no se puede caminar mientras se cubre
                self.blocking = True
                self.set_state(C.STATE_BLOCK)
                self.vel_x = 0
            elif crouch:
                # agacharse sin cubrirse: no reduce daño, es solo postura
                self.blocking = False
                self.set_state(C.STATE_CROUCH)
                self.vel_x = 0
            elif inp.pressed("up") and self.on_ground:
                self.vel_y = self.jump_power
                self.on_ground = False
                self.set_state(C.STATE_JUMP)
            elif inp.pressed("left"):
                self.vel_x = -self.walk_speed
                if self.on_ground:
                    self.set_state(C.STATE_WALK)
            elif inp.pressed("right"):
                self.vel_x = self.walk_speed
                if self.on_ground:
                    self.set_state(C.STATE_WALK)
            else:
                self.vel_x = 0
                if self.on_ground:
                    self.set_state(C.STATE_IDLE)

        # Orientarse automáticamente hacia el rival
        self.facing = 1 if opponent_x >= self.x else -1

    def clamp_x(self, min_x, max_x):
        """Restringe la posición X a un rango -- lo llama main.py una vez
        por cuadro con los bordes de la CÁMARA actual (no de la pantalla
        fija), para que el personaje nunca quede fuera de la parte
        visible de un escenario más ancho que 16:9 (ver
        compute_camera_x/Stage.get_camera_x)."""
        self.x = max(min_x, min(max_x, self.x))

    def physics_update(self, dt):
        if self.knocked_out:
            self._ko_physics_update()
        else:
            if not self.on_ground:
                self.vel_y += C.GRAVITY
                self.y += self.vel_y
                if self.y >= C.GROUND_Y:
                    self.y = C.GROUND_Y
                    self.vel_y = 0
                    self.on_ground = True
                    if self.state == C.STATE_JUMP:
                        # Mismo criterio que al terminar un ataque (ver
                        # más abajo): si venía agachando/cubriendo la
                        # tecla mientras caía, ir directo ahí en vez de
                        # pasar por "idle" un cuadro de más.
                        if self._block_held and self._down_held:
                            self.set_state(C.STATE_BLOCK_CROUCH, force=True)
                            self.blocking = True
                        elif self._block_held:
                            self.set_state(C.STATE_BLOCK, force=True)
                            self.blocking = True
                        elif self._down_held:
                            self.set_state(C.STATE_CROUCH, force=True)
                        else:
                            self.set_state(C.STATE_IDLE, force=True)

            self.x += self.vel_x
            # El límite de hasta dónde puede moverse en X ya NO se aplica
            # acá (antes era fijo a los bordes de pantalla) -- ahora lo
            # aplica main.py cada cuadro, contra la ventana de cámara
            # actual (ver clamp_x y compute_camera_x), porque en un
            # escenario más ancho que 16:9 el límite real depende de
            # dónde está la cámara en ese momento, no de un valor fijo.

        anim = self.animations.get(self.state)
        if anim and self.state != C.STATE_KO:
            anim.update(dt)

        # "Erró el Especial" se dispara apenas termina de pasar la
        # ventana de golpe activo (active_frames) sin haber conectado --
        # NO cuando termina toda la animación (eso incluye cuadros de
        # recuperación después del golpe, que en algunos personajes son
        # varios cuadros más -- esperar a 'finished' sonaba perceptiblemente
        # tarde). Se chequea una sola vez por Especial (_special_miss_checked).
        if (
            self.state == C.STATE_SPECIAL and anim and not self.attack_has_hit
            and not self._special_miss_checked
        ):
            active = self.animations_data.get(C.STATE_SPECIAL, {}).get("active_frames", [])
            # Puede pasar ("anim.index > max(active)") o, si el frame
            # activo es justo el ÚLTIMO de toda la animación, terminar
            # ("anim.finished") sin llegar nunca a superarlo -- los dos
            # casos cuentan como "ya pasó la ventana de golpe".
            if active and (anim.index > max(active) or (anim.finished and anim.index >= max(active))):
                self._special_miss_checked = True
                self.sound_manager.play_sfx_fallback(None, "special_miss", volume=1.0)

        if self.state in C.ATTACK_STATES and anim and anim.finished:
            # Ir DIRECTO al estado que corresponda según lo que se seguía
            # apretando (ver _down_held/_block_held en handle_input) --
            # no siempre "idle": si el jugador mantuvo agachado/cubriendo
            # DURANTE todo el ataque (ej. "ranged_crouch"), pasar por
            # "idle" aunque sea un solo cuadro se notaba como un
            # parpadeo (bug reportado).
            if self._block_held and self._down_held:
                self.set_state(C.STATE_BLOCK_CROUCH, force=True)
                self.blocking = True
            elif self._block_held:
                self.set_state(C.STATE_BLOCK, force=True)
                self.blocking = True
            elif self._down_held:
                self.set_state(C.STATE_CROUCH, force=True)
            else:
                self.set_state(C.STATE_IDLE, force=True)

        if self.hit_flash_timer > 0:
            self.hit_flash_timer -= dt

    def _ko_physics_update(self):
        """Hace que el personaje salga despedido hacia atrás, caiga por
        gravedad, rebote un par de veces contra el piso (cada vez con menos
        fuerza) y finalmente quede tirado. Los sonidos de golpe contra el
        piso se disparan solos en cada rebote y en el impacto final."""
        if self.ko_settled:
            return

        self.vel_y += C.GRAVITY
        self.y += self.vel_y
        self.x += self.vel_x
        self.vel_x *= 0.9  # fricción con el piso / aire
        # ver comentario en physics_update: el límite en X lo aplica
        # main.py cada cuadro contra la cámara actual, no acá.

        if self.y >= C.GROUND_Y:
            self.y = C.GROUND_Y
            if self.ko_bounces < self.ko_max_bounces and abs(self.vel_y) > 4:
                self.vel_y = -self.vel_y * 0.4
                self.ko_bounces += 1
                if not self._play_character_sound("fall", volume=0.85):
                    self.sound_manager.play_sfx_fallback(None, "fall_bounce", volume=0.85)
            else:
                self.vel_y = 0
                self.ko_settled = True
                if not self._play_character_sound("fall", volume=1.0):
                    self.sound_manager.play_sfx_fallback(None, "fall_thud", volume=1.0)

        # La pose que se muestra se elige según la FASE FÍSICA real de la
        # caída (cayendo / rebotando / asentado), no por un timer aparte
        # -- si no, la animación podía "adelantarse" y mostrar una pose ya
        # tirada en el piso mientras el cuerpo todavía estaba en el aire
        # rebotando, dando la sensación de que quedaba flotando.
        ko_anim = self.animations.get(C.STATE_KO)
        if ko_anim and ko_anim.frames:
            n = len(ko_anim.frames)
            if self.ko_settled:
                idx = n - 1
            elif self.ko_bounces >= 1:
                idx = min(n - 1, round(n * 0.55))
            else:
                idx = min(n - 1, round(n * 0.25))
            ko_anim.index = idx

    # ------------------------------------------------------------------
    # Combate: hitbox / daño
    # ------------------------------------------------------------------
    def get_hurtbox(self):
        """Caja de golpe del cuerpo. Depende del ESTADO, no solo de la
        posición: un personaje agachado es físicamente más bajo (la caja
        se achica desde arriba, dejando pasar tiros altos por encima), y
        uno en el aire está más arriba Y más compacto (pose encogida del
        salto) -- así importa poco que el .png de la pose se salga un
        poco de la caja calculada (van a pasar cosas раras de encastre
        para cada sprite distinto), lo que importa es que agacharse y
        saltar sirvan de verdad para esquivar."""
        h = self.body_h
        if self.state in (C.STATE_CROUCH, C.STATE_BLOCK_CROUCH, C.STATE_RANGED_CROUCH):
            h = int(self.body_h * 0.55)
        elif not self.on_ground:
            h = int(self.body_h * 0.75)
        return pygame.Rect(
            self.x - self.body_w // 2, self.y - h, self.body_w, h
        )

    def get_active_hitbox(self):
        """Devuelve el rectángulo de golpe SOLO si el ataque está en su
        rango de frames activos (definido en el JSON del personaje).
        El ataque a distancia normalmente NO pega cuerpo a cuerpo: lanza
        un proyectil aparte (ver get_ranged_launch) -- salvo que el
        personaje tenga 'melee_whip': true en su config de 'ranged' (ej.
        un látigo/cinta/pelo), en cuyo caso pega directo con un 'reach'
        largo, sin ningún objeto viajando por la pantalla."""
        if self.state not in C.ATTACK_STATES:
            return None
        cfg = self.animations_data.get(self.state, {})
        if self.state == C.STATE_RANGED and not cfg.get("melee_whip", False):
            return None
        active_frames = cfg.get("active_frames", [])
        anim = self.animations[self.state]
        if anim.index not in active_frames:
            return None

        # reach/hit_height/hit_offset_y están calibrados en el JSON sobre
        # el lienzo base (960x540) -- se escalan acá según C.RES_SCALE
        # para que la caja de golpe siga coincidiendo con el sprite (que
        # también se dibuja más grande) sea cual sea RESOLUTION.
        reach = cfg.get("reach", 70) * C.RES_SCALE
        height = cfg.get("hit_height", 60) * C.RES_SCALE
        offset_y = cfg.get("hit_offset_y", 90) * C.RES_SCALE
        if self.facing == 1:
            rect_x = self.x
        else:
            rect_x = self.x - reach
        rect_y = self.y - offset_y - height // 2
        return pygame.Rect(rect_x, rect_y, reach, height)

    def get_damage_for_state(self):
        cfg = self.animations_data.get(self.state, {})
        damage = cfg.get("damage", 5)
        if self.state == C.STATE_SPECIAL:
            damage = damage * C.SPECIAL_DAMAGE_MULT
        return damage

    def get_ranged_launch(self):
        """Si este es el frame exacto en que el ataque a distancia debe
        soltar el proyectil (y todavía no lo soltó), devuelve un dict con
        los datos para crear el Projectile. Si no, devuelve None.

        Funciona igual para STATE_RANGED (de pie) y STATE_RANGED_CROUCH
        (agachado, ver handle_input) -- cada uno usa SU PROPIA config del
        JSON (normalmente con 'launch_height' más bajo en la versión
        agachada, para poder pegarle a un rival agachado).

        Si el personaje tiene 'melee_whip': true, NUNCA suelta un
        proyectil (pega directo, ver get_active_hitbox) y esto siempre
        devuelve None."""
        if self.state not in (C.STATE_RANGED, C.STATE_RANGED_CROUCH) or self.projectile_spawned:
            return None
        cfg = self.animations_data.get(self.state, {})
        if cfg.get("melee_whip", False):
            return None
        active_frames = cfg.get("active_frames", [])
        anim = self.animations[self.state]
        if anim.index not in active_frames:
            return None

        self.projectile_spawned = True
        height = cfg.get("launch_height", "mid")
        # Los escalones y el offset de salida están en espacio base
        # (960x540) -- se escalan por C.RES_SCALE acá. "crouch_mid" es
        # el pecho estando AGACHADO (para ranged_crouch) -- claramente
        # más abajo que "mid" (pecho de pie), pero más arriba que "low"
        # (a ras del piso), ya que agachado el pecho sigue estando a una
        # altura considerable, no tirado en el piso.
        HEIGHT_OFFSETS = {"high": 220, "mid": 105, "crouch_mid": 65, "low": 25}
        offset_y = HEIGHT_OFFSETS.get(height, 105) * C.RES_SCALE
        # Ajuste fino opcional por personaje (JSON: "launch_offset_mult"),
        # para subir/bajar un poco la altura de salida sin tener que
        # inventar un nuevo escalón entre los de arriba.
        offset_y *= cfg.get("launch_offset_mult", 1.0)
        launch_x = self.x + (36 * C.RES_SCALE * self.facing)
        launch_y = self.y - offset_y

        image_paths = self.projectile_frame_paths
        mode = cfg.get("projectile_mode", "spin")
        if mode == "random" and image_paths:
            # una sola imagen, elegida al azar en CADA lanzamiento, SIN
            # girar (ej. Nico: siempre la misma bala, no gira ni cambia)
            image_paths = [random.choice(image_paths)]
        elif mode == "random_spin" and image_paths:
            # elige un objeto DISTINTO al azar en cada tiro (ej. Omar:
            # una vez llave, otra pinza, otra destornillador) y ESE gira
            # mientras vuela -- requiere que 'projectile/' tenga
            # subcarpetas (ver _resolve_projectile_frames); si por algún
            # motivo no las tiene, se degrada solo a 'spin' normal.
            if image_paths and isinstance(image_paths[0], list):
                # Por default cada subcarpeta tiene la MISMA
                # probabilidad -- pero el JSON puede pedir pesos
                # distintos con "projectile_weights" (una lista de
                # números, en el mismo orden que las subcarpetas
                # 0/, 1/, 2/... -- no hace falta que sumen 100, son
                # relativos entre sí). Ej. Adrián: el DVD plateado
                # tiene que salir 4 veces más seguido que el violeta
                # (80%/20%) sin duplicar carpetas de sprites a mano.
                weights = cfg.get("projectile_weights")
                if weights and len(weights) == len(image_paths):
                    image_paths = random.choices(image_paths, weights=weights, k=1)[0]
                else:
                    image_paths = random.choice(image_paths)

        trajectory = cfg.get("trajectory", "straight")
        end_offset_y = {"high": 220, "mid": 105, "low": 25}.get(cfg.get("arc_end_height", "high"), 220) * C.RES_SCALE

        # Para 'bounce': por defecto nace donde se lo suelta y solo cae
        # (ej. Noah, tirado desde el pecho). Si el JSON tiene
        # 'kick_height' (px), en cambio nace CON un impulso hacia arriba
        # -- como una patada de verdad -- que lo hace subir esa altura
        # aprox. antes de que la gravedad empiece a tirarlo para abajo
        # (ej. la pelota de fútbol de Javier, que nace en sus pies).
        # 'kick_height' también está en espacio base -> se escala acá.
        kick_height = cfg.get("kick_height")
        if kick_height:
            kick_height *= C.RES_SCALE
        gravity_mult = cfg.get("gravity_mult", 1.0)
        effective_gravity = C.PROJECTILE_GRAVITY * gravity_mult
        launch_vel_y = -((2 * effective_gravity * kick_height) ** 0.5) if kick_height else 0.0

        return {
            "x": launch_x,
            "y": launch_y,
            "facing": self.facing,
            "damage": cfg.get("damage", 5),
            "speed": cfg.get("speed", 9) * C.RES_SCALE,
            "image_paths": image_paths,
            "owner": self,
            "trajectory": trajectory,
            "end_y": self.y - end_offset_y,
            "arc_height": cfg.get("arc_height", 110) * C.RES_SCALE,
            "arc_range": cfg.get("arc_range", 280) * C.RES_SCALE,
            "bounce_damping": cfg.get("bounce_damping", 0.55),
            "launch_vel_y": launch_vel_y,
            "gravity_mult": gravity_mult,
            "visual_y_offset": cfg.get("visual_y_offset", 0) * C.RES_SCALE,
        }

    def receive_hit(self, damage, knockback=12, critical=False):
        if self.knocked_out:
            return
        # 'knockback' llega en espacio base (960x540) desde todos sus
        # call-sites (default acá, o el knockback=8 fijo de los
        # proyectiles en main.py) -- se escala UNA sola vez acá, así
        # cubre ambos casos sin duplicar el factor.
        knockback = knockback * C.RES_SCALE
        self.hits_taken_since_special = min(
            C.SPECIAL_HITS_REQUIRED, self.hits_taken_since_special + 1
        )
        if self.blocking:
            damage = max(1, int(damage * 0.15 * 0.4))  # bloquear reduce mucho el daño (15% del original, y de ESO un 60% menos)
            knockback = knockback * 0.3
            if not self._play_character_sound("block", volume=0.8):
                self.sound_manager.play_sfx_fallback(None, "block_impact", volume=0.8)
        else:
            # Ya no cambia de pose al recibir un golpe (se sacó la animación
            # "hit" a pedido) -- el flash blanco + el empujón + el sonido ya
            # avisan que conectó, sin interrumpir la pose actual.
            #
            # El golpe FÍSICO (el "thwack" genérico) suena SIEMPRE, pase lo
            # que pase. Aparte, si el personaje tiene su propia voz en
            # sounds/hit/ (ej. un grito/quejido), esa suena por separado
            # con una probabilidad baja (VOICE_LINE_CHANCE, 5% por
            # defecto) -- así no se escucha la voz en TODOS los golpes,
            # pero el ruido del impacto nunca falta.
            #
            # Golpe CRÍTICO (sólo puñetazo/patada, ver resolve_combat en
            # main.py, que ya viene con el daño de CRITICAL_HIT_MULT
            # aplicado si 'critical' es True): en vez del golpe normal
            # suena un efecto propio y bien distinto -- pedido explícito,
            # "es otro sound effect para hit_impact pero debería tener
            # sólo menos posibilidades de sonar".
            if critical:
                self.sound_manager.play_sfx_fallback(None, "critical_hit", volume=1.0)
            else:
                self.sound_manager.play_sfx_fallback(None, "hit_impact", volume=1.0)
            self._play_character_sound("hit", volume=1.0, chance=C.VOICE_LINE_CHANCE, force_chance=True)

        self.health = max(0, self.health - damage)
        self.vel_x = -self.facing * knockback
        self.hit_flash_timer = 0.12

        if self.health <= 0:
            self.knocked_out = True
            self.on_ground = False
            self.ko_bounces = 0
            self.ko_settled = False
            # impulso hacia arriba y hacia atrás: la caída dramática
            self.vel_y = -17 * C.RES_SCALE
            self.vel_x = -self.facing * max(knockback, 10 * C.RES_SCALE) * 1.4
            self.set_state(C.STATE_KO, force=True)
            self.play_voice("ko")

    # ------------------------------------------------------------------
    # Dibujo
    # ------------------------------------------------------------------
    def draw(self, surface, camera_x=0):
        # VIEW_PAD: en pantallas más anchas que 16:9 la ventana de pelea
        # queda centrada en el lienzo (ver C.set_resolution)
        screen_x = self.x - camera_x + C.VIEW_PAD
        anim = self.animations.get(self.state)
        frame = anim.current_frame() if anim else None
        if frame is None:
            # placeholder si falta el sprite: un rectángulo de color
            rect = pygame.Rect(0, 0, self.body_w, self.body_h)
            rect.midbottom = (screen_x, self.y)
            pygame.draw.rect(surface, (200, 60, 60), rect, border_radius=C.scaled(8))
            return

        img = frame
        # Casi todas las animaciones son de perfil, así que espejarlas
        # para el lado izquierdo funciona bien -- pero una pose más de
        # FRENTE con texto/logos en la ropa (ej. el "win" de Joaquín, con
        # el escudo y los sponsors de la camiseta) se ve mal invertida
        # (todo al revés). Config por animación: "no_flip": true en el
        # JSON para que esa puntual nunca se espeje, sea cual sea el lado.
        no_flip = self.animations_data.get(self.state, {}).get("no_flip", False)
        if self.facing == -1 and not no_flip:
            # Cacheado por cuadro: espejar un sprite grande en CADA
            # cuadro de juego pesa bastante en un celular.
            key = (self.state, anim.index if anim else 0, id(frame))
            cache = self.__dict__.setdefault("_flip_cache", {})
            flipped = cache.get(key)
            if flipped is None:
                flipped = pygame.transform.flip(img, True, False)
                cache[key] = flipped
            img = flipped

        if self.mystery:
            # silueta 100% negra, conservando la forma real (el alpha del
            # sprite) -- no revela quién es hasta reveal()
            silhouette = img.copy()
            silhouette.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
            img = silhouette
        elif self.hit_flash_timer > 0:
            flash = img.copy()
            flash.fill((255, 255, 255, 120), special_flags=pygame.BLEND_RGBA_MULT)
            img = flash

        rect = img.get_rect(midbottom=(screen_x, self.y))
        # Ajuste vertical manual opcional por animación (JSON:
        # "y_offset", en px base 960x540, escalado por C.RES_SCALE) --
        # el sprite SIEMPRE se ancla por el borde inferior de su propio
        # recuadro a self.y (el piso), así que una pose que representa
        # al personaje EN EL AIRE (ej. "win" saltando, con las piernas
        # flexionadas) terminaba con esas piernas pegadas al piso en
        # vez de levantadas -- se veía como si estuviera agachándose
        # en vez de saltando (bug reportado: "pareciera que se
        # arrodilla, pero debería ser en el aire"). Con "y_offset" se
        # puede subir (número positivo) la pose entera sin tocar su
        # tamaño ni su recorte real.
        #
        # Puede ser un solo número (mismo salto en TODOS los cuadros de
        # esa animación) o una LISTA con un valor por cuadro -- hace
        # falta cuando la animación es un salto que REBOTA (ej. "win":
        # algunos cuadros con los pies bien apoyados en el piso, otros
        # bien arriba en el aire, ver JSON de cada personaje) -- con un
        # solo número para toda la animación esos cuadros "en el piso"
        # quedaban igual de levantados que los del aire, y se seguía
        # viendo mal (bug reportado: "siguen mal las poses").
        y_offset_cfg = self.animations_data.get(self.state, {}).get("y_offset", 0)
        if isinstance(y_offset_cfg, list):
            frame_idx = anim.index if anim else 0
            y_offset_base = y_offset_cfg[frame_idx] if frame_idx < len(y_offset_cfg) else 0
        else:
            y_offset_base = y_offset_cfg
        y_offset = y_offset_base * C.RES_SCALE
        if y_offset:
            rect = img.get_rect(midbottom=(screen_x, self.y - y_offset))
        surface.blit(img, rect)
