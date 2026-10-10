"""
device.py
----------
Detección de plataforma (PC vs Android) y utilidades específicas de
Android: pantalla completa al ancho real del celular, mantener la
pantalla encendida y "MulticastLock" (sin eso, muchos celulares
descartan los paquetes broadcast de WiFi que se usan para encontrar
partidas en la red local, ver engine/netplay.py).

El juego entero sigue dibujando sobre el lienzo de siempre (C.SCREEN_W x
C.SCREEN_H, 16:9). En Android la ventana real es más ancha (los
celulares son ~20:9): ese lienzo se dibuja CENTRADO y los costados
sobrantes quedan para los controles táctiles (ver engine/touch.py), que
se dibujan encima de todo, sobre la pantalla completa.

Para probar la versión táctil en PC (sin celular), correr:
    python main.py --touch
(el mouse hace de dedo; un solo "dedo" a la vez, claro).
"""

import os
import sys

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ or "ANDROID_PRIVATE" in os.environ or hasattr(sys, "getandroidapilevel")
TOUCH_SIM = "--touch" in sys.argv  # PC: simular la interfaz táctil con el mouse
TOUCH_UI = IS_ANDROID or TOUCH_SIM

# Aspecto de pantalla simulado en PC con --touch (celular típico 20:9)
SIM_ASPECT = 20 / 9

_multicast_lock = None
_wake_lock_done = False


def force_landscape():
    """Fuerza horizontal (cualquiera de los dos sentidos) desde Java.
    Llamar DESPUÉS de crear la ventana: SDL decide la orientación al
    crearla y podría pisar la del manifest."""
    if not IS_ANDROID:
        return
    try:
        from jnius import autoclass
        from android.runnable import run_on_ui_thread  # type: ignore

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        ActivityInfo = autoclass("android.content.pm.ActivityInfo")

        @run_on_ui_thread
        def _set():
            activity.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE)

        _set()
    except Exception as e:  # pragma: no cover - solo en Android
        print(f"[AVISO] No pude forzar horizontal: {e}")


def android_setup():
    """Llamar una vez al arrancar, en Android. Nunca rompe si algo
    falla (por ejemplo, si pyjnius no está disponible)."""
    global _multicast_lock, _wake_lock_done
    if not IS_ANDROID:
        return
    # pista para SDL ANTES de abrir la ventana: solo horizontal
    os.environ["SDL_IOS_ORIENTATIONS"] = "LandscapeLeft LandscapeRight"
    try:
        from jnius import autoclass, cast

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        activity = PythonActivity.mActivity
        if _multicast_lock is None:
            service = activity.getApplicationContext().getSystemService(Context.WIFI_SERVICE)
            wifi = cast("android.net.wifi.WifiManager", service)
            lock = wifi.createMulticastLock("mortal_kompa")
            lock.setReferenceCounted(False)
            lock.acquire()
            _multicast_lock = lock
    except Exception as e:  # pragma: no cover - solo en Android
        print(f"[AVISO] No pude activar MulticastLock: {e}")
    if not _wake_lock_done:
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            WindowManager = autoclass("android.view.WindowManager$LayoutParams")
            activity = PythonActivity.mActivity

            # addFlags tiene que correr en el hilo de UI de Android
            from android.runnable import run_on_ui_thread  # type: ignore

            @run_on_ui_thread
            def _keep_on():
                activity.getWindow().addFlags(WindowManager.FLAG_KEEP_SCREEN_ON)

            _keep_on()
            _wake_lock_done = True
        except Exception as e:  # pragma: no cover
            print(f"[AVISO] No pude mantener la pantalla encendida: {e}")


