// =====================================================================
// config.js — Constantes globales de Mortal Kompa (versión navegador)
// ---------------------------------------------------------------------
// Toda la física, hitboxes y HUD están calibrados sobre el lienzo base
// de 960x540 (mismos valores que Mortal Kompa). El navegador escala ese
// lienzo a la pantalla real, así que acá NO hay RES_SCALE: todo se
// expresa directamente en píxeles base.
// =====================================================================

// Subila en cada entrega: V.0.1, V.0.2 ... hasta V.1.0
export const GAME_VERSION = "V.1.3";
export const GAME_TITLE = "Mortal Kompa";

export const BASE_W = 960;          // ancho de la "ventana de pelea" (16:9)
export const BASE_H = 540;
export const FPS = 60;
export const DT = 1 / FPS;

export const GROUND_H = 45;
export const GROUND_Y = BASE_H - GROUND_H;   // altura del piso (donde paran los pies)
export const GRAVITY = 1.4;                  // incremento fijo por cuadro (saltos / K.O.)
export const PROJECTILE_GRAVITY = 900;       // px/seg² para trayectoria "bounce"
export const CHARACTER_SCALE_MULT = 0.9;     // tamaño global de todos los personajes
export const JUMP_POWER_DEFAULT = -25;
export const KO_MAX_WIDTH_FRAC = 0.4;

export const ROUND_TIME = 60;        // segundos por round
export const ROUNDS_TO_WIN = 2;      // al mejor de 3

export const SPECIAL_HITS_REQUIRED = 5;   // golpes RECIBIDOS para habilitar el especial
export const SPECIAL_DAMAGE_MULT = 1.0;
export const CRITICAL_HIT_CHANCE = 0.02;  // solo puño/patada
export const CRITICAL_HIT_MULT = 2.0;    // crítico = doble daño
// daño que recibe el que BLOQUEA, según el ataque
export const BLOCK_DAMAGE = { punch: 0.5, kick: 0.5, special: 2, ranged: 0.1, ranged_crouch: 0.1 };
export const SOUND_RANDOM_CHANCE = 0.10;
export const VOICE_LINE_CHANCE = 0.05;

// Pausas de anuncios (segundos)
export const ROUND_INTRO_PAUSE = 0.35;
export const WIN_AUDIO_GAP = 0.35;
export const ROUND_INTRO_TRAILING_PAD = 0.3;

// Colores UI
export const COLORS = {
  white: "#ffffff",
  black: "#000000",
  red: "#dc2828",
  green: "#28c85a",
  yellow: "#f0c828",
  gray: "#3c3c3c",
  dark: "#141418",
  panel: "#1e1e26",
  celeste: "#6cb4ee",
};

// Estados de personaje (nombre de carpeta / animación)
export const S = {
  IDLE: "idle", WALK: "walk", JUMP: "jump", PUNCH: "punch", KICK: "kick",
  SPECIAL: "special", RANGED: "ranged", RANGED_CROUCH: "ranged_crouch",
  CROUCH: "crouch", BLOCK: "block", BLOCK_CROUCH: "block_crouch", KO: "ko", WIN: "win",
};
export const ATTACK_STATES = new Set([S.PUNCH, S.KICK, S.SPECIAL, S.RANGED, S.RANGED_CROUCH]);

export const ACTIONS = ["left", "right", "up", "down", "punch", "kick", "special", "block", "ranged", "start", "confirm", "cancel"];

export const DIFFICULTY_LABELS = ["Muy fácil", "Fácil", "Fácil", "Normal-", "Normal", "Normal+", "Difícil", "Difícil", "Muy difícil", "Imposible"];

// Online: servidores ICE (STUN/TURN). Con STUN alcanza para la mayoría
// de las conexiones; si a alguien no le conecta nunca (pasa con algunas
// redes de datos móviles), sumá acá un servidor TURN propio.
export const ICE_SERVERS = [
  { urls: "stun:stun.l.google.com:19302" },
  { urls: "stun:stun1.l.google.com:19302" },
];
