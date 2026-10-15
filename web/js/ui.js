// =====================================================================
// ui.js — dibujo de textos, HUD, menús y botones tocables
// Todo se dibuja en coordenadas del lienzo lógico (alto 540; ancho
// view.w >= 960 en pantallas más anchas que 16:9).
// =====================================================================
import * as C from "./config.js";
import { COLORS } from "./config.js";

export const FONT = "'Roboto Black', 'Arial Black', Impact, sans-serif";

// Imágenes de interfaz (las mismas de Mortal Kompa, en assets/ui/). Si
// falta alguna, el juego dibuja un reemplazo por código.
import { loadImage } from "./assets.js";
export const IMG = {};
const UI_FILES = {
  title_logo: "title_logo.png", title_bg: "title_background.jpg", select_bg: "character_selection_background.jpg",
  tower_bg: "tower_background.jpg", healthbar_frame: "healthbar_frame.png", ko_banner: "ko_banner.png",
  timer: "timer_container.png", round_on: "round_pip_filled.png", round_off: "round_pip_empty.png",
  sp_empty: "special_pip_empty.png", sp_filled: "special_pip_filled.png", sp_ready: "special_pip_ready.png",
  random_pose: "random_pose.png", random_sel: "random_selection.png", random_stage: "random_stage_selection.png",
  t_punch: "touch/punch.png", t_kick: "touch/kick.png", t_ranged: "touch/ranged.png", t_block: "touch/block.png",
  t_special: "touch/special.png", t_special_locked: "touch/special_locked.png", t_pause: "touch/pause.png",
  t_joy_base: "touch/joystick_base.png", t_joy_knob: "touch/joystick_knob.png",
  b_square: "buttons/square.png", b_cross: "buttons/cross.png", b_circle: "buttons/circle.png",
  b_triangle: "buttons/triangle.png", b_r1: "buttons/r1.png", b_options: "buttons/options.png", b_dpad: "buttons/dpad.png",
};
export async function loadUiImages() {
  await Promise.all(Object.entries(UI_FILES).map(async ([k, f]) => { IMG[k] = await loadImage(`assets/ui/${f}`); }));
}

// Zonas tocables/clickeables registradas en cada cuadro por la escena
// activa (menús con mouse o dedo). Se vacían antes de cada draw.
export const hits = [];
export function addHit(rect, fn, id = null) { hits.push({ ...rect, fn, id }); }
export function clearHits() { hits.length = 0; }
export function hitAt(x, y) {
  for (let i = hits.length - 1; i >= 0; i--) {
    const h = hits[i];
    if (x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) return h;
  }
  return null;
}

export function text(ctx, str, x, y, o = {}) {
  const size = o.size ?? 20;
  ctx.font = `${o.weight ?? 900} ${size}px ${FONT}`;
  ctx.textAlign = o.align ?? "center";
  ctx.textBaseline = o.baseline ?? "middle";
  if (o.shadow !== false) {
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    const off = Math.max(1, size / 16);
    ctx.fillText(str, x + off, y + off);
  }
  if (o.stroke) {
    ctx.lineWidth = o.stroke;
    ctx.strokeStyle = o.strokeColor ?? "#000";
    ctx.lineJoin = "round";
    ctx.strokeText(str, x, y);
  }
  ctx.fillStyle = o.color ?? COLORS.white;
  ctx.fillText(str, x, y);
  return ctx.measureText(str).width;
}

export function measure(ctx, str, size) {
  ctx.font = `900 ${size}px ${FONT}`;
  return ctx.measureText(str).width;
}

export function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

export function fillBg(ctx, view, top = "#1d1530", bottom = "#0b0b10") {
  const g = ctx.createLinearGradient(0, 0, 0, C.BASE_H);
  g.addColorStop(0, top);
  g.addColorStop(1, bottom);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, view.w, C.BASE_H);
}

