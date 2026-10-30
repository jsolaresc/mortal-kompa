// =====================================================================
// audio.js — sonido con Web Audio (efectos, locutor) + <audio> (música)
// ---------------------------------------------------------------------
// Los navegadores no dejan sonar nada hasta el primer toque/tecla: por
// eso existe la pantalla de "Tocá para empezar" (ver scenes/title).
// Todo lo que suena pasa por play(): eso permite que en una partida
// online el anfitrión "grabe" los sonidos y los mande a los invitados.
// =====================================================================
import { url } from "./assets.js";

const SFX_DIR = "assets/sounds/sfx";
const ANNOUNCER_DIR = "assets/sounds/announcer";

// Efectos genéricos (respaldo cuando el personaje no tiene sonido propio)
const FALLBACK_SFX = {
  hit_impact: [1, 2, 3, 4, 5, 6].map((i) => `${SFX_DIR}/hit_impact/punch_${i}.wav`),
  critical_hit: [`${SFX_DIR}/critical_hit/critical_hit.wav`],
  block_impact: [`${SFX_DIR}/block_impact.wav`],
  fall_bounce: [`${SFX_DIR}/fall_bounce.wav`],
  fall_thud: [`${SFX_DIR}/fall_thud.wav`],
  projectile_bounce: [`${SFX_DIR}/projectile_bounce.wav`],
  projectile_hit: [`${SFX_DIR}/projectile_hit.wav`],
  special_hit: [`${SFX_DIR}/special_hit.mp3`],
  special_miss: [`${SFX_DIR}/special_miss.mp3`],
  throw: [`${SFX_DIR}/throw.wav`],
};
const ANNOUNCER = ["round1", "round2", "round3", "fight", "wins", "flawless", "draw", "sudden_death"];

class AudioManager {
  constructor() {
    this.ctx = null;
    this.buffers = new Map();     // path -> AudioBuffer | Promise
    this.active = new Set();      // fuentes sonando (para cortarlas)
    this.loops = new Map();       // id -> source
    this.loopSeq = 0;
    this.volumes = { music: 0.5, stage: 0.5, sfx: 0.9, announcer: 1.0 };
    this.music = new Audio();
    this.music.preload = "auto";
    this.onMusicEnded = null;     // lo usa la música de menú para pasar al siguiente tema
    this.music.addEventListener("ended", () => { if (this.onMusicEnded) this.onMusicEnded(this.musicPath); });
    this.musicPath = null;
    this.musicBaseVolume = 0.5;
    this.listeners = [];          // para replicar sonidos por red
    this.muted = false;           // invitado online: no reproducir eventos propios del motor
    this.videos = new Set();      // videos en uso (intro, escenarios): se pausan con la app
  }

  setVolumes(v) {
    Object.assign(this.volumes, v);
    this.music.volume = Math.min(1, this.musicBaseVolume * this.musicVolumeFactor() * 2);
  }

