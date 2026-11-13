"""AURA X1 — full 73 s concept film. 1080x1920 @ 30fps.

python scripts/long_render.py                  # render build/aura_x1_full.mp4
python scripts/long_render.py --preview 5,20   # PNG stills
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_core import *  # noqa: F401,F403
import render_core as rc
import render as short  # reuse sprites/builders
import textrender as tr
import audio
import imageio_ffmpeg

W, H, FPS = 1080, 1920, 30

# ---------------------------------------------------------------- timeline --
VO_PLAN = [
    ("np_s1.mp3", 0.60),
    ("np_s2.mp3", 3.35),
    ("np_design.mp3", 9.60),
    ("np_s3.mp3", 14.60),
    ("np_s4.mp3", 20.60),
    ("np_night.mp3", 26.20),
    ("np_s5.mp3", 29.60),
    ("np_durable.mp3", 35.40),
    ("np_battery.mp3", 40.90),
    ("np_chip.mp3", 46.60),
    ("np_update.mp3", 52.10),
    ("np_colors.mp3", 56.90),
    ("np_s6.mp3", 61.00),
    ("np_preorder.mp3", 64.40),
    ("np_s7.mp3", 69.20),
]

SCENES = [0.0, 3.2, 8.6, 14.2, 20.0, 25.6, 29.2, 34.8, 39.8, 45.4,
          50.8, 55.6, 60.0, 63.6, 68.4]
DURATION = 73.2
NFRAMES = int(DURATION * FPS)

S_OPEN, S_HERO, S_DESIGN, S_DISPLAY, S_CAM, S_NIGHT, S_METAL, S_ROBUST = range(8)
S_POWER, S_CHIP, S_SOFT, S_COLORS, S_DATE, S_PRE, S_LOCK = range(8, 15)

TINT = {
    "intro": ((6, 8, 12), (2, 3, 5)),
    "teal": ((7, 12, 17), (3, 4, 6)),
    "mint": ((5, 15, 18), (2, 4, 7)),
    "amber": ((16, 11, 8), (4, 3, 4)),
    "steel": ((12, 12, 13), (3, 3, 4)),
    "blue": ((6, 10, 16), (2, 3, 5)),
    "violet": ((11, 9, 18), (3, 3, 6)),
    "ink": ((5, 9, 13), (1, 2, 3)),
}
SCENE_TINT = ["intro", "teal", "amber", "mint", "amber", "blue", "steel", "blue",
              "mint", "steel", "violet", "teal", "blue", "amber", "ink"]

_bg = {}


def bg_for(name, seed):
    if name not in _bg:
        _bg[name] = np.asarray(rc.background(*TINT[name], seed=seed), dtype=np.float32)
    return _bg[name]


def scene_index(t):
    if t >= SCENES[-1]:
        return len(SCENES) - 1
    for i in range(len(SCENES) - 1):
        if SCENES[i] <= t < SCENES[i + 1]:
            return i
    return len(SCENES) - 2


def base_frame(t):
    i = scene_index(t)
    cur = bg_for(SCENE_TINT[i], i)
    fade = 0.55
    if i > 0 and t - SCENES[i] < fade:
        w = smooth((t - SCENES[i]) / fade)
        arr = bg_for(SCENE_TINT[i - 1], i - 1) * (1 - w) + cur * w
    elif i < len(SCENES) - 1 and SCENES[i + 1] - t < fade:
        w = smooth((SCENES[i + 1] - t) / fade)
        arr = bg_for(SCENE_TINT[i + 1], i + 1) * (1 - w) + cur * w
    else:
        arr = cur
    return arr, i


# ----------------------------------------------------------------- helpers --
IMG = lambda n: os.path.join(ASSETS, "img", n)  # noqa: E731
_spr = {}


def sprite(name, height):
    key = (name, height)
    if key not in _spr:
        _spr[key] = Sprite(load_product(IMG(name), height))
    return _spr[key]


def photo(name):
    if name not in _spr:
        _spr[name] = Image.open(IMG(name)).convert("RGB")
    return _spr[name]


def label(text, px=22, color=None, tracking=0.30, lang="en", font=None):
    """Small tracked-out all-caps support type."""
    color = color or DIM
    font = font or EN_SB
    return text_img(text, font, px, color, lang=lang, tracking=tracking)


def floating(t, amp=10, speed=0.45, phase=0.0):
    return amp * math.sin(2 * math.pi * speed * t + phase)


def flash(glow, t, at, strength=1.0, dur=0.5):
    if at <= t <= at + dur:
        k = 1 - (t - at) / dur
        rc.add_glow_layer(glow, rc.radial_glow(700, (255, 255, 255), 1.6), (W / 2, H / 2),
                          strength * (k ** 3) * 0.45)


def hero_copy(canvas, glow, t, a, b, title, sub, kicker=None, dy=0.0):
    """Lower-third headline + Nepali subline with staggered fade-ins."""
    op = seg(t, a, b, 0.6, 0.5)
    y = H * 0.72 + dy
    im = text_img(title, EN_XB, 96, INK, lang="en", tracking=0.04)
    blit(canvas, im, (W / 2, y), op, center_x=True)
    if sub:
        s = mixed_mask(sub, NP_BOLD, EN_XB, 44, MINT) if sub.startswith("~") is False else None
        blit(canvas, s, (W / 2, y + im.height + 14), seg(t, a + 0.35, b, 0.6, 0.5), center_x=True)
    if kicker:
        k = label(kicker, 18, (140, 148, 160), 0.42)
        blit(canvas, k, (W / 2, y - 56), seg(t, a + 0.5, b, 0.7, 0.5) * 0.9, center_x=True)


def number_block(canvas, glow, t, a, b, big, unit, npl, eng, unit_color=MINT):
    """Left-aligned stat block used across the spec scenes."""
    op = seg(t, a, b, 0.6, 0.6)
    num = text_img(big, EN_XB, 190, INK, lang="en")
    blit(canvas, num, (74, H * 0.70), op)
    if unit:
        u = text_img(unit, EN_XB, 76, unit_color, lang="en", tracking=0.04)
        blit(canvas, u, (74 + num.width + 16, H * 0.70 + num.height - u.height - 14),
             seg(t, a + 0.2, b, 0.6, 0.6))
    if npl:
        n1 = mixed_mask(npl, NP_BOLD, EN_XB, 40, (214, 220, 228))
        blit(canvas, n1, (78, H * 0.70 - n1.height - 22), seg(t, a + 0.25, b, 0.6, 0.6))
    if eng:
        e1 = label(eng, 18, (150, 158, 170), 0.42)
        blit(canvas, e1, (80, H * 0.70 + num.height + 10), seg(t, a + 0.4, b, 0.6, 0.6) * 0.95)


def full_bleed(canvas, t, tl, name, dur, zoom=(1.18, 1.02), pan=(0.05, 0.0), dim=0.25):
    """Ken-burns a photo to fill the frame, darkened for typography."""
    src = photo(name)
    cover = max(W / src.width, H / src.height)
    src = src.resize((int(src.width * cover) + 2, int(src.height * cover) + 2), Image.LANCZOS)
    z = lerp(zoom[0], zoom[1], smooth(tl / dur))
    cw, ch = int(W / z), int(H / z)
    cx = int(clamp(W / 2 + pan[0] * W * (tl / dur - 0.5), cw // 2, src.width - cw // 2))
    cy = int(clamp(H / 2 + pan[1] * H * (tl / dur - 0.5), ch // 2, src.height - ch // 2))
    crop = src.crop((cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2)).resize((W, H), Image.BICUBIC)
    crop = Image.blend(crop, Image.new("RGB", (W, H), (6, 7, 9)), dim)
    canvas.paste(crop, (0, 0))


# ------------------------------------------------------------------ scenes --
def s_open(canvas, glow, tl, t):
    rc.add_glow_layer(glow, rc.radial_glow(360, (40, 130, 150), 2.0), (W / 2, H * 0.44),
                      0.30 * seg(t, 0.1, 3.2, 0.8, 0.4))
    light_streak(canvas, glow, W / 2, H * 0.44, 560 * ease_out(t / 1.6), 2, MINT,
                 0.8 * seg(t, 0.2, 3.2, 0.9, 0.5))
    op = seg(t, 0.35, 3.15, 0.55, 0.45)
    blit(canvas, label("A NEW ERA OF MOBILE", 20, DIM, 0.44), (W / 2, H * 0.40), op * 0.9, center_x=True)
    big = text_img("केही नयाँ", NP_BOLD, 92, INK, max_w=860)
    blit(canvas, big, (W / 2, H * 0.455), op, center_x=True)
    big2 = text_img("आउँदैछ।", NP_BOLD, 92, MINT, max_w=860)
    blit(canvas, big2, (W / 2, H * 0.455 + big.height + 6), seg(t, 0.75, 3.15, 0.55, 0.45), center_x=True)
    blit(canvas, label("SOMETHING IS COMING", 18, (128, 136, 148), 0.52),
         (W / 2, H * 0.455 + big.height + big2.height + 54), seg(t, 1.25, 3.1, 0.6, 0.5) * 0.85,
         center_x=True)


def s_hero(canvas, glow, tl, t):
    sp = sprite("hero_front.png", 1090)
    center = (W / 2, H * 0.45 + floating(t, 10))
    rc.bottom_scrim(canvas, 0.45, 0.62)
    rc.add_glow_layer(glow, rc.radial_glow(430, (30, 120, 140), 2.2), center, 0.50)
    sp.draw(canvas, center, lerp(-10, -3, ease_out(tl / 5.4, 2)), lerp(0.95, 1.05, smooth(tl / 5.4)),
            seg(t, 3.2, 8.6, 0.5, 0.5))
    short.sweep_band(glow, tl, 1.0, 2.2, strength=0.085, width=300, angle=10)

    op = seg(t, 3.8, 8.3, 0.7, 0.6)
    name = text_img("AURA X1", EN_XB, 104, INK, lang="en", tracking=0.06)
    blit(canvas, name, (W / 2, H * 0.74), op, center_x=True)
    np_name = text_img("औरा एक्स वान", NP_BOLD, 46, MINT, max_w=760)
    blit(canvas, np_name, (W / 2, H * 0.74 + name.height + 12), seg(t, 4.2, 8.3, 0.7, 0.6), center_x=True)
    blit(canvas, label("FLAGSHIP  •  2026", 19, (136, 144, 156), 0.46),
         (W / 2, H * 0.74 + name.height + np_name.height + 44), seg(t, 4.6, 8.3, 0.7, 0.6) * 0.9,
         center_x=True)


def s_design(canvas, glow, tl, t):
    src = photo("in_hand.png")
    full_bleed(canvas, t, tl, "in_hand.png", 5.6, zoom=(1.10, 1.0), pan=(0.0, 0.04), dim=0.18)
    rc.bottom_scrim(canvas, 0.78, 0.44)
    rc.add_glow_layer(glow, rc.radial_glow(420, (90, 40, 120), 2.4), (W * 0.42, H * 0.46), 0.22)
    op = seg(t, 9.0, 14.0, 0.7, 0.6)
    big = mixed_mask("हरेक विवरण", NP_BOLD, EN_XB, 74, INK)
    blit(canvas, big, (W / 2, H * 0.68), op, center_x=True)
    big2 = mixed_mask("हातले बनाए जस्तै।", NP_REG, EN_RG, 52, MINT)
    blit(canvas, big2, (W / 2, H * 0.68 + big.height + 12), seg(t, 9.7, 14.0, 0.7, 0.6), center_x=True)
    blit(canvas, label("CRAFTED  •  TITANIUM FRAME", 18, (140, 148, 160), 0.42),
         (W / 2, H * 0.68 - 54), seg(t, 9.4, 14.0, 0.8, 0.6) * 0.9, center_x=True)


def s_display(canvas, glow, tl, t):
    sp = sprite("hero_front.png", 1090)
    center = (W / 2 + 40, H * 0.45 + floating(t, 8, 0.5))
    rc.bottom_scrim(canvas, 0.55, 0.55)
    rc.add_glow_layer(glow, rc.radial_glow(460, (26, 130, 120), 2.0), center, 0.42)
    sp.draw(canvas, center, lerp(-6, 4, smooth(tl / 5.6)), lerp(0.92, 1.0, smooth(tl / 5.6)),
            seg(t, 14.2, 20.0, 0.45, 0.5) * 0.96)
    op = seg(t, 14.6, 19.9, 0.6, 0.6)
    num = text_img('6.8"', EN_XB, 210, INK, lang="en", tracking=-0.02)
    blit(canvas, num, (74, H * 0.685 - num.height * 0.5), op)
    blit(canvas, label("INCH  •  EDGE-TO-EDGE", 19, (134, 142, 154), 0.44),
         (80, H * 0.685 + num.height * 0.5 + 6), op * 0.9)
    np1 = text_img("छ दशमलव आठ इन्चको", NP_REG, 40, (206, 212, 220), max_w=560)
    blit(canvas, np1, (78, H * 0.685 - num.height * 0.5 - 108), seg(t, 15.2, 19.9, 0.6, 0.6))
    np2 = text_img("डिस्प्ले", NP_BOLD, 40, MINT, max_w=560)
    blit(canvas, np2, (78, H * 0.685 - num.height * 0.5 - 108 + np1.height + 2), seg(t, 15.2, 19.9, 0.6, 0.6))
    hz = text_img("144Hz", EN_XB, 74, AMBER, lang="en")
    blit(canvas, hz, (80, H * 0.80), seg(t, 16.0, 19.9, 0.6, 0.6))
    blit(canvas, label("PRO MOTION DISPLAY", 17, (150, 142, 130), 0.40),
         (84, H * 0.80 + 84), seg(t, 16.2, 19.9, 0.6, 0.6) * 0.9)


def s_camera(canvas, glow, tl, t):
    sp = sprite("hero_back.png", 1090)
    center = (W / 2 - 30, H * 0.42 + floating(t, 9, 0.42, 1.0))
    rc.bottom_scrim(canvas, 0.55, 0.55)
    rc.add_glow_layer(glow, rc.radial_glow(430, (150, 96, 40), 2.2), center, 0.42)
    sp.draw(canvas, center, lerp(-13, 5, smooth(tl / 5.6)), lerp(0.95, 1.02, smooth(tl / 5.6)),
            seg(t, 20.0, 25.6, 0.45, 0.5))
    op = seg(t, 20.4, 25.5, 0.6, 0.6)
    mp = text_img("200", EN_XB, 240, INK, lang="en")
    blit(canvas, mp, (72, H * 0.70), op)
    mpl = text_img("MP", EN_XB, 92, AMBER, lang="en")
    blit(canvas, mpl, (72 + mp.width + 14, H * 0.70 + mp.height - mpl.height - 10), seg(t, 20.7, 25.5, 0.6, 0.6))
    np_t = text_img("दुई सय मेगापिक्सेलको", NP_REG, 40, (208, 214, 222), max_w=640)
    blit(canvas, np_t, (76, H * 0.70 - 96), seg(t, 21.0, 25.5, 0.6, 0.6))
    np_t2 = text_img("क्यामेरा। रात पनि दिन जस्तै।", NP_BOLD, 40, MINT, max_w=700)
    blit(canvas, np_t2, (76, H * 0.70 - 96 + np_t.height + 4), seg(t, 21.2, 25.5, 0.6, 0.6))
    for k, (dx, dy, ph) in enumerate([(-52, -20, 0.0), (10, 26, 1.2), (-30, 58, 2.1)]):
        a = seg(t, 21.4 + k * 0.25, 25.5, 0.5, 0.5)
        rc.add_glow_layer(glow, rc.radial_glow(90, (255, 214, 170), 2.4),
                          (center[0] + dx, center[1] - 60 + dy), a * (0.45 + 0.12 * math.sin(t * 3 + ph)))


def s_night(canvas, glow, tl, t):
    full_bleed(canvas, t, tl, "night_shot.png", 3.6, zoom=(1.22, 1.04), pan=(0.0, -0.06), dim=0.30)
    rc.bottom_scrim(canvas, 0.85, 0.40)
    rc.add_glow_layer(glow, rc.radial_glow(500, (20, 90, 130), 2.2), (W / 2, H * 0.42),
                      0.20 * seg(t, 25.6, 29.2, 0.5, 0.5))
    op = seg(t, 26.0, 29.1, 0.6, 0.5)
    a = mixed_mask("आँखाले देख्न नसक्ने", NP_REG, EN_RG, 46, (228, 234, 240))
    blit(canvas, a, (W / 2, H * 0.735), op, center_x=True)
    b = mixed_mask("रातमा पनि।", NP_BOLD, EN_XB, 78, MINT)
    blit(canvas, b, (W / 2, H * 0.735 + a.height + 14), seg(t, 26.5, 29.1, 0.6, 0.5), center_x=True)
    blit(canvas, label("NIGHT MODE  •  NO TRIPOD", 18, (156, 164, 176), 0.42),
         (W / 2, H * 0.735 - 46), seg(t, 26.2, 29.1, 0.7, 0.5) * 0.9, center_x=True)


def s_metal(canvas, glow, tl, t):
    src = photo("macro_edge.png")
    full = src.resize((W, int(src.height * W / src.width)), Image.LANCZOS)
    zoom = lerp(1.32, 1.04, smooth(tl / 5.4))
    cover = max(W / full.width, H / full.height)
    full = full.resize((int(full.width * cover) + 2, int(full.height * cover) + 2), Image.LANCZOS)
    cw, ch = int(W / zoom), int(H / zoom)
    cx = int(clamp(W / 2 + 55 * math.sin(tl * 0.35), cw // 2, full.width - cw // 2))
    cy = int(clamp(H / 2 + (tl / 5.4 - 0.5) * 110, ch // 2, full.height - ch // 2))
    crop = full.crop((cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2)).resize((W, H), Image.BICUBIC)
    crop = Image.blend(crop, Image.new("RGB", (W, H), (10, 11, 12)), 0.34)
    canvas.paste(crop, (0, 0))
    rc.bottom_scrim(canvas, 0.62, 0.50)
    rc.add_glow_layer(glow, rc.radial_glow(500, (60, 120, 140), 2.4), (W / 2, H * 0.40),
                      0.22 * seg(t, 29.2, 34.8, 0.5, 0.5))
    op = seg(t, 29.6, 34.7, 0.7, 0.7)
    mm = text_img("6.9", EN_XB, 210, INK, lang="en")
    blit(canvas, mm, (76, H * 0.63), op)
    mml = text_img("MM", EN_XB, 80, MINT, lang="en", tracking=0.05)
    blit(canvas, mml, (76 + mm.width + 18, H * 0.63 + mm.height - mml.height - 14), seg(t, 29.9, 34.7, 0.7, 0.7))
    l1 = text_img("एयरोस्पेस ग्रेड", NP_REG, 40, (210, 216, 224), max_w=640)
    blit(canvas, l1, (80, H * 0.63 - 108), seg(t, 30.2, 34.7, 0.7, 0.7))
    l2 = text_img("टाइटेनियम", NP_BOLD, 56, INK, max_w=640)
    blit(canvas, l2, (80, H * 0.63 - 108 + l1.height + 2), seg(t, 30.3, 34.7, 0.7, 0.7))
    l3 = text_img("छ दशमलव नौ मिलिमिटर मात्र पातलो।", NP_REG, 30, (150, 158, 170), max_w=760)
    blit(canvas, l3, (82, H * 0.63 + mm.height + 24), seg(t, 31.2, 34.7, 0.7, 0.7) * 0.95)
    short.sweep_band(glow, tl, 0.5, 2.4, strength=0.070, width=380, angle=14)


def s_robust(canvas, glow, tl, t):
    # water/dust: concentric ripple rings over the metal
    src = photo("hero_back.png")
    cover = max(W / src.width, H / src.height)
    src2 = src.resize((int(src.width * cover) + 2, int(src.height * cover) + 2), Image.LANCZOS)
    zoom = lerp(1.02, 1.14, smooth(tl / 5.0))
    cw, ch = int(W / zoom), int(H / zoom)
    cx, cy = src2.width // 2, src2.height // 2
    crop = src2.crop((cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2)).resize((W, H), Image.BICUBIC)
    crop = Image.blend(crop, Image.new("RGB", (W, H), (4, 10, 16)), 0.66)
    canvas.paste(crop, (0, 0))
    for k in range(3):
        p = ((tl + k * 0.6) % 1.8) / 1.8
        r = int(120 + p * 520)
        ring = Image.new("RGBA", (r * 2, r * 2), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse([0, 0, r * 2 - 1, r * 2 - 1], outline=MINT + (int(150 * (1 - p)),), width=3)
        a = (1 - p) * seg(t, 34.8, 39.8, 0.5, 0.5)
        blit(canvas, ring, (W / 2, H * 0.45), a * 0.55)
    rc.add_glow_layer(glow, rc.radial_glow(460, (30, 110, 140), 2.2), (W / 2, H * 0.45),
                      0.24 * seg(t, 34.8, 39.8, 0.5, 0.5))
    cscrim = rc.radial_glow(560, (3, 5, 7), 1.4)
    canvas.paste(cscrim.convert("RGB"), (int(W / 2 - 560), int(H * 0.42 - 560)),
                 cscrim.getchannel("A").point(lambda v: int(v * 0.55 * seg(t, 34.8, 39.8, 0.5, 0.5))))
    op = seg(t, 35.2, 39.7, 0.6, 0.6)
    big = text_img("IP68", EN_XB, 178, INK, lang="en", tracking=0.02)
    blit(canvas, big, (W / 2, H * 0.46), op, center_x=True)
    n1 = mixed_mask("पानी र धुलोबाट सुरक्षित।", NP_BOLD, EN_XB, 46, MINT)
    blit(canvas, n1, (W / 2, H * 0.46 + big.height + 26), seg(t, 35.6, 39.7, 0.6, 0.6), center_x=True)
    blit(canvas, label("WATER  •  DUST  •  2M DROP", 18, (152, 160, 172), 0.42),
         (W / 2, H * 0.46 - 44), seg(t, 35.4, 39.7, 0.7, 0.6) * 0.9, center_x=True)


def battery_ring(canvas, glow, t, a, b, pct=0.86):
    cx, cy, r = W / 2, H * 0.40, 210
    k = smooth((t - a) / 1.4)
    layer = Image.new("RGBA", (r * 2 + 24, r * 2 + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    box = [12, 12, r * 2 + 11, r * 2 + 11]
    d.arc(box, 0, 360, fill=(52, 58, 64, 255), width=10)
    d.arc(box, -90, -90 + 360 * pct * k, fill=MINT + (255,), width=10)
    op = seg(t, a, b, 0.6, 0.6)
    blit(canvas, layer, (cx, cy), op, anchor="center")
    rc.add_glow_layer(glow, rc.radial_glow(300, (26, 120, 120), 2.2), (cx, cy), 0.22 * op)


def s_power(canvas, glow, tl, t):
    sp = sprite("hero_front.png", 1000)
    sp.draw(canvas, (W / 2, H * 0.42 + floating(t, 7, 0.4)), -6, 1.0, 0.18 * seg(t, 39.8, 45.4, 0.5, 0.5))
    rc.bottom_scrim(canvas, 0.55, 0.58)
    battery_ring(canvas, glow, t, 40.2, 45.3)
    number_block(canvas, glow, t, 40.4, 45.3, "5,000", "mAh", "पाँच हजार एम ए एच ब्याट्री।",
                 "ALL-DAY BATTERY  •  80W CHARGE", unit_color=AMBER)
    # charge ticks
    op = seg(t, 41.4, 45.3, 0.6, 0.6)
    d = ImageDraw.Draw(canvas)
    for i in range(30):
        x = 78 + i * 30
        h = 14 if (i / 30) < 0.86 * smooth((t - 41.4) / 1.6) else 6
        d.line([(x, H * 0.345), (x, H * 0.345 + h)], fill=(MINT if h > 8 else (50, 56, 62)), width=3)


def s_chip(canvas, glow, tl, t):
    cx, cy = W / 2, H * 0.40
    op = seg(t, 45.8, 50.7, 0.6, 0.6)
    # chip die
    size = int(300 * ease_out(clamp((tl - 0.2) / 1.0)))
    if size > 10:
        die = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(die)
        r = size * 0.16
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(14, 20, 26, 235),
                            outline=(90, 210, 205, 220), width=3)
        d.rounded_rectangle([size * 0.16, size * 0.16, size * 0.84, size * 0.84], radius=r * 0.7,
                            outline=(60, 140, 150, 200), width=2)
        for i in range(6):
            p = size * (0.20 + i * 0.12)
            d.line([(p, size * 0.05), (p, size * 0.16)], fill=(120, 230, 220, 190), width=3)
            d.line([(p, size * 0.84), (p, size * 0.95)], fill=(120, 230, 220, 190), width=3)
            d.line([(size * 0.05, p), (size * 0.16, p)], fill=(120, 230, 220, 190), width=3)
            d.line([(size * 0.84, p), (size * 0.95, p)], fill=(120, 230, 220, 190), width=3)
        blit(canvas, die, (cx, cy), op, anchor="center")
        rc.add_glow_layer(glow, rc.radial_glow(360, (20, 140, 130), 2.2), (cx, cy), 0.30 * op)
    # travelling data pulses
    for k in range(5):
        p = ((tl * 0.9 + k * 0.2) % 1.0)
        ang = k * 1.3
        rr = lerp(150, 420, p)
        px, py = cx + rr * math.cos(ang), cy + rr * math.sin(ang) * 0.9
        rc.add_glow_layer(glow, rc.radial_glow(16, MINT, 1.6), (px, py), (1 - p) * 0.9 * op)
    number_block(canvas, glow, t, 46.4, 50.7, "2x", "FASTER", "दुई गुणा छिटो, धेरै कम तात्ने।",
                 "NEXT-GEN SILICON", unit_color=MINT)


def s_soft(canvas, glow, tl, t):
    sp = sprite("hero_front.png", 1040)
    sp.draw(canvas, (W / 2, H * 0.43 + floating(t, 6, 0.35, 0.5)), 4, 1.0,
            0.22 * seg(t, 50.8, 55.6, 0.5, 0.5))
    rc.bottom_scrim(canvas, 0.58, 0.56)
    rc.add_glow_layer(glow, rc.radial_glow(420, (70, 50, 130), 2.2), (W / 2, H * 0.43), 0.28)
    op = seg(t, 51.2, 55.5, 0.6, 0.6)
    for i in range(7):
        a = seg(t, 51.2 + i * 0.16, 55.5, 0.5, 0.5)
        d = ImageDraw.Draw(canvas)
        x = W / 2 - 210 + (i % 7) * 70
        y = H * 0.43 + 320
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=MINT if a > 0.4 else (60, 66, 74))
    big = text_img("7", EN_XB, 230, INK, lang="en")
    blit(canvas, big, (W / 2 - 60, H * 0.62), op, center_x=True)
    yr = text_img("YEARS", EN_XB, 70, MINT, lang="en", tracking=0.06)
    blit(canvas, yr, (W / 2 + 190, H * 0.62 + big.height - yr.height - 16), seg(t, 51.5, 55.5, 0.6, 0.6))
    n1 = mixed_mask("सात वर्षको अपडेट।", NP_BOLD, EN_XB, 46, INK)
    blit(canvas, n1, (W / 2, H * 0.62 + big.height + 18), op, center_x=True)
    n2 = mixed_mask("हरेक दिन नयाँ जस्तै।", NP_REG, EN_RG, 38, (186, 194, 206))
    blit(canvas, n2, (W / 2, H * 0.62 + big.height + 18 + n1.height + 8), seg(t, 51.9, 55.5, 0.6, 0.6),
         center_x=True)


def s_colors(canvas, glow, tl, t):
    sp = sprite("variants.png", 1080)
    center = (W / 2, H * 0.47 + floating(t, 8, 0.4))
    rc.add_glow_layer(glow, rc.radial_glow(520, (36, 110, 130), 2.2), center, 0.30)
    sp.draw(canvas, center, 0, lerp(1.06, 1.0, smooth(tl / 4.2)), seg(t, 55.6, 60.0, 0.6, 0.5))
    rc.bottom_scrim(canvas, 0.58, 0.62)
    # per-colour labels, staggered
    op = seg(t, 56.4, 59.9, 0.6, 0.5)
    a1 = mixed_mask("चार रङ।", NP_BOLD, EN_XB, 62, INK)
    blit(canvas, a1, (W / 2, H * 0.74), op, center_x=True)
    a2 = mixed_mask("एउटै विरासत।", NP_REG, EN_RG, 44, MINT)
    blit(canvas, a2, (W / 2, H * 0.74 + a1.height + 10), seg(t, 57.2, 59.9, 0.6, 0.5), center_x=True)
    blit(canvas, label("FOUR FINISHES", 18, (146, 154, 166), 0.42),
         (W / 2, H * 0.74 - 46), seg(t, 56.6, 59.9, 0.7, 0.5) * 0.9, center_x=True)


def s_date(canvas, glow, tl, t):
    op = seg(t, 60.1, 63.5, 0.55, 0.4)
    add_dev = 0.30 * op
    sp = sprite("hero_back.png", 1090)
    sp.draw(canvas, (W / 2 + 30, H * 1.12), lerp(-15, -9, smooth(tl / 3.4)),
            lerp(0.95, 1.05, smooth(tl / 3.4)), add_dev)
    rc.add_glow_layer(glow, rc.radial_glow(520, (40, 110, 130), 2.2), (W / 2, H * 0.48), 0.40 * op)
    a = text_img("आउँदो महिना", NP_REG, 44, (196, 204, 214), max_w=700)
    blit(canvas, a, (W / 2, H * 0.38), op, center_x=True)
    b = mixed_mask("डिसेम्बर 2026", NP_BOLD, EN_XB, 92, INK)
    blit(canvas, b, (W / 2, H * 0.38 + a.height + 16), seg(t, 60.4, 63.5, 0.5, 0.4), center_x=True)
    c = label("DECEMBER 2026  •  WORLDWIDE", 20, MINT, 0.46)
    blit(canvas, c, (W / 2, H * 0.38 + a.height + b.height + 58), seg(t, 60.8, 63.5, 0.5, 0.4) * 0.95,
         center_x=True)
    light_streak(canvas, glow, W / 2, H * 0.52, 560 * ease_out(tl / 1.2), 1.4, MINT, 0.32 * op)


def s_pre(canvas, glow, tl, t):
    op = seg(t, 63.9, 68.3, 0.6, 0.5)
    rc.add_glow_layer(glow, rc.radial_glow(520, (60, 110, 140), 2.2), (W / 2, H * 0.46), 0.34 * op)
    k = label("PRE-ORDER  •  LIMITED FIRST BATCH", 18, (150, 158, 170), 0.42)
    blit(canvas, k, (W / 2, H * 0.36), seg(t, 63.9, 68.3, 0.7, 0.5) * 0.9, center_x=True)
    big = text_img("AURA X1", EN_XB, 118, INK, lang="en", tracking=0.05)
    blit(canvas, big, (W / 2, H * 0.40), op, center_x=True)
    n1 = mixed_mask("अहिले नै दर्ता गर्नुहोस्।", NP_BOLD, EN_XB, 48, MINT)
    blit(canvas, n1, (W / 2, H * 0.40 + big.height + 20), seg(t, 64.4, 68.3, 0.6, 0.5), center_x=True)
    n2 = mixed_mask("पहिलो पाउनेमा।", NP_REG, EN_RG, 38, (198, 206, 218))
    blit(canvas, n2, (W / 2, H * 0.40 + big.height + 20 + n1.height + 8), seg(t, 64.9, 68.3, 0.6, 0.5),
         center_x=True)
    # CTA pill
    pw, ph = 460, 96
    pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([0, 0, pw - 1, ph - 1], radius=ph // 2, fill=MINT + (235,))
    cta = text_img("PRE-ORDER NOW", EN_XB, 30, (8, 20, 22), lang="en", tracking=0.14)
    blit(canvas, pill, (W / 2, H * 0.615), seg(t, 65.4, 68.3, 0.5, 0.5), center_x=True)
    blit(canvas, cta, (W / 2, H * 0.615 + 30), seg(t, 65.4, 68.3, 0.5, 0.5), center_x=True)
    blit(canvas, label("AURA.COM/X1", 16, (140, 148, 160), 0.34),
         (W / 2, H * 0.615 + 120), seg(t, 65.9, 68.3, 0.5, 0.5) * 0.85, center_x=True)


def s_lock(canvas, glow, tl, t):
    op = seg(t, 68.5, DURATION + 1, 0.5, 0.4)
    rc.add_glow_layer(glow, rc.radial_glow(560, (34, 120, 140), 2.3), (W / 2, H * 0.47), 0.5 * op)
    scrim = rc.radial_glow(620, (3, 4, 6), 1.4)
    canvas.paste(scrim.convert("RGB"), (int(W / 2 - 620), int(H * 0.44 - 620)),
                 scrim.getchannel("A").point(lambda v: int(v * 0.60 * op)))
    sp = sprite("hero_front.png", 1180)
    sp.draw(canvas, (W / 2, H * 0.50), -4, lerp(1.0, 1.06, smooth(tl / 4.8)), 0.12 * op)
    name = text_img("AURA X1", EN_XB, 132, INK, lang="en", tracking=0.05)
    s = ease_out_back(clamp((tl - 0.3) / 1.1), 1.1)
    scaled = name.resize((max(int(name.width * (0.86 + 0.14 * s)), 1),
                          max(int(name.height * (0.86 + 0.14 * s)), 1)), Image.LANCZOS)
    blit(canvas, scaled, (W / 2, H * 0.44 - scaled.height / 2), seg(t, 68.8, DURATION + 1, 0.8, 0.4),
         center_x=True)
    tag = mixed_mask("भोलिको फोन। आज।", NP_BOLD, EN_XB, 48, MINT)
    blit(canvas, tag, (W / 2, H * 0.44 + scaled.height / 2 + 18), seg(t, 69.6, DURATION + 1, 0.7, 0.4),
         center_x=True)
    fine = mixed_mask("अवधारणा नमुना  •  CONCEPT FILM", NP_REG, EN_SB, 22, (126, 134, 146), en_px=15)
    blit(canvas, fine, (W / 2, H * 0.44 + scaled.height / 2 + 106), seg(t, 70.4, DURATION + 1, 0.8, 0.4) * 0.9,
         center_x=True)
    k = clamp((tl - 0.2) / 1.4)
    light_streak(canvas, glow, W / 2, H * 0.44 - scaled.height / 2 - 46, 700 * ease_out(k), 1.6, MINT,
                 0.55 * seg(t, 68.5, DURATION + 1, 0.4, 0.4))


SCENE_FN = [s_open, s_hero, s_design, s_display, s_camera, s_night, s_metal, s_robust,
            s_power, s_chip, s_soft, s_colors, s_date, s_pre, s_lock]


# ------------------------------------------------------------------ render --
def render_frame(t):
    arr, si = base_frame(t)
    canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    SCENE_FN[si](canvas, glow, t - SCENES[si], t)

    short.wordmark(canvas, 0.42 * seg(t, 0.8, DURATION, 0.9, 1.0))
    short.progress_ticks(canvas, t) if False else None
    d = ImageDraw.Draw(canvas)
    n = 34
    x0, x1, y = 90, W - 90, H - 96
    for i in range(n):
        x = lerp(x0, x1, i / (n - 1))
        on = (i / (n - 1)) <= (t / DURATION)
        d.line([(x, y), (x, y + (10 if on else 5))], fill=(MINT if on else (54, 58, 64)), width=2)
    d.line([(x0, y + 26), (x1, y + 26)], fill=(26, 30, 34), width=1)

    for cut in SCENES[1:]:
        flash(glow, t, cut - 0.16, 1.0, 0.5)

    canvas = ImageChops.add(canvas, glow)
    canvas = ImageChops.multiply(canvas, rc.vignette())
    g = rc.grain_tiles()[int(t * FPS) % 6]
    canvas = Image.fromarray(np.clip(np.asarray(canvas, dtype=np.float32) + g, 0, 255).astype(np.uint8), "RGB")
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "aura_x1_full.mp4"))
    ap.add_argument("--audio", default="")
    ap.add_argument("--audio-only", action="store_true")
    args = ap.parse_args()

    os.makedirs(os.path.join(BUILD, "stills"), exist_ok=True)
    audio_path = args.audio or os.path.join(BUILD, "audio_full.wav")

    if args.audio_only or (not os.path.exists(audio_path) and not args.preview):
        audio.build(vo_plan=VO_PLAN, total=DURATION, out_name=os.path.basename(audio_path))
    if args.audio_only:
        return

    if args.preview:
        for s in args.preview.split(","):
            t = float(s)
            img = render_frame(t)
            p = os.path.join(BUILD, "stills", f"L{t:05.2f}.png")
            img.save(p)
            print("wrote", p)
        return

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio_path,
           "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-tune", "film",
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
           "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-shortest", args.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(NFRAMES):
            proc.stdin.write(render_frame(i / FPS).tobytes())
            if i % 60 == 0:
                print(f"frame {i}/{NFRAMES}", flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    print("done ->", args.out, "exit", proc.returncode)


if __name__ == "__main__":
    main()
