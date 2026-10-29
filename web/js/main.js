// =====================================================================
// main.js — arranque, lienzo, loop de 60 cuadros fijos y escenas
// =====================================================================
import * as C from "./config.js";
import { loadDatabase } from "./assets.js";
import { audio } from "./audio.js";
import { PlayerInput, CombinedInput, pollGamepads, endKeyboardFrame, gamepads, keyboard } from "./input.js";
import { TouchControls, IS_TOUCH_DEVICE } from "./touch.js";
import * as UI from "./ui.js";
import { loadSettings, saveSettings } from "./settings.js";
import { tickMenuVoices } from "./scenes/menus.js";
import { IS_TV, IS_APP } from "./platform.js";

const canvas = document.getElementById("game");
const ctx = canvas.getContext("2d");

export const app = {
  canvas, ctx,
  view: { w: C.BASE_W, h: C.BASE_H, pad: 0, scale: 1, ox: 0, oy: 0 },
  settings: loadSettings(),
  scene: null,
  t: 0,
  toastText: "", toastUntil: 0,
  touch: new TouchControls(),
  inputs: [],
  isTouchDevice: IS_TOUCH_DEVICE && !IS_TV,
  inviteRoom: (new URLSearchParams(location.search).get("sala") || "").trim().toLowerCase() || null,
  lastTouchAt: 0,
};

app.inputs = [new PlayerInput(0, app.settings, app.touch), new PlayerInput(1, app.settings, null)];
// "menú": cualquiera de los dos jugadores locales puede navegar
app.menuInput = app.inputs[0];
app.anyInput = new CombinedInput(app.inputs[0], app.inputs[1]);

app.setScene = (scene) => {
  if (app.scene && app.scene.exit) app.scene.exit();
  app.scene = scene;
  app.touch.releaseAll();
  if (scene && scene.enter) scene.enter();
};
app.toast = (msg, secs = 3.5) => { app.toastText = msg; app.toastUntil = performance.now() + secs * 1000; };
app.saveSettings = () => {
  saveSettings(app.settings);
  audio.setVolumes(app.settings.volumes);
};
audio.setVolumes(app.settings.volumes);

// ¿Mostrar controles táctiles? (auto = celular sin joystick conectado)
app.touchVisible = () => {
  const mode = app.settings.touchControls || "auto";
  if (mode === "on") return true;
  if (mode === "off") return false;
  if (!app.isTouchDevice) return false;
  if (gamepads.list.length && gamepads.lastUsed > app.lastTouchAt) return false;
  return true;
};

// ---------------------------------------------------------------------
// Tamaño del lienzo: alto lógico 540; si la pantalla es más ancha que
// 16:9 (celulares), el ancho lógico crece (se ve más escenario); si es
// más angosta, se agregan franjas.
// ---------------------------------------------------------------------
// El juego SIEMPRE se ve en horizontal. Si el celular está en vertical,
// el lienzo (y el panel de compartir) se dibujan girados 90°: alcanza con
// mirar el teléfono de costado, sin depender de la rotación automática.
// En Android, además, al entrar a pantalla completa se traba la pantalla
// en horizontal (ver enterFullscreen).
const stage = document.getElementById("stage");
function resize() {
  const W = window.innerWidth, H = window.innerHeight;
  // en la tele: el lienzo siempre dibuja a 1080 líneas como mínimo
  const dpr = IS_TV
    ? Math.max(window.devicePixelRatio || 1, 1080 / Math.max(1, Math.min(W, H)))
    : Math.min(window.devicePixelRatio || 1, 2);
  const v = app.view;
  const rotated = app.isTouchDevice && H > W;
  const LW = rotated ? H : W, LH = rotated ? W : H;   // pantalla "acostada"
  const aspect = LW / LH;
  let vw = C.BASE_W, scale;
  if (aspect >= C.BASE_W / C.BASE_H) {
    scale = LH / C.BASE_H;
    vw = Math.min(LW / scale, C.BASE_H * 2.4);
  } else {
    scale = LW / C.BASE_W;
  }
  const cssW = vw * scale, cssH = C.BASE_H * scale;
  stage.style.width = `${cssW}px`;
  stage.style.height = `${cssH}px`;
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  if (rotated) {
    // girado 90° horario: arriba del juego = borde derecho de la pantalla
    v.tx = (W + cssH) / 2;
    v.ty = (H - cssW) / 2;
    stage.style.transform = `translate(${v.tx}px, ${v.ty}px) rotate(90deg)`;
  } else {
    v.tx = (W - cssW) / 2;
    v.ty = (H - cssH) / 2;
    stage.style.transform = `translate(${v.tx}px, ${v.ty}px)`;
  }
  v.rotated = rotated;
  v.cssW = cssW;
  v.cssH = cssH;
  v.w = vw;
  v.pad = (vw - C.BASE_W) / 2;
  v.scale = scale * dpr;
  v.css = scale;
  v.fullH = C.BASE_H;
  v.oy = 0;
  v.portrait = false;
  app.touch.scale = (app.settings.touchScale || 100) / 100;
  app.touch.layoutFor(v);
}
window.addEventListener("resize", resize);
document.addEventListener("fullscreenchange", () => setTimeout(resize, 100));
window.addEventListener("orientationchange", () => setTimeout(resize, 200));
if (screen.orientation) screen.orientation.addEventListener("change", () => setTimeout(resize, 150));
app.relayout = resize;

