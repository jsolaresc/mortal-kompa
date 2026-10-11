// =====================================================================
// scenes/tower.js — Torre de Batalla (como Mortal Kompa): peleás contra
// todos los demás en orden al azar, cada piso 5% más difícil, y al final
// un jefe misterioso (silueta negra, nombre al revés, +20%) en el
// escenario secreto.
// =====================================================================
import * as C from "../config.js";
import { COLORS } from "../config.js";
import * as UI from "../ui.js";
import { audio } from "../audio.js";
import { DB, randomStage, secretStage } from "../assets.js";
import { CPUInput, ok } from "../input.js";
import { Match } from "../match.js";
import { CharSelectScene, drawRandomTile } from "./select.js";

function drawRounded(ctx, img, x, y, s, r) {
  if (!img) return;
  ctx.save(); UI.roundRect(ctx, x, y, s, s, r); ctx.clip();
  ctx.drawImage(img, x, y, s, s); ctx.restore();
}
import * as Flow from "../flow.js";

const DIFFICULTY_STEP = 1.05;
const BOSS_MULT = 1.20;
// medidas de la Torre de Mortal Kompa de PC (engine/tower.py, base 960x540)
const FLOOR_H = 130;
const FLOOR_GAP = 24;
const POSE_SIZE = 286;
const CELL = 100, THUMB = 92;
const PLAYER_BLUE = "rgb(80,170,240)", RIVAL_YELLOW = "rgb(240,200,50)", OTHER_GRAY = "rgb(90,90,100)";

function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

export function startTower(app, startLevel) {
  app.setScene(new CharSelectScene(app, {
    players: [{ input: app.inputs[0] }],
    onBack: () => Flow.onePlayerMenu(app, 0),
    onDone: (picks) => {
      const me = picks[0].slug;
      const opps = shuffle(DB.roster.filter((c) => c.slug !== me)).map((c) => ({ slug: c.slug, name: c.name }));
      const cands = DB.roster.filter((c) => c.slug !== me);
      const boss = cands[Math.floor(Math.random() * cands.length)];
      const rev = boss.name.split("").reverse().join("").toLowerCase();
      opps.push({ slug: boss.slug, name: rev.charAt(0).toUpperCase() + rev.slice(1), boss: true, realName: boss.name });
      const tower = { me, opps, floor: 0, difficulty: startLevel, startLevel };
      app.setScene(new TowerScene(app, tower));
    },
  }));
}

class TowerScene {
  constructor(app, tower, justWon = false) {
    this.app = app;
    this.tower = tower;
    this.scroll = Math.max(0, tower.floor - (justWon ? 1 : 0)) * FLOOR_H;
    this.anim = 0;
  }
  enter() { this.app.touch.fightMode = false; }
  update(dt) {
    const target = this.tower.floor * FLOOR_H;
    this.anim = Math.min(1, this.anim + dt / 1.8);
    const e = 1 - Math.pow(1 - this.anim, 3);
    this.scrollNow = this.scroll + (target - this.scroll) * e;
    if (ok(this.app.anyInput) && this.anim > 0.3) this.fight();
    else if (this.app.anyInput.justPressed("cancel")) Flow.onePlayerMenu(this.app, 0);
  }
  async fight() {
    if (this.starting) return;
    this.starting = true;
    const t = this.tower;
    const opp = t.opps[t.floor];
    const stageDef = opp.boss ? (secretStage() || randomStage()) : randomStage();
    const prep = await Flow.prepareFight(this.app, [t.me, opp.slug], stageDef);
    audio.stopAllSfx();
    Flow.playStageMusic(prep.stage);
    const cpu = new CPUInput(t.difficulty);
    const match = new Match({
      entries: prep.entries, frames: prep.frames, stage: prep.stage,
      inputs: [this.app.inputs[0], cpu], boss: opp.boss ? { name: opp.name } : null,
    });
    const app = this.app;
    app.setScene(new Flow.FightScene(app, {
      match, pausers: [app.inputs[0]], overDelay: 3.5,
      onOver: (m) => {
        if (m.stage) m.stage.dispose();
        if (m.winner === 0) {
          t.floor += 1;
          t.difficulty *= t.floor === t.opps.length - 1 ? BOSS_MULT : DIFFICULTY_STEP;
          if (t.floor >= t.opps.length) app.setScene(new TowerVictory(app, t));
          else app.setScene(new TowerScene(app, t, true));
        } else app.setScene(new TowerDefeat(app, t));
      },
    }));
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t, "tower", 0);
    const t = this.tower;
    const n = t.opps.length;
    const X = view.pad || 0;        // el diseño es de 960 de ancho: centrado en pantallas más anchas
    const baseY = C.BASE_H - 110;   // altura del piso actual
    const scroll = this.scrollNow ?? this.scroll;
    const me = DB.bySlug[t.me];

    // pose grande del jugador, a la izquierda (anclada por los pies)
    if (me.pose) ctx.drawImage(me.pose, X + 130 - POSE_SIZE / 2, C.BASE_H - 30 - POSE_SIZE, POSE_SIZE, POSE_SIZE);

    const playerCx = X + 320;
    const rivalsCx = playerCx + 100 + FLOOR_GAP;

