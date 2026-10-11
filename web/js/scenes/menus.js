// =====================================================================
// scenes/menus.js — pantalla de inicio, menús, dificultad, opciones
// =====================================================================
import * as C from "../config.js";
import { COLORS, GAME_VERSION } from "../config.js";
import * as UI from "../ui.js";
import { audio } from "../audio.js";
import { DB } from "../assets.js";
import { ok, DEFAULT_KEYS, prettyKey, keyboard, keyLabel, PAD_LABELS, gamepads } from "../input.js";
import * as Flow from "../flow.js";

// Como en la versión de PC: los temas de menú NO se repiten en loop;
// cuando termina uno arranca otro al azar (distinto del anterior).
function randomTrack(list, exclude) {
  const pool = list.length > 1 ? list.filter((p) => p !== exclude) : list;
  return pool[Math.floor(Math.random() * pool.length)];
}

export function playMenuMusic() {
  if (audio.isMusicPlaying() && audio.musicCategory === "menu") return;
  const list = DB.menuMusic;
  if (!list.length) { audio.stopMusic(); return; }
  audio.playMusic(randomTrack(list, audio.musicPath), { loop: false, volume: 0.5 });
  audio.musicCategory = "menu";
}

audio.onMusicEnded = (path) => {
  if (audio.musicCategory !== "menu" || !DB.menuMusic.length) return;
  audio.musicPath = null;
  audio.playMusic(randomTrack(DB.menuMusic, path), { loop: false, volume: 0.5 });
  audio.musicCategory = "menu";
};

// Vocecitas random de menú (assets/sounds/menu_voices): cada 25 s hay
// 15% de chance de que suene una, nunca la misma dos veces seguidas.
// Solo mientras suena música de menú (igual que en PC).
const MENU_VOICE_INTERVAL = 25, MENU_VOICE_CHANCE = 0.15;
let menuVoiceTimer = MENU_VOICE_INTERVAL, lastMenuVoice = null;
export function tickMenuVoices(dt) {
  if (audio.musicCategory !== "menu" || !DB.menuVoices.length || audio.muted) return;
  menuVoiceTimer -= dt;
  if (menuVoiceTimer > 0) return;
  menuVoiceTimer = MENU_VOICE_INTERVAL;
  if (Math.random() < MENU_VOICE_CHANCE) {
    lastMenuVoice = randomTrack(DB.menuVoices, lastMenuVoice);
    audio.play(lastMenuVoice, 1, "sfx", true);  // local: cada celular las suyas (no se mandan por red)
  }
}

// ---------------------------------------------------------------------
// Lista genérica de opciones
// ---------------------------------------------------------------------
export class ListMenu {
  constructor(app, { title = "", items, onBack = null, centerY = null, showLogo = false, footer = null, index = 0 }) {
    this.app = app;
    this.title = title;
    this.items = items;   // [{label, action, disabled}]
    this.onBack = onBack;
    this.centerY = centerY;
    this.showLogo = showLogo;
    this.footerText = footer;
    this.index = index;
  }
  enter() { playMenuMusic(); }
  pick(i) {
    const it = this.items[i];
    if (!it || it.disabled) return;
    this.index = i;
    it.action();
  }
  update() {
    const inp = this.app.anyInput;
    const n = this.items.length;
    if (inp.justPressed("up")) this.index = (this.index - 1 + n) % n;
    else if (inp.justPressed("down")) this.index = (this.index + 1) % n;
    else if (ok(inp)) this.pick(this.index);
    else if (inp.justPressed("cancel") && this.onBack) this.onBack();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t, this.showLogo ? "title" : "select", this.showLogo ? 0.25 : 0.35);
    if (this.showLogo) UI.logo(ctx, view, 120);
    if (this.title) UI.title(ctx, view, this.title, 70);
    const cy = this.centerY ?? (this.showLogo ? 360 : 280);
    UI.menuList(ctx, view, this.items.map((i) => i.label), this.index, cy, (i) => this.pick(i),
      { disabled: this.items.map((i) => i.disabled) });
    if (this.onBack) UI.pillButton(ctx, 80, 36, "◄ VOLVER", () => this.onBack(), { size: 15, h: 36, minW: 110, color: "#3c3c48" });
    fullscreenButton(this.app, ctx, view);
    UI.footer(ctx, view, this.footerText ?? footerHelp(this.app, !!this.onBack));
  }
}

