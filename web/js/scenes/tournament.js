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
import { DB, randomStage, secretStage, loadCharacterFrames } from "../assets.js";
import { Character } from "../character.js";
import { ok } from "../input.js";
import { Match, announcerNamePath } from "../match.js";
import { drawRandomTile, gridLayout, drawThumb, drawFlipped, P1_COLOR, P2_COLOR, FRAME_COLOR, GRID_TOP, GRID_BOTTOM_MARGIN, SIDE_PANEL_W, SIDE_MARGIN, GRID_SIDE_GAP, GAP, SEL_FRAME_PAD } from "./select.js";
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
      history: this.history.map((h) => ({
        round: h.round, matches: h.matches.map(([a, b]) => [e(a), e(b)]), bye: e(h.bye), results: h.results.map((r) => r.label),
      })),
    };
  }
}

// ---------------------------------------------------------------------
// Cuadro del torneo, igual que en PC (engine/menu.py
// TournamentBracketScreen): árbol completo desde la Ronda 1 (las líneas
// no cambian en todo el torneo), tarjetas que van subiendo a medida que
// se ganan los cruces, y las poses de los dos que pelean a los costados.
// ---------------------------------------------------------------------
const RISE_DURATION = 0.8;     // las poses "suben" al entrar a cada pelea
export const RESULT_DURATION = 1.8;   // el perdedor "cae" en la pantalla de resultado
const LINE_COLOR = "rgb(150,150,158)";
const GREY = "rgb(90,90,100)", WIN_GREY = "rgb(120,120,128)", BYE_GREY = "rgb(140,140,148)";

// misma estructura de slots que _build_slot_structure (PC)
function slotStructure(leafCount) {
  let level = [...Array(leafCount).keys()];
  const rounds = [];
  let nextId = leafCount;
  while (level.length > 1) {
    const slots = [...level];
    const bye = slots.length % 2 === 1 ? slots.pop() : null;
    const pairs = [];
    for (let i = 0; i < slots.length; i += 2) pairs.push([slots[i], slots[i + 1]]);
    const winnerSlots = pairs.map((_, i) => nextId + i);
    rounds.push({ pairs, bye, winnerSlots });
    nextId += pairs.length;
    level = [...winnerSlots, ...(bye !== null ? [bye] : [])];
  }
  return rounds;
}

function bracketLayout(st, view) {
  const struct = slotStructure(st.total);
  const r1 = st.history.length ? st.history[0] : { matches: st.matches, bye: st.bye };
  let card = 40, pairGap = card * 0.62, branchGap = card * 0.55;
  const nM = r1.matches.length, hasBye = !!r1.bye, entries = nM + (hasBye ? 1 : 0);
  const matchHalf = () => pairGap + card * 0.5;
  const natural = matchHalf() * 2 * nM + (hasBye ? card : 0) + branchGap * Math.max(0, entries - 1);
  const push = 70;
  const budget = (view.w - 2 * SIDE_MARGIN - 2 * SIDE_PANEL_W) + 2 * push + 2 * SIDE_PANEL_W * 0.2;
  if (natural > budget && budget > 0) { card *= budget / natural; pairGap = card * 0.62; branchGap = card * 0.55; }
  const centerBottom = C.BASE_H - 110;
  const rowH = 330 / (struct.length + 1);
  const leafY = centerBottom - rowH * 0.5;
  const totalW = matchHalf() * 2 * nM + (hasBye ? card : 0) + branchGap * Math.max(0, entries - 1);
  let cx = view.w / 2 - totalW / 2;
  const pos = {};
  for (let m = 0; m < nM; m++) {
    const sc = cx + matchHalf();
    cx += matchHalf() * 2 + branchGap;
    pos[2 * m] = [sc - pairGap, leafY];
    pos[2 * m + 1] = [sc + pairGap, leafY];
  }
  if (hasBye) pos[2 * nM] = [cx + card * 0.5, leafY];
  const lines = [], winnerPos = {}, byePos = {};
  const minGap = card * 1.05;
  let curY = leafY;
  struct.forEach((rnd, ri) => {
    const nextY = curY - rowH;
    const raw = rnd.pairs.map(([a, b], i) => [rnd.winnerSlots[i], (pos[a][0] + pos[b][0]) / 2]);
    if (rnd.bye !== null) raw.push([rnd.bye, pos[rnd.bye][0]]);
    raw.sort((p, q) => p[1] - q[1]);
    const resolved = {};
    let prev = null;
    for (let [id, x] of raw) { if (prev !== null && x - prev < minGap) x = prev + minGap; resolved[id] = x; prev = x; }
    rnd.pairs.forEach(([a, b], i) => {
      const [ax, ay] = pos[a], [bx] = pos[b];
      const ns = rnd.winnerSlots[i], nx = resolved[ns];
      pos[ns] = [nx, nextY]; winnerPos[ns] = [nx, nextY];
      const mergeY = nextY + (ay - nextY) * 0.65;
      lines.push([ax, ay, ax, mergeY], [bx, ay, bx, mergeY], [ax, mergeY, bx, mergeY], [(ax + bx) / 2, mergeY, nx, nextY]);
    });
    if (rnd.bye !== null) {
      const [ox, oy] = pos[rnd.bye];
      pos[rnd.bye] = [resolved[rnd.bye], nextY];
      byePos[ri] = [ox, oy, resolved[rnd.bye], nextY];
    }
    curY = nextY;
  });
  return { struct, card, pos, lines, winnerPos, byePos, r1 };
}

