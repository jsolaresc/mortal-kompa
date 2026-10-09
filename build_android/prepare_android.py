"""
prepare_android.py
-------------------
Arma la carpeta del proyecto ANDROID a partir de la carpeta del juego de
PC (la de siempre). Uso:

    python tools/prepare_android.py  <carpeta_juego_pc>  <carpeta_salida>

Qué hace (además de copiar código y datos):
  - NO copia la intro en video (assets/video/) ni su audio: pesan mucho y
    en el celular el juego arranca directo en el menú.
  - Los escenarios en video (.mp4) se reemplazan por UNA captura fija
    (.png), sacada de la versión _1080p si existe (más nítida).
  - Todo el audio .mp3 se convierte a .ogg (Vorbis): en Android el
    soporte de mp3 de pygame/SDL_mixer no es confiable, ogg sí, y pesa
    parecido.
  - data/settings.json arranca con valores pensados para celular (720p).
  - No copia dist/, build/, tools/, instaladores de Windows, etc.

Requiere ffmpeg en el PATH.
"""

import json
import os
import shutil
import subprocess
import sys

# segundo del video que se usa como captura fija, por escenario
STAGE_SHOT_TIME = {"final destination": 3.0, "living forest": 3.0}
DEFAULT_SHOT_TIME = 2.0

SKIP_DIRS = {"dist", "build", "tools", "__pycache__", ".git", ".github", "video", "_tower_boss_cache"}
SKIP_FILES = {"intro.mp3", "mortal_kompa.iss", "mortal_kompa.spec", "build_installer.bat",
              "Mortal Kompa.bat", "requirements.txt"}
SKIP_EXTS = {".pyc", ".zip", ".exe", ".ico"}

ANDROID_SETTINGS = {
    "music_volume": 0.6,
    "stage_music_volume": 0.7,
    "sfx_volume": 1.0,
    "announcer_volume": 1.0,
    "fullscreen": True,
    "resolution": "720p",
    "touch_scale": 1.0,
}


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def convert_audio(src, dst_ogg):
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-c:a", "libvorbis", "-q:a", "4", dst_ogg])


def stage_screenshot(video_path, dst_png):
    base, ext = os.path.splitext(video_path)
    hd = f"{base}_1080p{ext}"
    src = hd if os.path.isfile(hd) else video_path
    name = os.path.basename(base).lower()
    t = STAGE_SHOT_TIME.get(name, DEFAULT_SHOT_TIME)
    run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", src, "-frames:v", "1", dst_png])


def main(src_root, out_root):
    src_root = os.path.abspath(src_root)
    out_root = os.path.abspath(out_root)
    copied = converted = shots = 0
    for dirpath, dirnames, filenames in os.walk(src_root):
        rel_dir = os.path.relpath(dirpath, src_root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        out_dir = os.path.join(out_root, rel_dir) if rel_dir != "." else out_root
        for fname in filenames:
            if fname in SKIP_FILES or os.path.splitext(fname)[1].lower() in SKIP_EXTS:
                continue
            if rel_dir == "." and fname.lower().endswith(".md"):
                continue
            src = os.path.join(dirpath, fname)
            stem, ext = os.path.splitext(fname)
            ext = ext.lower()
            os.makedirs(out_dir, exist_ok=True)
            if ext == ".mp4":
                if stem.lower().endswith("_1080p"):
                    continue
                stage_screenshot(src, os.path.join(out_dir, stem + ".png"))
                shots += 1
            elif ext == ".mp3":
                convert_audio(src, os.path.join(out_dir, stem + ".ogg"))
                converted += 1
            else:
                shutil.copy2(src, os.path.join(out_dir, fname))
                copied += 1

    # JSONs de personajes que apunten a .mp3 explícitamente -> .ogg
    chars_dir = os.path.join(out_root, "data", "characters")
    for fname in os.listdir(chars_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(chars_dir, fname)
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        data = json.loads(raw)
        sounds = data.get("sounds", {})
        changed = False
        for k, v in list(sounds.items()):
            if k.startswith("_"):
                continue
            if isinstance(v, str) and v.lower().endswith(".mp3"):
                sounds[k] = v[:-4] + ".ogg"
                changed = True
            elif isinstance(v, list):
                nv = [x[:-4] + ".ogg" if isinstance(x, str) and x.lower().endswith(".mp3") else x for x in v]
                if nv != v:
                    sounds[k] = nv
                    changed = True
        if changed:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_root, "data", "settings.json"), "w", encoding="utf-8") as f:
        json.dump(ANDROID_SETTINGS, f, ensure_ascii=False, indent=2)

    print(f"Listo: {copied} copiados, {converted} audios a .ogg, {shots} escenarios a captura fija.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
