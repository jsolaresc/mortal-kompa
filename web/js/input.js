// =====================================================================
// input.js — teclado, joysticks (Gamepad API), táctil, CPU y red
// ---------------------------------------------------------------------
// Igual que en Mortal Kompa: cada jugador tiene ENTRADA DUAL (teclado +
// joystick a la vez; cualquiera activa la acción). Todos los "controles"
// exponen pressed(acción) / justPressed(acción), así Character no sabe
// si lo maneja una persona, la CPU o alguien por internet.
// =====================================================================
import { ACTIONS, SPECIAL_HITS_REQUIRED } from "./config.js";

export const DEFAULT_KEYS = [
  { left: "KeyA", right: "KeyD", up: "KeyW", down: "KeyS", punch: "KeyJ", kick: "KeyK", special: "KeyL", ranged: "KeyI", block: "KeyO", start: "Enter" },
  { left: "ArrowLeft", right: "ArrowRight", up: "ArrowUp", down: "ArrowDown", punch: "Numpad1", kick: "Numpad2", special: "Numpad5", ranged: "Numpad3", block: "Numpad4", start: "NumpadEnter" },
];
// alternativas fijas (fila de números además del teclado numérico)
const EXTRA_KEYS = [
  { confirm: ["Space"], cancel: ["Escape", "Backspace"] },
  { punch: ["Digit1"], kick: ["Digit2"], ranged: ["Digit3"], block: ["Digit4"], special: ["Digit5"], start: ["Digit0"] },
];
const FALLBACK = { confirm: "punch", cancel: "kick" };

// Mapeo "standard" de la Gamepad API: misma POSICIÓN física que en la PC
// (Cuadrado/X = puño, Cruz/A = patada, Círculo/B = distancia,
// Triángulo/Y = especial, R1/RB = cubrirse, Options/Start = pausa)
export const PAD_BUTTONS = {
  kick: [0], ranged: [1], punch: [2], special: [3], block: [5, 7, 4], start: [9],
  confirm: [0], cancel: [1], up: [12], down: [13], left: [14], right: [15],
};
export const PAD_LABELS = { punch: "□/X", kick: "✕/A", ranged: "○/B", special: "△/Y", block: "R1", start: "START", confirm: "✕/A", cancel: "○/B" };

// ---------------------------------------------------------------------
// Teclado (global)
// ---------------------------------------------------------------------
const keysDown = new Set();
const keyEdges = new Set();     // teclas que se apretaron desde el último poll
export const keyboard = { lastUsed: 0, listeners: [] };

window.addEventListener("keydown", (e) => {
  if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
  if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space", "Backspace", "Tab"].includes(e.code)) e.preventDefault();
  if (!e.repeat) {
    keysDown.add(e.code);
    keyEdges.add(e.code);
    for (const fn of keyboard.listeners) fn(e.code);
  }
  keyboard.lastUsed = performance.now();
});
window.addEventListener("keyup", (e) => keysDown.delete(e.code));
window.addEventListener("blur", () => keysDown.clear());

export function endKeyboardFrame() { keyEdges.clear(); }
export function escJustPressed() { return keyEdges.has("Escape"); }
// confirmar en menús: confirmar o Start/Enter
export function ok(inp) { return inp.justPressed("confirm") || inp.justPressed("start"); }
function keyActive(code) { return keysDown.has(code) || keyEdges.has(code); }

// ---------------------------------------------------------------------
// Joysticks
// ---------------------------------------------------------------------
export const gamepads = { list: [], lastUsed: 0, onChange: null };
const padEdge = new Map(); // index -> Set(botones apretados desde el último poll)

// App de Google TV: Android lee los joysticks y los pasa acá (mismo
// formato "standard" que la Gamepad API: 17 botones + stick izquierdo)
const nativePads = [];
window.__mkPad = (slot, bits, ax, ay) => {
  if (bits < 0) { nativePads[slot] = null; return; }
  const buttons = [];
  for (let k = 0; k < 17; k++) { const p = !!(bits & (1 << k)); buttons.push({ pressed: p, value: p ? 1 : 0 }); }
  nativePads[slot] = { id: `android-${slot}`, index: slot, connected: true, mapping: "standard", buttons, axes: [ax || 0, ay || 0, 0, 0] };
};

