// =====================================================================
// scenes/tournament.js — Torneo de eliminación directa (3 a 16)
// Port de engine/tournament.py: el sorteo es UNA vez al armarlo; el
// ganador del cruce 1 juega contra el del cruce 2, etc. Si queda un
// número impar, el último pasa directo (bye). La final siempre es en el
// escenario secreto.
// =====================================================================
import * as C from "../config.js";
import { COLORS } from "../config.js";
import * as UI from "../ui.js";
import { audio } from "../audio.js";
import { DB, randomStage, secretStage } from "../assets.js";
import { ok } from "../input.js";
import { Match, announcerNamePath } from "../match.js";
import { drawRandomTile, gridLayout, drawThumb, P1_COLOR, FRAME_COLOR, GRID_TOP, GRID_BOTTOM_MARGIN, SIDE_PANEL_W, SIDE_MARGIN, GRID_SIDE_GAP, GAP, SEL_FRAME_PAD } from "./select.js";
import * as Flow from "../flow.js";

export function labelPicks(picks) {
  const counts = {};
  return picks.map((p) => {
    if (p.label) return { ...p };
    counts[p.slug] = (counts[p.slug] || 0) + 1;
    const n = counts[p.slug];
    const name = DB.bySlug[p.slug].name;
    return { ...p, label: n === 1 ? name : `${name} ${n}` };
  });
}

export class TournamentBracket {
  constructor(picks, keepOrder = false) {
    this.entrants = labelPicks(picks);
    this.roundNumber = 1;
    this.champion = null;
    this.history = [];
    const seeded = [...this.entrants];
    if (!keepOrder) for (let i = seeded.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [seeded[i], seeded[j]] = [seeded[j], seeded[i]]; }
    this.startRound(seeded);
  }
  startRound(parts) {
    parts = [...parts];
    this.bye = parts.length % 2 === 1 ? parts.pop() : null;
    this.matches = [];
    for (let i = 0; i < parts.length; i += 2) this.matches.push([parts[i], parts[i + 1]]);
    this.matchIndex = 0;
    this.results = [];
  }
  currentMatch() { return this.matches[this.matchIndex] || null; }
  isFinalMatch() { return this.matches.length === 1 && !this.bye; }
  reportResult(winner) {
    this.results.push(winner);
    this.matchIndex += 1;
    if (this.matchIndex >= this.matches.length) {
      const adv = [...this.results];
      if (this.bye) adv.push(this.bye);
      this.history.push({ round: this.roundNumber, matches: this.matches, bye: this.bye, results: [...this.results] });
      if (adv.length === 1) { this.champion = adv[0]; return true; }
      this.roundNumber += 1;
      this.startRound(adv);
    }
    return false;
  }
  // estado plano (para dibujar y para mandar por red)
  state() {
    const e = (x) => (x ? { slug: x.slug, label: x.label, owner: x.owner ?? null } : null);
    return {
      round: this.roundNumber, final: this.isFinalMatch(), idx: this.matchIndex,
      matches: this.matches.map(([a, b]) => [e(a), e(b)]),
      results: this.results.map((r) => r.label), bye: e(this.bye), champion: e(this.champion),
      total: this.entrants.length,
      history: this.history.map((h) => ({ round: h.round, winners: h.results.map((r) => r.label) })),
    };
  }
}

function portrait(ctx, slug, x, y, s) {
  const ent = DB.bySlug[slug];
  ctx.save();
  UI.roundRect(ctx, x, y, s, s, 8);
  ctx.clip();
  if (ent) UI.drawImageCover(ctx, ent.selection, x, y, s, s); else drawRandomTile(ctx, x, y, s);
  ctx.restore();
}