export function fullscreenButton(app, ctx, view) {
  if (!document.fullscreenEnabled || document.fullscreenElement) return;
  UI.pillButton(ctx, view.w - 110, 36, "⛶ PANTALLA COMPLETA", () => app.enterFullscreen(), { size: 13, h: 32, minW: 190, color: "#3c3c48" });
}

export function footerHelp(app, back = true) {
  if (app.touchVisible() || (app.isTouchDevice && !gamepads.list.length)) return "Tocá una opción";
  if (gamepads.list.length && gamepads.lastUsed > keyboard.lastUsed) return back ? "[dpad] elegir    [cross] confirmar    [circle] volver" : "[dpad] elegir    [cross] confirmar";
  const s = app.settings;
  const parts = [`▲▼ elegir`, `${keyLabel(s, "confirm")} / ENTER confirmar`];
  if (back) parts.push(`${keyLabel(s, "cancel")} / ESC volver`);
  return parts.join("   ·   ");
}

// ---------------------------------------------------------------------
// Pantalla de inicio ("tocá para empezar": desbloquea el audio)
// ---------------------------------------------------------------------
export class TitleScene {
  constructor(app) { this.app = app; this.t = 0; this.started = false; }
  start() {
    if (this.started) return;
    this.started = true;
    audio.unlock();
    if (this.app.isTouchDevice) this.app.enterFullscreen();
    if (this.app.inviteRoom) Flow.joinOnline(this.app, this.app.inviteRoom);
    else Flow.mainMenu(this.app);
  }
  onPointer() { this.start(); return true; }
  update(dt) {
    this.t += dt;
    const i = this.app.anyInput;
    if (["confirm", "start", "cancel", "punch", "kick"].some((a) => i.justPressed(a))) this.start();
    if (keyboard.lastUsed && performance.now() - keyboard.lastUsed < 50) this.start();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.t, "title", 0.15);
    UI.logo(ctx, view, 190, 1.15);
    if (Math.floor(this.t * 2) % 2 === 0) {
      const msg = this.app.inviteRoom
        ? (this.app.isTouchDevice ? "Te invitaron a pelear: tocá para entrar" : "Te invitaron a pelear: apretá una tecla para entrar")
        : (this.app.isTouchDevice ? "Tocá la pantalla para empezar" : "Apretá cualquier tecla para empezar");
      UI.text(ctx, msg, view.w / 2, 400, { size: 24, color: COLORS.white });
    }
    UI.text(ctx, GAME_VERSION, 14, C.BASE_H - 16, { size: 14, align: "left", color: "#aaa" });
    fullscreenButton(this.app, ctx, view);
  }
}

