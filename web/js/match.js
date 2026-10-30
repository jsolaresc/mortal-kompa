// =====================================================================
// match.js — una pelea completa (al mejor de 3) entre dos luchadores
// Port de los estados ROUND_INTRO / FIGHT / ROUND_END de main.py de
// Mortal Kompa: mismos tiempos, críticos, muerte súbita, Flawless, etc.
//
// El anfitrión de una partida online corre esta misma clase; los
// invitados solo reciben snapshot() y lo dibujan con drawSnapshot().
// =====================================================================
import * as C from "./config.js";
import { S } from "./config.js";
import { audio } from "./audio.js";
import { Character } from "./character.js";
import { Projectile } from "./projectile.js";
import { drawFighterFrame } from "./character.js";
import { drawProjectile } from "./projectile.js";
import * as UI from "./ui.js";

function overlap(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

export function announcerNamePath(entry) {
  const a = entry && entry.data && entry.data.announcer;
  if (!a) return null;
  return a.includes("/") ? a : `${entry.data.sprite_folder}/${a}`;
}

export class Match {
  /**
   * opts: { entries:[e,e], frames:[f,f], stage, inputs:[in,in],
   *         mystery:[bool,bool], boss: {name} | null }
   */
  constructor(opts) {
    this.entries = opts.entries;
    this.frames = opts.frames;
    this.stage = opts.stage;
    this.inputs = opts.inputs;
    this.mysteryOpt = opts.mystery || [false, false];
    this.boss = opts.boss || null;
    this.names = opts.names || null;
    this.projectiles = [];
    this.wins = [0, 0];
    this.roundNumber = 1;
    this.suddenDeath = false;
    this.timeLeft = C.ROUND_TIME;
    this.phase = "intro";
    this.phaseT = 0;
    this.roundWinner = null;
    this.winner = null;        // índice 0/1 del ganador de la PELEA
    this.winAudioTimer = null;
    this.winAudioQueue = [];
    this.banner = null;
    this.t = 0;
    this.newFighters();
    this.startIntro();
  }

  newFighters() {
    this.f = [0, 1].map((i) => new Character(this.entries[i], this.frames[i]));
    for (const ch of this.f) for (const list of Object.values(ch.soundPools || {})) for (const p of list) audio.load(p);
    const [a, b] = this.f;
    const worldW = this.stage ? this.stage.worldW : C.BASE_W;
    const center = worldW / 2;
    const gap = C.BASE_W * 0.2;
    a.x = center - gap; b.x = center + gap;
    a.facing = 1; b.facing = -1;
    a.playVoice("intro"); b.playVoice("intro");
    if (this.stage) this.stage.cameraX = this.stage.getCameraX(center);
    if (this.names) this.f.forEach((ch, i) => { if (this.names[i]) { ch.name = this.names[i]; ch.realName = this.names[i]; } });
    this.f.forEach((ch, i) => { if (this.mysteryOpt[i]) ch.enterMystery(); });
    if (this.boss) { b.mystery = true; b.name = this.boss.name; }
    this.projectiles.forEach((p) => audio.stopLoop(p.loopId));
    this.projectiles = [];
  }

  startIntro() {
    const name = this.suddenDeath ? "sudden_death" : `round${Math.min(3, this.roundNumber)}`;
    const roundDur = audio.announcerDuration(name);
    audio.playAnnouncer(name);
    const fightDur = audio.announcerDuration("fight");
    const fightAt = roundDur + C.ROUND_INTRO_PAUSE;
    this.introTimer = fightAt + fightDur + C.ROUND_INTRO_TRAILING_PAD;
    this.fightThreshold = this.introTimer - fightAt;
    this.fightPlayed = false;
    this.phase = "intro";
    this.phaseT = 0;
  }

  // ---------------------------------------------------------------
  updateCamera() {
    const st = this.stage;
    const [a, b] = this.f;
    const cam = st ? st.cameraX : 0;
    const lo = cam + 45, hi = cam + C.BASE_W - 45;
    a.clampX(lo, hi); b.clampX(lo, hi);
    if (st) st.cameraX = st.getCameraX((a.x + b.x) / 2);
  }

  resolveCombat(att, def) {
    if (att.attackHasHit) return;
    const hb = att.getActiveHitbox();
    if (!hb || !overlap(hb, def.getHurtbox())) return;
    let dmg = att.getDamageForState();
    const crit = (att.state === S.PUNCH || att.state === S.KICK) && Math.random() < C.CRITICAL_HIT_CHANCE;
    if (crit) dmg *= C.CRITICAL_HIT_MULT;
    const wasBlocking = def.blocking;
    def.receiveHit(dmg, 12, crit, C.BLOCK_DAMAGE[att.state] ?? 0.5);
    att.attackHasHit = true;
    if (att.state === S.SPECIAL && !wasBlocking) audio.playSfx("special_hit", 1);
    if (!wasBlocking) att.playCharacterSound("give_hit", 1, C.VOICE_LINE_CHANCE, true);
  }

  spawnProjectiles(att) {
    const l = att.getRangedLaunch();
    if (!l) return;
    const p = new Projectile(l);
    p.ownerIndex = this.f.indexOf(att);
    if (l.loopSound) {
      const path = att.characterSoundPath("ranged");
      p.loopId = path ? audio.playLoop(path, 0.8) : null;
    }
    this.projectiles.push(p);
  }

  updateProjectiles(dt) {
    const worldW = this.stage ? this.stage.worldW : C.BASE_W;
    for (const p of [...this.projectiles]) {
      p.update(dt, worldW);
      if (p.justBounced) {
        if (!p.owner.playCharacterSound("projectile_bounce", 0.8)) audio.playSfx("projectile_bounce", 0.8);
      }
      const target = p.owner === this.f[0] ? this.f[1] : this.f[0];
      if (!target.knockedOut && p.alive && overlap(p.getHitbox(), target.getHurtbox())) {
        target.receiveHit(p.damage, 8, false, C.BLOCK_DAMAGE.ranged);
        if (!p.owner.playCharacterSound("projectile_hit")) audio.playSfx("projectile_hit", 0.9);
        p.alive = false;
      }
      if (!p.alive) {
        audio.stopLoop(p.loopId);
        this.projectiles.splice(this.projectiles.indexOf(p), 1);
      }
    }
  }

  queueWinAudio(names, delay = 1.05) {
    this.winAudioTimer = delay;
    this.winAudioQueue = [...names];
  }

  winAudioDuration(delay = 1.05, pad = 0.5) {
    if (!this.winAudioQueue.length) return 0;
    let total = delay;
    for (const n of this.winAudioQueue) total += audio.announcerDuration(n) + C.WIN_AUDIO_GAP;
    return total + pad;
  }

  tickWinAudio(dt) {
    if (this.winAudioTimer === null || !this.winAudioQueue.length) return;
    this.winAudioTimer -= dt;
    if (this.winAudioTimer <= 0) {
      const n = this.winAudioQueue.shift();
      audio.playAnnouncer(n);
      this.winAudioTimer = this.winAudioQueue.length ? audio.announcerDuration(n) + C.WIN_AUDIO_GAP : null;
    }
  }

  // ---------------------------------------------------------------
  update(dt) {
    this.t += dt;
    this.phaseT += dt;
    this.tickWinAudio(dt);
    const [a, b] = this.f;
    if (this.phase === "intro") {
      this.updateCamera();
      this.introTimer -= dt;
      if (!this.fightPlayed && this.introTimer <= this.fightThreshold) {
        audio.playAnnouncer("fight");
        this.fightPlayed = true;
      }
      if (this.introTimer <= 0) {
        a.reveal();
        if (!this.boss) b.reveal();
        this.phase = "fight";
        this.phaseT = 0;
      }
    } else if (this.phase === "fight") {
      this.timeLeft -= dt;
      const [ia, ib] = this.inputs;
      if (ia.thinkFight) ia.thinkFight(dt, a, b);
      if (ib.thinkFight) ib.thinkFight(dt, b, a);
      a.handleInput(ia, b.x);
      b.handleInput(ib, a.x);
      a.physicsUpdate(dt);
      b.physicsUpdate(dt);
      this.updateCamera();
      this.resolveCombat(a, b);
      this.resolveCombat(b, a);
      this.spawnProjectiles(a);
      this.spawnProjectiles(b);
      this.updateProjectiles(dt);
      if (this.timeLeft <= 0 || a.knockedOut || b.knockedOut) this.endRound();
    } else if (this.phase === "roundEnd") {
      a.physicsUpdate(dt);
      b.physicsUpdate(dt);
      this.updateCamera();
      this.roundEndTimer -= dt;
      if (this.roundEndTimer <= 0) this.afterRound();
    } else if (this.phase === "over") {
      a.physicsUpdate(dt);
      b.physicsUpdate(dt);
      this.updateCamera();
    }
  }

  endRound() {
    const [a, b] = this.f;
    let w = null;
    if (a.knockedOut && !b.knockedOut) w = 1;
    else if (b.knockedOut && !a.knockedOut) w = 0;
    else if (a.health > b.health) w = 0;
    else if (b.health > a.health) w = 1;
    this.roundWinner = w;
    this.banner = (a.knockedOut || b.knockedOut) ? (w === null ? "draw" : "ko") : (w === null ? "draw" : "time");
    if (w !== null) {
      this.wins[w] += 1;
      const ch = this.f[w];
      ch.setState(S.WIN, true);
      audio.play(announcerNamePath(this.entries[w]), 1, "announcer");
      if (ch.health >= ch.maxHealth) this.queueWinAudio(["wins", "flawless"]);
      else this.queueWinAudio(["wins"]);
    } else {
      audio.playAnnouncer("draw");
      this.winAudioQueue = [];
    }
    this.projectiles.forEach((p) => audio.stopLoop(p.loopId));
    this.projectiles = [];
    this.roundEndTimer = Math.max(2.8, this.winAudioDuration());
    this.phase = "roundEnd";
    this.phaseT = 0;
  }

  afterRound() {
    if (this.wins[0] >= C.ROUNDS_TO_WIN || this.wins[1] >= C.ROUNDS_TO_WIN) {
      this.winner = this.wins[0] > this.wins[1] ? 0 : 1;
      const ch = this.f[this.winner];
      ch.playWinVoice();
      audio.play(announcerNamePath(this.entries[this.winner]), 1, "announcer");
      this.queueWinAudio(["wins"]);
      ch.setState(S.WIN, true);
      if (this.boss && this.winner === 0) { this.f[1].mystery = false; this.f[1].name = this.f[1].realName; }
      this.phase = "over";
      this.phaseT = 0;
      this.banner = null;
      return;
    }
    audio.stopAllSfx();
    this.roundNumber += 1;
    this.timeLeft = C.ROUND_TIME;
    const tie = this.roundWinner === null && this.wins[0] === 1 && this.wins[1] === 1;
    this.newFighters();
    if (tie) {
      this.suddenDeath = true;
      this.f.forEach((ch) => { ch.health = Math.max(1, Math.round(ch.maxHealth * 0.01)); });
    } else this.suddenDeath = false;
    this.banner = null;
    this.startIntro();
  }

  // ---------------------------------------------------------------
  // Snapshot: todo lo necesario para dibujar este cuadro (red)
  snapshot() {
    const r1 = (v) => Math.round(v * 10) / 10;
    return {
      ph: this.phase,
      pt: r1(this.phaseT),
      tm: r1(this.timeLeft),
      rn: this.roundNumber,
      sd: this.suddenDeath ? 1 : 0,
      w: this.wins,
      bn: this.banner,
      cam: r1(this.stage ? this.stage.cameraX : 0),
      f: this.f.map((c) => [c.state, c.animations[c.state].index, r1(c.x), r1(c.y), c.facing,
        c.hitFlashTimer > 0 ? 1 : 0, c.mystery ? 1 : 0, Math.round(c.health * 10) / 10, c.hitsTakenSinceSpecial, c.name]),
      pr: this.projectiles.map((p) => [p.ownerIndex, p.group, p.frameIndex, r1(p.x), r1(p.y - p.visualYOffset), p.facing, r1(p.w), r1(p.h)]),
      win: this.winner,
    };
  }

  draw(ctx, view) {
    drawSnapshot(ctx, view, this.snapshot(), this.f, this.stage);
  }
}

// Dibuja un cuadro de pelea a partir de un snapshot. 'chars' son
// Character (para sus animaciones/escala) y 'stage' el escenario.
export function drawSnapshot(ctx, view, s, chars, stage) {
  const cam = s.cam;
  if (stage) stage.draw(ctx, cam, view.pad, view.w);
  else { ctx.fillStyle = "#283c5a"; ctx.fillRect(0, 0, view.w, C.BASE_H); }
  // primero el que está en K.O./perdiendo, después el otro
  const order = [0, 1].sort((i, j) => (s.f[i][0] === S.KO ? -1 : 0) - (s.f[j][0] === S.KO ? -1 : 0));
  for (const i of order) {
    const d = s.f[i];
    drawFighterFrame(ctx, chars[i], { state: d[0], index: d[1], x: d[2], y: d[3], facing: d[4], flash: !!d[5], mystery: !!d[6] }, cam, view.pad);
  }
  for (const p of s.pr) {
    const owner = chars[p[0]];
    let frames = owner ? owner.projectileFrames : [];
    if (frames.length && Array.isArray(frames[0])) frames = frames[p[1]] || frames[0];
    const cfg = owner ? (owner.animData.ranged || {}) : {};
    if (cfg.projectile_mode === "random" && frames.length && !Array.isArray(frames[0])) frames = [frames[p[1]] || frames[0]];
    drawProjectile(ctx, frames, p[2], p[3], p[4], p[5], p[6], p[7], cam, view.pad);
  }
  UI.drawHud(ctx, view, {
    f: s.f.map((d, i) => ({ name: d[9], health: d[7], maxHealth: chars[i].maxHealth, hits: d[8] })),
    time: s.tm, wins: s.w, t: performance.now() / 1000,
  });
  if (s.ph === "intro") {
    UI.centerText(ctx, view, s.sd ? "MUERTE SÚBITA" : `ROUND ${s.rn}`, C.COLORS.white);
  } else if (s.ph === "roundEnd" && s.bn) {
    UI.koBanner(ctx, view, s.bn, s.pt);
  }
}
