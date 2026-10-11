// =====================================================================
// net.js — conexión online por link (WebRTC peer-to-peer con PeerJS)
// ---------------------------------------------------------------------
// MODELO "anfitrión con autoridad" (igual que el multijugador WiFi de la
// versión Android): el que invita corre TODO el juego; los invitados le
// mandan qué botones aprietan y dibujan lo que el anfitrión les manda
// (posiciones, poses, vida, sonidos...). No hay "salas" ni servidor
// propio: PeerJS usa su servidor público gratuito solo para presentar a
// los dos navegadores; después la pelea viaja directo entre ellos.
//
// Para probar sin internet en una misma PC: agregá ?net=local a la URL
// y abrí el link de invitación en otra pestaña del mismo navegador.
// =====================================================================
import { ICE_SERVERS, GAME_VERSION } from "./config.js";

const ID_PREFIX = "mortalkompa-";
const LOCAL = new URLSearchParams(location.search).get("net") === "local";

export function newRoomCode() {
  const abc = "abcdefghjkmnpqrstuvwxyz23456789";
  let s = "";
  for (let i = 0; i < 6; i++) s += abc[Math.floor(Math.random() * abc.length)];
  return s;
}

export function inviteLink(code) {
  const u = new URL(location.href);
  u.search = "";
  u.hash = "";
  u.searchParams.set("sala", code);
  if (LOCAL) u.searchParams.set("net", "local");
  return u.toString();
}

// ---------------------------------------------------------------------
// Conexión mínima: send(obj), onData, onClose, close()
// ---------------------------------------------------------------------
class Conn {
  constructor() { this.onData = null; this.onClose = null; this.open = false; }
}

// --- PeerJS ---
function peerAvailable() { return typeof window.Peer === "function"; }

function makePeer(id) {
  return new window.Peer(id, { config: { iceServers: ICE_SERVERS }, debug: 1 });
}

function wrapPeerConn(dc) {
  const c = new Conn();
  c.peerId = dc.peer;
  c.send = (o) => { if (dc.open) dc.send(o); };
  c.close = () => { try { dc.close(); } catch (e) { /* nada */ } };
  dc.on("data", (d) => c.onData && c.onData(d));
  dc.on("close", () => { c.open = false; c.onClose && c.onClose(); });
  dc.on("error", () => { c.open = false; c.onClose && c.onClose(); });
  return c;
}

// --- Transporte local (BroadcastChannel) para pruebas ---
class LocalHub {
  constructor(id) {
    this.id = id;
    this.ch = new BroadcastChannel("mkp-local-net");
    this.conns = new Map();
    this.ch.onmessage = (e) => this.onMsg(e.data);
  }
  onMsg(m) {
    if (m.to !== this.id) return;
    if (m.k === "connect" && this.onConnection) {
      const c = this.makeConn(m.from);
      c.open = true;
      this.ch.postMessage({ k: "accept", to: m.from, from: this.id });
      this.onConnection(c);
    } else if (m.k === "accept") {
      const c = this.conns.get(m.from);
      if (c) { c.open = true; c.onOpen && c.onOpen(); }
    } else if (m.k === "data") {
      const c = this.conns.get(m.from);
      if (c && c.onData) c.onData(m.d);
    } else if (m.k === "close") {
      const c = this.conns.get(m.from);
      if (c) { c.open = false; c.onClose && c.onClose(); this.conns.delete(m.from); }
    }
  }
  makeConn(peer) {
    const c = new Conn();
    c.peerId = peer;
    c.send = (d) => this.ch.postMessage({ k: "data", to: peer, from: this.id, d });
    c.close = () => this.ch.postMessage({ k: "close", to: peer, from: this.id });
    this.conns.set(peer, c);
    return c;
  }
  connect(peer) {
    const c = this.makeConn(peer);
    this.ch.postMessage({ k: "connect", to: peer, from: this.id });
    return c;
  }
  destroy() { for (const c of this.conns.values()) c.close(); this.ch.close(); }
}

// ---------------------------------------------------------------------
// Anfitrión: abre la "sala" y acepta conexiones
// ---------------------------------------------------------------------
export function openHost(code, { onReady, onConnection, onError }) {
  const id = ID_PREFIX + code;
  if (LOCAL) {
    const hub = new LocalHub(id);
    hub.onConnection = onConnection;
    setTimeout(() => onReady(code), 50);
    return { destroy: () => hub.destroy() };
  }
  if (!peerAvailable()) { onError("No se pudo cargar la librería de conexión (PeerJS)."); return { destroy() {} }; }
  const peer = makePeer(id);
  peer.on("open", () => onReady(code));
  peer.on("connection", (dc) => {
    dc.on("open", () => { const c = wrapPeerConn(dc); c.open = true; onConnection(c); });
  });
  peer.on("error", (err) => {
    if (err.type === "unavailable-id") onError("unavailable-id");
    else onError(describeError(err));
  });
  peer.on("disconnected", () => { try { peer.reconnect(); } catch (e) { /* nada */ } });
  return { destroy: () => { try { peer.destroy(); } catch (e) { /* nada */ } } };
}

// Invitado: se conecta a la sala del link
export function openGuest(code, { onOpen, onError }) {
  const hostId = ID_PREFIX + code;
  const myId = ID_PREFIX + "g-" + newRoomCode() + newRoomCode();
  if (LOCAL) {
    const hub = new LocalHub(myId);
    const c = hub.connect(hostId);
    c.onOpen = () => onOpen(c);
    const t = setTimeout(() => { if (!c.open) onError("La sala no existe o ya se cerró."); }, 4000);
    return { destroy: () => { clearTimeout(t); hub.destroy(); } };
  }
  if (!peerAvailable()) { onError("No se pudo cargar la librería de conexión (PeerJS)."); return { destroy() {} }; }
  const peer = makePeer(myId);
  let done = false;
  const timeout = setTimeout(() => { if (!done) onError("No se pudo conectar (tiempo agotado). Probá de nuevo o con otra red."); }, 20000);
  peer.on("open", () => {
    const dc = peer.connect(hostId, { reliable: true, serialization: "json" });
    dc.on("open", () => { done = true; clearTimeout(timeout); const c = wrapPeerConn(dc); c.open = true; onOpen(c); });
  });
  peer.on("error", (err) => { done = true; clearTimeout(timeout); onError(describeError(err)); });
  return { destroy: () => { clearTimeout(timeout); try { peer.destroy(); } catch (e) { /* nada */ } } };
}

function describeError(err) {
  switch (err && err.type) {
    case "peer-unavailable": return "La sala no existe o ya se cerró.";
    case "network": case "server-error": case "socket-error": case "socket-closed":
      return "Sin conexión con el servidor de partidas. Revisá tu internet.";
    case "browser-incompatible": return "Este navegador no soporta partidas online.";
    default: return "Error de conexión" + (err && err.type ? ` (${err.type})` : "");
  }
}

export const NET_VERSION = GAME_VERSION;