// ---------------------------------------------------------------------
// Dificultad (1 a 10)
// ---------------------------------------------------------------------
export class DifficultyScene {
  constructor(app, { title = "DIFICULTAD DE LA CPU", onDone, onBack }) {
    this.app = app; this.level = 5; this.onDone = onDone; this.onBack = onBack; this.title = title;
  }
  update() {
    const i = this.app.anyInput;
    if (i.justPressed("left")) this.level = Math.max(1, this.level - 1);
    else if (i.justPressed("right")) this.level = Math.min(10, this.level + 1);
    else if (ok(i)) this.onDone(this.level);
    else if (i.justPressed("cancel")) this.onBack();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, this.title, 120);
    const cx = view.w / 2, cy = 260;
    UI.text(ctx, String(this.level), cx, cy, { size: 96, color: COLORS.yellow, stroke: 8 });
    UI.text(ctx, C.DIFFICULTY_LABELS[this.level - 1], cx, cy + 75, { size: 26 });
    UI.roundButton(ctx, cx - 150, cy, 34, "−", () => { this.level = Math.max(1, this.level - 1); });
    UI.roundButton(ctx, cx + 150, cy, 34, "+", () => { this.level = Math.min(10, this.level + 1); });
    UI.pillButton(ctx, cx, cy + 150, "ELEGIR", () => this.onDone(this.level), { minW: 180 });
    UI.pillButton(ctx, 80, 40, "◄ VOLVER", () => this.onBack(), { size: 15, h: 36, minW: 110, color: "#3c3c48" });
    UI.footer(ctx, view, "◄ ► cambiar   ·   confirmar para elegir");
  }
}

// Cantidad de luchadores del torneo local (3 a 16)
export class TournamentSizeScene {
  constructor(app, { onDone, onBack }) { this.app = app; this.count = 8; this.onDone = onDone; this.onBack = onBack; }
  update() {
    const i = this.app.anyInput;
    if (i.justPressed("left")) this.count = Math.max(3, this.count - 1);
    else if (i.justPressed("right")) this.count = Math.min(16, this.count + 1);
    else if (ok(i)) this.onDone(this.count);
    else if (i.justPressed("cancel")) this.onBack();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, "TORNEO: ¿CUÁNTOS LUCHADORES?", 120);
    const cx = view.w / 2, cy = 260;
    UI.text(ctx, String(this.count), cx, cy, { size: 96, color: COLORS.yellow, stroke: 8 });
    UI.text(ctx, "Se eligen de a uno (se pueden repetir). Las peleas las juegan J1 y J2.", cx, cy + 75, { size: 17 });
    UI.roundButton(ctx, cx - 150, cy, 34, "−", () => { this.count = Math.max(3, this.count - 1); });
    UI.roundButton(ctx, cx + 150, cy, 34, "+", () => { this.count = Math.min(16, this.count + 1); });
    UI.pillButton(ctx, cx, cy + 150, "ELEGIR", () => this.onDone(this.count), { minW: 180 });
    UI.pillButton(ctx, 80, 40, "◄ VOLVER", () => this.onBack(), { size: 15, h: 36, minW: 110, color: "#3c3c48" });
  }
}