// Fondo de menú: imagen de Mortal Kompa (title / select / tower) con
// un velo oscuro para que se lea el texto; si falta, franjas celestes.
export function menuBackground(ctx, view, t = 0, bg = "select", dim = 0.35) {
  const img = IMG[bg + "_bg"];
  if (img) {
    drawImageCover(ctx, img, 0, 0, view.w, C.BASE_H);
    if (dim > 0) { ctx.fillStyle = `rgba(0,0,0,${dim})`; ctx.fillRect(0, 0, view.w, C.BASE_H); }
    return;
  }
  fillBg(ctx, view, "#16203a", "#08080d");
  ctx.save();
  ctx.globalAlpha = 0.07;
  ctx.fillStyle = COLORS.celeste;
  const off = (t * 20) % 120;
  for (let x = -600; x < view.w + 600; x += 120) {
    ctx.beginPath();
    ctx.moveTo(x + off, 0);
    ctx.lineTo(x + off + 60, 0);
    ctx.lineTo(x + off - 200, C.BASE_H);
    ctx.lineTo(x + off - 260, C.BASE_H);
    ctx.fill();
  }
  ctx.restore();
}

export function title(ctx, view, str, y = 46, color = COLORS.yellow, size = 34) {
  const r = wrapText(ctx, str, size, textMaxW(view));
  r.lines.forEach((l, i) => text(ctx, l, view.w / 2, y + i * r.size * 1.15, { size: r.size, color, stroke: 6 }));
}

export function logo(ctx, view, y = 120, scale = 1) {
  ctx.save();
  ctx.translate(view.w / 2, y);
  ctx.scale(scale, scale);
  if (IMG.title_logo) {
    const w = 600, h = w * IMG.title_logo.naturalHeight / IMG.title_logo.naturalWidth;
    ctx.drawImage(IMG.title_logo, -w / 2, -h / 2 - 18, w, h);
  } else {
    text(ctx, "MORTAL KOMPA", 0, -10, { size: 74, color: "#f0c828", stroke: 10, strokeColor: "#3a1400" });
  }
  ctx.restore();
}

// ---------------------------------------------------------------------
// HUD de pelea
// ---------------------------------------------------------------------
const HUD_MARGIN = 30, HUD_DOTS_Y = 14, HUD_BAR_Y = 36, HUD_BAR_H = 26;
const HUD_NAME_Y = HUD_BAR_Y + HUD_BAR_H + 16;

function healthBar(ctx, x, y, w, h, ratio, flip) {
  roundRect(ctx, x - 3, y - 3, w + 6, h + 6, 6);
  ctx.fillStyle = "#000";
  ctx.fill();
  roundRect(ctx, x, y, w, h, 4);
  ctx.fillStyle = COLORS.gray;
  ctx.fill();
  const fw = Math.max(0, w * Math.max(0, ratio));
  ctx.fillStyle = ratio > 0.5 ? COLORS.green : ratio > 0.2 ? COLORS.yellow : COLORS.red;
  if (fw > 0) {
    roundRect(ctx, flip ? x + w - fw : x, y, fw, h, 4);
    ctx.fill();
  }
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  ctx.fillRect(x + 2, y + 2, w - 4, h * 0.35);
  if (IMG.healthbar_frame) ctx.drawImage(IMG.healthbar_frame, x - 10, y - 10, w + 20, h + 20);
}

function pipImg(ctx, img, cx, cy, size) {
  ctx.drawImage(img, cx - size / 2, cy - size / 2, size, size);
}

function pip(ctx, cx, cy, r, fill, stroke = "#000") {
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = stroke;
  ctx.stroke();
}

function specialPips(ctx, x, y, hits, req, alignRight, t) {
  const gap = 18;
  const ready = hits >= req;
  for (let i = 0; i < req; i++) {
    const cx = alignRight ? x - (req - 1 - i) * gap : x + i * gap;
    const img = ready ? IMG.sp_ready : i < hits ? IMG.sp_filled : IMG.sp_empty;
    if (img) { pipImg(ctx, img, cx, y, ready ? 15 + Math.sin(t * 8) * 1.5 : 14); continue; }
    let col = i < hits ? COLORS.white : COLORS.gray;
    if (ready) col = `hsl(${45 + Math.sin(t * 8) * 10}, 95%, ${55 + Math.sin(t * 8) * 10}%)`;
    pip(ctx, cx, y, 5.5, col);
  }
}

export const hudOpts = { showSpecialPips: true };
// En pantallas táctiles los menús se dibujan como "pastillas" separadas y
// un poco más grandes (mismo criterio que la versión Android).
export const menuOpts = { touch: false };