// ---------------------------------------------------------------------
// Dedo / mouse
// ---------------------------------------------------------------------
// coordenadas del lienzo completo (y de 0 a fullH)
function toLogical(e) {
  const v = app.view;
  let cx, cy; // coordenadas dentro del lienzo, en px CSS (sin girar)
  if (v.rotated) { cx = e.clientY - v.ty; cy = v.tx - e.clientX; }
  else { cx = e.clientX - v.tx; cy = e.clientY - v.ty; }
  return { x: (cx / v.cssW) * v.w, y: (cy / v.cssH) * v.fullH };
}
canvas.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  audio.unlock();
  if (e.pointerType === "touch") app.lastTouchAt = performance.now();
  const p = toLogical(e);
  if (app.touch.down(e.pointerId, p.x, p.y)) {
    canvas.setPointerCapture && canvas.setPointerCapture(e.pointerId);
    return;
  }
  if (!app.fullscreenAsked && app.isTouchDevice) { app.fullscreenAsked = true; app.enterFullscreen(); }
  const gy = p.y - app.view.oy; // coordenadas de la zona de juego
  if (app.scene && app.scene.onPointer && app.scene.onPointer(p.x, gy)) return;
  const h = UI.hitAt(p.x, gy);
  if (h) h.fn();
});
canvas.addEventListener("pointermove", (e) => { const p = toLogical(e); app.touch.move(e.pointerId, p.x, p.y); });
const up = (e) => app.touch.up(e.pointerId);
canvas.addEventListener("pointerup", up);
canvas.addEventListener("pointercancel", up);
canvas.addEventListener("contextmenu", (e) => e.preventDefault());

// Pantalla completa + horizontal en celulares (requiere un toque)
app.enterFullscreen = async () => {
  const el = document.documentElement;
  try {
    if (!document.fullscreenElement) {
      if (el.requestFullscreen) await el.requestFullscreen({ navigationUI: "hide" });
      else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    }
    // Android: trabar en horizontal (la pantalla gira sola aunque el
    // celular esté en vertical). Donde no se puede (iPhone), queda el
    // lienzo girado por CSS.
    if (app.isTouchDevice && screen.orientation && screen.orientation.lock) {
      await screen.orientation.lock("landscape").catch(() => {});
    }
  } catch (e) { /* no soportado (iPhone) */ }
};
app.toggleFullscreen = async () => {
  if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
  else await app.enterFullscreen();
};

