// =====================================================================
// touch.js — controles táctiles para celular (joystick + botones)
// Misma ubicación, tamaño y comportamiento que la versión Android de
// Mortal Kompa (engine/touch.py):
//   - Izquierda: joystick flotante (aparece donde apoyás el dedo, en la
//     mitad izquierda; si no hay dedo queda de guía abajo a la izquierda).
//   - Derecha: abanico para el pulgar con Patada, Puño, Distancia,
//     Especial y Bloqueo. El botón de Especial REEMPLAZA a los 5 pips del
//     HUD: arranca con candado y un aro de 5 partes que se va llenando.
//   - Arriba a la izquierda (debajo del nombre del J1): pausa.
// Solo se muestran en las pantallas de pelea; en los menús se toca
// directo la opción.
// =====================================================================
import * as C from "./config.js";
import { text, IMG } from "./ui.js";

export const IS_TOUCH_DEVICE = (() => {
  const coarse = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
  return !!(coarse || ("ontouchstart" in window && navigator.maxTouchPoints > 0));
})();

const COLORS = { punch: "#4696eb", kick: "#eb5a50", ranged: "#3cbe78", special: "#f0be28", block: "#9696a5" };
const LABELS = { punch: "PUÑO", kick: "PATADA", ranged: "DISTANCIA", special: "ESPECIAL", block: "BLOQUEO" };
// disco real de los PNG de especial (las llamas que sobresalen no cuentan)
const SPECIAL_DISC = { ox: -0.006, oy: 0.096, fr: 0.889 };

export class TouchControls {
  constructor() {
    this.pointers = new Map(); // id -> {kind:'joy'|'btn', ...}
    this.joy = null;           // {bx, by, x, y}
    this.fightMode = false;
    this.visible = false;
    this.pauseTapped = false;
    this.edges = new Set();    // botones tocados desde el último cuadro (toques cortísimos)
    this.specialCharge = 0;
    this.scale = 1;
    this.layoutFor({ w: C.BASE_W, pad: 0 });
  }

  // u(): mismas medidas que la versión Android (calibradas sobre una
  // pantalla de 720 px de alto) llevadas al lienzo de 540 de alto.
  layoutFor(view) {
    const dw = view.w, dh = C.BASE_H;
    const u = (v) => (v * dh) / 720 * this.scale;
    this.u = u;
    this.dw = dw; this.dh = dh;
    this.joyR = u(105);
    this.knobR = u(48);
    this.joyHome = { x: u(70) + this.joyR, y: dh - u(60) - this.joyR };
    this.buttons = [
      { a: "kick", x: dw - u(112), y: dh - u(118), r: u(74) },
      { a: "punch", x: dw - u(272), y: dh - u(92), r: u(66) },
      { a: "ranged", x: dw - u(240), y: dh - u(258), r: u(58) },
      { a: "special", x: dw - u(92), y: dh - u(298), r: u(64) },
      { a: "block", x: dw - u(405), y: dh - u(150), r: u(50) },
    ];
    // pausa: arriba a la izquierda, debajo del nombre del luchador 1
    this.pausePos = { x: u(66), y: u(182), r: u(28) };
    this.view = view;
  }

  buttonAt(x, y, slop = 1.15) {
    let best = null, bestD = Infinity;
    for (const b of this.buttons) {
      const d = Math.hypot(x - b.x, y - b.y);
      if (d <= b.r * slop && d < bestD) { best = b.a; bestD = d; }
    }
    return best;
  }

  down(id, x, y) {
    if (!this.visible || !this.fightMode) return false;
    const pp = this.pausePos;
    if (Math.hypot(x - pp.x, y - pp.y) <= pp.r * 1.3) { this.pauseTapped = true; return true; }
    const b = this.buttonAt(x, y);
    if (b) { this.pointers.set(id, { kind: "btn", a: b }); this.edges.add(b); return true; }
    if (x < this.dw * 0.42 && y > this.dh * 0.22 && !this.joy) {
      const r = this.joyR;
      const bx = Math.min(Math.max(x, r + this.u(10)), this.dw * 0.42);
      const by = Math.min(Math.max(y, this.dh * 0.22 + r * 0.5), this.dh - r - this.u(10));
      this.joy = { id, bx, by, x, y };
      this.pointers.set(id, { kind: "joy" });
      return true;
    }
    return false;
  }

  move(id, x, y) {
    const p = this.pointers.get(id);
    if (!p) return;
    if (p.kind === "joy" && this.joy) { this.joy.x = x; this.joy.y = y; }
    else if (p.kind === "btn") {
      // se puede deslizar de un botón a otro sin levantar el dedo
      const b = this.buttonAt(x, y, 1.0);
      if (b) p.a = b;
    }
  }

  up(id) {
    const p = this.pointers.get(id);
    if (p && p.kind === "joy") this.joy = null;
    this.pointers.delete(id);
  }

  releaseAll() { this.pointers.clear(); this.joy = null; }

  isPressed(action) {
    if (!this.visible || !this.fightMode) return false;
    if (action === "start" && this.pauseTapped) return true;
    if (this.edges.has(action)) return true;
    for (const p of this.pointers.values()) if (p.kind === "btn" && p.a === action) return true;
    if (this.joy) {
      const dx = (this.joy.x - this.joy.bx) / this.joyR;
      const dy = (this.joy.y - this.joy.by) / this.joyR;
      if (action === "right") return dx > 0.38;
      if (action === "left") return dx < -0.38;
      if (action === "up") return dy < -0.55;
      if (action === "down") return dy > 0.55;
    }
    return false;
  }