/** hud = { f: [{name, health, maxHealth, hits}], time, wins:[a,b], t } */
export function drawHud(ctx, view, hud) {
  const m = HUD_MARGIN;
  const barW = view.w / 2 - m - 90;
  const [a, b] = hud.f;
  healthBar(ctx, m, HUD_BAR_Y, barW, HUD_BAR_H, a.health / a.maxHealth, false);
  healthBar(ctx, view.w - m - barW, HUD_BAR_Y, barW, HUD_BAR_H, b.health / b.maxHealth, true);
  // nombres largos: se achica la letra para no pisar los pips del especial
  const nameW = barW - (hudOpts.showSpecialPips ? 130 : 10);
  const fit = (s) => { let z = 18; while (z > 11 && measure(ctx, s, z) > nameW) z -= 1; return z; };
  text(ctx, a.name, m, HUD_NAME_Y + 8, { size: fit(a.name), align: "left" });
  text(ctx, b.name, view.w - m, HUD_NAME_Y + 8, { size: fit(b.name), align: "right" });
  // con controles táctiles, el botón de Especial reemplaza a los pips
  if (hudOpts.showSpecialPips) {
    specialPips(ctx, m + barW - 3, HUD_NAME_Y + 8, a.hits, C.SPECIAL_HITS_REQUIRED, true, hud.t);
    specialPips(ctx, view.w - m - barW + 3, HUD_NAME_Y + 8, b.hits, C.SPECIAL_HITS_REQUIRED, false, hud.t);
  }
  for (let i = 0; i < C.ROUNDS_TO_WIN; i++) {
    const pos = [[m + 10 + i * 20, 0], [view.w - m - 10 - i * 20, 1]];
    for (const [cx, k] of pos) {
      const won = i < hud.wins[k];
      const img = won ? IMG.round_on : IMG.round_off;
      if (img) pipImg(ctx, img, cx, HUD_DOTS_Y, 16);
      else pip(ctx, cx, HUD_DOTS_Y, 6, won ? COLORS.yellow : COLORS.gray);
    }
  }
  if (IMG.timer) {
    ctx.drawImage(IMG.timer, view.w / 2 - 43, HUD_BAR_Y + HUD_BAR_H / 2 - 28, 86, 56);
  } else {
    roundRect(ctx, view.w / 2 - 40, HUD_BAR_Y + HUD_BAR_H / 2 - 26, 80, 52, 10);
    ctx.fillStyle = "rgba(10,10,16,0.85)";
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = COLORS.yellow;
    ctx.stroke();
  }
  text(ctx, String(Math.max(0, Math.floor(hud.time))), view.w / 2, HUD_BAR_Y + HUD_BAR_H / 2 + 1, { size: 30 });
}

// Parte un texto en renglones que entren en maxW (por palabras; si una
// sola palabra no entra ni sola, achica la letra). Devuelve {lines, size}.
export function wrapText(ctx, str, size, maxW, minSize = 18) {
  const words = String(str).split(/[ \t\n]+/).filter(Boolean);   // el espacio duro (\u00a0) no corta
  while (size > minSize && words.some((w) => measure(ctx, w, size) > maxW)) size -= 2;
  const lines = [];
  let cur = "";
  for (const w of words) {
    const t = cur ? cur + " " + w : w;
    if (cur && measure(ctx, t, size) > maxW) { lines.push(cur); cur = w; } else cur = t;
  }
  if (cur) lines.push(cur);
  return { lines, size };
}
function textMaxW(view) { return Math.min(view.w - 80, 900); }

export function centerText(ctx, view, str, color = COLORS.white, yOff = 0, size = 64) {
  const r = wrapText(ctx, str, size, textMaxW(view));
  const lh = r.size * 1.12;
  const y0 = C.BASE_H / 2 + yOff - ((r.lines.length - 1) * lh) / 2;
  r.lines.forEach((l, i) => text(ctx, l, view.w / 2, y0 + i * lh, { size: r.size, color, shadow: false }));
}

// título de pantalla como el de PC: sombra negra suave, sin contorno.
// Si no entra en un renglón, sigue en los de abajo.
export function pcTitle(ctx, view, str, y, color = COLORS.yellow, size = 38) {
  const r = wrapText(ctx, str, size, textMaxW(view));
  const lh = r.size * 1.15;
  r.lines.forEach((l, i) => {
    const ly = y + i * lh;
    ctx.save(); ctx.globalAlpha = 140 / 255;
    text(ctx, l, view.w / 2 + 2, ly + 2, { size: r.size, color: "#000", shadow: false });
    ctx.restore();
    text(ctx, l, view.w / 2, ly, { size: r.size, color, shadow: false });
  });
  return r.lines.length * lh;
}