// ---------------------------------------------------------------------
// Opciones
// ---------------------------------------------------------------------
export class OptionsScene {
  constructor(app, { onBack }) {
    this.app = app; this.onBack = onBack; this.index = 0;
  }
  rows() {
    const s = this.app.settings;
    const pct = (v) => `${Math.round(v * 10)}`;
    const touchL = { auto: "Automático", on: "Siempre", off: "Nunca" };
    return [
      { label: `Música: ${pct(s.volumes.music)}`, adj: (d) => { s.volumes.music = clamp01(s.volumes.music + d * 0.1); } },
      { label: `Efectos: ${pct(s.volumes.sfx)}`, adj: (d) => { s.volumes.sfx = clamp01(s.volumes.sfx + d * 0.1); audio.playSfx("hit_impact", 1); } },
      { label: `Locutor: ${pct(s.volumes.announcer)}`, adj: (d) => { s.volumes.announcer = clamp01(s.volumes.announcer + d * 0.1); audio.playAnnouncer("fight"); } },
      { label: `Pantalla completa: ${document.fullscreenElement ? "Sí" : "No"}`, act: () => this.app.toggleFullscreen() },
      { label: `Controles táctiles: ${touchL[s.touchControls || "auto"]}`, adj: (d) => {
        const order = ["auto", "on", "off"];
        s.touchControls = order[(order.indexOf(s.touchControls || "auto") + (d > 0 ? 1 : 2)) % 3];
      } },
      { label: `Tamaño botones táctiles: ${s.touchScale || 100}%`, adj: (d) => {
        s.touchScale = Math.max(70, Math.min(140, (s.touchScale || 100) + d * 10));
        this.app.relayout();
      } },
      { label: "Controles (teclado / joystick)", act: () => this.app.setScene(new ControlsScene(this.app, { onBack: () => this.app.setScene(this) })) },
      { label: "Volver", act: () => this.back() },
    ];
  }
  back() { this.app.saveSettings(); this.onBack(); }
  update() {
    const i = this.app.anyInput;
    const rows = this.rows();
    if (i.justPressed("up")) this.index = (this.index - 1 + rows.length) % rows.length;
    else if (i.justPressed("down")) this.index = (this.index + 1) % rows.length;
    else if (i.justPressed("left") && rows[this.index].adj) { rows[this.index].adj(-1); this.app.saveSettings(); }
    else if (i.justPressed("right") && rows[this.index].adj) { rows[this.index].adj(1); this.app.saveSettings(); }
    else if (ok(i)) { const r = rows[this.index]; if (r.act) r.act(); else if (r.adj) { r.adj(1); this.app.saveSettings(); } }
    else if (i.justPressed("cancel")) this.back();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, "OPCIONES", 50);
    const rows = this.rows();
    const touch = UI.menuOpts.touch;
    const gap = touch ? 52 : 48, top = touch ? 102 : 110;
    rows.forEach((r, k) => {
      const y = top + k * gap;
      const sel = k === this.index;
      if (touch) {
        UI.roundRect(ctx, view.w / 2 - 210, y - 21, 420, 42, 21);
        ctx.fillStyle = "rgba(0,0,0,0.62)"; ctx.fill();
        ctx.strokeStyle = sel ? COLORS.yellow : "rgba(255,255,255,0.38)"; ctx.lineWidth = 2; ctx.stroke();
      } else if (sel) {
        UI.roundRect(ctx, view.w / 2 - 260, y - 20, 520, 40, 10);
        ctx.fillStyle = "rgba(240,200,40,0.14)"; ctx.fill();
        ctx.strokeStyle = COLORS.yellow; ctx.lineWidth = 2; ctx.stroke();
      }
      UI.text(ctx, r.label, view.w / 2, y, { size: touch ? 21 : 22, color: sel ? COLORS.yellow : COLORS.white });
      UI.addHit({ x: view.w / 2 - 210, y: y - gap / 2, w: 420, h: gap }, () => {
        this.index = k;
        if (r.act) r.act(); else if (r.adj) { r.adj(1); this.app.saveSettings(); }
      });
      if (r.adj) {
        const br = touch ? 20 : 16, bx = touch ? 238 : 230;
        UI.roundButton(ctx, view.w / 2 - bx, y, br, "−", () => { this.index = k; r.adj(-1); this.app.saveSettings(); });
        UI.roundButton(ctx, view.w / 2 + bx, y, br, "+", () => { this.index = k; r.adj(1); this.app.saveSettings(); });
      }
    });
    UI.footer(ctx, view, "▲▼ elegir   ·   ◄ ► ajustar   ·   volver para guardar");
  }
}
function clamp01(v) { return Math.max(0, Math.min(1, Math.round(v * 10) / 10)); }

// ---------------------------------------------------------------------
// Controles: muestra y permite reasignar el teclado de J1/J2
// ---------------------------------------------------------------------
const REMAP_ACTIONS = ["left", "right", "up", "down", "punch", "kick", "ranged", "special", "block", "start"];
const ACTION_NAMES = { left: "Izquierda", right: "Derecha", up: "Saltar", down: "Agacharse", punch: "Puño", kick: "Patada", ranged: "A distancia", special: "Especial", block: "Cubrirse", start: "Pausa" };