def android_local_ips():
    """IPs IPv4 de las interfaces de red del celular (WiFi o zona WiFi
    compartida), vía Java -- en Android los trucos de Python para saber
    la IP propia no siempre andan (sobre todo en el celular que comparte
    su zona WiFi, que muchas veces no tiene ruta a internet)."""
    if not IS_ANDROID:
        return []
    ips = []
    try:
        from jnius import autoclass

        NetworkInterface = autoclass("java.net.NetworkInterface")
        Collections = autoclass("java.util.Collections")
        for iface in Collections.list(NetworkInterface.getNetworkInterfaces()).toArray():
            try:
                if not iface.isUp() or iface.isLoopback():
                    continue
                for addr in Collections.list(iface.getInetAddresses()).toArray():
                    host = str(addr.getHostAddress())
                    if "." in host and ":" not in host and not host.startswith("127."):
                        ips.append(host)
            except Exception:
                continue
    except Exception as e:  # pragma: no cover
        print(f"[AVISO] No pude leer las IPs del celular: {e}")
    # primero las de WiFi/hotspot típicas (192.168.x / 10.x), al final datos móviles
    ips.sort(key=lambda ip: (not ip.startswith("192.168."), ip))
    return ips


def device_name():
    """Nombre corto para mostrar en el lobby de red."""
    if IS_ANDROID:
        try:
            from jnius import autoclass

            Build = autoclass("android.os.Build")
            model = str(Build.MODEL or "").strip()
            if model:
                return model[:18]
        except Exception:
            pass
        return "Celular"
    try:
        import socket

        return socket.gethostname()[:18]
    except Exception:
        return "PC"


def screen_aspect():
    """Aspecto (ancho/alto) de la pantalla real, apaisada. En PC normal
    siempre 16:9 (la ventana de siempre)."""
    if TOUCH_SIM and not IS_ANDROID:
        return SIM_ASPECT
    if not IS_ANDROID:
        return 16 / 9
    import pygame

    try:
        pygame.display.init()
        info = pygame.display.Info()
        w, h = info.current_w, info.current_h
    except Exception:
        w, h = 0, 0
    if not w or not h:
        return 16 / 9
    if h > w:
        w, h = h, w  # el juego va siempre apaisado
    return max(16 / 9, min(w / h, 2.4))


def fix_android_paths(force=False):
    """En Android, SDL interpreta una ruta RELATIVA ("assets/ui/icon.png")
    como un archivo DENTRO del paquete del APK, no en la carpeta donde se
    desempaquetó el juego -- os.path.isfile() dice que existe pero
    pygame.image.load() no lo encuentra. Acá se envuelven las funciones de
    pygame que abren archivos para que siempre reciban rutas absolutas.
    En PC no hace nada (salvo force=True, para probarlo)."""
    if not (IS_ANDROID or force):
        return
    import pygame

    def _abs(p):
        if isinstance(p, (str, bytes, os.PathLike)):
            p = os.fspath(p)
            if isinstance(p, bytes):
                p = p.decode("utf-8")
            if not os.path.isabs(p):
                return os.path.abspath(p)
        return p

    _load = pygame.image.load
    _save = pygame.image.save
    _music_load = pygame.mixer.music.load

    def image_load(file, *args, **kwargs):
        return _load(_abs(file), *args, **kwargs)

    def image_save(surface, file, *args, **kwargs):
        return _save(surface, _abs(file), *args, **kwargs)

    def music_load(file, *args, **kwargs):
        return _music_load(_abs(file), *args, **kwargs)

    class Sound(pygame.mixer.Sound):
        def __init__(self, *args, **kwargs):
            if args:
                args = (_abs(args[0]),) + tuple(args[1:])
            if "file" in kwargs:
                kwargs["file"] = _abs(kwargs["file"])
            super().__init__(*args, **kwargs)

    class Font(pygame.font.Font):
        def __init__(self, file=None, *args, **kwargs):
            super().__init__(_abs(file) if file is not None else None, *args, **kwargs)

    pygame.image.load = image_load
    pygame.image.save = image_save
    pygame.mixer.music.load = music_load
    pygame.mixer.Sound = Sound
    pygame.font.Font = Font