export function koBanner(ctx, view, kind, t = 0) {
  if (kind === "draw") { centerText(ctx, view, "EMPATE", COLORS.yellow); return; }
  if (kind === "ko") {
    ctx.save();
    ctx.translate(view.w / 2, C.BASE_H / 2);
    if (IMG.ko_banner) ctx.drawImage(IMG.ko_banner, -240, -82, 480, 165);
    else text(ctx, "K.O.", 0, 0, { size: 64, color: COLORS.red, shadow: false });
    ctx.restore();
    return;
  }
  centerText(ctx, view, "TIEMPO", COLORS.red);
}

export function overlay(ctx, view, alpha = 0.65) {
  ctx.fillStyle = `rgba(0,0,0,${alpha})`;
  ctx.fillRect(0, 0, view.w, C.BASE_H);
}

// Lista vertical de opciones. Devuelve nada; registra zonas tocables
// que llaman onPick(i) (un toque sobre la opción la elige directo).
export function menuList(ctx, view, items, index, centerY, onPick, o = {}) {
  if (menuOpts.touch) return menuListTouch(ctx, view, items, index, centerY, onPick, o);
  const size = o.size ?? 28;
  const gap = o.gap ?? 50;
  const top = centerY - ((items.length - 1) * gap) / 2;
  items.forEach((label, i) => {
    const y = top + i * gap;
    const sel = i === index;
    const w = Math.max(260, measure(ctx, label, size) + 70);
    if (sel) {
      roundRect(ctx, view.w / 2 - w / 2, y - gap / 2 + 4, w, gap - 8, 12);
      ctx.fillStyle = "rgba(240,200,40,0.16)";
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = COLORS.yellow;
      ctx.stroke();
    }
    const disabled = o.disabled && o.disabled[i];
    text(ctx, label, view.w / 2, y, { size, color: disabled ? "#666" : sel ? COLORS.yellow : COLORS.white });
    if (onPick) addHit({ x: view.w / 2 - w / 2, y: y - gap / 2, w, h: gap }, () => onPick(i));
  });
}

function menuListTouch(ctx, view, items, index, centerY, onPick, o = {}) {
  const size = o.size ?? 25;
  const rowH = 46;
  const gap = Math.min(64, Math.max(rowH + 8, 380 / Math.max(1, items.length)));
  let top = centerY - ((items.length - 1) * gap) / 2;
  top = Math.max(top, 40 + rowH / 2);
  const w = Math.min(view.w - 60, Math.max(340, ...items.map((l) => measure(ctx, l, size) + 70)));
  items.forEach((label, i) => {
    const y = top + i * gap;
    const sel = i === index;
    const disabled = o.disabled && o.disabled[i];
    roundRect(ctx, view.w / 2 - w / 2, y - rowH / 2, w, rowH, rowH / 2);
    ctx.fillStyle = "rgba(0,0,0,0.62)";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = sel ? COLORS.yellow : "rgba(255,255,255,0.38)";
    ctx.stroke();
    text(ctx, label, view.w / 2, y + 1, { size, color: disabled ? "#666" : sel ? COLORS.yellow : COLORS.white });
    if (onPick) addHit({ x: view.w / 2 - w / 2 - 6, y: y - gap / 2, w: w + 12, h: gap }, () => onPick(i));
  });
}

// Pie de ayuda. Admite íconos de botón de joystick con [cross], [circle],
// [square], [triangle], [r1], [options], [dpad] (los de Mortal Kompa).
export function footer(ctx, view, str, y = C.BASE_H - 22) {
  if (!str.includes("[")) { text(ctx, str, view.w / 2, y, { size: 15, color: "#cfcfd8" }); return; }
  const parts = str.split(/(\[[a-z0-9]+\])/).filter(Boolean);
  const ICON = 24;
  const widths = parts.map((p) => (/^\[.+\]$/.test(p) ? ICON + 4 : measure(ctx, p, 15)));
  let x = view.w / 2 - widths.reduce((a, b) => a + b, 0) / 2;
  parts.forEach((p, i) => {
    const m = p.match(/^\[(.+)\]$/);
    if (m && IMG["b_" + m[1]]) ctx.drawImage(IMG["b_" + m[1]], x + 2, y - ICON / 2, ICON, ICON);
    else text(ctx, p, x, y, { size: 15, color: "#cfcfd8", align: "left" });
    x += widths[i];
  });
}