export class ControlsScene {
  constructor(app, { onBack }) {
    this.app = app; this.onBack = onBack; this.player = 0; this.index = 0; this.waiting = false;
    this.listener = (code) => {
      if (!this.waiting) return;
      if (code === "Escape") { this.waiting = false; return; }
      const s = this.app.settings;
      if (!s.keys) s.keys = JSON.parse(JSON.stringify(DEFAULT_KEYS));
      s.keys[this.player][REMAP_ACTIONS[this.index]] = code;
      this.waiting = false;
      this.skipFrame = true;
      this.app.saveSettings();
    };
  }
  enter() { keyboard.listeners.push(this.listener); }
  exit() { keyboard.listeners.splice(keyboard.listeners.indexOf(this.listener), 1); }
  keys() { return (this.app.settings.keys || DEFAULT_KEYS)[this.player]; }
  update() {
    if (this.waiting) return;
    if (this.skipFrame) { this.skipFrame = false; return; }
    const i = this.app.inputs[0];
    const n = REMAP_ACTIONS.length + 2;
    if (i.justPressed("up")) this.index = (this.index - 1 + n) % n;
    else if (i.justPressed("down")) this.index = (this.index + 1) % n;
    else if (i.justPressed("left") || i.justPressed("right")) this.player = 1 - this.player;
    else if (ok(i)) this.activate();
    else if (i.justPressed("cancel")) this.onBack();
  }
  activate() {
    if (this.index < REMAP_ACTIONS.length) this.waiting = true;
    else if (this.index === REMAP_ACTIONS.length) { this.app.settings.keys = null; this.app.saveSettings(); this.app.toast("Teclas por defecto restauradas"); }
    else this.onBack();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, "CONTROLES", 40);
    const cx = view.w / 2;
    UI.pillButton(ctx, cx - 110, 88, "JUGADOR 1", () => { this.player = 0; }, { size: 16, h: 34, color: this.player === 0 ? "#b08a10" : "#3c3c48" });
    UI.pillButton(ctx, cx + 110, 88, "JUGADOR 2", () => { this.player = 1; }, { size: 16, h: 34, color: this.player === 1 ? "#b08a10" : "#3c3c48" });
    const k = this.keys();
    const top = 130, gap = 30;
    REMAP_ACTIONS.forEach((a, j) => {
      const y = top + j * gap;
      const sel = j === this.index;
      UI.text(ctx, ACTION_NAMES[a], cx - 220, y, { size: 18, align: "left", color: sel ? COLORS.yellow : "#ddd" });
      const val = sel && this.waiting ? "apretá una tecla..." : prettyKey(k[a] || "-");
      UI.text(ctx, val, cx + 30, y, { size: 18, align: "left", color: sel ? COLORS.yellow : "#fff" });
      UI.text(ctx, PAD_LABELS[a] || ({ left: "◄ / stick", right: "► / stick", up: "▲ / stick", down: "▼ / stick" })[a], cx + 230, y, { size: 15, align: "left", color: "#9ab" });
      UI.addHit({ x: cx - 230, y: y - 14, w: 400, h: 28 }, () => { this.index = j; this.waiting = true; });
    });
    const yR = top + REMAP_ACTIONS.length * gap + 8;
    UI.text(ctx, "Restaurar teclas por defecto", cx, yR, { size: 18, color: this.index === REMAP_ACTIONS.length ? COLORS.yellow : "#fff" });
    UI.addHit({ x: cx - 200, y: yR - 14, w: 400, h: 28 }, () => { this.index = REMAP_ACTIONS.length; this.activate(); });
    UI.text(ctx, "Volver", cx, yR + 32, { size: 18, color: this.index === REMAP_ACTIONS.length + 1 ? COLORS.yellow : "#fff" });
    UI.addHit({ x: cx - 200, y: yR + 18, w: 400, h: 28 }, () => this.onBack());
    UI.text(ctx, "Columna celeste: joystick (posición de PlayStation / Xbox). Menús: confirmar = Puño o ENTER, volver = Patada o ESC.", cx, C.BASE_H - 18, { size: 13, color: "#bbb" });
  }
}
