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
import * as Flow from "../flow.js";

const DIFFICULTY_STEP = 1.05;
const BOSS_MULT = 1.20;
const FLOOR_H = 92;

function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

export function startTower(app, startLevel) {
  app.setScene(new CharSelectScene(app, {
    players: [{ input: app.inputs[0] }],
    title: "TORRE DE BATALLA",
    subtitle: "Elegí tu luchador",
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
    UI.menuBackground(ctx, view, this.app.t, "tower", 0.2);
    const t = this.tower;
    const n = t.opps.length;
    UI.title(ctx, view, `PISO ${t.floor + 1} DE ${n}`, 40);
    // torre (columna central): piso 0 abajo
    const cx = view.w / 2;
    const baseY = C.BASE_H - 110;
    const scroll = this.scrollNow ?? this.scroll;
    ctx.save();
    ctx.beginPath(); ctx.rect(cx - 170, 70, 340, C.BASE_H - 120); ctx.clip();
    for (let i = 0; i < n; i++) {
      const y = baseY - i * FLOOR_H + scroll;
      if (y < 0 || y > C.BASE_H) continue;
      const o = t.opps[i];
      const cur = i === t.floor;
      const done = i < t.floor;
      UI.roundRect(ctx, cx - 160, y - 38, 320, 76, 12);
      ctx.fillStyle = cur ? "rgba(240,200,40,0.18)" : done ? "rgba(40,200,90,0.12)" : "rgba(255,255,255,0.06)";
      ctx.fill();
      ctx.lineWidth = cur ? 3 : 1.5; ctx.strokeStyle = cur ? COLORS.yellow : "rgba(255,255,255,0.25)"; ctx.stroke();
      const ent = DB.bySlug[o.slug];
      const sx = cx - 150, sy = y - 30;
      if (o.boss) {
        drawRandomTile(ctx, sx, sy, 60);
      } else {
        ctx.save(); UI.roundRect(ctx, sx, sy, 60, 60, 8); ctx.clip();
        UI.drawImageCover(ctx, ent.selection, sx, sy, 60, 60); ctx.restore();
      }
      UI.text(ctx, o.boss ? "???" : o.name, cx - 75, y - 8, { size: 20, align: "left", color: cur ? COLORS.yellow : "#fff" });
      UI.text(ctx, done ? "VENCIDO" : cur ? "PRÓXIMO RIVAL" : `Piso ${i + 1}${o.boss ? " · JEFE FINAL" : ""}`, cx - 75, y + 16, { size: 13, align: "left", color: done ? COLORS.green : "#bbb" });
    }
    ctx.restore();
    // poses grandes: vos a la izquierda, rival a la derecha
    const me = DB.bySlug[t.me];
    UI.drawImageContain(ctx, me.pose, 30, 90, 220, C.BASE_H - 170);
    UI.text(ctx, me.name, 140, C.BASE_H - 60, { size: 24 });
    const o = t.opps[t.floor];
    if (o) {
      if (o.boss && UI.IMG.random_pose) UI.drawImageContain(ctx, UI.IMG.random_pose, view.w - 250, 90, 220, C.BASE_H - 170, true);
      else if (o.boss) UI.text(ctx, "?", view.w - 140, C.BASE_H / 2, { size: 160, color: "#22222c", stroke: 6, strokeColor: "#555" });
      else if (DB.bySlug[o.slug].pose2) UI.drawImageContain(ctx, DB.bySlug[o.slug].pose2, view.w - 250, 90, 220, C.BASE_H - 170, false);
      else UI.drawImageContain(ctx, DB.bySlug[o.slug].pose, view.w - 250, 90, 220, C.BASE_H - 170, true);
      UI.text(ctx, o.boss ? "???" : o.name, view.w - 140, C.BASE_H - 60, { size: 24, color: COLORS.yellow });
    }
    UI.text(ctx, `Dificultad ${t.difficulty.toFixed(1)}`, view.w - 140, 70, { size: 14, color: "#aaa" });
    UI.pillButton(ctx, cx, C.BASE_H - 28, "¡A PELEAR!", () => this.fight(), { size: 18, h: 38, minW: 170 });
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
