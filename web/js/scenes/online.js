// =====================================================================
// scenes/online.js — partidas online por link: 1 vs 1 y Torneo
// ---------------------------------------------------------------------
// Anfitrión: Multijugador > Online -> se abre la sala y aparece el link
// para compartir (copiar, WhatsApp, mail o el menú de compartir del
// celular). Cada uno que abre el link entra a la sala. El anfitrión
// elige "Pelea 1 vs 1" (contra el primero que entró; el resto mira) o
// "Torneo" (todos los de la sala, cada uno elige su luchador en su
// propia pantalla).
// =====================================================================
import * as C from "../config.js";
import { COLORS, GAME_VERSION, ACTIONS } from "../config.js";
import * as UI from "../ui.js";
import { audio } from "../audio.js";
import { DB, loadCharacterFrames, randomStage, secretStage, stageById } from "../assets.js";
import { RemoteInput, IDLE, ok } from "../input.js";
import { Character } from "../character.js";
import { Stage } from "../stage.js";
import { Match, drawSnapshot } from "../match.js";
import { CharSelectScene, StageSelectScene } from "./select.js";
import { TournamentBracket, drawBracket, TournamentVictory } from "./tournament.js";
import { openHost, openGuest, newRoomCode, inviteLink } from "../net.js";
import { playMenuMusic } from "./menus.js";
import { BRIDGE, roomFromText } from "../platform.js";
import * as Flow from "../flow.js";

// ---------------------------------------------------------------------
// Panel HTML de compartir / nombre (los navegadores solo dejan copiar
// al portapapeles o abrir "compartir" desde un botón real)
// ---------------------------------------------------------------------
const panel = () => document.getElementById("share");
function showPanel({ link = null, app }) {
  const p = panel();
  p.classList.remove("hidden");
  const nameIn = document.getElementById("share-name");
  nameIn.value = app.settings.playerName || "";
  nameIn.onchange = () => {
    app.settings.playerName = nameIn.value.trim().slice(0, 16);
    app.saveSettings();
    if (app.net && app.net.onNameChange) app.net.onNameChange();
  };
  const linkBox = document.getElementById("share-link-box");
  if (!link) { linkBox.classList.add("hidden"); return; }
  linkBox.classList.remove("hidden");
  const input = document.getElementById("share-link");
  input.value = link;
  const msg = `¡Te desafío a una pelea en Mortal Kompa! Entrá acá: ${link}`;
  document.getElementById("share-copy").onclick = async () => {
    if (BRIDGE) { BRIDGE.copy(link); app.toast("¡Link copiado!"); return; }
    try { await navigator.clipboard.writeText(link); app.toast("¡Link copiado!"); }
    catch (e) { input.select(); document.execCommand && document.execCommand("copy"); app.toast("Link copiado"); }
  };
  // "Compartir": menú nativo del celular (WhatsApp, mail, etc.); en la PC,
  // donde casi nunca existe, abre WhatsApp con el mensaje armado
  document.getElementById("share-native").onclick = () => {
    if (BRIDGE) BRIDGE.share(msg);
    else if (navigator.share) navigator.share({ title: "Mortal Kompa", text: msg, url: link }).catch(() => {});
    else window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, "_blank", "noopener");
  };
}
function hidePanel() { panel().classList.add("hidden"); }

// "Unirse con un link": se pega el link (o el código) que mandó el anfitrión
export function showJoinPanel(app, onBack) {
  const p = document.getElementById("join");
  const input = document.getElementById("join-link");
  p.classList.remove("hidden");
  input.value = "";
  input.oninput = () => { if (!/[\/:?]/.test(input.value)) input.value = input.value.toUpperCase(); };
  input.onkeydown = (e) => { if (e.key === "Enter") document.getElementById("join-go").click(); };
  setTimeout(() => input.focus(), 50);
  const close = () => { p.classList.add("hidden"); };
  document.getElementById("join-go").onclick = () => {
    const room = roomFromText(input.value);
    if (!room) { app.toast("Escribí el código de 6 letras de la sala"); return; }
    close();
    // el código es de una sala que creó este mismo aparato: se reabre
    if (room === lastHostedRoom()) hostOnline(app, room);
    else joinOnlineScene(app, room);
  };
  document.getElementById("join-paste").onclick = async () => {
    try {
      const t = BRIDGE ? BRIDGE.paste() : await navigator.clipboard.readText();
      if (t) input.value = t;
    } catch (e) { app.toast("Mantené apretado el casillero y elegí Pegar"); }
  };
  app.setScene({
    draw(ctx, view) { UI.menuBackground(ctx, view, app.t); UI.title(ctx, view, "UNIRSE A UNA SALA", 50); UI.backButton(ctx, () => { close(); onBack(); }); },
    update() { if (app.anyInput.justPressed("cancel")) { close(); onBack(); } },
    exit() { close(); },
  });
}