/** Dibuja el bracket a partir de TournamentBracket.state() */
export function drawBracket(ctx, view, st, { phase = "ready", result = null, t = 0, hint = "" } = {}) {
  UI.menuBackground(ctx, view, t);
  UI.title(ctx, view, st.final ? "FINAL" : `RONDA ${st.round}`, 36);
  UI.text(ctx, `${st.total} luchadores · eliminación directa`, view.w / 2, 66, { size: 14, color: "#aaa" });
  const cur = st.matches[st.idx];
  // pelea actual, grande
  if (cur && phase !== "result") {
    const cx = view.w / 2;
    portrait(ctx, cur[0].slug, cx - 230, 90, 110);
    portrait(ctx, cur[1].slug, cx + 120, 90, 110);
    UI.text(ctx, cur[0].label, cx - 175, 220, { size: 20 });
    UI.text(ctx, cur[1].label, cx + 175, 220, { size: 20 });
    UI.text(ctx, "VS", cx, 145, { size: 54, color: COLORS.red, stroke: 6 });
  }
  if (phase === "result" && result) {
    UI.text(ctx, `¡${result.winner.toUpperCase()} AVANZA!`, view.w / 2, 150, { size: 40, color: COLORS.yellow, stroke: 7 });
    UI.text(ctx, `${result.loser} queda eliminado`, view.w / 2, 195, { size: 18, color: "#ccc" });
  }
  // lista de cruces de la ronda
  const n = st.matches.length + (st.bye ? 1 : 0);
  const cols = n > 4 ? 2 : 1;
  const perCol = Math.ceil(n / cols);
  const rowH = Math.min(36, (C.BASE_H - 300) / perCol);
  const colW = 360;
  const x0 = view.w / 2 - (cols * colW + (cols - 1) * 20) / 2;
  const rows = st.matches.map((m, i) => ({ m, i }));
  if (st.bye) rows.push({ bye: st.bye });
  rows.forEach((r, k) => {
    const x = x0 + Math.floor(k / perCol) * (colW + 20);
    const y = 250 + (k % perCol) * rowH;
    const isCur = r.i === st.idx;
    UI.roundRect(ctx, x, y, colW, rowH - 6, 8);
    ctx.fillStyle = isCur ? "rgba(240,200,40,0.18)" : "rgba(255,255,255,0.06)";
    ctx.fill();
    if (r.bye) {
      UI.text(ctx, `${r.bye.label} pasa directo`, x + colW / 2, y + rowH / 2 - 3, { size: 15, color: "#9cf" });
      return;
    }
    const w = st.results[r.i];
    const [a, b] = r.m;
    const colA = w ? (w === a.label ? COLORS.green : "#777") : "#fff";
    const colB = w ? (w === b.label ? COLORS.green : "#777") : "#fff";
    UI.text(ctx, a.label, x + colW / 2 - 24, y + rowH / 2 - 3, { size: 15, align: "right", color: colA });
    UI.text(ctx, "vs", x + colW / 2, y + rowH / 2 - 3, { size: 13, color: COLORS.red });
    UI.text(ctx, b.label, x + colW / 2 + 24, y + rowH / 2 - 3, { size: 15, align: "left", color: colB });
  });
  if (hint) UI.footer(ctx, view, hint);
}

// ---------------------------------------------------------------------
// Torneo LOCAL: se eligen N luchadores de a uno (J1), las peleas las
// juegan J1 y J2 en el mismo equipo.
// ---------------------------------------------------------------------
// Igual que la de PC (engine/menu.py TournamentCharacterSelect): pose a
// la izquierda, grilla en el medio y "Personajes elegidos" a la derecha.
const TOURNAMENT_LIST_W = 230;