function drawCard(ctx, ent, cx, cy, color, size, { dim = false, alpha = 1 } = {}) {
  const radius = Math.max(2, Math.min(Math.round(size * 0.15), 14));
  const bw = Math.max(2, Math.min(Math.round(size * 0.065), 6));
  const x = cx - size / 2, y = cy - size / 2;
  const db = ent && DB.bySlug[ent.slug];
  ctx.save();
  ctx.globalAlpha = alpha;
  UI.roundRect(ctx, x, y, size, size, radius);
  ctx.fillStyle = "rgb(35,35,42)"; ctx.fill();
  ctx.save(); ctx.clip();
  if (db && db.selection) UI.drawImageCover(ctx, db.selection, x, y, size, size); else drawRandomTile(ctx, x, y, size);
  ctx.restore();
  UI.roundRect(ctx, x - bw / 2, y - bw / 2, size + bw, size + bw, radius + bw / 2);
  ctx.lineWidth = bw; ctx.strokeStyle = color; ctx.stroke();
  if (dim) { UI.roundRect(ctx, x, y, size, size, radius); ctx.fillStyle = "rgba(0,0,0,0.51)"; ctx.fill(); }
  ctx.restore();
}

function drawPose(ctx, view, ent, side, yOff) {
  const db = ent && DB.bySlug[ent.slug];
  const y = C.BASE_H / 2 - SIDE_PANEL_W / 2 + yOff;
  const push = 70;
  if (db) {
    if (side === "left") drawFlipped(ctx, db.pose, SIDE_MARGIN - push, y, SIDE_PANEL_W, SIDE_PANEL_W, false);
    else {
      const x = view.w - SIDE_MARGIN - SIDE_PANEL_W + push;
      if (db.pose2) drawFlipped(ctx, db.pose2, x, y, SIDE_PANEL_W, SIDE_PANEL_W, false);
      else drawFlipped(ctx, db.pose, x, y, SIDE_PANEL_W, SIDE_PANEL_W, true);
    }
  }
  const left = side === "left";
  UI.text(ctx, `${left ? "J1" : "J2"}: ${ent.label}`, left ? 40 : view.w - 40, C.BASE_H / 2 + 240,
    { size: 20, color: left ? P1_COLOR : P2_COLOR, align: left ? "left" : "right", baseline: "top" });
}

/**
 * Dibuja el cuadro a partir de TournamentBracket.state().
 * phase: "ready" | "result";  anim: segundos desde que empezó esa fase;
 * result: {winner, loser} (labels) en la fase "result".
 */
