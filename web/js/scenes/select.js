// =====================================================================
// scenes/select.js — selección de luchador y de escenario
// =====================================================================
import * as C from "../config.js";
import { COLORS } from "../config.js";
import * as UI from "../ui.js";
import { audio } from "../audio.js";
import { DB, normalStages, secretStage } from "../assets.js";
import { ok } from "../input.js";
import { announcerNamePath } from "../match.js";

const RANDOM = "__random__";
// Mismos colores y medidas que la selección de Mortal Kompa de PC
// (engine/menu.py, calibrado sobre el lienzo base 960x540).
export const P1_COLOR = "rgb(80,170,240)";
const P2_COLOR = "rgb(240,80,90)";
const CPU_COLOR = "rgb(240,200,50)";
export const FRAME_COLOR = "rgb(45,45,52)";
export const GRID_TOP = 70, GRID_BOTTOM_MARGIN = 95;
export const SIDE_PANEL_W = 286, SIDE_MARGIN = 20, GRID_SIDE_GAP = 20;
const CELL_MIN = 34, CELL_MAX = 120;
export const GAP = 10;
export const SEL_FRAME_PAD = 8 * 0.7;

export function gridLayout(n, availW, availH, gap = GAP) {
  let best = null;
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const cell = Math.min((availW - (cols - 1) * gap) / cols, (availH - (rows - 1) * gap) / rows);
    if (cell <= 0) continue;
    if (!best || cell > best.cell) best = { cell, cols, rows };
  }
  best = best || { cell: CELL_MIN, cols: 1, rows: n };
  best.cell = Math.max(CELL_MIN, Math.min(CELL_MAX, best.cell));
  return best;
}

export function drawRandomTile(ctx, x, y, s) {
  if (UI.IMG.random_sel) {
    ctx.save(); UI.roundRect(ctx, x, y, s, s, 10); ctx.clip();
    ctx.drawImage(UI.IMG.random_sel, x, y, s, s); ctx.restore(); return;
  }
  UI.roundRect(ctx, x, y, s, s, 10);
  const g = ctx.createLinearGradient(x, y, x, y + s);
  g.addColorStop(0, "#3a3a48"); g.addColorStop(1, "#1a1a22");
  ctx.fillStyle = g; ctx.fill();
  UI.text(ctx, "?", x + s / 2, y + s / 2 + 2, { size: s * 0.6, color: COLORS.yellow });
}

// imagen redondeada dentro de un cuadrado (miniatura de selección)
export function drawThumb(ctx, img, x, y, s, r = 8) {
  if (!img) return;
  ctx.save(); UI.roundRect(ctx, x, y, s, s, r); ctx.clip();
  ctx.drawImage(img, x, y, s, s); ctx.restore();
}

function drawFlipped(ctx, img, x, y, w, h, flip) {
  if (!img) return;
  ctx.save();
  if (flip) { ctx.translate(x + w, y); ctx.scale(-1, 1); ctx.drawImage(img, 0, 0, w, h); }
  else ctx.drawImage(img, x, y, w, h);
  ctx.restore();
}

/**
 * players: [{ input, cpu:bool, label }]  (1 = solo, 2 = versus/cpu)
 * onDone([{slug, random}]), onBack()
 */
export class CharSelectScene {
  constructor(app, { players, title = null, onDone, onBack, subtitle = null, allowRandom = true }) {
    this.app = app;
    this.players = players;
    this.onDone = onDone;
    this.onBack = onBack;
    const solo = players.length === 1;
    const cpu = players.some((p) => p.cpu);
    this.title = title || (solo ? "ELEGÍ TU LUCHADOR" : "SELECCIONÁ PERSONAJE" + (cpu ? "" : "S"));
    this.subtitle = subtitle;
    this.cells = DB.roster.map((c) => ({ slug: c.slug, entry: c }));
    if (allowRandom) this.cells.push({ slug: RANDOM, entry: null });
    this.cursor = players.map((_, i) => Math.min(i, this.cells.length - 1));
    this.confirmed = players.map(() => false);
    this.picks = players.map(() => null);
    this.cpuTimer = 0.9;
    this.cpuMoves = 3 + Math.floor(Math.random() * 4);
    this.doneTimer = null;
    // nombres del locutor bajados de antemano: así suenan apenas se elige
    for (const c of DB.roster) audio.load(announcerNamePath(c));
  }

