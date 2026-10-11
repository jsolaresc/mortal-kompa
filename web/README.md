# Mortal Kompa — versión navegador

Se juega desde una página web: PC (teclado o joystick), Android y iPhone
(controles táctiles). No hace falta instalar nada.

## Cómo se juega
- **PC:** J1 `A D` moverse · `W` saltar · `S` agacharse · `J` puño · `K` patada ·
  `I` a distancia · `L` especial · `O` cubrirse · `ENTER` pausa. J2: flechas +
  `1 2 3 4 5`. Joystick: □ puño · ✕ patada · ○ distancia · △ especial · R1 cubrirse.
  Las teclas se cambian en Opciones > Controles.
- **Celular:** joystick a la izquierda y botones a la derecha, como en el APK. El
  juego siempre se ve en horizontal (si el celular está vertical, se dibuja ya
  acostado). Al primer toque pasa a pantalla completa (Android). En iPhone,
  Safari no deja poner páginas en pantalla completa: *Compartir > Agregar a
  pantalla de inicio* y abrirlo desde ese ícono.
- **Escenario secreto:** en la elección de escenario, START / ENTER.

## Online: invitar por link
Multijugador → **Online: invitar por link**. Aparece el link para mandar por
WhatsApp, mail o copiarlo. Quien lo abre (en cualquier celular o PC, no hace
falta estar en la misma red) entra a la sala. El anfitrión elige **Pelea 1 vs 1**
o **Torneo** (3 o más).

- El que invita corre la pelea; los demás le mandan sus botones y reciben lo que
  hay que dibujar, directo entre navegadores (WebRTC). Para "presentarlos" se usa
  el servidor público gratuito de PeerJS.
- Si alguien nunca logra conectarse (pasa en algunas redes de datos móviles muy
  cerradas), hace falta un servidor TURN en `js/config.js` (`ICE_SERVERS`).
- El invitado siente un pequeño retraso en sus golpes (lo que tarda internet).

## Probarlo en la PC
Los navegadores no dejan abrir `index.html` con doble clic: usá
**`Jugar en mi PC.bat`** (necesita Python) y entrá a `http://localhost:8000`.
Para probar el online en una sola PC, sin internet: `http://localhost:8000/?net=local`,
creá la sala y abrí el link de invitación en otra pestaña.

## Actualizar personajes / escenarios / música
Todo sale del proyecto del APK. Desde la raíz del repo:

    python tools/build_web.py --audio-src "RUTA\AL\JUEGO\DE\PC"

- Los personajes se procesan con el motor Python real (mismas correcciones de
  tamaño/zoom que el juego) y se guardan ya listos para el navegador.
- `--audio-src` toma los audios ORIGINALES de la versión de PC (mp3). Sin eso,
  convierte los .ogg del APK (el iPhone no reproduce .ogg).
- Los escenarios que en PC son video, acá también (en 720p, livianos).

## Publicación
`.github/workflows/pages.yml` publica la carpeta `web/` en GitHub Pages cada vez
que cambia. Requiere (una sola vez) que el repo sea público y en
*Settings > Pages > Build and deployment > Source* elegir **GitHub Actions**.

El motor JS es el de Mortal Kompa Político (misma jugabilidad), con la música en
lista, las vocecitas de menú, la pose aparte para el lado derecho y escenarios sin
deformar en pantallas anchas.