    // columna de rivales: van subiendo
    for (let i = 0; i < n; i++) {
      const y = baseY - i * FLOOR_H + scroll;
      if (y < -FLOOR_H || y > C.BASE_H + FLOOR_H) continue;
      const o = t.opps[i];
      const beaten = i < t.floor;
      const rx = rivalsCx - CELL / 2, ry = y - CELL / 2;
      ctx.save();
      if (beaten) ctx.globalAlpha = 0.3;
      UI.roundRect(ctx, rx, ry, CELL, CELL, 10);
      ctx.fillStyle = i === t.floor ? RIVAL_YELLOW : OTHER_GRAY;
      ctx.fill();
      const img = o.boss ? UI.IMG.random_sel : DB.bySlug[o.slug].selection;
      if (img) drawRounded(ctx, img, rx + (CELL - THUMB) / 2, ry + (CELL - THUMB) / 2, THUMB, 10);
      else if (o.boss) drawRandomTile(ctx, rx + (CELL - THUMB) / 2, ry + (CELL - THUMB) / 2, THUMB);
      ctx.restore();
      UI.text(ctx, o.boss ? "???" : o.name, rx + CELL + 16, y, { size: 20, align: "left", color: beaten ? "rgb(120,120,125)" : "rgb(230,230,230)" });
    }

    // el jugador sube en paralelo, a la altura del rival actual
    const py = baseY - t.floor * FLOOR_H + scroll;
    const px = playerCx - CELL / 2, pty = py - CELL / 2;
    UI.roundRect(ctx, px, pty, CELL, CELL, 10);
    ctx.fillStyle = PLAYER_BLUE; ctx.fill();
    drawRounded(ctx, me.selection, px + (CELL - THUMB) / 2, pty + (CELL - THUMB) / 2, THUMB, 10);
    UI.text(ctx, me.name, playerCx, pty + CELL + 8, { size: 20, color: "rgb(230,230,230)", baseline: "top" });

    // velo arriba para que los pisos aparezcan/desaparezcan suave
    const g = ctx.createLinearGradient(0, 0, 0, 70);
    g.addColorStop(0, "rgba(20,20,24,1)"); g.addColorStop(1, "rgba(20,20,24,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, view.w, 70);

    // piso + rival (columna derecha)
    const textX = X + 800;
    const o = t.opps[t.floor];
    if (o) {
      const isBoss = !!o.boss;
      UI.text(ctx, isBoss ? "FINAL" : `PISO ${t.floor + 1} DE ${n}`, X + 130, 40, { size: 30, color: COLORS.yellow });
      UI.text(ctx, "Rival:", textX, 90, { size: 30, color: COLORS.yellow });
      UI.text(ctx, isBoss ? "???" : o.name, textX, 90 + 18 + 12 + 38, { size: 64, color: COLORS.yellow });
      const pose = isBoss ? UI.IMG.random_pose : DB.bySlug[o.slug].pose;
      if (pose) {
        ctx.save();
        ctx.translate(textX + POSE_SIZE / 2, C.BASE_H - 30 - POSE_SIZE);
        ctx.scale(-1, 1);   // mirando hacia el jugador
        ctx.drawImage(pose, 0, 0, POSE_SIZE, POSE_SIZE);
        ctx.restore();
      }
    }
    // tocar / clic en cualquier lado = pelear
    UI.addHit({ x: 0, y: 0, w: view.w, h: C.BASE_H }, () => { if (this.anim > 0.3) this.fight(); });
    UI.footer(ctx, view, this.app.isTouchDevice ? "Tocá la pantalla para continuar" : "Puño o ENTER: continuar", C.BASE_H - 30);
  }
}

class TowerDefeat {
  constructor(app, tower) { this.app = app; this.tower = tower; this.index = 0; }
  enter() { this.app.touch.fightMode = false; }
  pick(i) {
    if (i === 0) this.app.setScene(new TowerScene(this.app, this.tower));
    else Flow.mainMenu(this.app);
  }
  update() {
    const i = this.app.anyInput;
    if (i.justPressed("up") || i.justPressed("down")) this.index = 1 - this.index;
    else if (ok(i)) this.pick(this.index);
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, "PERDISTE", 150, COLORS.red, 56);
    UI.text(ctx, `Llegaste al piso ${this.tower.floor + 1} de ${this.tower.opps.length}`, view.w / 2, 215, { size: 22 });
    UI.menuList(ctx, view, ["Reintentar", "Volver al menú"], this.index, 330, (k) => this.pick(k));
  }
}

class TowerVictory {
  constructor(app, tower) {
    this.app = app; this.tower = tower; this.confetti = new UI.Confetti(app.view);
    const boss = tower.opps[tower.opps.length - 1];
    this.bossReal = boss.realName;
  }
  enter() { this.app.touch.fightMode = false; }
  update(dt) {
    this.confetti.update(dt);
    if (ok(this.app.anyInput)) Flow.mainMenu(this.app);
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, 0, "tower", 0.3);
    const me = DB.bySlug[this.tower.me];
    UI.drawImageContain(ctx, me.pose, view.w / 2 - 140, 130, 280, C.BASE_H - 170);
    this.confetti.draw(ctx);
    UI.title(ctx, view, "¡COMPLETASTE LA TORRE DE BATALLA!", 60, COLORS.yellow, 34);
    UI.text(ctx, `${me.name} le ganó a los ${this.tower.opps.length} rivales (el jefe era ${this.bossReal})`, view.w / 2, 100, { size: 18 });
    UI.pillButton(ctx, view.w / 2, C.BASE_H - 30, "CONTINUAR", () => Flow.mainMenu(this.app), { size: 16, h: 36 });
  }
}