  layout(view) {
    const availW = view.w - 2 * (SIDE_MARGIN + SIDE_PANEL_W + GRID_SIDE_GAP);
    const availH = C.BASE_H - GRID_TOP - GRID_BOTTOM_MARGIN;
    const g = gridLayout(this.cells.length, availW, availH);
    const gw = g.cols * g.cell + (g.cols - 1) * GAP;
    const gh = g.rows * g.cell + (g.rows - 1) * GAP;
    const x0 = Math.floor(view.w / 2 - gw / 2);
    const y0 = GRID_TOP + Math.max(0, Math.floor((availH - gh) / 2));
    return { ...g, x0, y0 };
  }

  cellRect(L, i) {
    return { x: L.x0 + (i % L.cols) * (L.cell + GAP), y: L.y0 + Math.floor(i / L.cols) * (L.cell + GAP), w: L.cell, h: L.cell };
  }

  move(p, dx, dy) {
    const n = this.cells.length;
    const cols = this._cols || 3;
    let i = this.cursor[p];
    if (dx) i = (i + dx + n) % n;
    if (dy) i = (((i + dy * cols) % n) + n) % n;   // igual que en PC: da la vuelta
    this.cursor[p] = i;
  }

  confirm(p) {
    if (this.confirmed[p]) return;
    const cell = this.cells[this.cursor[p]];
    let slug = cell.slug, random = false;
    if (slug === RANDOM) {
      const real = DB.roster;
      slug = real[Math.floor(Math.random() * real.length)].slug;
      random = true;
    }
    this.confirmed[p] = true;
    this.picks[p] = { slug, random };
    if (!random) audio.play(announcerNamePath(DB.bySlug[slug]), 0.9, "announcer");
    if (this.confirmed.every(Boolean)) this.doneTimer = 0.6;
  }

  cancel(p) {
    if (this.doneTimer !== null) return;
    if (this.confirmed[p]) { this.confirmed[p] = false; this.picks[p] = null; return; }
    if (p === 0 || this.players.length === 1) this.onBack();
  }

  tap(i) {
    // toque directo: mueve al primer jugador humano sin confirmar; si
    // ya estaba ahí, confirma
    const p = this.players.findIndex((pl, k) => !pl.cpu && !this.confirmed[k]);
    if (p < 0) return;
    if (this.cursor[p] === i) this.confirm(p);
    else this.cursor[p] = i;
  }

  update(dt) {
    if (this.doneTimer !== null) {
      this.doneTimer -= dt;
      if (this.doneTimer <= 0) { this.doneTimer = null; this.onDone(this.picks); }
      return;
    }
    this.players.forEach((pl, p) => {
      if (pl.cpu) {
        if (this.confirmed[p] || !this.confirmed[0]) return;
        this.cpuTimer -= dt;
        if (this.cpuTimer <= 0) {
          if (this.cpuMoves-- > 0) { this.move(p, Math.random() < 0.5 ? -1 : 1, 0); this.cpuTimer = 0.25 + Math.random() * 0.3; }
          else this.confirm(p);
        }
        return;
      }
      const inp = pl.input;
      if (!this.confirmed[p]) {
        if (inp.justPressed("left")) this.move(p, -1, 0);
        else if (inp.justPressed("right")) this.move(p, 1, 0);
        else if (inp.justPressed("up")) this.move(p, 0, -1);
        else if (inp.justPressed("down")) this.move(p, 0, 1);
        else if (ok(inp)) this.confirm(p);
        else if (inp.justPressed("cancel")) this.cancel(p);
      } else if (inp.justPressed("cancel")) this.cancel(p);
    });
  }

  // índice de celda que corresponde a lo elegido por p (Aleatorio -> su celda)
  pickedCell(p) {
    const pk = this.picks[p];
    if (!pk) return -1;
    return pk.random ? this.cells.findIndex((c) => c.slug === RANDOM) : this.cells.findIndex((c) => c.slug === pk.slug);
  }

