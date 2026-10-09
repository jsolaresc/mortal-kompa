[app]
# Nombre que aparece debajo del ícono en el celular
title = Mortal Kompa
package.name = mortalkompa
package.domain = ar.joaquin
source.dir = .
source.include_exts = py,png,jpg,jpeg,ogg,wav,ttf,json,txt
source.exclude_dirs = bin,.buildozer,.github,build_android,tools
source.exclude_patterns = buildozer.spec,README*.md
# La versión real la pone el build automático (1.3.<número de build>)
version = 1.3.0

requirements = python3,pygame,pyjnius,android

icon.filename = %(source.dir)s/build_android/icon.png
presplash.filename = %(source.dir)s/build_android/presplash.png
android.presplash_color = #141418

# Apaisado (se puede girar el celular para cualquiera de los dos lados)
orientation = sensorLandscape
fullscreen = 1

# Red local (multijugador WiFi) + mantener la pantalla prendida
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE, CHANGE_WIFI_MULTICAST_STATE, WAKE_LOCK
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = False
p4a.bootstrap = sdl2

[buildozer]
log_level = 2
warn_on_root = 1
