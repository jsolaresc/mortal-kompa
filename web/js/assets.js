// =====================================================================
// assets.js — carga de JSON, imágenes y datos de personajes/escenarios
// (el navegador no puede listar carpetas: todo sale de los JSON de data/)
// =====================================================================

const imageCache = new Map();
const jsonCache = new Map();

export function url(path) {
  // rutas con espacios/tildes (ej. "Plaza de Mayo.png")
  return encodeURI(path);
}

export function loadJSON(path) {
  if (!jsonCache.has(path)) {
    jsonCache.set(path, fetch(url(path), { cache: "no-cache" }).then((r) => {
      if (!r.ok) throw new Error(`No pude cargar ${path} (${r.status})`);
      return r.json();
    }));
  }
  return jsonCache.get(path);
}

const loadedImages = new Map();

export function loadImage(path) {
  if (!path) return Promise.resolve(null);
  if (!imageCache.has(path)) {
    imageCache.set(path, new Promise((resolve) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => { loadedImages.set(path, img); resolve(img); };
      img.onerror = () => {
        console.warn(`[AVISO] no encontré la imagen '${path}'`);
        resolve(null);
      };
      img.src = url(path);
    }));
  }
  return imageCache.get(path);
}

export const loadImageSync = loadImage;

export function cachedImage(path) {
  return loadedImages.get(path) || null;
}

// ---------------------------------------------------------------------
// Roster
// ---------------------------------------------------------------------
export const DB = {
  roster: [],         // [{slug, name, data, selection, pose}]
  bySlug: {},
  stages: [],         // [{id, name, image, music, secret}]
  menuMusic: [],
  menuVoices: [],
};

export async function loadDatabase() {
  const [roster, stages, music] = await Promise.all([
    loadJSON("data/roster.json"),
    loadJSON("data/stages.json"),
    loadJSON("data/music.json").catch(() => ({ menu: [] })),
  ]);
  DB.menuMusic = (music.menu || []).filter(Boolean);
  DB.menuVoices = (music.menu_voices || []).filter(Boolean);
  DB.stages = stages.stages;
  const entries = await Promise.all(roster.characters.map(async (slug) => {
    try {
      const data = await loadJSON(`data/characters/${slug}.json`);
      const folder = data.sprite_folder || `assets/characters/${slug}`;
      const [selection, pose, pose2] = await Promise.all([
        loadImageSync(data.selection_image ? `${folder}/${data.selection_image}` : `${folder}/selection.png`),
        loadImageSync(data.pose_image ? `${folder}/${data.pose_image}` : `${folder}/pose.png`),
        // pose2: foto aparte para el lado derecho (ej. ropa con texto, que
        // espejada se leería al revés). Si no hay, se espeja la pose normal.
        data.pose2_image ? loadImageSync(`${folder}/${data.pose2_image}`) : Promise.resolve(null),
      ]);
      return { slug, name: data.name || slug, data, selection, pose, pose2, accent: data.accent || "#888888" };
    } catch (e) {
      console.warn(`[AVISO] personaje '${slug}':`, e);
      return null;
    }
  }));
  DB.roster = entries.filter(Boolean);
  for (const c of DB.roster) DB.bySlug[c.slug] = c;
  // miniaturas de escenarios (la imagen completa ya sirve)
  await Promise.all(DB.stages.map(async (s) => {
    if (/\.(mp4|webm)$/i.test(s.image)) {
      s.thumb = s.thumb_image ? await loadImageSync(s.thumb_image) : null;
    } else {
      s.thumb = await loadImageSync(s.image);
    }
  }));
}

export function normalStages() {
  return DB.stages.filter((s) => !s.secret);
}

export function secretStage() {
  return DB.stages.find((s) => s.secret) || null;
}

export function randomStage() {
  const list = normalStages();
  return list.length ? list[Math.floor(Math.random() * list.length)] : null;
}

export function stageById(id) {
  return DB.stages.find((s) => s.id === id) || null;
}

// ---------------------------------------------------------------------
// Frames de un personaje (todas sus animaciones + proyectil)
// ---------------------------------------------------------------------
const charFrameCache = new Map();

export function loadCharacterFrames(slug) {
  if (charFrameCache.has(slug)) return charFrameCache.get(slug);
  const entry = DB.bySlug[slug];
  const p = (async () => {
    const data = entry.data;
    const folder = data.sprite_folder || `assets/characters/${slug}`;
    const anims = {};
    const jobs = [];
    for (const [name, cfg] of Object.entries(data.animations || {})) {
      const n = cfg.frames || 1;
      anims[name] = new Array(n).fill(null);
      for (let i = 0; i < n; i++) {
        jobs.push(loadImageSync(`${folder}/${name}/${i}.png`).then((img) => { anims[name][i] = img; }));
      }
    }
    // proyectil: carpeta projectile/ con 0.png.. (o subcarpetas 0/,1/.. si
    // "projectile_groups" = [cant. de cuadros de cada grupo])
    let projectile = [];
    if (Array.isArray(data.projectile_groups)) {
      projectile = data.projectile_groups.map(() => []);
      data.projectile_groups.forEach((count, g) => {
        for (let i = 0; i < count; i++) {
          jobs.push(loadImageSync(`${folder}/projectile/${g}/${i}.png`).then((img) => { projectile[g][i] = img; }));
        }
      });
    } else {
      const n = data.projectile_frames || 0;
      projectile = new Array(n).fill(null);
      for (let i = 0; i < n; i++) {
        jobs.push(loadImageSync(`${folder}/projectile/${i}.png`).then((img) => { projectile[i] = img; }));
      }
    }
    await Promise.all(jobs);
    for (const k of Object.keys(anims)) anims[k] = anims[k].filter(Boolean);
    if (Array.isArray(data.projectile_groups)) projectile = projectile.map((g) => g.filter(Boolean)).filter((g) => g.length);
    else projectile = projectile.filter(Boolean);
    return { anims, projectile, folder };
  })();
  charFrameCache.set(slug, p);
  return p;
}
