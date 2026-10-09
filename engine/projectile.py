"""
projectile.py
---------------
Objeto lanzado por el ataque a distancia (ver Character.get_ranged_launch).
Se puede esquivar (saltando fuera de su altura) y bloquear (Character.
receive_hit ya reduce el daño solo si blocking=True).

Trayectorias soportadas (parámetro 'trajectory'):
- "straight" (por defecto): línea recta horizontal, como siempre.
- "arc": parábola de un punto de altura a otro, en un rango HORIZONTAL
  FIJO (no persigue al rival) -- ej. la pelota de Javier, que sube desde
  la altura de la patada y baja hasta la altura de cabeza.
- "bounce": cae con gravedad y va rebotando contra el piso (como el K.O.),
  hasta perder energía o salir de pantalla -- ej. la pelota picando de
  Noah (nace a la altura del pecho y solo cae) o la pelota de fútbol de
  Javier (nace al ras del piso, en sus pies, con un impulso hacia arriba
  -- 'kick_height' en el JSON -- así sube como una patada de verdad
  antes de empezar a caer y picar). El 'gravity_mult' (JSON, default 1)
  multiplica la gravedad SOLO para este proyectil: sube/baja más rápido
  sin cambiar cuánto sube en total, así el arco no se queda "pegado"
  arriba de la cabeza de un rival parado a la distancia típica de
  pelea (con gravedad normal, un tiro que sube bastante puede terminar
  volando justo por ENCIMA de la cabeza del rival en vez de pegarle,
  porque el pico de la parábola coincide con esa distancia -- subir
  más rápido en el tiempo, aunque llegue a la misma altura, angosta
  esa "zona muerta" horizontal). Avisa cuándo rebota
  (self.just_bounced) para que quien lo use pueda disparar un sonido.

Puede tener VARIOS frames (carpeta assets/characters/<nombre>/projectile/):
- Si Character los resuelve en modo "spin" (varios frames, todos usados):
  se van alternando solos mientras vuela, para un efecto de giro.
- Si Character los resuelve en modo "random" (un solo path, elegido al
  azar antes de crear el Projectile): se queda fijo con esa única imagen.
Ver Character._resolve_projectile_frames y get_ranged_launch.
"""

import os
import pygame

from engine import constants as C

# Tamaños de ícono e y el margen de cámara fuera de pantalla están
# calibrados en espacio base (960x540) -- se escalan con C.scaled() para
# verse igual de proporcionados sea cual sea C.RESOLUTION.
DEFAULT_PROJECTILE_SIZE = (C.scaled(26), C.scaled(26))
MAX_PROJECTILE_DIM = C.scaled(60)  # ningún proyectil (imagen propia de un personaje)
                              # debería superar esto de lado más largo -- si la
                              # llegara a superar (pasa si alguien sube una foto
                              # en vez de un ícono chico), se reescala para abajo
                              # preservando proporciones, en vez de tirar un
                              # proyectil gigante que además "se ve" quieto por
                              # moverse pocos píxeles relativos a su tamaño.
SPIN_FPS = 12          # a cuantos cuadros por segundo alterna los frames al girar
GRAVITY = C.PROJECTILE_GRAVITY   # para trajectory="bounce" (ya viene escalado por RES_SCALE)
MIN_BOUNCE_SPEED = C.scaled(60)   # por debajo de esto, la pelota se da por quieta/muerta