  endFrame() { this.pauseTapped = false; this.edges.clear(); }

  // ---------------------------------------------------------------
  face(ctx, key, x, y, r, alpha) {
    const im = IMG[key];
    if (!im) return false;
    const w = im.naturalWidth, h = im.naturalHeight;
    const f = (2 * r) / Math.max(w, h);
    ctx.globalAlpha = alpha;
    ctx.drawImage(im, x - (w * f) / 2, y - (h * f) / 2, w * f, h * f);
    return true;
  }

  fallbackDisc(ctx, action, x, y, r, alpha) {
    ctx.globalAlpha = alpha;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = COLORS[action] || "#5a5a64"; ctx.fill();
    ctx.lineWidth = 3; ctx.strokeStyle = "rgba(255,255,255,0.9)"; ctx.stroke();
    ctx.globalAlpha = 1;
    if (LABELS[action]) text(ctx, LABELS[action], x, y + 1, { size: r * 0.32, shadow: false });
  }

  draw(ctx) {
    if (!this.visible || !this.fightMode) return;
    ctx.save();
    const pressed = new Set([...this.pointers.values()].filter((p) => p.kind === "btn").map((p) => p.a));

    // joystick
    let base, knob, aBase, aKnob;
    if (this.joy) {
      base = { x: this.joy.bx, y: this.joy.by };
      let dx = this.joy.x - base.x, dy = this.joy.y - base.y;
      const d = Math.hypot(dx, dy), lim = this.joyR * 0.85;
      if (d > lim) { dx = (dx * lim) / d; dy = (dy * lim) / d; }
      knob = { x: base.x + dx, y: base.y + dy };
      aBase = 150 / 255; aKnob = 220 / 255;
    } else {
      base = this.joyHome; knob = base;
      aBase = 95 / 255; aKnob = 120 / 255;
    }
    if (!this.face(ctx, "t_joy_base", base.x, base.y, this.joyR, aBase)) {
      ctx.globalAlpha = aBase * 0.6;
      ctx.beginPath(); ctx.arc(base.x, base.y, this.joyR, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
    }
    if (!this.face(ctx, "t_joy_knob", knob.x, knob.y, this.knobR, aKnob)) {
      ctx.globalAlpha = aKnob;
      ctx.beginPath(); ctx.arc(knob.x, knob.y, this.knobR, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
    }

    // botones
    for (const b of this.buttons) {
      const on = pressed.has(b.a);
      const rr = b.r * (on ? 0.93 : 1);
      if (b.a === "special") { this.drawSpecial(ctx, b.x, b.y, b.r, on); continue; }
      const alpha = on ? 240 / 255 : 165 / 255;
      if (!this.face(ctx, "t_" + b.a, b.x, b.y, rr, alpha)) this.fallbackDisc(ctx, b.a, b.x, b.y, rr, alpha);
    }

    // pausa
    const pp = this.pausePos;
    if (!this.face(ctx, "t_pause", pp.x, pp.y, pp.r, 165 / 255)) this.fallbackDisc(ctx, "start", pp.x, pp.y, pp.r, 0.65);
    ctx.restore();
  }

  drawSpecial(ctx, bx, by, r, on) {
    const req = C.SPECIAL_HITS_REQUIRED;
    const charge = Math.max(0, Math.min(req, this.specialCharge));
    const ready = charge >= req;
    const rr = r * (on ? 0.93 : 1);
    const cx = bx + SPECIAL_DISC.ox * rr, cy = by + SPECIAL_DISC.oy * rr;
    const discR = SPECIAL_DISC.fr * rr;
    const width = Math.max(3, this.u(5));
    if (ready) {
      const pulse = 0.5 + 0.5 * Math.sin((performance.now() / 1000) * 7);
      ctx.globalAlpha = (60 + 50 * pulse) / 255;
      ctx.beginPath(); ctx.arc(cx, cy, discR + width + this.u(4 + 3 * pulse), 0, Math.PI * 2);
      ctx.fillStyle = "rgb(255,220,60)"; ctx.fill();
    }
    const drawFace = () => {
      const key = ready ? "t_special" : "t_special_locked";
      const alpha = ready ? (on ? 245 : 215) / 255 : 165 / 255;
      if (!this.face(ctx, key, bx, by, rr, alpha)) this.fallbackDisc(ctx, "special", bx, by, rr, ready ? alpha : 0.35);
    };
    // bloqueado: aro encima (se ve la carga); habilitado: aro detrás
    if (!ready) drawFace();
    const rIn = discR + this.u(1), rOut = rIn + width;
    const seg = (2 * Math.PI) / req, gap = 0.10;
    ctx.globalAlpha = 1;
    for (let i = 0; i < req; i++) {
      const a0 = -Math.PI / 2 + i * seg + gap / 2, a1 = a0 + seg - gap;
      ctx.beginPath();
      ctx.arc(cx, cy, rOut, a0, a1);
      ctx.arc(cx, cy, rIn, a1, a0, true);
      ctx.closePath();
      ctx.fillStyle = i < charge ? "rgb(255,215,50)" : "rgb(55,55,65)";
      ctx.fill();
    }
    if (ready) drawFace();
  }
}
