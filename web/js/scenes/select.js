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
const P_COLORS = ["#f0c828", "#4aa8ff"];
const SIDE_W = 230;

function gridLayout(n, availW, availH, gap = 10) {
  let best = null;
  for (let cols = 1; cols <= n; cols++) {
    const rows = Math.ceil(n / cols);
    const cell = Math.min((availW - (cols - 1) * gap) / cols, (availH - (rows - 1) * gap) / rows);
    if (!best || cell > best.cell) best = { cell, cols, rows };
  }
  best.cell = Math.max(48, Math.min(130, best.cell));
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

/**
 * players: [{ input, cpu:bool, label }]  (1 = solo, 2 = versus/cpu)
 * onDone([{slug, random}]), onBack()
 */
export class CharSelectScene {
  constructor(app, { players, title = "ELEGÍ TU LUCHADOR", onDone, onBack, subtitle = null, allowRandom = true }) {
    this.app = app;
    this.players = players;
    this.onDone = onDone;
    this.onBack = onBack;
    this.title = title;
    this.subtitle = subtitle;
    this.cells = DB.roster.map((c) => ({ slug: c.slug, entry: c }));
    if (allowRandom) this.cells.push({ slug: RANDOM, entry: null });
    this.cursor = players.map((_, i) => Math.min(i, this.cells.length - 1));
    this.confirmed = players.map(() => false);
    this.picks = players.map(() => null);
    this.cpuTimer = 0.9;
    this.cpuMoves = 3 + Math.floor(Math.random() * 4);
    this.doneTimer = null;
  }

  layout(view) {
    const solo = this.players.length === 1;
    const side = solo ? SIDE_W : SIDE_W;
    const availW = view.w - 2 * (side + 30);
    const g = gridLayout(this.cells.length, availW, C.BASE_H - 200);
    const gw = g.cols * g.cell + (g.cols - 1) * 10;
    const gh = g.rows * g.cell + (g.rows - 1) * 10;
    const x0 = view.w / 2 - gw / 2;
    const y0 = 110 + Math.max(0, (C.BASE_H - 200 - gh) / 2);
    return { ...g, x0, y0 };
  }

  cellRect(L, i) {
    return { x: L.x0 + (i % L.cols) * (L.cell + 10), y: L.y0 + Math.floor(i / L.cols) * (L.cell + 10), w: L.cell, h: L.cell };
  }

  move(p, dx, dy) {
    const n = this.cells.length;
    const cols = this._cols || 5;
    let i = this.cursor[p];
    if (dx) i = (i + dx + n) % n;
    if (dy) { i += dy * cols; if (i < 0) i += Math.ceil(n / cols) * cols; if (i >= n) i = i % cols; i = Math.min(n - 1, Math.max(0, i)); }
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

  drawSide(ctx, view, p, x, w) {
    const cell = this.cells[this.cursor[p]];
    const pick = this.picks[p];
    const entry = pick ? (pick.random ? null : DB.bySlug[pick.slug]) : cell.entry;
    const col = P_COLORS[p];
    const top = 100, h = C.BASE_H - 170;
    // pedestal
    const g = ctx.createRadialGradient(x + w / 2, top + h, 10, x + w / 2, top + h, w * 0.7);
    g.addColorStop(0, col + "55"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.fillRect(x, top, w, h + 20);
    if (entry && p === 1 && entry.pose2) UI.drawImageContain(ctx, entry.pose2, x + 10, top, w - 20, h, false);
    else if (entry && entry.pose) UI.drawImageContain(ctx, entry.pose, x + 10, top, w - 20, h, p === 1);
    else if (!entry && UI.IMG.random_pose) UI.drawImageContain(ctx, UI.IMG.random_pose, x + 10, top, w - 20, h, p === 1);
    else if (!entry) {
      UI.text(ctx, "?", x + w / 2, top + h / 2, { size: 150, color: "#2a2a34", shadow: false, stroke: 6, strokeColor: "#555" });
    }
    const label = this.players[p].label || `J${p + 1}`;
    UI.text(ctx, label, x + w / 2, top - 8, { size: 18, color: col });
    const name = entry ? entry.name : "Aleatorio";
    UI.text(ctx, this.confirmed[p] ? name.toUpperCase() : name, x + w / 2, top + h + 32, { size: 26, color: this.confirmed[p] ? col : "#fff", stroke: 5 });
    if (this.confirmed[p]) UI.text(ctx, "¡LISTO!", x + w / 2, top + h + 60, { size: 15, color: col });
  }

  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, this.title, 40);
    if (this.subtitle) UI.text(ctx, this.subtitle, view.w / 2, 74, { size: 16, color: "#ccc" });
    const L = this.layout(view);
    this._cols = L.cols;
    this.cells.forEach((c, i) => {
      const r = this.cellRect(L, i);
      if (c.entry) {
        ctx.save();
        UI.roundRect(ctx, r.x, r.y, r.w, r.h, 10);
        ctx.clip();
        UI.drawImageCover(ctx, c.entry.selection, r.x, r.y, r.w, r.h);
        ctx.restore();
        UI.roundRect(ctx, r.x, r.y, r.w, r.h, 10);
        ctx.lineWidth = 2; ctx.strokeStyle = "rgba(255,255,255,0.25)"; ctx.stroke();
      } else drawRandomTile(ctx, r.x, r.y, r.w);
      UI.addHit(r, () => this.tap(i));
    });
    // cursores
    this.players.forEach((pl, p) => {
      const r = this.cellRect(L, this.cursor[p]);
      const inset = p === 1 && this.cursor[0] === this.cursor[1] ? 5 : 0;
      UI.roundRect(ctx, r.x - 4 + inset, r.y - 4 + inset, r.w + 8 - 2 * inset, r.h + 8 - 2 * inset, 12);
      ctx.lineWidth = this.confirmed[p] ? 6 : 4;
      ctx.strokeStyle = P_COLORS[p];
      ctx.stroke();
      UI.text(ctx, pl.cpu ? "CPU" : `J${p + 1}`, r.x + (p === 0 ? 16 : r.w - 16), r.y + 12, { size: 13, color: P_COLORS[p], stroke: 3 });
    });
    this.drawSide(ctx, view, 0, 20, SIDE_W);
    if (this.players.length > 1) this.drawSide(ctx, view, 1, view.w - 20 - SIDE_W, SIDE_W);
    UI.pillButton(ctx, 70, 30, "◄ VOLVER", () => this.cancel(0), { size: 14, h: 30, minW: 100, color: "#3c3c48" });
    UI.footer(ctx, view, this.app.isTouchDevice ? "Tocá una cara para marcarla y otra vez para elegirla" : "Moverse con las flechas/stick · Puño o ENTER elige · Patada o ESC deshace");
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
    const availH = C.BASE_H - 90 - 44;   // entre el título y el pie
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
    UI.pillButton(ctx, 70, 30, "◄ VOLVER", () => this.onBack(), { size: 14, h: 30, minW: 100, color: "#3c3c48" });
    UI.footer(ctx, view, "Confirmar elige · Patada/ESC vuelve");
  }
}
