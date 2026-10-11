// settings.js — opciones guardadas en el navegador (localStorage)
const KEY = "mkp_settings_v1";

export const DEFAULTS = {
  volumes: { music: 0.5, sfx: 0.9, announcer: 1.0 },
  touchControls: "auto",   // auto | on | off
  touchScale: 100,         // % del tamaño de los botones táctiles
  keys: null,              // null = teclas por defecto (ver input.js DEFAULT_KEYS)
  playerName: "",
};

export function loadSettings() {
  let s = {};
  try { s = JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { s = {}; }
  return { ...DEFAULTS, ...s, volumes: { ...DEFAULTS.volumes, ...(s.volumes || {}) } };
}

export function saveSettings(s) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* modo privado */ }
}