export function pillButton(ctx, cx, cy, label, onTap, o = {}) {
  const size = o.size ?? 20;
  const w = Math.max(o.minW ?? 120, measure(ctx, label, size) + 44);
  const h = o.h ?? 44;
  roundRect(ctx, cx - w / 2, cy - h / 2, w, h, h / 2);
  ctx.fillStyle = o.color ?? "#3ca05a";
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = o.border ?? "rgba(255,255,255,0.85)";
  ctx.stroke();
  text(ctx, label, cx, cy + 1, { size, shadow: false, color: o.textColor ?? "#fff" });
  const r = { x: cx - w / 2, y: cy - h / 2, w, h };
  if (onTap) addHit(r, onTap);
  return r;
}

// Botón "volver" de todas las pantallas: mismo tamaño y lugar (arriba a la
// izquierda) que en los menús 1 Jugador / Multijugador.
export function backButton(ctx, onTap, label = "◄ VOLVER", y = 36) {
  // siempre arrancando del mismo borde izquierdo, aunque el texto sea más largo
  const w = Math.max(110, measure(ctx, label, 15) + 44);
  return pillButton(ctx, 25 + w / 2, y, label, onTap, { size: 15, h: 36, minW: 110, color: "#3c3c48" });
}

export function roundButton(ctx, cx, cy, r, label, onTap) {
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = "#3c3c48";
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = "#fff";
  ctx.stroke();
  text(ctx, label, cx, cy + 1, { size: r, shadow: false });
  if (onTap) addHit({ x: cx - r, y: cy - r, w: 2 * r, h: 2 * r }, onTap);
}

export function drawImageCover(ctx, img, x, y, w, h) {
  if (!img) return;
  const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
  const k = Math.max(w / iw, h / ih);
  const sw = w / k, sh = h / k;
  ctx.drawImage(img, (iw - sw) / 2, (ih - sh) / 2, sw, sh, x, y, w, h);
}

export function drawImageContain(ctx, img, x, y, w, h, flip = false, anchorBottom = true) {
  if (!img) return;
  const iw = img.naturalWidth || img.width, ih = img.naturalHeight || img.height;
  const k = Math.min(w / iw, h / ih);
  const dw = iw * k, dh = ih * k;
  const dx = x + (w - dw) / 2;
  const dy = anchorBottom ? y + h - dh : y + (h - dh) / 2;
  ctx.save();
  if (flip) { ctx.translate(dx + dw, dy); ctx.scale(-1, 1); ctx.drawImage(img, 0, 0, dw, dh); }
  else ctx.drawImage(img, dx, dy, dw, dh);
  ctx.restore();
}

// Confeti (victorias de Torre / Torneo)
export class Confetti {
  constructor(view, n = 140) {
    this.p = [];
    const cols = ["#f0c828", "#6cb4ee", "#ffffff", "#dc2828", "#28c85a", "#a060e0"];
    for (let i = 0; i < n; i++) {
      this.p.push({ x: Math.random() * view.w, y: -Math.random() * 540, vx: (Math.random() - 0.5) * 60, vy: 60 + Math.random() * 120,
        r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 8, c: cols[i % cols.length], s: 5 + Math.random() * 6 });
    }
    this.w = view.w;
  }
  update(dt) {
    for (const q of this.p) {
      q.x += q.vx * dt; q.y += q.vy * dt; q.r += q.vr * dt;
      if (q.y > 560) { q.y = -10; q.x = Math.random() * this.w; }
    }
  }
  draw(ctx) {
    for (const q of this.p) {
      ctx.save();
      ctx.translate(q.x, q.y);
      ctx.rotate(q.r);
      ctx.fillStyle = q.c;
      ctx.fillRect(-q.s / 2, -q.s / 4, q.s, q.s / 2);
      ctx.restore();
    }
  }
}