// Pantalla de error de conexión: frena la pelea y la música, y deja que el
// jugador elija (esperar en la sala / volver al menú principal).
class ConnectionLostScene {
  constructor(app, { message, options }) {
    this.app = app; this.message = message; this.options = options; this.index = 0;
  }
  enter() {
    hidePanel();
    audio.stopAllSfx();
    audio.stopMusic();
    audio.resumeSfx();
    this.app.touch.fightMode = false;
  }
  update() {
    const i = this.app.anyInput, n = this.options.length;
    if (i.justPressed("up")) this.index = (this.index + n - 1) % n;
    else if (i.justPressed("down")) this.index = (this.index + 1) % n;
    else if (ok(i)) this.options[this.index].act();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    UI.overlay(ctx, view, 0.45);
    UI.title(ctx, view, "CONEXIÓN PERDIDA", 150, COLORS.red, 44);
    UI.text(ctx, this.message, view.w / 2, 205, { size: 20 });
    UI.menuList(ctx, view, this.options.map((o) => o.label), this.index, 320, (k) => this.options[k].act());
  }
}

function myName(app, fallback) { return (app.settings.playerName || "").trim() || fallback; }

// =====================================================================
// ANFITRIÓN
// =====================================================================
// Última sala creada en este aparato: si se corta todo (o se cierra el
// juego), el anfitrión la recupera escribiendo el mismo código en "Unirse".
const LAST_ROOM_KEY = "mk_last_room";
function rememberRoom(code) {
  try { localStorage.setItem(LAST_ROOM_KEY, JSON.stringify({ code, at: Date.now() })); } catch (e) { /* nada */ }
}
function lastHostedRoom() {
  try {
    const r = JSON.parse(localStorage.getItem(LAST_ROOM_KEY) || "null");
    if (r && r.code && Date.now() - r.at < 24 * 3600 * 1000) return r.code;
  } catch (e) { /* nada */ }
  return null;
}

class HostSession {
  constructor(app, code = null) {
    this.app = app;
    this.code = code || newRoomCode();
    // sala recuperada: el servidor puede tardar en soltar el código viejo
    this.keepCodeUntil = code ? performance.now() + 90000 : 0;
    this.clients = new Map();
    this.nextId = 1;
    this.ready = false;
    this.error = null;
    this.stream = null;      // Match que se está transmitiendo
    this.audioBuf = [];
    this.lastSent = null;
    this.listener = (ev) => this.audioBuf.push(ev);
    audio.listeners.push(this.listener);
    this.open();
  }
  open() {
    this.transport = openHost(this.code, {
      onReady: () => { this.ready = true; rememberRoom(this.code); },
      onConnection: (conn) => this.accept(conn),
      onSignal: (ok) => { this.signalLost = !ok; },
      onError: (e) => {
        if (e === "unavailable-id") {
          const old = this.transport;
          setTimeout(() => old && old.destroy(), 0);
          if (performance.now() < this.keepCodeUntil) { this.retryT = setTimeout(() => this.open(), 3000); return; }
          this.code = newRoomCode(); this.open(); return;
        }
        this.error = e;
      },
    });
  }
  get link() { return inviteLink(this.code); }
  accept(conn) {
    if (this.clients.size >= 15) { conn.send({ t: "full" }); setTimeout(() => conn.close(), 500); return; }
    const id = this.nextId++;
    const cl = { id, conn, name: `Invitado ${id}`, input: new RemoteInput(), pick: null, ready: false, lastSeen: performance.now() };
    this.clients.set(id, cl);
    conn.onData = (m) => { cl.lastSeen = performance.now(); this.onMsg(cl, m); };
    conn.onClose = () => this.drop(cl);
    conn.send({ t: "welcome", id, ver: GAME_VERSION });
  }
  drop(cl) {
    if (!this.clients.has(cl.id)) return;
    this.clients.delete(cl.id);
    cl.input.receive(0, cl.input.counts);
    this.app.toast(`${cl.name} se desconectó`);
    this.sendLobby();
    if (this.onDrop) this.onDrop(cl);
  }
  onMsg(cl, m) {
    if (!m || typeof m !== "object") return;
    switch (m.t) {
      case "hello":
        cl.name = String(m.name || cl.name).slice(0, 16);
        if (m.ver !== GAME_VERSION) cl.conn.send({ t: "toast", msg: `Ojo: el anfitrión tiene ${GAME_VERSION} y vos ${m.ver}` });
        this.app.toast(`${cl.name} entró a la sala`);
        this.sendLobby();
        if (this.onJoin) this.onJoin(cl);
        break;
      case "name": cl.name = String(m.name || cl.name).slice(0, 16); this.sendLobby(); break;
      case "in": cl.input.receive(m.m, m.c); break;
      case "pick": cl.pick = { slug: m.slug, random: !!m.random }; if (this.onPick) this.onPick(cl); break;
      case "ready": cl.ready = true; break;
      case "ping": cl.conn.send({ t: "pong", ts: m.ts }); break;
      default: break;
    }
  }
  players() {
    return [{ id: 0, name: myName(this.app, "Anfitrión") }, ...[...this.clients.values()].map((c) => ({ id: c.id, name: c.name }))];
  }
  nameOf(id) { return id === 0 ? myName(this.app, "Anfitrión") : (this.clients.get(id) || {}).name || "?"; }
  inputOf(id) { if (id === 0) return this.app.inputs[0]; const c = this.clients.get(id); return c ? c.input : IDLE; }
  broadcast(m) { for (const c of this.clients.values()) c.conn.send(m); }
  sendLobby() { this.broadcast({ t: "lobby", players: this.players() }); }
  onNameChange() { this.sendLobby(); }
  // cada cuadro (lo llama el loop principal)
  tick() {
    for (const c of this.clients.values()) c.input.poll();
    if (this.stream) {
      this.broadcast({ t: "fs", s: this.stream.snapshot(), a: this.audioBuf });
    } else {
      // señal de vida para los invitados (fuera de pelea casi no se manda nada)
      this.hb = (this.hb || 0) + 1;
      if (this.hb >= 30) { this.hb = 0; this.broadcast({ t: "hb" }); }
    }
    this.audioBuf = [];
    // invitado que no manda nada hace 5 s: se cerró el juego o se cortó internet
    const now = performance.now();
    for (const c of [...this.clients.values()]) {
      if (now - c.lastSeen > 5000) { try { c.conn.close(); } catch (e) { /* nada */ } this.drop(c); }
    }
  }
  close() {
    clearTimeout(this.retryT);
    this.broadcast({ t: "bye" });
    audio.listeners.splice(audio.listeners.indexOf(this.listener), 1);
    setTimeout(() => this.transport && this.transport.destroy(), 300);
    if (this.app.net === this) this.app.net = null;
  }
}

