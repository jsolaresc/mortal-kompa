// =====================================================================
// character.js — Character: sprites, física, máquina de estados de combate
// Port directo de engine/character.py de Mortal Kompa (misma lógica,
// mismos números), adaptado a Canvas.
// =====================================================================
import * as C from "./config.js";
import { S, ATTACK_STATES } from "./config.js";
import { audio } from "./audio.js";

export class Animation {
  constructor(frames, fps, loop = true) {
    this.frames = frames;
    this.fps = Math.max(1, fps);
    this.loop = loop;
    this.timer = 0;
    this.index = 0;
    this.finished = false;
  }
  reset() { this.timer = 0; this.index = 0; this.finished = false; }
  update(dt) {
    if (this.finished || !this.frames.length) return;
    this.timer += dt;
    const fd = 1 / this.fps;
    while (this.timer >= fd) {
      this.timer -= fd;
      this.index += 1;
      if (this.index >= this.frames.length) {
        if (this.loop) this.index = 0;
        else { this.index = this.frames.length - 1; this.finished = true; }
      }
    }
  }
  current() { return this.frames.length ? this.frames[this.index] : null; }
}

const silhouetteCache = new WeakMap();
function silhouette(img) {
  let c = silhouetteCache.get(img);
  if (!c) {
    c = document.createElement("canvas");
    c.width = img.naturalWidth || img.width;
    c.height = img.naturalHeight || img.height;
    const x = c.getContext("2d");
    x.drawImage(img, 0, 0);
    x.globalCompositeOperation = "source-atop";
    x.fillStyle = "#000";
    x.fillRect(0, 0, c.width, c.height);
    silhouetteCache.set(img, c);
  }
  return c;
}

export class Character {
  /**
   * @param {object} entry  entrada del roster (DB.bySlug[slug])
   * @param {object} frames resultado de loadCharacterFrames(slug)
   */
  constructor(entry, frames) {
    const data = entry.data;
    this.slug = entry.slug;
    this.data = data;
    this.name = data.name || entry.slug;
    this.realName = this.name;
    this.folder = frames.folder;
    this.scale = (data.scale ?? 2) * C.CHARACTER_SCALE_MULT;
    this.maxHealth = data.health ?? 100;
    this.health = this.maxHealth;
    this.walkSpeed = data.walk_speed ?? 4;
    this.jumpPower = data.jump_power ?? C.JUMP_POWER_DEFAULT;
    this.animData = data.animations || {};
    this.projectileFrames = frames.projectile;
    this.soundPools = this.buildSoundPools();

    this.animations = {};
    for (const [name, cfg] of Object.entries(this.animData)) {
      this.animations[name] = new Animation(frames.anims[name] || [], cfg.fps ?? 8, cfg.loop ?? true);
    }
    // compatibilidad: si falta crouch/block_crouch/win se usa la más parecida
    const has = (k) => this.animations[k] && this.animations[k].frames.length;
    if (!has(S.CROUCH)) this.animations[S.CROUCH] = this.animations[S.BLOCK] || this.animations[S.IDLE];
    if (!has(S.BLOCK_CROUCH)) this.animations[S.BLOCK_CROUCH] = this.animations[S.CROUCH] || this.animations[S.BLOCK];
    if (!has(S.WIN)) this.animations[S.WIN] = this.animations[S.IDLE];
    for (const k of Object.values(S)) if (!this.animations[k]) this.animations[k] = new Animation([], 8, true);

    // KO: techo de ancho en pantalla
    this.koScale = 1;
    const ko = this.animations[S.KO];
    if (ko && ko.frames.length) {
      const maxW = C.BASE_W * C.KO_MAX_WIDTH_FRAC;
      const w = Math.max(...ko.frames.map((f) => f.naturalWidth || f.width)) * this.scale * (this.animData.ko?.extra_scale ?? 1);
      if (w > maxW * 1.6) this.koScale = (maxW * 1.6) / w; // aprox: el PNG tiene margen transparente
    }

    // física
    this.x = 0;
    this.y = C.GROUND_Y;
    this.velX = 0;
    this.velY = 0;
    this.facing = 1;
    this.onGround = true;

    // combate
    this.state = S.IDLE;
    this.blocking = false;
    this.attackHasHit = false;
    this.specialMissChecked = false;
    this.downHeld = false;
    this.blockHeld = false;
    this.knockedOut = false;
    this.hitFlashTimer = 0;
    this.mystery = false;
    this.koBounces = 0;
    this.koMaxBounces = 2;
    this.koSettled = false;
    this.hitsTakenSinceSpecial = 0;
    this.projectileSpawned = false;

    this.bodyW = Math.floor(90 * C.CHARACTER_SCALE_MULT);
    this.bodyH = Math.floor(260 * C.CHARACTER_SCALE_MULT);
  }

