// =====================================================================
// stage.js — escenario (imagen fija o video en loop) + cámara
// Un escenario más panorámico que 16:9 da un "mundo" más ancho que la
// pantalla y la cámara sigue a los luchadores (como en Mortal Kompa).
// =====================================================================
import * as C from "./config.js";
import { loadImage, url } from "./assets.js";

const MAX_WORLD_W_MULT = 3;

export class Stage {
  static async load(def) {
    const st = new Stage(def);
    if (!def) return st;
    if (/\.(mp4|webm)$/i.test(def.image)) {
      const v = document.createElement("video");
      v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true;
      v.setAttribute("playsinline", "");
      v.src = url(def.image);
      await new Promise((res) => {
        v.addEventListener("loadeddata", res, { once: true });
        v.addEventListener("error", res, { once: true });
        setTimeout(res, 8000);
      });
      v.play().catch(() => {});
      st.media = v;
      st.srcW = v.videoWidth; st.srcH = v.videoHeight;
    } else {
      const img = await loadImage(def.image);
      st.media = img;
      st.srcW = img ? img.naturalWidth : 0;
      st.srcH = img ? img.naturalHeight : 0;
    }
    if (st.srcW && st.srcH) {
      const w = Math.round(st.srcW * C.BASE_H / st.srcH);
      st.worldW = Math.max(C.BASE_W, Math.min(C.BASE_W * MAX_WORLD_W_MULT, w));
    }
    st.cameraX = st.getCameraX(st.worldW / 2);
    return st;
  }

  constructor(def) {
    this.def = def;
    this.id = def ? def.id : null;
    this.name = def ? def.name : "";
    this.music = def ? def.music : null;
    this.media = null;
    this.worldW = C.BASE_W;
    this.cameraX = 0;
  }

  getCameraX(mid) {
    const maxCam = Math.max(0, this.worldW - C.BASE_W);
    return Math.max(0, Math.min(maxCam, mid - C.BASE_W / 2));
  }

  dispose() {
    if (this.media && this.media.tagName === "VIDEO") { this.media.pause(); this.media.src = ""; }
  }

  draw(ctx, cameraX, viewPad, viewW) {
    const m = this.media;
    if (!m || !this.srcW) {
      ctx.fillStyle = "#283c5a";
      ctx.fillRect(0, 0, viewW, C.BASE_H);
      ctx.fillStyle = "#32281e";
      ctx.fillRect(0, C.GROUND_Y, viewW, C.BASE_H - C.GROUND_Y);
      return;
    }
    const kx = this.srcW / this.worldW;
    const ky = this.srcH / C.BASE_H;
    if (this.worldW >= viewW) {
      // sin deformar: ventana de viewW px dentro del mundo
      const left = Math.max(0, Math.min(this.worldW - viewW, cameraX - viewPad));
      ctx.drawImage(m, left * kx, 0, viewW * kx, this.srcH, 0, 0, viewW, C.BASE_H);
    } else {
      // pantalla más ancha que el escenario (celular 20:9 con escenario
      // 16:9): se agranda SIN deformar hasta cubrir el ancho y se recorta
      // lo que sobra de alto -- más de arriba que de abajo, para no perder
      // el piso (mismo criterio que la versión Android)
      const visH = this.srcW * C.BASE_H / viewW;      // alto de la fuente que entra en pantalla
      const sy = Math.max(0, (this.srcH - visH) * 0.7);
      ctx.drawImage(m, 0, sy, this.srcW, visH, 0, 0, viewW, C.BASE_H);
    }
    void ky;
  }
}