export function hostOnline(app, code = null) {
  if (app.net && app.net.close) app.net.close();
  app.net = new HostSession(app, code);
  app.setScene(new HostLobbyScene(app));
}

class HostLobbyScene {
  constructor(app) { this.app = app; this.index = 0; this.net = app.net; }
  enter() {
    this.app.touch.fightMode = false;
    this.net.stream = null;
    this.net.onPick = null;
    this.net.onDrop = null;
    this.net.broadcast({ t: "lobby", players: this.net.players(), go: true });
    playMenuMusic();
  }
  exit() { hidePanel(); }
  items() {
    const n = this.net.clients.size;
    const close = { label: "Cerrar sala", ok: true, act: () => this.closeRoom() };
    // con 1 invitado se pelea 1 vs 1; con 2 o más, torneo entre todos
    if (n >= 2) return [{ label: "Empezar torneo", ok: true, act: () => hostTournament(this.app) }, close];
    return [{ label: "Empezar pelea", ok: n >= 1, act: () => host1v1(this.app), why: "Falta que entre alguien a la sala" }, close];
  }
  closeRoom() {
    this.net.close();
    Flow.onlineMenu(this.app, 0);
  }
  update() {
    const i = this.app.anyInput;
    const items = this.items();
    if (i.justPressed("up")) this.index = (this.index + items.length - 1) % items.length;
    else if (i.justPressed("down")) this.index = (this.index + 1) % items.length;
    else if (ok(i)) { const it = items[this.index]; if (it.ok) it.act(); else this.app.toast(it.why); }
    else if (i.justPressed("cancel")) this.closeRoom();
    if (this.net.ready && !this.panelShown) { this.panelShown = true; showPanel({ link: this.net.link, app: this.app }); }
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    const lx = 40;
    // título a la izquierda: a la derecha va el panel del link
    UI.text(ctx, `SALA ONLINE: ${String(this.net.code || "").toUpperCase()}`, lx, 36, { size: 30, color: COLORS.yellow, stroke: 6, align: "left" });
    if (this.net.error) {
      UI.text(ctx, this.net.error, lx, 78, { size: 15, align: "left", color: COLORS.red });
    } else if (this.net.ready && this.net.signalLost) {
      UI.text(ctx, "Reconectando... (los que ya entraron siguen en la sala)", lx, 78, { size: 15, align: "left", color: "#fb4" });
    } else if (!this.net.ready) {
      UI.text(ctx, "Abriendo la sala...", lx, 90, { size: 20, align: "left" });
    } else {
      UI.text(ctx, "Pasales el código o mandales el link (panel de la derecha)", lx, 78, { size: 15, align: "left", color: "#cfe" });
    }
    UI.text(ctx, "En la sala:", lx, 116, { size: 18, align: "left", color: COLORS.yellow });
    this.net.players().forEach((p, k) => {
      UI.text(ctx, `${k === 0 ? "★" : "•"} ${p.name}${k === 0 ? " (vos)" : ""}`, lx + 10, 144 + k * 24, { size: 17, align: "left" });
    });
    const items = this.items();
    const y0 = C.BASE_H - 150;
    items.forEach((it, k) => {
      const y = y0 + k * 46;
      const sel = k === this.index;
      UI.roundRect(ctx, lx, y - 20, 300, 40, 10);
      ctx.fillStyle = sel ? "rgba(240,200,40,0.18)" : "rgba(255,255,255,0.05)";
      ctx.fill();
      if (sel) { ctx.strokeStyle = COLORS.yellow; ctx.lineWidth = 2; ctx.stroke(); }
      UI.text(ctx, it.label, lx + 150, y, { size: 21, color: it.ok ? (sel ? COLORS.yellow : "#fff") : "#666" });
      UI.addHit({ x: lx, y: y - 20, w: 300, h: 40 }, () => { this.index = k; if (it.ok) it.act(); else if (it.why) this.app.toast(it.why); });
    });
    // acá arriba a la izquierda va el título: el volver va abajo de todo
    UI.backButton(ctx, () => this.closeRoom(), "◄ VOLVER", y0 + items.length * 46 + 16);
  }
}