export function pollGamepads() {
  const nat = nativePads.filter(Boolean);
  const raw = nat.length ? nat : navigator.getGamepads ? Array.from(navigator.getGamepads()) : [];
  const list = raw.filter((g) => g && g.connected);
  const changed = list.length !== gamepads.list.length;
  gamepads.list = list;
  for (const g of list) {
    if (g.buttons.some((b) => b.pressed) || g.axes.some((a) => Math.abs(a) > 0.5)) gamepads.lastUsed = performance.now();
  }
  if (changed && gamepads.onChange) gamepads.onChange(list.length);
}

function padFor(slot) {
  // Jugador 1 = primer joystick conectado, Jugador 2 = el segundo
  return gamepads.list[slot] || null;
}

function padAction(pad, action) {
  if (!pad) return false;
  const btns = PAD_BUTTONS[action] || [];
  for (const b of btns) if (pad.buttons[b] && pad.buttons[b].pressed) return true;
  const dz = 0.35;
  const ax = pad.axes[0] || 0, ay = pad.axes[1] || 0;
  if (action === "left" && ax < -dz) return true;
  if (action === "right" && ax > dz) return true;
  if (action === "up" && ay < -dz * 1.6) return true;
  if (action === "down" && ay > dz * 1.6) return true;
  if (FALLBACK[action]) return false;
  return false;
}

// ---------------------------------------------------------------------
// Base
// ---------------------------------------------------------------------
export class InputState {
  constructor() {
    this.cur = {};
    this.prev = {};
    for (const a of ACTIONS) { this.cur[a] = false; this.prev[a] = false; }
  }
  pressed(a) { return !!this.cur[a]; }
  justPressed(a) { return !!this.cur[a] && !this.prev[a]; }
  poll() {}
  // bitmask compacto (para mandar por red)
  mask() { let m = 0; ACTIONS.forEach((a, i) => { if (this.cur[a]) m |= 1 << i; }); return m; }
}

export class IdleInput extends InputState {}
export const IDLE = new IdleInput();

// Jugador local: teclado (perfil 0 o 1) + joystick (slot 0 o 1) + táctil
export class PlayerInput extends InputState {
  constructor(slot, settings, touch = null) {
    super();
    this.slot = slot;
    this.settings = settings;
    this.touch = touch;
    this.extraPresses = new Set(); // toques en pantalla sobre botones de menú, etc.
  }
  keysFor(action) {
    const prof = (this.settings.keys && this.settings.keys[this.slot]) || DEFAULT_KEYS[this.slot] || {};
    const out = [];
    if (prof[action]) out.push(prof[action]);
    const extra = EXTRA_KEYS[this.slot] && EXTRA_KEYS[this.slot][action];
    if (extra) out.push(...extra);
    return out;
  }
  read(action) {
    for (const k of this.keysFor(action)) if (keyActive(k)) return true;
    const pad = padFor(this.slot);
    if (padAction(pad, action)) return true;
    if (this.touch && this.touch.isPressed(action)) return true;
    if (this.extraPresses.has(action)) return true;
    const fb = FALLBACK[action];
    if (fb) {
      for (const k of this.keysFor(fb)) if (keyActive(k)) return true;
    }
    return false;
  }
  inject(action) { this.extraPresses.add(action); }
  poll() {
    this.prev = this.cur;
    const c = {};
    for (const a of ACTIONS) c[a] = this.read(a);
    this.cur = c;
    this.extraPresses.clear();
  }
}

// Suma de varios controles (ej. "cualquiera puede confirmar")
export class CombinedInput extends InputState {
  constructor(...inputs) { super(); this.inputs = inputs; }
  pressed(a) { return this.inputs.some((i) => i.pressed(a)); }
  justPressed(a) { return this.inputs.some((i) => i.justPressed(a)); }
}

// Control de un jugador por internet: llega una máscara de botones +
// contadores de "apretadas" (así un toque cortísimo entre dos cuadros
// del anfitrión no se pierde).
export class RemoteInput extends InputState {
  constructor() {
    super();
    this.mask_ = 0;
    this.counts = new Array(ACTIONS.length).fill(0);
    this.seen = new Array(ACTIONS.length).fill(0);
    this.edge = new Array(ACTIONS.length).fill(false);
  }
  receive(mask, counts) {
    this.mask_ = mask;
    if (counts) this.counts = counts;
  }
  poll() {
    this.prev = this.cur;
    const c = {};
    ACTIONS.forEach((a, i) => {
      const newPress = this.counts[i] > this.seen[i];
      this.seen[i] = this.counts[i];
      // si hubo una apretada nueva y ya está soltado, igual cuenta
      // como "apretado" este cuadro (y el anterior como suelto)
      c[a] = !!(this.mask_ & (1 << i)) || newPress;
      if (newPress) this.prev[a] = false;
    });
    this.cur = c;
  }
}

