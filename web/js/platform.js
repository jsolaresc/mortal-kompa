// =====================================================================
// platform.js — ¿dónde está corriendo el juego? (navegador o app Android)
// ---------------------------------------------------------------------
// La app de Android (APK) es ESTE MISMO juego dentro de un WebView: los
// archivos van adentro del APK y se sirven desde
// https://appassets.androidplatform.net/. La app expone un puente
// "MKAndroid" (compartir, copiar, salir).
// =====================================================================

export const BRIDGE = typeof window !== "undefined" ? window.MKAndroid || null : null;
export const IS_APP = !!BRIDGE;

// Dirección pública del juego (para los links de invitación: desde la app
// tienen que apuntar a la página, no a los archivos internos del APK)
export const PUBLIC_URL = "https://jsolaresc.github.io/mortal-kompa/web/";

// APK más reciente (lo publica el workflow en Releases con este nombre fijo)
export const APK_URL = "https://github.com/jsolaresc/mortal-kompa/releases/latest/download/MortalKompa.apk";

const UA = typeof navigator !== "undefined" ? navigator.userAgent : "";
export const IS_ANDROID = /Android/i.test(UA);
export const IS_IOS = /iPhone|iPad|iPod/i.test(UA) || (/Macintosh/.test(UA) && typeof navigator !== "undefined" && navigator.maxTouchPoints > 1);
export const IS_STANDALONE = typeof window !== "undefined" &&
  ((window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
   (window.matchMedia && window.matchMedia("(display-mode: fullscreen)").matches) || navigator.standalone === true);

// ¿Mostrar el botón "INSTALAR"? Solo en el navegador de Android (baja el
// APK) o de iPhone (explica cómo agregar el ícono).
export function canOfferInstall() {
  if (IS_APP || IS_STANDALONE) return false;
  return IS_ANDROID || IS_IOS;
}

// Saca el código de sala de un link de invitación (o de un código suelto)
export function roomFromText(text) {
  const t = String(text || "").trim();
  if (!t) return null;
  try {
    const u = new URL(t);
    const s = u.searchParams.get("sala");
    if (s) return s.trim().toLowerCase();
  } catch (e) { /* no es un link */ }
  const m = t.match(/sala=([a-z0-9]+)/i);
  if (m) return m[1].toLowerCase();
  if (/^[a-z0-9]{4,12}$/i.test(t)) return t.toLowerCase();
  return null;
}
