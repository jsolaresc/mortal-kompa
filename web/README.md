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

## Instalar
En el menú principal, desde el celular, aparece **INSTALAR**:
- **Android:** baja el APK (la app es este mismo juego, en pantalla completa).
- **iPhone:** explica cómo agregar el ícono (Safari > Compartir > Agregar a
  pantalla de inicio). Safari no deja que una página lo haga sola.

## Online: invitar por link
Multijugador → **Online** → **2 Jugadores** o **Torneo**. Aparece el link para
copiarlo o compartirlo (WhatsApp, mail...). Quien lo abre (en cualquier celular o PC, no hace
falta estar en la misma red) entra a la sala y el anfitrión arranca cuando
están todos (torneo: 3 o más). También se puede entrar con
**Online > Unirse con un link** (pegando el link): útil desde la app de Android.
La app y el navegador juegan juntos.

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
Pages está en *Deploy from a branch: main / (root)*: GitHub publica el repo y el
`index.html` de la raíz redirige a esta carpeta. Cada push a `main` actualiza la
página en un par de minutos: https://jsolaresc.github.io/mortal-kompa/

El motor JS es el de Mortal Kompa Político (misma jugabilidad), con la música en
lista, las vocecitas de menú, la pose aparte para el lado derecho y escenarios sin
deformar en pantallas anchas.
