# Mortal Kompa — versión Android

Este repo es la versión para celular de Mortal Kompa (V.1.3). Cada vez que se
sube un cambio a `main`, GitHub compila solo el APK (pestaña **Actions**) y lo
publica en **Releases**.

## Instalar en un celular
1. En el celular, entrá a este repo (logueado en GitHub) → **Releases** → el
   último "Mortal Kompa Android (build N)" → tocá el `.apk`.
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
- Arriba a la derecha: pausa. Botón "Atrás" del celular: volver / pausa.
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
