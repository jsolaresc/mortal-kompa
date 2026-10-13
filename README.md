# Mortal Kompa — navegador y Android

**Un solo juego para todo:** la carpeta `web/` es Mortal Kompa en JavaScript.
- **Navegador** (PC, Android, iPhone): https://jsolaresc.github.io/mortal-kompa/
- **App Android (APK):** es ese mismo juego adentro de una app (`android_app/`),
  en pantalla completa y con todos los archivos incluidos. Cada cambio en `web/`
  compila un APK nuevo solo (pestaña **Actions**) y lo publica en **Releases**.
- La app y la página juegan **online entre sí** (link de invitación).

La versión instalable de PC (Python, escenarios en video) no se toca desde acá.
El código Python de la app vieja queda en el repo como referencia
(`main.py`, `engine/`, `buildozer.spec`); ya no se compila.

## Instalar en un celular
1. Desde el celular, en la página del juego: menú principal → **INSTALAR** (baja
   el APK). O en este repo → **Releases** → `MortalKompa.apk`.
2. Abrilo y aceptá "instalar apps de origen desconocido" si lo pide.
3. La primera vez que se abre tarda unos segundos más (descomprime los
   personajes y la música).

Para actualizar, instalá el APK nuevo encima: no hace falta desinstalar
(todos los builds se firman con la misma llave, `build_android/debug.keystore`).

## Controles
- Izquierda: joystick (en pelea aparece donde apoyás el dedo).
- Derecha: Puño, Patada, Distancia, Especial y Bloqueo.
- El botón de Especial arranca con candado y se va llenando con cada golpe que
  recibís; con 5 golpes se habilita (brilla).
- Arriba a la izquierda, debajo del nombre: pausa. Botón "Atrás" del celular: volver / pausa.
- En los menús se puede tocar directamente las opciones y las caras.

## Multijugador (WiFi)
Todos los celulares en la **misma red WiFi**. Si no hay WiFi, uno comparte
datos ("Zona WiFi" / hotspot) y los demás se conectan a esa red (no gasta datos:
el juego no usa internet).

1. Uno: Multijugador → **Crear partida**. Queda en la sala, con su IP en pantalla.
2. Los demás: Multijugador → **Unirse a partida** → tocan la partida que aparece
   (si no aparece sola: "Escribir IP a mano" con la IP que muestra el anfitrión).
3. El anfitrión elige **1 vs 1** (con 1 invitado o más; el resto mira) o
   **Torneo** (3 jugadores o más: cada uno elige su luchador en su celular).

## Para desarrolladores
- El código es el mismo que el de PC; `engine/device.py` detecta Android.
- Para probar la interfaz táctil en PC: `python main.py --touch` (el mouse hace de dedo).
- `build_android/prepare_android.py` arma esta carpeta desde la versión de PC
  (saca la intro, pasa los escenarios en video a captura fija y el audio a .ogg).
- `tools/build_web.py` arma los personajes, escenarios y sonidos de la versión
  de navegador (`web/`) a partir de este mismo proyecto (ver `web/README.md`).