  // ---------------------------------------------------------------
  // Sonidos propios: data.sounds = { "punch": ["sounds/punch/a.mp3", ...], ... }
  // (rutas relativas a la carpeta del personaje)
  buildSoundPools() {
    const pools = {};
    for (const [k, v] of Object.entries(this.data.sounds || {})) {
      if (k.startsWith("_") || !v) continue;
      const list = Array.isArray(v) ? v : [v];
      pools[k] = list.map((p) => `${this.folder}/${p}`);
    }
    return pools;
  }

  playCharacterSound(key, volume = 1, chance = null, forceChance = false) {
    const paths = this.soundPools[key];
    if (!paths || !paths.length) return false;
    const use = chance ?? C.SOUND_RANDOM_CHANCE;
    let any = false;
    for (const p of paths) {
      const always = paths.length === 1 && !forceChance;
      if (always || Math.random() < use) { audio.play(p, volume); any = true; }
    }
    return any;
  }

  characterSoundPath(key) {
    const paths = this.soundPools[key];
    return paths && paths.length ? paths[Math.floor(Math.random() * paths.length)] : null;
  }

  playVoice(key) { this.playCharacterSound(key); }

  playWinVoice() {
    const p = this.characterSoundPath("win");
    if (p) audio.play(p, 1);
  }

  enterMystery() { this.mystery = true; this.name = "???"; }
  reveal() { if (this.mystery) { this.mystery = false; this.name = this.realName; } }

  // ---------------------------------------------------------------
  setState(newState, force = false) {
    if (this.knockedOut && !force) return;
    if (this.state === newState && !force) return;
    if (ATTACK_STATES.has(this.state) && !this.animations[this.state].finished && !force) return;
    this.state = newState;
    this.animations[newState].reset();
    this.attackHasHit = false;
    this.projectileSpawned = false;
    if (newState === S.SPECIAL) this.specialMissChecked = false;
    if (newState === S.WIN) { this.velX = 0; this.velY = 0; }
    const sk = { [S.PUNCH]: "punch", [S.KICK]: "kick", [S.SPECIAL]: "special" }[newState];
    if (sk) this.playCharacterSound(sk);
    if (newState === S.RANGED || newState === S.RANGED_CROUCH) {
      const cfg = this.animData[newState] || {};
      if (!cfg.loop_sound) {
        if (!this.playCharacterSound("ranged", 0.8)) audio.playSfx("throw", 0.8);
      }
    }
  }

  handleInput(inp, opponentX) {
    if (this.knockedOut) return;
    if (inp.forceDefend && this.onGround) {
      this.blocking = true;
      this.velX = 0;
      this.setState(S.BLOCK, true);
      return;
    }
    const busy = ATTACK_STATES.has(this.state) && !this.animations[this.state].finished;
    this.downHeld = inp.pressed("down") && this.onGround;
    this.blockHeld = inp.pressed("block") && this.onGround;
    this.blocking = false;

    if (!busy) {
      if (inp.justPressed("punch")) { this.setState(S.PUNCH); return; }
      if (inp.justPressed("kick")) { this.setState(S.KICK); return; }
      if (inp.justPressed("ranged")) {
        if (inp.pressed("down") && this.onGround && this.animData[S.RANGED_CROUCH]) this.setState(S.RANGED_CROUCH);
        else this.setState(S.RANGED);
        return;
      }
      if (inp.justPressed("special")) {
        if (this.hitsTakenSinceSpecial >= C.SPECIAL_HITS_REQUIRED) {
          this.hitsTakenSinceSpecial = 0;
          this.setState(S.SPECIAL);
        }
        return;
      }
      const guard = inp.pressed("block") && this.onGround;
      const crouch = inp.pressed("down") && this.onGround;
      if (guard && crouch) { this.blocking = true; this.setState(S.BLOCK_CROUCH); this.velX = 0; }
      else if (guard) { this.blocking = true; this.setState(S.BLOCK); this.velX = 0; }
      else if (crouch) { this.blocking = false; this.setState(S.CROUCH); this.velX = 0; }
      else if (inp.pressed("up") && this.onGround) {
        this.velY = this.jumpPower;
        this.onGround = false;
        this.setState(S.JUMP);
      } else if (inp.pressed("left")) {
        this.velX = -this.walkSpeed;
        if (this.onGround) this.setState(S.WALK);
      } else if (inp.pressed("right")) {
        this.velX = this.walkSpeed;
        if (this.onGround) this.setState(S.WALK);
      } else {
        this.velX = 0;
        if (this.onGround) this.setState(S.IDLE);
      }
    }
    this.facing = opponentX >= this.x ? 1 : -1;
  }

  clampX(min, max) { this.x = Math.max(min, Math.min(max, this.x)); }

