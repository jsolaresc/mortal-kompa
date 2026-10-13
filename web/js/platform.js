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
export function isStandalone() {
  try {
    return navigator.standalone === true ||
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches && !document.fullscreenElement);
  } catch (e) { return false; }
}

// ¿Mostrar el botón "INSTALAR"? Solo en el navegador de Android (baja el
// APK) o de iPhone (explica cómo agregar el ícono).
export function canOfferInstall(isTouch = false) {
  if (IS_APP || isStandalone()) return false;
  return IS_ANDROID || IS_IOS || isTouch;   // celular con navegador "modo PC": por las dudas, igual
}

// Saca el código de sala de un link de invitación (o de un código suelto)
export function roomFromText(text) {
  const t = String(text || "").trim().replace(/\s+/g, "");
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

// Última versión publicada del APK (Releases de GitHub). El archivo lleva
// la versión en el nombre: MortalKompa_v1_03_22.apk = versión 1.3.22.
const RELEASES_API = "https://api.github.com/repos/jsolaresc/mortal-kompa/releases/latest";
export async function latestApk() {
  const r = await fetch(RELEASES_API, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  const j = await r.json();
  const build = parseInt(String(j.tag_name || "").replace(/\D/g, ""), 10) || 0;
  const assets = j.assets || [];
  const a = assets.find((x) => /^MortalKompa_v[\d_]+\.apk$/i.test(x.name)) || assets.find((x) => /\.apk$/i.test(x.name));
  return { build, version: `1.3.${build}`, url: a ? a.browser_download_url : APK_URL, name: a ? a.name : "MortalKompa.apk" };
}

// número de compilación de esta app ("V.1.3.22" -> 22; en la web no hay)
export function appBuild(version) {
  const m = String(version).match(/(\d+)\.(\d+)\.(\d+)/);
  return m ? parseInt(m[3], 10) : 0;
}