// Espera genérica del anfitrión ("esperando que elijan...")
class HostWaitScene {
  constructor(app, { textFn, onCancel, check }) { this.app = app; this.textFn = textFn; this.onCancel = onCancel; this.check = check; }
  enter() { this.app.touch.fightMode = false; }
  update() {
    if (this.check) this.check();
    if (this.app.anyInput.justPressed("cancel")) this.onCancel();
  }
  draw(ctx, view) {
    UI.menuBackground(ctx, view, this.app.t);
    const lines = this.textFn();
    lines.forEach((l, k) => UI.text(ctx, l, view.w / 2, 200 + k * 34, { size: k === 0 ? 26 : 18, color: k === 0 ? COLORS.yellow : "#ddd" }));
    UI.pillButton(ctx, view.w / 2, C.BASE_H - 50, "Volver a la sala", () => this.onCancel(), { size: 15, h: 36, color: "#3c3c48" });
  }
}

function backToLobby(app, msg) {
  const net = app.net;
  if (!net) { Flow.mainMenu(app); return; }
  if (net.stream && net.stream.stage) net.stream.stage.dispose();
  net.stream = null;
  if (msg) app.toast(msg);
  audio.stopAllSfx();
  app.setScene(new HostLobbyScene(app));
}

// ---------------------------------------------------------------------
// 1 vs 1 online
// ---------------------------------------------------------------------
function host1v1(app, keepStage = null) {
  const net = app.net;
  const rival = [...net.clients.values()][0];
  if (!rival) { backToLobby(app, "No hay nadie en la sala"); return; }
  rival.pick = null;
  net.broadcast({ t: "pick", who: [rival.id], title: "ELEGÍ TU LUCHADOR", sub: `Peleás contra ${net.nameOf(0)}` });
  net.onDrop = (cl) => { if (cl.id === rival.id) backToLobby(app, `${cl.name} se fue de la pelea`); };
  let myPick = null;
  const afterPicks = () => {
    if (!myPick || !rival.pick) return;
    net.onPick = null;
    net.broadcast({ t: "wait", msg: `${net.nameOf(0)} está eligiendo el escenario...` });
    app.setScene(new StageSelectScene(app, {
      input: app.inputs[0],
      onBack: () => backToLobby(app),
      onDone: (stageDef) => netFight(app, {
        slugs: [myPick.slug, rival.pick.slug], mystery: [false, false], owners: [0, rival.id],
        stageDef, kind: "versus",
      }),
    }));
  };
  net.onPick = () => {
    if (myPick) afterPicks();
  };
  app.setScene(new CharSelectScene(app, {
    players: [{ input: app.inputs[0], label: net.nameOf(0) }],
    title: "ELEGÍ TU LUCHADOR",
    subtitle: `Peleás contra ${rival.name} (elige en su pantalla)`,
    onBack: () => { net.broadcast({ t: "wait", msg: "El anfitrión volvió a la sala" }); backToLobby(app); },
    onDone: (picks) => {
      myPick = picks[0];
      if (rival.pick) afterPicks();
      else app.setScene(new HostWaitScene(app, {
        textFn: () => [`Esperando que ${rival.name} elija...`, "Lo elige en su propia pantalla"],
        onCancel: () => backToLobby(app),
        check: () => { if (rival.pick) afterPicks(); },
      }));
    },
  }));
}