  shownEntry(p) {
    const pk = this.picks[p];
    if (pk) return pk.random ? null : DB.bySlug[pk.slug];
    return this.cells[this.cursor[p]].entry;
  }

  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t, "select", 0);
    const solo = this.players.length === 1;
    const p2cpu = !solo && this.players[1].cpu;
    const p2Color = p2cpu ? CPU_COLOR : P2_COLOR;
    const L = this.layout(view);
    this._cols = L.cols;
    const picked = this.players.map((_, p) => this.pickedCell(p));

    this.cells.forEach((c, i) => {
      const r = this.cellRect(L, i);
      const p1Here = this.cursor[0] === i;
      const p2Here = !solo && this.cursor[1] === i;
      // el marco ES el color del jugador; si coinciden, mitad y mitad
      UI.roundRect(ctx, r.x, r.y, r.w, r.h, 8);
      ctx.fillStyle = p1Here ? P1_COLOR : p2Here ? p2Color : FRAME_COLOR;
      ctx.fill();
      if (p1Here && p2Here) {
        ctx.save(); ctx.beginPath(); ctx.rect(r.x + r.w / 2, r.y, r.w / 2, r.h); ctx.clip();
        UI.roundRect(ctx, r.x, r.y, r.w, r.h, 8); ctx.fillStyle = p2Color; ctx.fill(); ctx.restore();
      }
      const s = r.w - SEL_FRAME_PAD, o = SEL_FRAME_PAD / 2;
      if (c.entry) drawThumb(ctx, c.entry.selection, r.x + o, r.y + o, s, 8);
      else if (UI.IMG.random_sel) drawThumb(ctx, UI.IMG.random_sel, r.x + o, r.y + o, s, 8);
      else drawRandomTile(ctx, r.x + o, r.y + o, s);
      if (picked[0] === i && this.confirmed[0]) {
        ctx.beginPath(); ctx.arc(r.x + 14, r.y + 14, 10, 0, Math.PI * 2); ctx.fillStyle = P1_COLOR; ctx.fill();
      }
      if (!solo && picked[1] === i && this.confirmed[1]) {
        ctx.beginPath(); ctx.arc(r.x + r.w - 14, r.y + 14, 10, 0, Math.PI * 2); ctx.fillStyle = p2Color; ctx.fill();
      }
      UI.addHit(r, () => this.tap(i));
    });

    // poses a los costados (mismo tamaño que en PC, sin brillos)
    const py = C.BASE_H / 2 - SIDE_PANEL_W / 2;
    const e1 = this.shownEntry(0);
    drawFlipped(ctx, e1 ? e1.pose : UI.IMG.random_pose, SIDE_MARGIN, py, SIDE_PANEL_W, SIDE_PANEL_W, false);
    if (!solo) {
      const e2 = this.shownEntry(1);
      const x2 = view.w - SIDE_MARGIN - SIDE_PANEL_W;
      if (e2 && e2.pose2) drawFlipped(ctx, e2.pose2, x2, py, SIDE_PANEL_W, SIDE_PANEL_W, false);
      else drawFlipped(ctx, e2 ? e2.pose : UI.IMG.random_pose, x2, py, SIDE_PANEL_W, SIDE_PANEL_W, true);
      const l2 = p2cpu ? "CPU" : `${this.players[1].label || "J2"}: ${e2 ? e2.name : "Aleatorio"}`;
      UI.text(ctx, l2, view.w - 40, C.BASE_H / 2 + 240, { size: 20, color: p2Color, align: "right", baseline: "top" });
    }

    UI.text(ctx, this.title, view.w / 2, 25, { size: 38, color: COLORS.yellow });
    if (this.subtitle) UI.text(ctx, this.subtitle, view.w / 2, 54, { size: 15, color: "#ddd" });
    UI.text(ctx, `${this.players[0].label || "J1"}: ${e1 ? e1.name : "Aleatorio"}`, 40, C.BASE_H / 2 + 240, { size: 20, color: P1_COLOR, align: "left", baseline: "top" });

    if (this.app.isTouchDevice) {
      UI.backButton(ctx, () => this.cancel(0));
      // celular: tocar una cara la marca; ACEPTAR la elige
      const p = this.players.findIndex((pl, k) => !pl.cpu && !this.confirmed[k]);
      if (p >= 0) UI.pillButton(ctx, view.w / 2, C.BASE_H - 46, "ACEPTAR", () => this.confirm(p), { size: 20, h: 42, minW: 200 });
      UI.footer(ctx, view, "Tocá un luchador y después ACEPTAR", C.BASE_H - 12);
    } else UI.footer(ctx, view, "Puño o ENTER confirma · Patada o ESC vuelve (J1)", C.BASE_H - 25);
  }
}

