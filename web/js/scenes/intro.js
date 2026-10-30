// =====================================================================
// scenes/intro.js — Video de intro al abrir el juego (como en la PC).
// Solo en la app de Google TV (el video va únicamente en ese APK): ahí
// puede arrancar con sonido sin tocar nada. Cualquier botón la saltea.
// =====================================================================
import * as C from "../config.js";
import { audio } from "../audio.js";
import { url } from "../assets.js";

export const INTRO_VIDEO = "assets/video/intro.mp4";

export class IntroScene {
  constructor(app, onDone) {
    this.app = app;
    this.onDone = onDone;
    this.finished = false;
    this.t = 0;
    const v = document.createElement("video");
    v.src = url(INTRO_VIDEO);
    v.playsInline = true;
    v.preload = "auto";
    v.volume = Math.max(0, Math.min(1, audio.volumes.music ?? 0.5));
    v.onended = () => this.finish();
    v.onerror = () => this.finish();          // sin video: directo al menú
    this.video = v;
    audio.videos.add(v);
  }
  enter() {
    this.app.touch.fightMode = false;
    const p = this.video.play();
    if (p && p.catch) p.catch(() => this.finish());   // no se pudo reproducir
    // si en 6 s todavía no arrancó (red lenta / formato), no se espera más
    this.startTimer = setTimeout(() => { if (this.video.currentTime === 0) this.finish(); }, 6000);
  }
  exit() {
    clearTimeout(this.startTimer);
    audio.videos.delete(this.video);
    try { this.video.pause(); this.video.removeAttribute("src"); this.video.load(); } catch (e) { /* nada */ }
  }
  finish() {
    if (this.finished) return;
    this.finished = true;
    this.onDone();
  }
  update(dt) {
    this.t += dt;
    if (this.t < 0.4) return;   // que no se saltee con la misma tecla que abrió la app
    const i = this.app.anyInput;
    if (["confirm", "start", "cancel", "punch", "kick"].some((a) => i.justPressed(a))) this.finish();
  }
  onPointer() { if (this.t > 0.4) this.finish(); return true; }
  draw(ctx, view) {
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, view.w, C.BASE_H);
    const v = this.video;
    if (v.readyState >= 2 && v.videoWidth) {
      // entra entero (con franjas negras si hace falta)
      const k = Math.min(view.w / v.videoWidth, C.BASE_H / v.videoHeight);
      const w = v.videoWidth * k, h = v.videoHeight * k;
      ctx.drawImage(v, (view.w - w) / 2, (C.BASE_H - h) / 2, w, h);
    }
  }
}