// Carga + pelea transmitida a todos los de la sala
async function netFight(app, { slugs, mystery, owners, stageDef, kind, names = null, onOver = null }) {
  const net = app.net;
  for (const c of net.clients.values()) c.ready = false;
  const nm = names || owners.map((o) => null);
  net.broadcast({ t: "load", slugs, stage: stageDef ? stageDef.id : null, owners, names: nm, kind });
  const prep = await Flow.prepareFight(app, slugs, stageDef);
  // esperar a que carguen los invitados (máx. 12 s)
  const t0 = performance.now();
  await new Promise((res) => {
    const iv = setInterval(() => {
      const all = [...net.clients.values()].every((c) => c.ready);
      if (all || performance.now() - t0 > 12000) { clearInterval(iv); res(); }
    }, 100);
  });
  if (!app.net) return;
  audio.stopAllSfx();
  Flow.playStageMusic(prep.stage);
  const inputs = owners.map((o) => net.inputOf(o));
  const build = () => new Match({ entries: prep.entries, frames: prep.frames, stage: prep.stage, inputs, mystery, names: names });
  const scene = new Flow.FightScene(app, {
    match: build(), pausers: [], net: true,
    endMenu: kind === "versus",
    endItems: ["Pelear de nuevo", "Cambiar personajes", "Volver a la sala"],
    overDelay: 3.2,
    onOver: onOver ? (m) => { net.stream = null; onOver(m); } : null,
    onEndChoice: (choice, sc) => {
      if (choice === 0) {
        net.broadcast({ t: "rematch" });
        sc.match = build();
        sc.overHandled = false;
        net.stream = sc.match;
        Flow.playStageMusic(prep.stage);
      } else if (choice === 1) { net.stream = null; sc.cleanup(); host1v1(app); }
      else { sc.cleanup(); backToLobby(app); }
    },
  });
  // pausa deshabilitada online
  scene.pauseItems = () => ["Reanudar", "Abandonar partida"];
  const origPick = scene.pausePick.bind(scene);
  scene.pausePick = (i) => { if (i === 1) { scene.cleanup(); backToLobby(app, "Partida abandonada"); } else origPick(0); };
  net.stream = scene.match;
  const prevDrop = net.onDrop;
  net.onDrop = (cl) => {
    if (owners.includes(cl.id) && kind === "versus") {
      net.stream = null;
      if (scene.match && scene.match.stage) scene.match.stage.dispose();
      app.setScene(new ConnectionLostScene(app, {
        message: `${cl.name} se desconectó de la pelea`,
        options: [
          { label: "Volver a la sala", act: () => { playMenuMusic(); backToLobby(app); } },
          { label: "Volver al menú principal", act: () => { if (app.net) app.net.close(); audio.stopAllSfx(); Flow.mainMenu(app); } },
        ],
      }));
    }
    else if (prevDrop && kind !== "versus") prevDrop(cl);
  };
  // tecla de pausa del anfitrión: no pausa el juego, abre "abandonar"
  app.setScene(scene);
}

// ---------------------------------------------------------------------
// Torneo online
// ---------------------------------------------------------------------
function hostTournament(app) {
  const net = app.net;
  const ids = [...net.clients.keys()];
  for (const c of net.clients.values()) c.pick = null;
  net.broadcast({ t: "pick", who: ids, title: "TORNEO: ELEGÍ TU LUCHADOR", sub: "Esperá a que elijan todos" });
  let myPick = null;
  const allIn = () => myPick && [...net.clients.values()].every((c) => c.pick);
  const go = () => {
    net.onPick = null;
    const picks = [{ slug: myPick.slug, owner: 0, label: `${net.nameOf(0)} (${DB.bySlug[myPick.slug].name})` }];
    for (const c of net.clients.values()) picks.push({ slug: c.pick.slug, owner: c.id, label: `${c.name} (${DB.bySlug[c.pick.slug].name})` });
    if (picks.length < 3) { backToLobby(app, "El torneo necesita 3 jugadores o más"); return; }
    const bracket = new TournamentBracket(picks);
    app.setScene(new HostBracketScene(app, bracket));
  };
  net.onPick = () => { if (allIn()) go(); };
  net.onDrop = () => { if (allIn()) go(); };
  app.setScene(new CharSelectScene(app, {
    players: [{ input: app.inputs[0], label: net.nameOf(0) }],
    title: "TORNEO: ELEGÍ TU LUCHADOR",
    subtitle: "Cada uno elige en su propia pantalla",
    allowRandom: true,
    onBack: () => { net.broadcast({ t: "wait", msg: "El anfitrión volvió a la sala" }); backToLobby(app); },
    onDone: (picks) => {
      myPick = picks[0];
      if (allIn()) go();
      else app.setScene(new HostWaitScene(app, {
        textFn: () => ["Esperando que elijan todos...", ...[...net.clients.values()].map((c) => `${c.name}: ${c.pick ? "¡listo!" : "eligiendo"}`)],
        onCancel: () => backToLobby(app),
        check: () => { if (allIn()) go(); },
      }));
    },
  }));
}