// ---------------------------------------------------------------------
// Escenario: grilla de miniaturas + "Aleatorio"; Start/Enter = secreto
// ---------------------------------------------------------------------
export class StageSelectScene {
  constructor(app, { input, onDone, onBack }) {
    this.app = app; this.input = input; this.onDone = onDone; this.onBack = onBack;
    this.cells = [...normalStages(), { id: RANDOM, name: "Aleatorio" }];
    this.index = 0;
  }
  choose(i) {
    const c = this.cells[i];
    if (c.id === RANDOM) {
      const list = normalStages();
      this.onDone(list[Math.floor(Math.random() * list.length)] || null);
    } else this.onDone(c);
  }
  update() {
    const i = this.input;
    const n = this.cells.length;
    const cols = this._cols || 3;
    if (i.justPressed("left")) this.index = (this.index - 1 + n) % n;
    else if (i.justPressed("right")) this.index = (this.index + 1) % n;
    else if (i.justPressed("up")) this.index = Math.max(0, this.index - cols);
    else if (i.justPressed("down")) this.index = Math.min(n - 1, this.index + cols);
    else if (i.justPressed("start")) { const s = secretStage(); if (s) this.onDone(s); else this.choose(this.index); }
    else if (i.justPressed("confirm")) this.choose(this.index);
    else if (i.justPressed("cancel")) this.onBack();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, "ELEGÍ EL ESCENARIO", 44);
    const n = this.cells.length;
    // 3 columnas hasta 6 escenarios; más que eso, 4 (Mortal Kompa tiene 8)
    const cols = Math.min(n <= 6 ? 3 : 4, n);
    this._cols = cols;
    const rows = Math.ceil(n / cols);
    const availH = C.BASE_H - 90 - (this.app.isTouchDevice ? 56 : 44);   // entre el título y el pie / botón
    const cw = Math.min(260, (view.w - 120) / cols - 20, ((availH / rows) - 46) * 16 / 9);
    const ch = cw * 9 / 16;
    const gw = cols * cw + (cols - 1) * 20;
    const x0 = view.w / 2 - gw / 2;
    const y0 = 90 + Math.max(0, (C.BASE_H - 150 - rows * (ch + 46)) / 2);
    this.cells.forEach((c, i) => {
      const x = x0 + (i % cols) * (cw + 20), y = y0 + Math.floor(i / cols) * (ch + 46);
      ctx.save();
      UI.roundRect(ctx, x, y, cw, ch, 10);
      ctx.clip();
      if (c.thumb) UI.drawImageCover(ctx, c.thumb, x, y, cw, ch);
      else if (c.id === RANDOM && UI.IMG.random_stage) UI.drawImageCover(ctx, UI.IMG.random_stage, x, y, cw, ch);
      else { ctx.fillStyle = "#24242e"; ctx.fillRect(x, y, cw, ch); UI.text(ctx, "?", x + cw / 2, y + ch / 2, { size: 60, color: COLORS.yellow }); }
      ctx.restore();
      const sel = i === this.index;
      UI.roundRect(ctx, x - 3, y - 3, cw + 6, ch + 6, 12);
      ctx.lineWidth = sel ? 5 : 2; ctx.strokeStyle = sel ? COLORS.yellow : "rgba(255,255,255,0.3)"; ctx.stroke();
      UI.text(ctx, c.name, x + cw / 2, y + ch + 18, { size: 18, color: sel ? COLORS.yellow : "#fff" });
      UI.addHit({ x, y, w: cw, h: ch + 30 }, () => { if (this.index === i) this.choose(i); else this.index = i; });
    });
    UI.backButton(ctx, () => this.onBack());
    if (this.app.isTouchDevice) UI.pillButton(ctx, view.w / 2, C.BASE_H - 24, "ACEPTAR", () => this.choose(this.index), { size: 20, h: 40, minW: 200 });
    else UI.footer(ctx, view, "Confirmar elige · Patada/ESC vuelve");
  }
}