class TournamentPickScene {
  constructor(app, count) {
    this.app = app; this.count = count; this.picks = []; this.cursor = 0;
    this.cells = DB.roster;
  }
  update() {
    const i = this.app.anyInput;
    const n = this.cells.length;
    const cols = this._cols || 3;
    if (i.justPressed("left")) this.cursor = (this.cursor - 1 + n) % n;
    else if (i.justPressed("right")) this.cursor = (this.cursor + 1) % n;
    else if (i.justPressed("up")) this.cursor = (((this.cursor - cols) % n) + n) % n;
    else if (i.justPressed("down")) this.cursor = (this.cursor + cols) % n;
    else if (ok(i)) this.add(this.cursor);
    else if (i.justPressed("cancel")) this.undo();
  }
  add(k) {
    this.picks.push({ slug: this.cells[k].slug });
    audio.play(announcerNamePath(this.cells[k]), 0.9, "announcer");
    if (this.picks.length >= this.count) {
      const bracket = new TournamentBracket(this.picks);
      this.app.setScene(new BracketScene(this.app, bracket));
    }
  }
  undo() {
    if (this.picks.length) this.picks.pop();
    else Flow.localMenu(this.app, 1);
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t, "select", 0);
    const n = this.cells.length;
    const availW = view.w - 2 * SIDE_MARGIN - SIDE_PANEL_W - GRID_SIDE_GAP - TOURNAMENT_LIST_W - GRID_SIDE_GAP;
    const availH = C.BASE_H - GRID_TOP - GRID_BOTTOM_MARGIN;
    const g = gridLayout(n, availW, availH);
    this._cols = g.cols;
    const gw = g.cols * g.cell + (g.cols - 1) * GAP, gh = g.rows * g.cell + (g.rows - 1) * GAP;
    const left = SIDE_MARGIN + SIDE_PANEL_W + GRID_SIDE_GAP;
    const right = view.w - SIDE_MARGIN - TOURNAMENT_LIST_W - GRID_SIDE_GAP;
    const x0 = left + Math.max(0, Math.floor((right - left - gw) / 2));
    const y0 = GRID_TOP + Math.max(0, Math.floor((availH - gh) / 2));
    this.cells.forEach((c, k) => {
      const x = x0 + (k % g.cols) * (g.cell + GAP), y = y0 + Math.floor(k / g.cols) * (g.cell + GAP);
      UI.roundRect(ctx, x, y, g.cell, g.cell, 8);
      ctx.fillStyle = k === this.cursor ? P1_COLOR : FRAME_COLOR; ctx.fill();
      drawThumb(ctx, c.selection, x + SEL_FRAME_PAD / 2, y + SEL_FRAME_PAD / 2, g.cell - SEL_FRAME_PAD, 8);
      UI.addHit({ x, y, w: g.cell, h: g.cell }, () => { if (this.cursor === k) this.add(k); else this.cursor = k; });
    });
    // pose del luchador marcado (izquierda)
    const cur = this.cells[this.cursor];
    if (cur.pose) ctx.drawImage(cur.pose, SIDE_MARGIN, C.BASE_H / 2 - SIDE_PANEL_W / 2, SIDE_PANEL_W, SIDE_PANEL_W);
    // lista de elegidos (derecha)
    const lx = view.w - SIDE_MARGIN - TOURNAMENT_LIST_W;
    UI.text(ctx, "Personajes elegidos", lx, GRID_TOP, { size: 20, align: "left", baseline: "top" });
    const rowH = Math.min(28, (C.BASE_H - GRID_TOP - GRID_BOTTOM_MARGIN - 24) / Math.max(1, this.count));
    const labeled = labelPicks(this.picks);
    for (let k = 0; k < this.count; k++) {
      const y = GRID_TOP + 24 + 10 + k * rowH;
      const txt = k < labeled.length ? `${k + 1}. ${labeled[k].label}` : `${k + 1}. _ _ _`;
      UI.text(ctx, txt, lx, y, { size: 15, align: "left", baseline: "top", color: k < labeled.length ? "#fff" : "rgb(110,110,118)" });
    }
    UI.text(ctx, `ELEGIR LUCHADOR ${this.picks.length + 1}`, view.w / 2, 25, { size: 38, color: COLORS.yellow });
    if (this.app.isTouchDevice) {
      UI.pillButton(ctx, 70, 30, "◄ DESHACER", () => this.undo(), { size: 13, h: 30, minW: 110, color: "#3c3c48" });
      UI.pillButton(ctx, view.w / 2, C.BASE_H - 46, "ACEPTAR", () => this.add(this.cursor), { size: 20, h: 42, minW: 200 });
      UI.footer(ctx, view, "Tocá un luchador y después ACEPTAR", C.BASE_H - 12);
    } else UI.footer(ctx, view, "Puño o ENTER confirma · Patada o ESC deshace/vuelve", C.BASE_H - 25);
  }
}

export function startLocalTournament(app, count) {
  app.setScene(new TournamentPickScene(app, count));
}

