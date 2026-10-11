// =====================================================================
// projectile.js — objeto del ataque a distancia (port de projectile.py)
// Trayectorias: "straight", "arc" (parábola de rango fijo), "bounce"
// (cae con gravedad y pica; con kick_height sale hacia arriba).
// =====================================================================
import * as C from "./config.js";

const DEFAULT_SIZE = 26;
const MAX_DIM = 60;
const SPIN_FPS = 12;
const MIN_BOUNCE_SPEED = 60;

export class Projectile {
  constructor(o) {
    this.x = o.x; this.y = o.y;
    this.startX = o.x; this.startY = o.y;
    this.endY = o.endY ?? o.y;
    this.facing = o.facing;
    this.damage = o.damage;
    this.speed = o.speed;
    this.velX = o.speed * o.facing;
    this.velY = o.launchVelY || 0;
    this.owner = o.owner;
    this.trajectory = o.trajectory || "straight";
    this.arcHeight = o.arcHeight ?? 110;
    this.arcRange = Math.max(1, o.arcRange ?? 280);
    this.arcT = 0;
    this.gravityMult = o.gravityMult ?? 1;
    this.bounceDamping = o.bounceDamping ?? 0.55;
    this.justBounced = false;
    this.visualYOffset = o.visualYOffset || 0;
    this.frames = o.frames || [];
    this.group = o.group || 0;
    this.frameIndex = 0;
    this.frameTimer = 0;
    this.alive = true;
    this.loopId = null;
    const f = this.frames[0];
    if (f) {
      const w = f.naturalWidth || f.width, h = f.naturalHeight || f.height;
      // los PNG se asumen hechos para el lienzo base; nunca más grande que MAX_DIM
      let k = o.scale ?? 1; // "projectile_scale" en el JSON del personaje
      if (Math.max(w, h) * k > MAX_DIM) k = MAX_DIM / Math.max(w, h);
      this.w = w * k; this.h = h * k;
    } else { this.w = DEFAULT_SIZE; this.h = DEFAULT_SIZE; }
  }

  update(dt, worldW) {
    this.justBounced = false;
    if (this.trajectory === "arc") {
      this.arcT += Math.abs(this.speed) / this.arcRange;
      const t = Math.min(1, this.arcT);
      this.x = this.startX + this.facing * this.arcRange * t;
      this.y = this.startY + (this.endY - this.startY) * t - this.arcHeight * 4 * t * (1 - t);
      if (t >= 1) this.alive = false;
    } else if (this.trajectory === "bounce") {
      this.x += this.velX;
      this.velY += C.PROJECTILE_GRAVITY * this.gravityMult * dt;
      this.y += this.velY * dt;
      if (this.y >= C.GROUND_Y) {
        this.y = C.GROUND_Y;
        this.velY = -this.velY * this.bounceDamping;
        this.justBounced = true;
        if (Math.abs(this.velY) < MIN_BOUNCE_SPEED) this.alive = false;
      }
    } else {
      this.x += this.velX;
    }
    const margin = 60;
    if (this.x < -margin || this.x > (worldW ?? C.BASE_W) + margin) this.alive = false;
    if (this.frames.length > 1) {
      this.frameTimer += dt;
      if (this.frameTimer >= 1 / SPIN_FPS) {
        this.frameTimer = 0;
        this.frameIndex = (this.frameIndex + 1) % this.frames.length;
      }
    }
  }

  getHitbox() { return { x: this.x - this.w / 2, y: this.y - this.h / 2, w: this.w, h: this.h }; }

  draw(ctx, cameraX, viewPad) {
    drawProjectile(ctx, this.frames, this.frameIndex, this.x, this.y - this.visualYOffset, this.facing, this.w, this.h, cameraX, viewPad);
  }
}

export function drawProjectile(ctx, frames, index, x, y, facing, w, h, cameraX, viewPad) {
  const sx = x - cameraX + viewPad;
  const img = frames && frames.length ? frames[index % frames.length] : null;
  if (!img) {
    ctx.fillStyle = C.COLORS.yellow;
    ctx.beginPath();
    ctx.arc(sx, y, DEFAULT_SIZE / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  ctx.save();
  ctx.translate(sx, y);
  if (facing === -1) ctx.scale(-1, 1);
  ctx.drawImage(img, -w / 2, -h / 2, w, h);
  ctx.restore();
}