class HostBracketScene {
  constructor(app, bracket) {
    this.app = app; this.bracket = bracket; this.phase = "ready"; this.result = null; this.timer = 0;
  }
  enter() {
    this.app.touch.fightMode = false;
    this.app.net.onDrop = null;
    this.send();
    playMenuMusic();
  }
  send() {
    this.app.net.broadcast({ t: "bracket", st: this.bracket.state(), phase: this.phase, result: this.result });
  }
  update(dt) {
    const net = this.app.net;
    if (!net) return;
    if (this.phase === "result") {
      this.timer -= dt;
      if (this.timer <= 0 || ok(this.app.anyInput)) this.advance();
      return;
    }
    // si falta alguno de los dos (se desconectó), pierde por abandono
    const m = this.bracket.currentMatch();
    if (m) {
      const missing = m.map((e) => e.owner !== 0 && !net.clients.has(e.owner));
      if (missing[0] || missing[1]) {
        const w = missing[0] ? 1 : 0;
        this.app.toast(`${m[w].label} gana por abandono`);
        this.finishMatch(w);
        return;
      }
    }
    if (ok(this.app.anyInput)) this.fight();
  }
  finishMatch(w) {
    const b = this.bracket;
    const m = b.currentMatch();
    if (b.isFinalMatch()) {
      b.reportResult(m[w]);
      this.champion();
      return;
    }
    this.result = { winner: m[w].label, loser: m[1 - w].label };
    this.winnerEntrant = m[w];
    this.phase = "result";
    this.timer = 3.5;
    this.app.setScene(this);
    this.send();
  }
  champion() {
    const b = this.bracket;
    const net = this.app.net;
    net.broadcast({ t: "champion", slug: b.champion.slug, label: b.champion.label, total: b.entrants.length });
    this.app.setScene(new TournamentVictory(this.app, b.champion, b.entrants.length, {
      onDone: () => backToLobby(this.app),
    }));
  }
  advance() {
    const finished = this.bracket.reportResult(this.winnerEntrant);
    this.phase = "ready";
    this.result = null;
    if (finished) this.champion();
    else this.send();
  }
  fight() {
    if (this.starting) return;
    this.starting = true;
    const b = this.bracket;
    const m = b.currentMatch();
    const stageDef = b.isFinalMatch() ? (secretStage() || randomStage()) : randomStage();
    netFight(this.app, {
      slugs: [m[0].slug, m[1].slug], mystery: [false, false], owners: [m[0].owner, m[1].owner],
      names: [m[0].label, m[1].label], stageDef, kind: "tournament",
      onOver: (mm) => {
        this.starting = false;
        if (mm.stage) mm.stage.dispose();
        this.finishMatch(mm.winner);
      },
    });
  }
  draw(ctx, view) {
    const st = this.bracket.state();
    const m = this.bracket.currentMatch();
    let hint = "";
    if (this.phase === "ready" && m) {
      const meIn = m.some((e) => e.owner === 0);
      hint = meIn ? "Confirmar: ¡a pelear! (vos jugás esta)" : "Confirmar: arrancar la pelea (vos mirás esta)";
    }
    drawBracket(ctx, view, st, { phase: this.phase, result: this.result, t: this.app.t, hint });
    if (this.phase === "ready") UI.pillButton(ctx, view.w / 2, 232, "¡PELEAR!", () => this.fight(), { size: 16, h: 34, minW: 140 });
    UI.backButton(ctx, () => backToLobby(this.app, "Torneo cancelado"), "◄ A LA SALA");
  }
}