// ---------------------------------------------------------------------
// CPU — misma lógica que CPUInput de Mortal Kompa
// ---------------------------------------------------------------------
export class CPUInput extends InputState {
  static LEVELS = 10;
  constructor(difficulty = 5) {
    super();
    this.difficulty = Math.max(1, difficulty);
    const d = (this.difficulty - 1) / (CPUInput.LEVELS - 1);
    this.reactionTime = Math.max(0.03, 0.45 - 0.38 * d);
    this.aggression = Math.min(0.98, 0.15 + 0.55 * d);
    this.blockChance = Math.min(0.97, 0.05 + 0.75 * d);
    this.mistakeChance = Math.max(0.0, 0.35 - 0.32 * d);
    this.timer = 0;
    this.lastHealth = null;
    this.consecutiveHits = 0;
    this.forceDefend = false;
  }

  clear() { const c = {}; for (const a of ACTIONS) c[a] = false; return c; }

  thinkFight(dt, me, opp) {
    this.prev = { ...this.cur };
    this.timer -= dt;
    if (this.timer > 0) return;
    this.timer = this.reactionTime;

    if (this.lastHealth !== null && me.health < this.lastHealth) this.consecutiveHits += 1;
    if (["punch", "kick", "special", "ranged"].includes(me.state) && me.attackHasHit) {
      this.consecutiveHits = Math.max(0, this.consecutiveHits - 1);
    }
    this.lastHealth = me.health;

    const s = this.clear();
    this.cur = s;
    this.forceDefend = false;
    if (Math.random() < this.mistakeChance) return;

    const distance = Math.abs(opp.x - me.x);
    const meleeRange = 90, rangedEngage = 420, blockMelee = 150, panicRetreat = 200;
    const oppMelee = ["punch", "kick", "special"].includes(opp.state);
    const oppRanged = opp.state === "ranged";
    const toward = opp.x > me.x ? "right" : "left";
    const away = opp.x > me.x ? "left" : "right";

    if (this.consecutiveHits >= 3) {
      if (distance < panicRetreat) {
        s.block = true;
        this.forceDefend = true;
        if (distance < meleeRange && Math.random() < 0.2) {
          s.block = false;
          this.forceDefend = false;
          s[Math.random() < 0.6 ? "punch" : "kick"] = true;
        }
      } else {
        s[toward] = true;
      }
      return;
    }

    const threat = (oppMelee && distance < blockMelee) || oppRanged;
    if (threat && Math.random() < this.blockChance) { s.block = true; return; }

    if (distance <= meleeRange) {
      if (Math.random() < this.aggression) {
        const c = Math.random();
        if (c < 0.45) s.punch = true;
        else if (c < 0.8) s.kick = true;
        else if (c < 0.92 && me.hitsTakenSinceSpecial >= SPECIAL_HITS_REQUIRED) s.special = true;
        else s.ranged = true;
      } else if (Math.random() < 0.3) {
        s[away] = true;
      }
    } else if (distance <= rangedEngage) {
      if (Math.random() < this.aggression * 0.8) s.ranged = true;
      else {
        s[toward] = true;
        if (Math.random() < 0.03 * (this.difficulty / CPUInput.LEVELS)) s.up = true;
      }
    } else {
      s[toward] = true;
      if (Math.random() < 0.03 * (this.difficulty / CPUInput.LEVELS)) s.up = true;
    }
  }
}

// Etiqueta corta de la tecla/botón asignado (para los textos de ayuda)
export function keyLabel(settings, action, slot = 0) {
  if (gamepads.list.length > slot && performance.now() - gamepads.lastUsed < 60000 && gamepads.lastUsed > keyboard.lastUsed) {
    return PAD_LABELS[action] || action.toUpperCase();
  }
  const prof = (settings.keys && settings.keys[slot]) || DEFAULT_KEYS[slot];
  let code = prof[action] || (FALLBACK[action] && prof[FALLBACK[action]]);
  if (action === "confirm" && slot === 0) code = prof.punch;
  if (!code) return action.toUpperCase();
  return prettyKey(code);
}

export function prettyKey(code) {
  const nice = { ArrowLeft: "◄", ArrowRight: "►", ArrowUp: "▲", ArrowDown: "▼", Enter: "ENTER", Space: "ESPACIO", Escape: "ESC", NumpadEnter: "ENTER" };
  if (nice[code]) return nice[code];
  return code.replace(/^Key/, "").replace(/^Digit/, "").replace(/^Numpad/, "NUM ").toUpperCase();
}