export function drawBracket(ctx, view, st, { phase = "ready", result = null, anim = 99, hint = "" } = {}) {
  UI.menuBackground(ctx, view, 0, "select", 0);
  UI.text(ctx, st.final ? "FINAL" : `RONDA ${st.round}`, view.w / 2, 25, { size: 38, color: COLORS.yellow });
  const L = bracketLayout(st, view);
  // todos los luchadores, por label
  const byLabel = {};
  L.r1.matches.forEach(([a, b]) => { byLabel[a.label] = a; byLabel[b.label] = b; });
  if (L.r1.bye) byLabel[L.r1.bye.label] = L.r1.bye;

  if (phase === "result" && result) {
    const cx = view.w / 2, cardY = 320, size = 150, gap = 230;
    const k = Math.min(1, anim / RESULT_DURATION);
    const w = byLabel[result.winner], l = byLabel[result.loser];
    if (w) drawCard(ctx, w, cx, cardY, WIN_GREY, size);
    if (l) drawCard(ctx, l, cx + gap, cardY + k * 90, GREY, size, { alpha: Math.max(60, 255 - k * 195) / 255 });
    const r = UI.wrapText(ctx, `${result.winner} avanza`, 28, view.w - 120);
    r.lines.forEach((ln, i) => UI.text(ctx, ln, cx, cardY + size / 2 + 50 + i * r.size * 1.15, { size: r.size, color: COLORS.yellow }));
    if (hint) UI.footer(ctx, view, hint, C.BASE_H - 30);
    return;
  }

  ctx.save();
  ctx.strokeStyle = LINE_COLOR; ctx.lineWidth = 2;
  for (const [x1, y1, x2, y2] of L.lines) { ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); }
  ctx.restore();

  // tarjetas (se dibujan después de las poses, para quedar por encima)
  const cards = [];
  const slotEnt = {};
  L.r1.matches.forEach(([a, b], i) => { slotEnt[2 * i] = a; slotEnt[2 * i + 1] = b; });
  if (L.r1.bye) slotEnt[2 * L.r1.matches.length] = L.r1.bye;
  const rounds = st.history.map((h) => ({ matches: h.matches, results: h.results, idx: h.matches.length, current: false }));
  rounds.push({ matches: st.matches, results: st.results, idx: st.idx, current: true });
  rounds.forEach((rd, ri) => {
    const s = L.struct[ri];
    if (!s) return;
    s.pairs.forEach(([sa, sb], i) => {
      const a = slotEnt[sa], b = slotEnt[sb];
      if (!a || !b) return;
      const [ax, ay] = L.pos[sa], [bx] = L.pos[sb];
      const decided = i < rd.idx;
      const active = rd.current && i === rd.idx;
      const [nx, ny] = L.winnerPos[s.winnerSlots[i]];
      if (decided) {
        const wl = rd.results[i];
        const winner = wl === a.label ? a : b, loser = winner === a ? b : a;
        cards.push([loser, loser === a ? ax : bx, ay, GREY, true]);
        cards.push([winner, winner === a ? ax : bx, ay, WIN_GREY, false]);
        cards.push([winner, nx, ny, WIN_GREY, false]);
        slotEnt[s.winnerSlots[i]] = winner;
      } else {
        cards.push([a, ax, ay, active ? P1_COLOR : GREY, false]);
        cards.push([b, bx, ay, active ? P2_COLOR : GREY, false]);
      }
    });
    if (s.bye !== null) {
      const be = slotEnt[s.bye];
      if (be && L.byePos[ri]) cards.push([be, L.byePos[ri][2], L.byePos[ri][3], BYE_GREY, false]);
    }
  });

  const cur = st.matches[st.idx];
  if (cur) {
    const p = Math.min(1, anim / RISE_DURATION);
    const eased = 1 - (1 - p) ** 3;
    const off = (1 - eased) * 120;
    drawPose(ctx, view, cur[0], "left", off);
    drawPose(ctx, view, cur[1], "right", off);
  }
  for (const [e, x, y, col, dim] of cards) drawCard(ctx, e, x, y, col, L.card, { dim });
  if (hint) UI.footer(ctx, view, hint, C.BASE_H - 30);
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
    for (const c of this.cells) audio.load(announcerNamePath(c));
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
      UI.backButton(ctx, () => this.undo(), "◄ DESHACER");
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
    this.app = app; this.bracket = bracket; this.phase = "ready"; this.result = null; this.timer = 0; this.anim = 0;
  }
  enter() { this.app.touch.fightMode = false; }
  update(dt) {
    this.anim += dt;
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
    this.anim = 0;
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
        this.timer = RESULT_DURATION;
        this.anim = 0;
        app.setScene(this);
      },
    }));
  }
  draw(ctx, view) {
    const touch = this.app.isTouchDevice;
    drawBracket(ctx, view, this.bracket.state(), {
      phase: this.phase, result: this.result, anim: this.anim,
      hint: touch ? "" : (this.phase === "ready" ? "ENTER: ¡a pelear!" : "ENTER: continuar"),
    });
    if (this.phase === "ready" && touch) UI.pillButton(ctx, view.w / 2, C.BASE_H - 34, "¡PELEAR!", () => this.fight(), { size: 18, h: 40, minW: 170 });
    UI.backButton(ctx, () => Flow.mainMenu(this.app), "◄ SALIR");
  }
}

export class TournamentVictory {
  constructor(app, champion, total, { onDone = null, label = null } = {}) {
    this.app = app; this.champion = champion; this.total = total; this.onDone = onDone;
    this.label = label || champion.label;
    this.confetti = new UI.Confetti(app.view);
    // el campeón festejando con su animación WIN (igual que en PC)
    this.char = null;
    const ent = DB.bySlug[champion.slug];
    if (ent) loadCharacterFrames(champion.slug).then((f) => {
      const ch = new Character(ent, f);
      ch.setState(C.S.WIN, true);
      ch.x = C.BASE_W / 2; ch.y = C.GROUND_Y; ch.facing = 1;
      this.char = ch;
    }).catch(() => {});
  }
  enter() { this.app.touch.fightMode = false; }
  update(dt) {
    this.confetti.update(dt);
    if (this.char) this.char.animations[C.S.WIN].update(dt);
    if (ok(this.app.anyInput)) this.done();
  }
  done() { if (this.onDone) this.onDone(); else Flow.mainMenu(this.app); }
  draw(ctx, view) {
    ctx.fillStyle = COLORS.dark; ctx.fillRect(0, 0, view.w, C.BASE_H);
    if (this.char) this.char.draw(ctx, 0, view.pad);
    this.confetti.draw(ctx);
    UI.pcTitle(ctx, view, `¡${this.label.toUpperCase()} GANA\u00a0EL\u00a0TORNEO!`, 60, COLORS.yellow);
    if (this.onDone !== false) UI.pillButton(ctx, view.w / 2, C.BASE_H - 30, "CONTINUAR", () => this.done(), { size: 16, h: 36 });
  }
}