// =====================================================================
// INVITADO
// =====================================================================
class GuestSession {
  constructor(app, code, { retry = false } = {}) {
    this.app = app;
    this.code = code;
    this.conn = null;
    this.myId = null;
    this.error = null;
    this.lastMask = -1;
    this.counts = new Array(ACTIONS.length).fill(0);
    this.sinceSend = 0;
    this.scene = null;
    // volviendo a una sala que se cortó: se reintenta un rato mientras el
    // anfitrión vuelve (o reabre la sala con el mismo código)
    this.retryUntil = retry ? performance.now() + 90000 : 0;
    this.connect();
  }
  connect() {
    const app = this.app;
    this.transport = openGuest(this.code, {
      onOpen: (conn) => {
        this.conn = conn;
        this.lastSeen = performance.now();
        conn.onData = (m) => { this.lastSeen = performance.now(); if (this.scene) this.scene.onMsg(m); };
        conn.onClose = () => this.scene && this.scene.onMsg({ t: "closed" });
        conn.send({ t: "hello", name: myName(app, ""), ver: GAME_VERSION });
      },
      onError: (e) => {
        if (!this.conn && !this.closed && performance.now() < this.retryUntil) {
          const old = this.transport;
          setTimeout(() => old && old.destroy(), 0);
          this.retryT = setTimeout(() => { if (!this.closed) this.connect(); }, 3000);
          return;
        }
        this.error = e;
      },
    });
  }
  send(m) { if (this.conn) this.conn.send(m); }
  onNameChange() { this.send({ t: "name", name: myName(this.app, "Invitado") }); }
  tick() {
    if (!this.conn) return;
    // anfitrión que no manda nada hace 5 s: conexión perdida
    if (!this.lostReported && performance.now() - this.lastSeen > 5000) {
      this.lostReported = true;
      if (this.scene) this.scene.onMsg({ t: "closed" });
    }
    const inp = this.app.inputs[0];
    ACTIONS.forEach((a, i) => { if (inp.justPressed(a)) this.counts[i]++; });
    const mask = inp.mask();
    this.sinceSend++;
    if (mask !== this.lastMask || this.sinceSend >= 10 || ACTIONS.some((a) => inp.justPressed(a))) {
      this.send({ t: "in", m: mask, c: this.counts });
      this.lastMask = mask;
      this.sinceSend = 0;
    }
  }
  close() {
    this.closed = true;
    clearTimeout(this.retryT);
    try { this.conn && this.conn.close(); } catch (e) { /* nada */ }
    this.transport && this.transport.destroy();
    if (this.app.net === this) this.app.net = null;
  }
}

export function joinOnlineScene(app, code, opts = {}) {
  // sacar ?sala= de la URL para que "volver al menú" no vuelva a entrar
  history.replaceState(null, "", location.pathname + (location.search.includes("net=local") ? "?net=local" : ""));
  app.inviteRoom = null;
  if (app.net && app.net.close) app.net.close();
  const net = new GuestSession(app, code, opts);
  app.net = net;
  const sc = new GuestScene(app, net);
  net.scene = sc;
  app.setScene(sc);
}