class BracketScene {
  constructor(app, bracket) {
    this.app = app; this.bracket = bracket; this.phase = "ready"; this.result = null; this.timer = 0;
  }
  enter() { this.app.touch.fightMode = false; }
  update(dt) {
    if (this.phase === "result") {
      this.timer -= dt;
      if (this.timer <= 0 || ok(this.app.anyInput)) this.advance();
    } else if (ok(this.app.anyInput)) this.fight();
    else if (this.app.anyInput.justPressed("cancel")) this.confirmQuit = true;
  }
  onPointer() { if (this.phase === "result") { this.advance(); return true; } return false; }
  advance() {
    const b = this.bracket;
    const finished = b.reportResult(this.result.winnerEntrant);
    this.phase = "ready";
    if (finished) this.app.setScene(new TournamentVictory(this.app, b.champion, b.entrants.length));
  }
  async fight() {
    if (this.starting) return;
    this.starting = true;
    const b = this.bracket;
    const m = b.currentMatch();
    const stageDef = b.isFinalMatch() ? (secretStage() || randomStage()) : randomStage();
    const prep = await Flow.prepareFight(this.app, [m[0].slug, m[1].slug], stageDef);
    audio.stopAllSfx();
    Flow.playStageMusic(prep.stage);
    const match = new Match({ entries: prep.entries, frames: prep.frames, stage: prep.stage, inputs: [this.app.inputs[0], this.app.inputs[1]], names: [m[0].label, m[1].label] });
    const app = this.app;
    app.setScene(new Flow.FightScene(app, {
      match, pausers: [app.inputs[0], app.inputs[1]], overDelay: 3.2,
      onOver: (mm) => {
        if (mm.stage) mm.stage.dispose();
        this.starting = false;
        const w = m[mm.winner], l = m[1 - mm.winner];
        if (b.isFinalMatch()) {
          b.reportResult(w);
          app.setScene(new TournamentVictory(app, b.champion, b.entrants.length));
          return;
        }
        this.result = { winner: w.label, loser: l.label, winnerEntrant: w };
        this.phase = "result";
        this.timer = 3;
        app.setScene(this);
      },
    }));
  }
  draw(ctx, view) {
    drawBracket(ctx, view, this.bracket.state(), {
      phase: this.phase, result: this.result, t: this.app.t,
      hint: this.phase === "ready" ? "Confirmar: ¡a pelear! (J1 a la izquierda, J2 a la derecha)" : "",
    });
    if (this.phase === "ready") UI.pillButton(ctx, view.w / 2, 232, "¡PELEAR!", () => this.fight(), { size: 16, h: 34, minW: 140 });
    UI.pillButton(ctx, 70, 30, "SALIR", () => Flow.mainMenu(this.app), { size: 13, h: 30, minW: 90, color: "#3c3c48" });
  }
}

export class TournamentVictory {
  constructor(app, champion, total, { onDone = null, label = null } = {}) {
    this.app = app; this.champion = champion; this.total = total; this.onDone = onDone;
    this.label = label || champion.label;
    this.confetti = new UI.Confetti(app.view);
  }
  enter() { this.app.touch.fightMode = false; }
  update(dt) {
    this.confetti.update(dt);
    if (ok(this.app.anyInput)) this.done();
  }
  done() { if (this.onDone) this.onDone(); else Flow.mainMenu(this.app); }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, 0, "tower", 0.3);
    const ent = DB.bySlug[this.champion.slug];
    if (ent) UI.drawImageContain(ctx, ent.pose, view.w / 2 - 140, 130, 280, C.BASE_H - 170);
    this.confetti.draw(ctx);
    UI.title(ctx, view, `¡${this.label.toUpperCase()} GANA EL TORNEO!`, 60, COLORS.yellow, 36);
    UI.text(ctx, `Campeón entre ${this.total} luchadores`, view.w / 2, 100, { size: 18 });
    if (this.onDone !== false) UI.pillButton(ctx, view.w / 2, C.BASE_H - 30, "CONTINUAR", () => this.done(), { size: 16, h: 36 });
  }
}