  returnToNeutral() {
    if (this.blockHeld && this.downHeld) { this.setState(S.BLOCK_CROUCH, true); this.blocking = true; }
    else if (this.blockHeld) { this.setState(S.BLOCK, true); this.blocking = true; }
    else if (this.downHeld) this.setState(S.CROUCH, true);
    else this.setState(S.IDLE, true);
  }

  physicsUpdate(dt) {
    if (this.knockedOut) this.koPhysics();
    else {
      if (!this.onGround) {
        this.velY += C.GRAVITY;
        this.y += this.velY;
        if (this.y >= C.GROUND_Y) {
          this.y = C.GROUND_Y;
          this.velY = 0;
          this.onGround = true;
          if (this.state === S.JUMP) this.returnToNeutral();
        }
      }
      this.x += this.velX;
    }
    const anim = this.animations[this.state];
    if (anim && this.state !== S.KO) anim.update(dt);

    if (this.state === S.SPECIAL && anim && !this.attackHasHit && !this.specialMissChecked) {
      const active = (this.animData[S.SPECIAL] || {}).active_frames || [];
      if (active.length) {
        const mx = Math.max(...active);
        if (anim.index > mx || (anim.finished && anim.index >= mx)) {
          this.specialMissChecked = true;
          audio.playSfx("special_miss", 1);
        }
      }
    }
    if (ATTACK_STATES.has(this.state) && anim && anim.finished) this.returnToNeutral();
    if (this.hitFlashTimer > 0) this.hitFlashTimer -= dt;
  }

  koPhysics() {
    if (this.koSettled) return;
    this.velY += C.GRAVITY;
    this.y += this.velY;
    this.x += this.velX;
    this.velX *= 0.9;
    if (this.y >= C.GROUND_Y) {
      this.y = C.GROUND_Y;
      if (this.koBounces < this.koMaxBounces && Math.abs(this.velY) > 4) {
        this.velY = -this.velY * 0.4;
        this.koBounces += 1;
        if (!this.playCharacterSound("fall", 0.85)) audio.playSfx("fall_bounce", 0.85);
      } else {
        this.velY = 0;
        this.koSettled = true;
        if (!this.playCharacterSound("fall", 1)) audio.playSfx("fall_thud", 1);
      }
    }
    const ko = this.animations[S.KO];
    if (ko && ko.frames.length) {
      const n = ko.frames.length;
      if (this.koSettled) ko.index = n - 1;
      else if (this.koBounces >= 1) ko.index = Math.min(n - 1, Math.round(n * 0.55));
      else ko.index = Math.min(n - 1, Math.round(n * 0.25));
    }
  }

  // ---------------------------------------------------------------
  getHurtbox() {
    let h = this.bodyH;
    if (this.state === S.CROUCH || this.state === S.BLOCK_CROUCH || this.state === S.RANGED_CROUCH) h = Math.floor(this.bodyH * 0.55);
    else if (!this.onGround) h = Math.floor(this.bodyH * 0.75);
    return { x: this.x - this.bodyW / 2, y: this.y - h, w: this.bodyW, h };
  }

  getActiveHitbox() {
    if (!ATTACK_STATES.has(this.state)) return null;
    const cfg = this.animData[this.state] || {};
    if ((this.state === S.RANGED || this.state === S.RANGED_CROUCH) && !cfg.melee_whip) return null;
    const active = cfg.active_frames || [];
    if (!active.includes(this.animations[this.state].index)) return null;
    const reach = cfg.reach ?? 70;
    const height = cfg.hit_height ?? 60;
    const offY = cfg.hit_offset_y ?? 90;
    const rx = this.facing === 1 ? this.x : this.x - reach;
    return { x: rx, y: this.y - offY - height / 2, w: reach, h: height };
  }

  getDamageForState() {
    const cfg = this.animData[this.state] || {};
    let dmg = cfg.damage ?? 5;
    if (this.state === S.SPECIAL) dmg *= C.SPECIAL_DAMAGE_MULT;
    return dmg;
  }

