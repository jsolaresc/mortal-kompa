"""
sound_manager.py
-----------------
Carga y reproduce sonidos/voces de personajes, efectos globales (golpes,
caídas), música de escenario y frases del presentador.

Si un archivo de sonido no existe todavía, el juego NO se rompe:
simplemente no suena nada (así podés probar el juego antes de grabar
las voces/sonidos definitivos). Todo lo que está en assets/sounds/ es
100% reemplazable: mismo nombre de archivo, tu propio contenido.
"""

import os
import random
import pygame

GLOBAL_SFX_DIR = os.path.join("assets", "sounds", "sfx")
ANNOUNCER_DIR = os.path.join("assets", "sounds", "announcer")
SOUND_EXTENSIONS = ("wav", "ogg", "mp3")


class SoundManager:
    def __init__(self):
        self._cache = {}
        self.sfx_mult = 1.0
        self.music_mult = 0.6
        self.stage_music_mult = 0.6
        self.announcer_mult = 1.0
        self._music_base_volume = 0.55  # ver apply_settings/play_music
        # Qué categoría de música está sonando AHORA MISMO ("menu" o
        # "stage") -- hace falta guardarla acá para que apply_settings
        # (que se llama todo el tiempo mientras se está en Opciones,
        # para escuchar el cambio al toque) sepa CUÁL de los dos
        # multiplicadores aplicarle a la música que ya está sonando.
        self._music_category = "menu"
        try:
            pygame.mixer.init()
            self.enabled = True
        except pygame.error:
            self.enabled = False

    def apply_settings(self, settings):
        """Aplica los multiplicadores de volumen desde Opciones (0.0-1.0
        por categoría). Se puede llamar de nuevo en cualquier momento
        (de hecho se llama en cada cuadro mientras se está en Opciones,
        para que mover el control se escuche al toque)."""
        self.sfx_mult = settings.get("sfx_volume", 1.0)
        self.music_mult = settings.get("music_volume", 0.6)
        self.stage_music_mult = settings.get("stage_music_volume", 0.6)
        self.announcer_mult = settings.get("announcer_volume", 1.0)
        if self.enabled:
            try:
                # OJO: tiene que ser 'volumen base de ESTA canción *
                # multiplicador', igual que play_music -- поner solo el
                # multiplicador acá (como estaba antes) pisaba el volumen
                # real con el que se la había puesto a sonar, y al entrar
                # a Opciones la música pegaba un salto para arriba de la
                # nada (bug reportado).
                mult = self.stage_music_mult if self._music_category == "stage" else self.music_mult
                pygame.mixer.music.set_volume(self._music_base_volume * mult)
            except pygame.error:
                pass

    def _load(self, path):
        if not self.enabled:
            return None
        if path in self._cache:
            return self._cache[path]
        if not path or not os.path.isfile(path):
            self._cache[path] = None
            return None
        try:
            sound = pygame.mixer.Sound(path)
            self._cache[path] = sound
            return sound
        except pygame.error:
            self._cache[path] = None
            return None

    def play(self, path, volume=1.0):
        sound = self._load(path)
        if sound:
            sound.set_volume(volume * self.sfx_mult)
            sound.play()

    def _find_in_dir(self, directory, name):
        """Busca el efecto 'name' en 'directory' -- puede ser UN sólo
        archivo (<name>.wav/.ogg/.mp3, como siempre) O una CARPETA
        <name>/ con VARIAS variantes adentro, en cuyo caso elige una al
        azar cada vez (pedido explícito: "son varios audios en uno...
        programá para que suenen de forma aleatoria" -- ej. hit_impact
        con varios golpes distintos). El resto de los efectos globales,
        que siguen siendo un solo archivo, no se ven afectados."""
        folder = os.path.join(directory, name)
        if os.path.isdir(folder):
            files = [
                os.path.join(folder, f) for f in os.listdir(folder)
                if f.lower().endswith(tuple("." + e for e in SOUND_EXTENSIONS))
            ]
            if files:
                return random.choice(files)
        for ext in SOUND_EXTENSIONS:
            p = os.path.join(directory, f"{name}.{ext}")
            if os.path.isfile(p):
                return p
        return None

    def play_sfx_fallback(self, character_specific_path, global_name, volume=1.0):
        """Reproduce el sonido propio del personaje si existe (ej. su propio
        'hit.wav'); si no lo tiene, busca un efecto genérico en
        assets/sounds/sfx/<global_name>.(wav|ogg|mp3)."""
        if character_specific_path and os.path.isfile(character_specific_path):
            self.play(character_specific_path, volume)
            return
        p = self._find_in_dir(GLOBAL_SFX_DIR, global_name)
        if p:
            self.play(p, volume)

    def play_announcer(self, name, volume=1.0):
        """Reproduce una frase del presentador desde assets/sounds/announcer/
        (ej. 'fight', 'round1'). Reemplazá esos archivos por tu propia voz
        cuando quieras."""
        p = self._find_in_dir(ANNOUNCER_DIR, name)
        if p:
            self.play_raw(p, volume * self.announcer_mult)

    def get_announcer_duration(self, name):
        """Duración real (en segundos) de un clip del presentador, o 0.0
        si no existe. Se usa para calcular CUÁNTO esperar antes de que
        arranque el siguiente audio (ej. "Round X" y después "FIGHT")
        en vez de usar un tiempo fijo a ojo -- así, si el día de mañana
        se reemplaza un audio por uno más largo o más corto, se siguen
        escuchando bien separados sin superponerse, sin tener que
        retocar ninguna constante a mano (ver ROUND_INTRO_* en main.py)."""
        p = self._find_in_dir(ANNOUNCER_DIR, name)
        sound = self._load(p) if p else None
        return sound.get_length() if sound else 0.0

    def play_loop(self, path, volume=1.0):
        """Arranca un sonido en LOOP en un canal propio (no se pisa con
        otros efectos) y devuelve ese canal para poder pararlo después
        con stop_loop(). Se usa para proyectiles que suenan mientras
        están en pantalla (ej. las tijeras de Sonia abriendo/cerrando, o
        la pelota de Noah picando) -- en vez de un sonido de un solo
        disparo al lanzar (eso sigue siendo _play_character_sound normal).
        Devuelve None si no hay canal libre o el sonido no existe."""
        sound = self._load(path)
        if not sound:
            return None
        channel = pygame.mixer.find_channel()
        if not channel:
            return None
        sound.set_volume(volume * self.sfx_mult)
        channel.play(sound, loops=-1)
        return channel

    def stop_loop(self, channel):
        """Para un canal devuelto por play_loop(). Tolera None (por si el
        proyectil nunca llegó a conseguir canal) y tolera que ya esté
        parado -- nunca rompe nada si se llama de más."""
        if channel is not None:
            try:
                channel.stop()
            except pygame.error:
                pass

    def play_raw(self, path, volume):
        """Como play(), pero sin volver a aplicar el multiplicador de sfx
        (para categorías que ya vienen multiplicadas, como el presentador)."""
        sound = self._load(path)
        if sound:
            sound.set_volume(volume)
            sound.play()

    def play_music(self, path, volume=0.55, loop=True, category="menu"):
        """'category': "menu" (música de menús/pantallas de resultado,
        multiplicador MUSIC_VOLUME) o "stage" (música propia de cada
        escenario durante la pelea, multiplicador STAGE_MUSIC_VOLUME
        aparte -- pedido explícito: separar el volumen de la música de
        escenario del de menú)."""
        if not self.enabled or not path or not os.path.isfile(path):
            return
        try:
            self._music_base_volume = volume
            self._music_category = category
            mult = self.stage_music_mult if category == "stage" else self.music_mult
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(volume * mult)
            pygame.mixer.music.play(-1 if loop else 0)
        except pygame.error:
            pass

    def stop_music(self):
        if self.enabled:
            try:
                pygame.mixer.music.stop()
            except pygame.error:
                pass

    def pause_music(self):
        if self.enabled:
            try:
                pygame.mixer.music.pause()
            except pygame.error:
                pass

    def is_music_playing(self):
        return self.enabled and pygame.mixer.music.get_busy()

    def unpause_music(self):
        if self.enabled:
            try:
                pygame.mixer.music.unpause()
            except pygame.error:
                pass

    def pause_all_sfx(self):
        """Pausa TODOS los canales de efectos (golpes, voces, y los
        loops de proyectil como la pelota de Noah o las tijeras de
        Sonia) -- pause_music() de arriba solo frena la música, no esto.
        Sin esto, un proyectil en loop seguía sonando de fondo aunque el
        juego estuviera en pausa (bug reportado)."""
        if self.enabled:
            try:
                pygame.mixer.pause()
            except pygame.error:
                pass

    def unpause_all_sfx(self):
        if self.enabled:
            try:
                pygame.mixer.unpause()
            except pygame.error:
                pass

    def stop_all_sfx(self):
        """Corta en seco TODOS los canales de efectos/voces (no la
        música, esa sigue con stop_music()/play_music() como siempre).
        Se usa al volver al menú principal después de una pelea/torneo,
        para que una voz larga (ej. "Win" de un personaje) no se quede
        sonando de fondo pisada con la música del menú -- antes se
        cortaba sola solo si terminaba a tiempo, ahora se corta siempre
        de una al volver al menú (bug reportado con el "Win" de Nico)."""
        if self.enabled:
            try:
                pygame.mixer.stop()
            except pygame.error:
                pass
