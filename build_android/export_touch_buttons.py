"""
export_touch_buttons.py
------------------------
Genera los PNG de fábrica de los controles táctiles en
assets/ui/touch/ (512x512, con transparencia), a partir del dibujo por
código de engine/touch.py. Después se pueden editar a gusto: el juego
usa el PNG si existe (cualquier tamaño, se escala solo) y si no, el
dibujo por código.

    python tools/export_touch_buttons.py
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((64, 64))
from engine import touch  # noqa: E402

os.makedirs(touch.TOUCH_DIR, exist_ok=True)
tc = touch.TouchControls((1600, 720), (0, 0, 1600, 720))
R = 254
for name in touch.TOUCH_FACES:
    surf = tc.render_default_face(name, R)
    out = pygame.Surface((512, 512), pygame.SRCALPHA)
    out.blit(surf, surf.get_rect(center=(256, 256)))
    path = os.path.join(touch.TOUCH_DIR, f"{name}.png")
    pygame.image.save(out, path)
    print("ok", path)