class GuestScene {
  constructor(app, net) {
    this.app = app;
    this.net = net;
    this.mode = "connecting";
    this.players = [];
    this.msg = "";
    this.snap = null;
    this.chars = null;
    this.stage = null;
    this.sub = null;
  }
  enter() { showPanel({ app: this.app }); playMenuMusic(); }
  exit() { hidePanel(); }
  lost(message, canRetry) {
    if (this.mode === "left") return;
    this.mode = "left";
    const code = this.net.code;
    this.net.close();
    if (this.stage) { this.stage.dispose(); this.stage = null; }
    const app = this.app;
    const options = [];
    if (canRetry) options.push({ label: "Volver a la sala", act: () => joinOnlineScene(app, code, { retry: true }) });
    options.push({ label: "Volver al menú principal", act: () => { audio.stopAllSfx(); Flow.mainMenu(app); } });
    app.setScene(new ConnectionLostScene(app, { message, options }));
  }
  leave(msg) {
    this.net.close();
    hidePanel();
    if (this.stage) this.stage.dispose();
    this.app.touch.fightMode = false;
    if (msg) this.app.toast(msg, 5);
    audio.stopAllSfx();
    Flow.mainMenu(this.app);
  }
  async onMsg(m) {
    switch (m.t) {
      case "welcome": this.net.myId = m.id; this.mode = "lobby"; break;
      case "full": this.leave("La sala está llena"); break;
      case "lobby":
        this.players = m.players;
        if (m.go || this.mode === "connecting" || this.mode === "lobby") {
          this.mode = "lobby"; this.sub = null; showPanel({ app: this.app }); this.app.touch.fightMode = false;
          if (this.stage) { this.stage.dispose(); this.stage = null; }
          playMenuMusic();
        }
        break;
      case "toast": this.app.toast(m.msg); break;
      case "wait": this.mode = "wait"; this.msg = m.msg; this.sub = null; this.app.touch.fightMode = false; break;
      case "pick":
        hidePanel();
        if (m.who.includes(this.net.myId)) {
          this.mode = "pick";
          this.sub = new CharSelectScene(this.app, {
            players: [{ input: this.app.inputs[0], label: myName(this.app, "Vos") }],
            title: m.title || "ELEGÍ TU LUCHADOR", subtitle: m.sub || "",
            onBack: () => {},
            onDone: (picks) => {
              this.net.send({ t: "pick", slug: picks[0].slug, random: picks[0].random });
              this.sub = null; this.mode = "wait"; this.msg = "¡Listo! Esperando a los demás...";
            },
          });
        } else { this.mode = "wait"; this.msg = "Están eligiendo luchador..."; }
        break;
      case "load": {
        this.mode = "loading";
        this.sub = null;
        hidePanel();
        this.owners = m.owners;
        this.kind = m.kind;
        this.endShown = false;
        if (this.stage) this.stage.dispose();
        const [f1, f2, st] = await Promise.all([loadCharacterFrames(m.slugs[0]), loadCharacterFrames(m.slugs[1]), Stage.load(stageById(m.stage))]);
        this.chars = [new Character(DB.bySlug[m.slugs[0]], f1), new Character(DB.bySlug[m.slugs[1]], f2)];
        this.stage = st;
        this.snap = null;
        this.net.send({ t: "ready" });
        this.mode = "fight";
        this.app.touch.fightMode = this.owners.includes(this.net.myId);
        break;
      }
      case "fs":
        if (this.mode !== "fight") break;
        this.snap = m.s;
        for (const ev of m.a || []) audio.applyRemote(ev);
        break;
      case "rematch": this.endShown = false; break;
      case "bracket": this.mode = "bracket"; this.bracket = m; this.sub = null; this.app.touch.fightMode = false; break;
      case "champion":
        this.mode = "champion";
        this.app.touch.fightMode = false;
        this.victory = new TournamentVictory(this.app, { slug: m.slug, label: m.label }, m.total, { onDone: false });
        break;
      case "bye": this.lost("El anfitrión cerró la sala", false); break;
      case "closed": if (this.mode !== "left") this.lost("Se cortó la conexión con el anfitrión", true); break;
      default: break;
    }
  }
  onPointer(x, y) { return this.sub && this.sub.onPointer ? this.sub.onPointer(x, y) : false; }
  update(dt) {
    if (this.net.error) { const e = this.net.error; this.net.error = null; this.leave(e); return; }
    if (this.sub) { this.sub.update(dt); return; }
    if (this.mode === "champion" && this.victory) this.victory.update(dt);
    if (this.mode === "fight" && this.snap) {
      const me = this.owners ? this.owners.indexOf(this.net.myId) : -1;
      if (me >= 0) this.app.touch.specialCharge = this.snap.f[me][8];
      if (this.snap.ph === "over") this.app.touch.fightMode = false;
    }
    if (["lobby", "wait", "connecting"].includes(this.mode) && this.app.anyInput.justPressed("cancel")) this.leave();
  }
  draw(ctx, view) {
    if (this.sub) { this.sub.draw(ctx, view); return; }
    if (this.mode === "fight" && this.snap && this.chars) {
      drawSnapshot(ctx, view, this.snap, this.chars, this.stage);
      if (this.snap.ph === "over" && this.snap.win !== null && this.snap.win !== undefined) {
        const name = this.snap.f[this.snap.win][9];
        UI.overlay(ctx, view, 140 / 255);
        UI.pcTitle(ctx, view, `¡${String(name).toUpperCase()} GANA LA PELEA!`, 70);
        if (this.kind === "versus") UI.text(ctx, "Esperando al anfitrión...", view.w / 2, C.BASE_H / 2 + 60, { size: 20 });
      }
      return;
    }
    if (this.mode === "bracket" && this.bracket) {
      drawBracket(ctx, view, this.bracket.st, { phase: this.bracket.phase, result: this.bracket.result, t: this.app.t, hint: "El anfitrión arranca cada pelea" });
      return;
    }
    if (this.mode === "champion" && this.victory) { this.victory.draw(ctx, view); return; }
    UI.menuBackground(ctx, view, this.app.t);
    UI.title(ctx, view, "PARTIDA ONLINE", 36);
    const lx = 40;
    if (this.mode === "connecting") UI.text(ctx, "Conectando a la sala...", lx, 100, { size: 22, align: "left" });
    else if (this.mode === "loading") UI.text(ctx, "Cargando la pelea...", view.w / 2, C.BASE_H / 2, { size: 26 });
    else {
      UI.text(ctx, this.mode === "wait" ? this.msg : "Esperando a que el anfitrión arranque...", lx, 90, { size: 18, align: "left", color: "#cfe" });
      UI.text(ctx, "En la sala:", lx, 130, { size: 18, align: "left", color: COLORS.yellow });
      this.players.forEach((p, k) => UI.text(ctx, `${k === 0 ? "★" : "•"} ${p.name}${p.id === this.net.myId ? " (vos)" : ""}`, lx + 10, 158 + k * 24, { size: 17, align: "left" }));
    }
    UI.backButton(ctx, () => this.leave(), "◄ SALIR");
  }
}
