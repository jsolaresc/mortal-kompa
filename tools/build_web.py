"""
build_web.py — arma los assets y datos de la versión de NAVEGADOR (web/)
a partir del mismo proyecto que el APK.

    python tools/build_web.py [--audio-src CARPETA_DEL_JUEGO_DE_PC]

Qué hace:
  * Personajes: carga cada luchador con el MOTOR PYTHON real (mismas
    correcciones automáticas de zoom, techo de altura, K.O., etc.) y
    guarda los cuadros YA PROCESADOS. Así el motor JS los dibuja tal cual,
    sin tener que replicar esas mediciones de píxeles. Se guardan en la
    resolución nativa del sprite (nunca agrandados) y el JSON lleva la
    escala para llevarlos al lienzo base 960x540.
  * Escenarios: imagen fija (.png del APK) + música del mismo nombre.
  * Audio: el navegador del iPhone (Safari) no reproduce .ogg, así que
    todo se pasa a .mp3/.wav. Con --audio-src se toman los ORIGINALES de
    la versión de PC (mp3 sin recomprimir); si no, se convierten los .ogg
    del APK.
  * Interfaz: imágenes de assets/ui (fondos a .jpg, más livianos).

Requiere: pygame, Pillow, ffmpeg y (opcional) pngquant.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

AUDIO_EXTS = (".mp3", ".ogg", ".wav")


def log(*a):
    print("[web]", *a)


def ensure_dir(p):
    os.makedirs(p, exist_ok=True)
    return p


def pngquant(paths):
    if not shutil.which("pngquant") or not paths:
        return
    for i in range(0, len(paths), 200):
        subprocess.run(["pngquant", "--quality=85-98", "--speed", "1", "--strip", "--skip-if-larger",
                        "-f", "--ext", ".png", *paths[i:i + 200]], stderr=subprocess.DEVNULL)


def copy_image(src, dst):
    ensure_dir(os.path.dirname(dst))
    shutil.copyfile(src, dst)
    return dst


def to_jpg(src, dst, quality=86):
    ensure_dir(os.path.dirname(dst))
    Image.open(src).convert("RGB").save(dst, "JPEG", quality=quality, optimize=True, progressive=True)


def audio_out(src, dst_noext):
    """Copia/convierte un audio a algo que reproduzca cualquier navegador
    (mp3 o wav). Devuelve la ruta final."""
    ext = os.path.splitext(src)[1].lower()
    ensure_dir(os.path.dirname(dst_noext))
    if ext in (".mp3", ".wav"):
        dst = dst_noext + ext
        shutil.copyfile(src, dst)
        return dst
    dst = dst_noext + ".mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map_metadata", "-1", "-vn",
                    "-c:a", "libmp3lame", "-q:a", "2", dst], check=True)
    return dst


def find_audio(base_noext, roots):
    """Busca base.(mp3|wav|ogg) primero en la carpeta de PC (originales)."""
    for r in roots:
        for ext in (".mp3", ".wav", ".ogg"):
            p = os.path.join(r, base_noext + ext)
            if os.path.isfile(p):
                return p
    return None


def rel(path):
    return os.path.relpath(path, WEB).replace(os.sep, "/")


# ---------------------------------------------------------------------
# Personajes
# ---------------------------------------------------------------------
def build_characters(audio_roots):
    from engine import constants as C
    C.set_resolution("1080p", 16 / 9)
    pygame.init()
    pygame.display.set_mode((16, 16))
    from engine.character import Character

    class _NoSound:
        def __getattr__(self, name):
            return lambda *a, **k: None

    roster = []
    out_root = os.path.join(WEB, "assets", "characters")
    new_pngs = []
    for jp in sorted(glob.glob("data/characters/*.json")):
        if os.path.basename(jp) == "character_template.json":
            continue
        data = json.load(open(jp, encoding="utf-8"))
        if data.get("hidden"):
            continue
        slug = os.path.splitext(os.path.basename(jp))[0]
        ch = Character(jp, _NoSound())
        # escala de guardado: nunca agrandar (factor total <= 1 respecto
        # del PNG original); el JSON web lleva la escala para llegar a base
        total_1080 = data.get("scale", 2) * C.CHARACTER_SCALE_MULT  # px 1080p por px original
        k = min(1.0, 1.0 / total_1080) if total_1080 > 0 else 1.0  # px guardado por px 1080p
        draw_scale = 1.0 / (2.0 * k)  # px base por px guardado
        folder = os.path.join(out_root, slug)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        anims_out = {}
        for name, cfg in (data.get("animations") or {}).items():
            anim = ch.animations.get(name)
            frames = anim.frames if anim else []
            if not frames or not os.path.isdir(os.path.join(data["sprite_folder"], name)):
                continue
            d = ensure_dir(os.path.join(folder, name))
            for i, surf in enumerate(frames):
                if k != 1.0:
                    w, h = surf.get_size()
                    surf = pygame.transform.smoothscale(surf, (max(1, round(w * k)), max(1, round(h * k))))
                p = os.path.join(d, f"{i}.png")
                pygame.image.save(surf, p)
                new_pngs.append(p)
            c2 = {kk: vv for kk, vv in cfg.items() if kk != "extra_scale"}
            c2["frames"] = len(frames)
            anims_out[name] = c2

        src_folder = data["sprite_folder"]
        for img in ("selection.png", "pose.png", "pose2.png", "thumbnail.png"):
            s = os.path.join(src_folder, img)
            if os.path.isfile(s):
                copy_image(s, os.path.join(folder, img))

        out = {
            "name": data.get("name", slug),
            "sprite_folder": f"assets/characters/{slug}",
            "scale": round(draw_scale / C.CHARACTER_SCALE_MULT * 2, 6),  # JS: scale*0.9 = px base por px guardado
            "health": data.get("health", 100),
            "walk_speed": data.get("walk_speed", 4),
            "announcer": f"assets/sounds/announcer/select/{slug}.wav",
            "animations": anims_out,
        }
        for k2 in ("jump_power",):
            if k2 in data:
                out[k2] = data[k2]
        if os.path.isfile(os.path.join(src_folder, "pose2.png")):
            out["pose2_image"] = "pose2.png"

        # proyectil: subcarpetas = grupos; archivos sueltos = un objeto que gira
        pdir = os.path.join(src_folder, "projectile")
        pout = os.path.join(folder, "projectile")
        subs = sorted([s for s in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, s))], key=lambda s: (not s.isdigit(), int(s) if s.isdigit() else s)) if os.path.isdir(pdir) else []
        if subs:
            groups = []
            for g, sname in enumerate(subs):
                files = sorted([f for f in os.listdir(os.path.join(pdir, sname)) if f.lower().endswith(".png")], key=lambda f: int(os.path.splitext(f)[0]) if os.path.splitext(f)[0].isdigit() else 999)
                for i, f in enumerate(files):
                    copy_image(os.path.join(pdir, sname, f), os.path.join(pout, str(g), f"{i}.png"))
                groups.append(len(files))
            out["projectile_groups"] = groups
        else:
            files = sorted([f for f in os.listdir(pdir) if f.lower().endswith(".png")], key=lambda f: int(os.path.splitext(f)[0]) if os.path.splitext(f)[0].isdigit() else 999) if os.path.isdir(pdir) else []
            if not files and data.get("projectile_image") and os.path.isfile(os.path.join(src_folder, data["projectile_image"])):
                copy_image(os.path.join(src_folder, data["projectile_image"]), os.path.join(pout, "0.png"))
                out["projectile_frames"] = 1
            else:
                for i, f in enumerate(files):
                    copy_image(os.path.join(pdir, f), os.path.join(pout, f"{i}.png"))
                out["projectile_frames"] = len(files)

        # sonidos: assets/characters/<slug>/sounds/<clave>/*
        sounds = {}
        sdir_rel = os.path.join("assets", "characters", slug, "sounds")
        for key_dir in sorted(glob.glob(os.path.join(sdir_rel, "*"))):
            key = os.path.basename(key_dir)
            items = []
            # preferir los originales de PC (mismo nombre de archivo, sin recomprimir)
            names = sorted({os.path.splitext(f)[0] for f in os.listdir(key_dir) if f.lower().endswith(AUDIO_EXTS)})
            for stem in names:
                src = find_audio(os.path.join(sdir_rel, key, stem), audio_roots)
                if not src:
                    continue
                dst = audio_out(src, os.path.join(folder, "sounds", key, stem))
                items.append(os.path.relpath(dst, folder).replace(os.sep, "/"))
            if items:
                sounds[key] = items
        out["sounds"] = sounds

        json.dump(out, open(os.path.join(WEB, "data", "characters", f"{slug}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        roster.append(slug)
        log(f"{slug}: {sum(a['frames'] for a in anims_out.values())} cuadros, escala guardado {k:.2f}, sonidos {list(sounds)}")
    pngquant(new_pngs)
    json.dump({"characters": roster}, open(os.path.join(WEB, "data", "roster.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------
# Escenarios, música, sonidos, interfaz
# ---------------------------------------------------------------------
SECRET = {"final destination"}


def build_stages(audio_roots):
    out = []
    sdir = os.path.join(WEB, "assets", "stages")
    if os.path.isdir(sdir):
        shutil.rmtree(sdir)
    ensure_dir(sdir)
    for img in sorted(glob.glob("assets/stages/*.png")):
        stem = os.path.splitext(os.path.basename(img))[0]
        jpg = os.path.join(sdir, stem + ".jpg")
        to_jpg(img, jpg, 88)
        music = find_audio(os.path.join("assets", "stages", stem), audio_roots)
        mpath = audio_out(music, os.path.join(sdir, stem)) if music else None
        entry = {
            "id": stem.lower().replace(" ", "_"), "name": stem, "image": rel(jpg),
            "music": rel(mpath) if mpath else None, **({"secret": True} if stem.lower() in SECRET else {}),
        }
        # escenarios que en PC son video: en la web también (son livianos);
        # la imagen fija queda como miniatura del selector
        for r in audio_roots:
            mp4 = os.path.join(r, "assets", "stages", stem + "_1080p.mp4")
            if not os.path.isfile(mp4):
                mp4 = os.path.join(r, "assets", "stages", stem + ".mp4")
            if os.path.isfile(mp4):
                dst = os.path.join(sdir, stem + ".mp4")
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-an", "-vf", "scale=-2:720", "-c:v", "libx264",
                                "-profile:v", "main", "-pix_fmt", "yuv420p", "-crf", "26", "-preset", "slow",
                                "-movflags", "+faststart", dst], check=True)
                entry["thumb_image"] = entry["image"]
                entry["image"] = rel(dst)
                break
        out.append(entry)
    json.dump({"stages": out}, open(os.path.join(WEB, "data", "stages.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("escenarios:", [s["name"] for s in out])


def build_sounds(audio_roots):
    base = os.path.join(WEB, "assets", "sounds")
    if os.path.isdir(base):
        shutil.rmtree(base)
    menu = []
    for sub in ("music", "menu_voices", "sfx", "sfx/hit_impact", "sfx/critical_hit", "announcer", "announcer/select"):
        names = set()
        for r in audio_roots:
            d = os.path.join(r, "assets", "sounds", sub)
            if os.path.isdir(d):
                names |= {os.path.splitext(f)[0] for f in os.listdir(d) if f.lower().endswith(AUDIO_EXTS)}
        for stem in sorted(names):
            src = find_audio(os.path.join("assets", "sounds", sub, stem), audio_roots)
            dst = audio_out(src, os.path.join(base, sub, stem))
            if sub == "music":
                menu.append(rel(dst))
            if sub == "menu_voices":
                menu_voices.append(rel(dst))
    json.dump({"menu": menu, "menu_voices": menu_voices}, open(os.path.join(WEB, "data", "music.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"música {len(menu)}, vocecitas {len(menu_voices)}")


menu_voices = []

UI_JPG = {"title_background.png": "title_background.jpg", "character_selection_background.png": "character_selection_background.jpg",
          "tower_background.png": "tower_background.jpg"}


def build_ui():
    src = os.path.join("assets", "ui")
    dst = os.path.join(WEB, "assets", "ui")
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    for root, _, files in os.walk(src):
        for f in files:
            if not f.lower().endswith(".png"):
                continue
            s = os.path.join(root, f)
            relp = os.path.relpath(s, src)
            if relp in UI_JPG:
                to_jpg(s, os.path.join(dst, UI_JPG[relp]), 85)
            else:
                copy_image(s, os.path.join(dst, relp))
    # ícono de la app (con fondo, como el del APK)
    icon = os.path.join("build_android", "icon_legacy.png")
    if os.path.isfile(icon):
        im = Image.open(icon).convert("RGB")
        for n in (192, 512):
            im.resize((n, n), Image.LANCZOS).save(os.path.join(dst, f"app_icon_{n}.png"), optimize=True)
    fonts = os.path.join(WEB, "assets", "fonts")
    ensure_dir(fonts)
    for f in glob.glob(os.path.join("assets", "fonts", "*")):
        shutil.copyfile(f, os.path.join(fonts, os.path.basename(f)))
    log("interfaz lista")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-src", help="carpeta del juego de PC (audios originales en mp3)")
    ap.add_argument("--only", choices=["characters", "stages", "sounds", "ui"], action="append")
    a = ap.parse_args()
    roots = ([os.path.abspath(a.audio_src)] if a.audio_src else []) + [ROOT]
    ensure_dir(os.path.join(WEB, "data", "characters"))
    only = set(a.only or ["characters", "stages", "sounds", "ui"])
    if "ui" in only:
        build_ui()
    if "sounds" in only:
        build_sounds(roots)
    if "stages" in only:
        build_stages(roots)
    if "characters" in only:
        build_characters(roots)


if __name__ == "__main__":
    main()