// ---------------------------------------------------------------------
// Loop
// ---------------------------------------------------------------------
let last = performance.now();
let acc = 0;
function frame(now) {
  requestAnimationFrame(frame);
  acc += Math.min(0.25, (now - last) / 1000);
  last = now;
  let steps = 0;
  while (acc >= C.DT && steps < 5) {
    pollGamepads();
    app.touch.visible = app.touchVisible();
    UI.hudOpts.showSpecialPips = !app.touch.visible;
    UI.menuOpts.touch = app.isTouchDevice;
    for (const i of app.inputs) i.poll();
    if (app.scene && app.scene.update) app.scene.update(C.DT);
    if (app.net && app.net.tick) app.net.tick(C.DT);
    if (!(app.scene && (app.scene.match || app.scene.mode === "fight" || app.scene.mode === "loading"))) tickMenuVoices(C.DT);
    endKeyboardFrame();
    app.touch.endFrame();
    app.t += C.DT;
    acc -= C.DT;
    steps++;
  }
  if (steps === 5) acc = 0;
  draw();
}

function draw() {
  const v = app.view;
  ctx.setTransform(v.scale, 0, 0, v.scale, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  UI.clearHits();
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, v.w, v.fullH);
  ctx.save();
  ctx.translate(0, v.oy);
  ctx.beginPath(); ctx.rect(0, 0, v.w, C.BASE_H); ctx.clip();
  if (app.scene && app.scene.draw) app.scene.draw(ctx, v);
  ctx.restore();
  app.touch.draw(ctx);
  ctx.save();
  ctx.translate(0, v.oy);
  if (app.toastText && performance.now() < app.toastUntil) {
    const w = UI.measure(ctx, app.toastText, 17) + 40;
    UI.roundRect(ctx, v.w / 2 - w / 2, C.BASE_H - 108, w, 38, 10);
    ctx.fillStyle = "rgba(20,20,26,0.92)";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = C.COLORS.yellow;
    ctx.stroke();
    UI.text(ctx, app.toastText, v.w / 2, C.BASE_H - 89, { size: 17 });
  }
  ctx.restore();
}


// ---------------------------------------------------------------------
async function boot() {
  resize();
  ctx.setTransform(app.view.scale, 0, 0, app.view.scale, 0, 0);
  try {
    await document.fonts.load("900 20px 'Roboto Black'");
  } catch (e) { /* sigue con fuente de respaldo */ }
  UI.fillBg(ctx, app.view);
  UI.text(ctx, "Cargando...", app.view.w / 2, C.BASE_H / 2, { size: 28 });
  try {
    await UI.loadUiImages();
    await loadDatabase();
  } catch (e) {
    UI.text(ctx, "No se pudo cargar el juego: " + e.message, app.view.w / 2, C.BASE_H / 2 + 40, { size: 16, color: C.COLORS.red });
    console.error(e);
    return;
  }
  // directo al menú principal (o a la sala, si se entró con un link de
  // invitación). El sonido se habilita con el primer toque/tecla (los
  // navegadores no dejan antes): ver audio.unlock().
  const Flow = await import("./flow.js");
  if (app.inviteRoom) Flow.joinOnline(app, app.inviteRoom);
  else if (IS_APP) {
    // apps (celular / Google TV): primero la intro en video, como en la PC
    const { IntroScene } = await import("./scenes/intro.js");
    app.setScene(new IntroScene(app, () => Flow.mainMenu(app)));
  } else Flow.mainMenu(app);
  requestAnimationFrame(frame);
}

window.__app = app; // para pruebas desde la consola

// App Android: el botón "atrás" del celular hace de ESC; en la pantalla de
// inicio / menú principal cierra la app.
window.__androidBack = () => {
  const sc = app.scene;
  const atRoot = sc && sc.constructor.name === "ListMenu" && !sc.onBack;
  if (atRoot && window.MKAndroid) { window.MKAndroid.exit(); return; }
  for (const type of ["keydown", "keyup"]) {
    window.dispatchEvent(new KeyboardEvent(type, { key: "Escape", code: "Escape", bubbles: true }));
  }
};
keyboard.listeners.push(() => audio.unlock());
boot();