  getRangedLaunch() {
    if ((this.state !== S.RANGED && this.state !== S.RANGED_CROUCH) || this.projectileSpawned) return null;
    const cfg = this.animData[this.state] || {};
    if (cfg.melee_whip) return null;
    if (!(cfg.active_frames || []).includes(this.animations[this.state].index)) return null;
    this.projectileSpawned = true;

    const H = { high: 220, mid: 105, crouch_mid: 65, low: 25 };
    let offY = (H[cfg.launch_height || "mid"] ?? 105) * (cfg.launch_offset_mult ?? 1);
    const launchX = this.x + 36 * this.facing;
    const launchY = this.y - offY;

    let frames = this.projectileFrames;
    let group = 0;
    const mode = cfg.projectile_mode || "spin";
    if (frames.length && Array.isArray(frames[0])) {
      // grupos (subcarpetas): random_spin elige uno al azar, con pesos opcionales
      const w = cfg.projectile_weights;
      if (w && w.length === frames.length) {
        let r = Math.random() * w.reduce((a, b) => a + b, 0);
        group = 0;
        while (r > w[group] && group < w.length - 1) { r -= w[group]; group++; }
      } else group = Math.floor(Math.random() * frames.length);
      frames = frames[group];
    } else if (mode === "random" && frames.length) {
      const i = Math.floor(Math.random() * frames.length);
      frames = [frames[i]];
      group = i;
    }

    const trajectory = cfg.trajectory || "straight";
    const endOff = { high: 220, mid: 105, low: 25 }[cfg.arc_end_height || "high"] ?? 220;
    const kick = cfg.kick_height || 0;
    const gm = cfg.gravity_mult ?? 1;
    const launchVelY = kick ? -Math.sqrt(2 * C.PROJECTILE_GRAVITY * gm * kick) : 0;
    return {
      x: launchX, y: launchY, facing: this.facing, damage: cfg.damage ?? 5, speed: cfg.speed ?? 9,
      frames, group, mode, owner: this, trajectory, endY: this.y - endOff,
      arcHeight: cfg.arc_height ?? 110, arcRange: cfg.arc_range ?? 280,
      bounceDamping: cfg.bounce_damping ?? 0.55, launchVelY, gravityMult: gm,
      visualYOffset: cfg.visual_y_offset ?? 0, scale: this.data.projectile_scale ?? 1, loopSound: !!cfg.loop_sound,
    };
  }

  receiveHit(damage, knockback = 12, critical = false) {
    if (this.knockedOut) return;
    this.hitsTakenSinceSpecial = Math.min(C.SPECIAL_HITS_REQUIRED, this.hitsTakenSinceSpecial + 1);
    if (this.blocking) {
      damage = Math.max(1, Math.floor(damage * 0.15 * 0.4));
      knockback *= 0.3;
      if (!this.playCharacterSound("block", 0.8)) audio.playSfx("block_impact", 0.8);
    } else {
      audio.playSfx(critical ? "critical_hit" : "hit_impact", 1);
      this.playCharacterSound("hit", 1, C.VOICE_LINE_CHANCE, true);
    }
    this.health = Math.max(0, this.health - damage);
    this.velX = -this.facing * knockback;
    this.hitFlashTimer = 0.12;
    if (this.health <= 0) {
      this.knockedOut = true;
      this.onGround = false;
      this.koBounces = 0;
      this.koSettled = false;
      this.velY = -17;
      this.velX = -this.facing * Math.max(knockback, 10) * 1.4;
      this.setState(S.KO, true);
      this.playVoice("ko");
    }
  }

  // ---------------------------------------------------------------
  // Dibujo (también lo usa el invitado online a partir de un snapshot)
  draw(ctx, cameraX = 0, viewPad = 0) {
    drawFighterFrame(ctx, this, {
      state: this.state, index: this.animations[this.state].index, x: this.x, y: this.y,
      facing: this.facing, flash: this.hitFlashTimer > 0, mystery: this.mystery,
    }, cameraX, viewPad);
  }
}

// Dibuja un luchador a partir de datos "planos" (sirve para el modo
// local y para el invitado online, que solo recibe estos datos).
export function drawFighterFrame(ctx, ch, s, cameraX, viewPad) {
  const anim = ch.animations[s.state];
  const frame = anim && anim.frames.length ? anim.frames[Math.min(s.index, anim.frames.length - 1)] : null;
  const sx = s.x - cameraX + viewPad;
  if (!frame) {
    ctx.fillStyle = "#c83c3c";
    ctx.fillRect(sx - ch.bodyW / 2, s.y - ch.bodyH, ch.bodyW, ch.bodyH);
    return;
  }
  const cfg = ch.animData[s.state] || {};
  let sc = ch.scale * (cfg.extra_scale ?? 1);
  if (s.state === S.KO) sc *= ch.koScale;
  const w = (frame.naturalWidth || frame.width) * sc;
  const h = (frame.naturalHeight || frame.height) * sc;
  let yo = cfg.y_offset ?? 0;
  if (Array.isArray(yo)) yo = yo[s.index] ?? 0;
  const img = s.mystery ? silhouette(frame) : frame;
  ctx.save();
  if (s.flash && !s.mystery) ctx.globalAlpha = 0.47;
  ctx.translate(sx, s.y - yo);
  if (s.facing === -1 && !cfg.no_flip) ctx.scale(-1, 1);
  ctx.drawImage(img, -w / 2, -h, w, h);
  ctx.restore();
}