class Projectile:
    _image_cache = {}

    def __init__(self, x, y, facing, damage, speed, image_paths, owner,
                 trajectory="straight", end_y=None, arc_height=110, arc_range=280,
                 bounce_damping=0.55, launch_vel_y=0.0, gravity_mult=1.0, visual_y_offset=0):
        self.x = x
        self.y = y
        self.start_x = x
        self.start_y = y
        self.end_y = end_y if end_y is not None else y
        self.facing = facing
        self.damage = damage
        self.speed = speed
        self.vel_x = speed * facing
        self.vel_y = launch_vel_y
        self.owner = owner
        self.trajectory = trajectory
        self.arc_height = arc_height
        self.gravity_mult = gravity_mult
        self.arc_range = max(1, arc_range)
        self.arc_t = 0.0
        self.bounce_damping = bounce_damping
        self.just_bounced = False  # True el frame exacto en que rebota (para disparar sonido)
        # Corrimiento SOLO visual (no toca la caja de golpe real, ver
        # get_hitbox): para casos como el arma de Nico, donde el techo
        # universal de altura de golpe (234px, ver body_h en Character)
        # obliga a que el impacto quede más abajo de donde
        # VISUALMENTE está el caño del arma en el sprite -- así se
        # dibuja saliendo del arma de verdad, sin arriesgar que deje de
        # pegarle a nadie (el impacto sigue calculándose con self.y real).
        self.visual_y_offset = visual_y_offset

        self.frames = self._load_frames(image_paths)
        # rutas de cada cuadro (para mandárselas a los invitados en una
        # partida por WiFi, ver engine/netplay.py)
        self.frame_paths = list(image_paths) if image_paths else [None]
        self.frame_index = 0
        self.frame_timer = 0.0
        self.image = self.frames[0]
        self.w, self.h = self.image.get_size()
        self.alive = True

    @classmethod
    def _load_frames(cls, image_paths):
        if not image_paths:
            return [cls._default_image()]
        frames = [cls._load_image(path) for path in image_paths]
        return frames or [cls._default_image()]

    @classmethod
    def _load_image(cls, image_path):
        if image_path in cls._image_cache:
            return cls._image_cache[image_path]
        if image_path and os.path.isfile(image_path):
            img = pygame.image.load(image_path).convert_alpha()
            # Igual que el resto de los assets, se asume que el PNG nativo
            # fue pensado para el lienzo base (960x540) -- se reescala por
            # C.RES_SCALE siempre (antes SOLO se achicaba si superaba
            # MAX_PROJECTILE_DIM, así que un ícono nativo chico se quedaba
            # con el mismo tamaño en píxeles sin importar la resolución:
            # se veía gigante en 540p y diminuto en 1080p).
            w, h = img.get_width(), img.get_height()
            factor = C.RES_SCALE
            biggest = max(w, h) * factor
            if biggest > MAX_PROJECTILE_DIM:
                factor *= MAX_PROJECTILE_DIM / biggest
            if factor != 1.0:
                img = pygame.transform.smoothscale(
                    img,
                    (max(1, round(w * factor)), max(1, round(h * factor))),
                )
        else:
            img = cls._default_image()
        cls._image_cache[image_path] = img
        return img

    @classmethod
    def _default_image(cls):
        if "__default__" in cls._image_cache:
            return cls._image_cache["__default__"]
        surf = pygame.Surface(DEFAULT_PROJECTILE_SIZE, pygame.SRCALPHA)
        pygame.draw.circle(
            surf, (240, 200, 40, 255),
            (DEFAULT_PROJECTILE_SIZE[0] // 2, DEFAULT_PROJECTILE_SIZE[1] // 2),
            DEFAULT_PROJECTILE_SIZE[0] // 2,
        )
        cls._image_cache["__default__"] = surf
        return surf

    def update(self, dt=1 / 60, world_w=None):
        self.just_bounced = False
        if self.trajectory == "arc":
            self._update_arc()
        elif self.trajectory == "bounce":
            self._update_bounce(dt)
        else:
            self._update_straight()

        # Se descarta si sale del ESCENARIO (no de la pantalla) -- en un
        # escenario más ancho que 16:9 (ver Stage.world_w) la cámara
        # puede estar desplazada, así que un proyectil con x mayor a
        # C.SCREEN_W puede seguir estando bien a la vista.
        world_w = world_w if world_w is not None else C.LOGIC_W
        margin = C.scaled(60)
        if self.x < -margin or self.x > world_w + margin:
            self.alive = False

        if len(self.frames) > 1:
            self.frame_timer += dt
            if self.frame_timer >= 1 / SPIN_FPS:
                self.frame_timer = 0.0
                self.frame_index = (self.frame_index + 1) % len(self.frames)
                self.image = self.frames[self.frame_index]
                self.w, self.h = self.image.get_size()

    def _update_straight(self):
        self.x += self.vel_x

    def _update_arc(self):
        # avanza un % fijo del rango total por frame (proporcional a la
        # "velocidad" configurada) -- así el rango de tiro es SIEMPRE el
        # mismo, no depende de dónde esté el rival ni lo persigue.
        self.arc_t += abs(self.speed) / self.arc_range
        t = min(1.0, self.arc_t)
        self.x = self.start_x + self.facing * self.arc_range * t
        # parabola: interpola la altura de inicio a la de destino, con un
        # "envión" hacia arriba que pesa más a la mitad del recorrido
        self.y = self.start_y + (self.end_y - self.start_y) * t - self.arc_height * 4 * t * (1 - t)
        if t >= 1.0:
            self.alive = False  # termino su recorrido fijo, no sigue de largo

    def _update_bounce(self, dt):
        self.x += self.vel_x
        self.vel_y += GRAVITY * self.gravity_mult * dt
        self.y += self.vel_y * dt
        if self.y >= C.GROUND_Y:
            self.y = C.GROUND_Y
            self.vel_y = -self.vel_y * self.bounce_damping
            self.just_bounced = True
            if abs(self.vel_y) < MIN_BOUNCE_SPEED:
                self.alive = False  # se quedo sin energia para seguir rebotando

    def get_hitbox(self):
        return pygame.Rect(self.x - self.w // 2, self.y - self.h // 2, self.w, self.h)

    def draw(self, surface, camera_x=0):
        img = self.image
        if self.facing == -1:
            img = pygame.transform.flip(img, True, False)
        rect = img.get_rect(center=(self.x - camera_x + C.VIEW_PAD, self.y - self.visual_y_offset))
        surface.blit(img, rect)