  // menú -> "Música"; escenario (pelea) -> "Escenario"
  musicVolumeFactor(cat = this.musicCategory) {
    return cat === "stage" ? (this.volumes.stage ?? this.volumes.music) : this.volumes.music;
  }

  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.connect(this.ctx.destination);
      this.preload();
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
    if (this.musicPath && this.music.paused && !this.music.ended) this.music.play().catch(() => {});
  }

  preload() {
    for (const list of Object.values(FALLBACK_SFX)) list.forEach((p) => this.load(p));
    ANNOUNCER.forEach((n) => this.load(`${ANNOUNCER_DIR}/${n}.wav`));
  }

  load(path) {
    if (!this.ctx || !path) return Promise.resolve(null);
    const cur = this.buffers.get(path);
    if (cur) return cur instanceof Promise ? cur : Promise.resolve(cur);
    const p = fetch(url(path))
      .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(r.status))))
      .then((ab) => new Promise((res, rej) => this.ctx.decodeAudioData(ab, res, rej)))
      .then((buf) => { this.buffers.set(path, buf); return buf; })
      .catch(() => { this.buffers.set(path, null); return null; });
    this.buffers.set(path, p);
    return p;
  }

  emit(ev) {
    for (const fn of this.listeners) fn(ev);
  }

  // ---------------------------------------------------------------
  play(path, volume = 1, category = "sfx", _remote = false) {
    if (!path) return;
    if (!_remote) this.emit({ t: "play", p: path, v: volume, c: category });
    if (this.muted && !_remote) return;
    if (!this.ctx) return;
    const buf = this.buffers.get(path);
    if (buf && !(buf instanceof Promise)) {
      this._start(buf, volume, category);
    } else if (buf === undefined || buf instanceof Promise) {
      const t0 = performance.now();
      this.load(path).then((b) => {
        // un efecto que llega tarde ya no tiene sentido, pero el nombre del
        // luchador sí (en el celular bajarlo puede tardar más de 0,4 s)
        const wait = category === "announcer" ? 3000 : 400;
        if (b && performance.now() - t0 < wait) this._start(b, volume, category);
      });
    }
  }

  _start(buf, volume, category, loop = false) {
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = loop;
    const g = this.ctx.createGain();
    g.gain.value = volume * (this.volumes[category] ?? 1);
    src.connect(g).connect(this.master);
    src.start();
    this.active.add(src);
    src.onended = () => this.active.delete(src);
    return src;
  }

  playSfx(key, volume = 1) {
    const list = FALLBACK_SFX[key];
    if (!list) return;
    this.play(list[Math.floor(Math.random() * list.length)], volume, "sfx");
  }

  playAnnouncer(name, volume = 1) {
    this.play(`${ANNOUNCER_DIR}/${name}.wav`, volume, "announcer");
  }

  announcerDuration(name) {
    const b = this.buffers.get(`${ANNOUNCER_DIR}/${name}.wav`);
    return b && !(b instanceof Promise) ? b.duration : 0.9;
  }

  playLoop(path, volume = 0.8, _remote = false, _id = null) {
    if (!path) return null;
    const id = _id ?? ++this.loopSeq;
    if (!_remote) this.emit({ t: "loop", p: path, v: volume, id });
    if ((this.muted && !_remote) || !this.ctx) return id;
    this.load(path).then((b) => {
      if (!b || this.loops.get(id) === "stopped") return;
      this.loops.set(id, this._start(b, volume, "sfx", true));
    });
    this.loops.set(id, "pending");
    return id;
  }

  stopLoop(id, _remote = false) {
    if (id == null) return;
    if (!_remote) this.emit({ t: "unloop", id });
    const src = this.loops.get(id);
    if (src && src.stop) { try { src.stop(); } catch (e) { /* ya paró */ } }
    this.loops.set(id, "stopped");
  }

  stopAllSfx(_remote = false) {
    if (!_remote) this.emit({ t: "stopall" });
    for (const s of this.active) { try { s.stop(); } catch (e) { /* nada */ } }
    this.active.clear();
    this.loops.clear();
  }

  pauseSfx() { if (this.ctx && this.ctx.state === "running") this.ctx.suspend(); }
  resumeSfx() { if (this.ctx && this.ctx.state === "suspended") this.ctx.resume(); }

  // ---------------------------------------------------------------
  // Música (streaming con <audio>, no se decodifica entera)
  // ---------------------------------------------------------------
  playMusic(path, { loop = true, volume = 0.5, category = "menu" } = {}, _remote = false) {
    if (!_remote) this.emit({ t: "music", p: path, l: loop, v: volume, c: category });
    this.musicCategory = category;
    if (this.muted && !_remote) return;
    if (!path) { this.stopMusic(true); return; }
    this.musicBaseVolume = volume;
    if (this.musicPath === path && !this.music.paused) return;
    this.musicPath = path;
    this.music.src = url(path);
    this.music.loop = loop;
    this.music.volume = Math.min(1, volume * this.musicVolumeFactor(category) * 2);
    this.music.play().catch(() => {});
  }

  stopMusic(_remote = false) {
    if (!_remote) this.emit({ t: "music", p: null });
    this.music.pause();
    this.musicPath = null;
  }

  isMusicPlaying() { return !!this.musicPath && !this.music.paused && !this.music.ended; }
  pauseMusic() { this.music.pause(); }
  // la app pasa a segundo plano (botón Inicio de la tele) o se cierra
  suspendAll() {
    this.wasPlaying = !!(this.musicPath && !this.music.paused);
    this.music.pause();
    if (this.ctx && this.ctx.state === "running") this.ctx.suspend();
    for (const v of this.videos) if (!v.paused) { v.dataset.mkResume = "1"; v.pause(); }
  }
  resumeAll() {
    if (this.ctx && this.ctx.state === "suspended") this.ctx.resume();
    if (this.wasPlaying) this.music.play().catch(() => {});
    for (const v of this.videos) if (v.dataset.mkResume) { delete v.dataset.mkResume; v.play().catch(() => {}); }
  }
  resumeMusic() { if (this.musicPath) this.music.play().catch(() => {}); }

  // Reproduce un evento recibido del anfitrión (online)
  applyRemote(ev) {
    switch (ev.t) {
      case "play": this.play(ev.p, ev.v, ev.c, true); break;
      case "loop": this.playLoop(ev.p, ev.v, true, "r" + ev.id); break;
      case "unloop": this.stopLoop("r" + ev.id, true); break;
      case "stopall": this.stopAllSfx(true); break;
      case "music": if (ev.p) this.playMusic(ev.p, { loop: ev.l, volume: ev.v, category: ev.c || "menu" }, true); else this.stopMusic(true); break;
      default: break;
    }
  }
}

export const audio = new AudioManager();
