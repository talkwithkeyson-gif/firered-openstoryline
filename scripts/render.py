"""AURA X1 — concept teaser. Builds every frame procedurally and pipes to ffmpeg."""
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
import textrender as tr
import imageio_ffmpeg

# ------------------------------------------------------------- scene map ----
S1, S2, S3, S4, S5, S6, S7 = 0.0, 3.2, 8.8, 14.8, 20.0, 27.0, 30.3
SCENES = [S1, S2, S3, S4, S5, S6, S7, 1e9]

BACKGROUNDS = [
    # (top, bottom)
    ((6, 8, 12), (2, 3, 5)),        # intro
    ((7, 12, 17), (3, 4, 6)),       # hero
    ((5, 15, 18), (2, 4, 7)),       # display
    ((16, 11, 8), (4, 3, 4)),       # camera
    ((12, 12, 13), (3, 3, 4)),      # titanium
    ((9, 11, 15), (2, 3, 5)),       # date
    ((5, 9, 13), (1, 2, 3)),        # lockup
]

_bgs = None


def backgrounds():
    global _bgs
    if _bgs is None:
        _bgs = [np.asarray(background(*tint, seed=i), dtype=np.float32)
                for i, tint in enumerate(BACKGROUNDS)]
    return _bgs


def scene_index(t):
    for i in range(len(SCENES) - 1):
        if SCENES[i] <= t < SCENES[i + 1]:
            return i
    return len(SCENES) - 2


def base_frame(t):
    bgs = backgrounds()
    i = scene_index(t)
    cur = bgs[i]
    prev_i = max(i - 1, 0)
    nxt_i = min(i + 1, len(bgs) - 1)
    # blend across scene boundaries (0.45 s each side)
    fade = 0.50
    if i > 0 and t - SCENES[i] < fade:
        w = smooth((t - SCENES[i]) / fade)
        arr = bgs[i - 1] * (1 - w) + cur * w
    elif i < len(bgs) - 1 and SCENES[i + 1] - t < fade:
        w = smooth((SCENES[i + 1] - t) / fade)
        arr = bgs[i + 1] * (1 - w) + cur * w
    else:
        arr = cur
    return arr, i


# --------------------------------------------------------------- sprites ----
_sprites = None


def sprites():
    global _sprites
    if _sprites is None:
        _sprites = {
            "front": Sprite(load_product(os.path.join(ASSETS, "img", "hero_front.png"), 1090)),
            "back": Sprite(load_product(os.path.join(ASSETS, "img", "hero_back.png"), 1180)),
            "macro": Image.open(os.path.join(ASSETS, "img", "macro_edge.png")).convert("RGB"),
            "front_big": Image.open(os.path.join(ASSETS, "img", "hero_front.png")).convert("RGB"),
        }
    return _sprites


# ---------------------------------------------------------------- helpers ----
def floating(t, amp=12, speed=0.55, phase=0.0):
    return amp * math.sin(2 * math.pi * speed * t + phase)


def sweep_band(glow, t, at, dur, strength=0.12, width=260, angle=0.0,
               color=(190, 232, 255)):
    """Soft diagonal glare travelling across the frame; additive into the glow layer."""
    if not (at <= t <= at + dur):
        return
    k = (t - at) / dur
    cx = lerp(-width, W + width, ease_out(k, 2)) + math.tan(math.radians(angle)) * (H / 2)
    x = np.arange(W, dtype=np.float32)[None, ::1]
    prof = np.exp(-((x - cx) / (width * 0.5)) ** 2)
    falloff = np.sin(np.pi * clamp(k)) ** 0.7
    col = np.array(color, dtype=np.float32)
    band = (prof.T * falloff * strength)[:, :, None] * col[None, None, :]  # (H,W,3)
    add = Image.fromarray(np.clip(band, 0, 255).astype(np.uint8), "RGB")
    glow.paste(ImageChops.add(glow, add), (0, 0))


def flash(glow, t, at, strength=1.0, dur=0.5):
    if at <= t <= at + dur:
        k = 1 - (t - at) / dur
        add_glow_layer(glow, rc.radial_glow(700, (255, 255, 255), 1.6), (W / 2, H / 2),
                       strength * (k ** 3) * 0.55)


def wordmark(canvas, opacity=0.55):
    im = text_img("AURA", EN_SB, 22, (200, 208, 216), lang="en", tracking=0.40)
    blit(canvas, im, (W / 2, 70), opacity, center_x=True)
    d = ImageDraw.Draw(canvas)
    dot = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    ImageDraw.Draw(dot).ellipse([0, 0, 8, 8], fill=MINT + (255,))
    blit(canvas, dot, (W / 2 + im.width / 2 + 16, 82), opacity)


def label(text, px=22, color=DIM, tracking=0.30, lang="en", font=EN_SB):
    return text_img(text, font, px, color, lang=lang, tracking=tracking)


def progress_ticks(canvas, t, opacity=0.5):
    d = ImageDraw.Draw(canvas)
    n = 24
    x0, x1, y = 90, W - 90, H - 96
    for i in range(n):
        x = lerp(x0, x1, i / (n - 1))
        on = (i / (n - 1)) <= (t / DURATION)
        col = (MINT if on else (54, 58, 64))
        h = 10 if on else 5
        d.line([(x, y), (x, y + h)], fill=col, width=2)
    d.line([(x0, y + 26), (x1, y + 26)], fill=(26, 30, 34), width=1)


# ----------------------------------------------------------------- scenes ----
def scene_intro(canvas, glow, tl, t):
    # pulsing ring behind the copy
    ring_r = 220 + 12 * math.sin(t * 2.4)
    add_glow_layer(glow, rc.radial_glow(340, (40, 130, 150), 2.0), (W / 2, H * 0.44),
                   0.30 * seg(t, 0.1, 3.2, 0.8, 0.4))
    light_streak(canvas, glow, W / 2, H * 0.44, 520 * ease_out(t / 1.6), 2, MINT,
                 0.85 * seg(t, 0.2, 3.2, 0.9, 0.5))

    op = seg(t, 0.35, 3.15, 0.55, 0.45)
    kicker = label("A NEW ERA OF MOBILE", 20, DIM, 0.44)
    blit(canvas, kicker, (W / 2, H * 0.40), op * 0.9, center_x=True)

    big = text_img("केही नयाँ", NP_BOLD, 92, INK, max_w=860)
    blit(canvas, big, (W / 2, H * 0.455), op, center_x=True)
    big2 = text_img("आउँदैछ।", NP_BOLD, 92, MINT, max_w=860)
    blit(canvas, big2, (W / 2, H * 0.455 + big.height + 6), seg(t, 0.75, 3.15, 0.55, 0.45),
         center_x=True)

    sub = label("SOMETHING IS COMING", 18, (128, 136, 148), 0.52)
    blit(canvas, sub, (W / 2, H * 0.455 + big.height + big2.height + 54),
         seg(t, 1.25, 3.1, 0.6, 0.5) * 0.85, center_x=True)


def scene_hero(canvas, glow, tl, t):
    sp = sprites()["front"]
    center = (W / 2, H * 0.45 + floating(t, 10, 0.45))
    ang = lerp(-9, -3.0, ease_out(tl / 5.6, 2))
    sc = lerp(0.94, 1.06, smooth(tl / 5.6))
    add_glow_layer(glow, rc.radial_glow(420, (30, 120, 140), 2.2), center, 0.55)
    bottom_scrim(canvas, 0.45, 0.62)
    sp.draw(canvas, center, ang, sc, seg(t, S2, S2 + 5.8, 0.5, 0.5))

    # soft glare travelling across the glass
    sweep_band(glow, tl, 1.1, 2.2, strength=0.085, width=300, angle=10)

    op = seg(t, S2 + 0.55, S2 + 5.55, 0.7, 0.6)
    ty = H * 0.755
    name = text_img("AURA X1", EN_XB, 104, INK, lang="en", tracking=0.06)
    blit(canvas, name, (W / 2, ty), op, center_x=True)
    np_name = text_img("औरा एक्स वान", NP_BOLD, 46, MINT, max_w=760)
    blit(canvas, np_name, (W / 2, ty + name.height + 12), seg(t, S2 + 0.95, S2 + 5.5, 0.7, 0.6),
         center_x=True)
    tag = label("FLAGSHIP  •  2026", 19, (136, 144, 156), 0.46)
    blit(canvas, tag, (W / 2, ty + name.height + np_name.height + 44),
         seg(t, S2 + 1.35, S2 + 5.4, 0.7, 0.6) * 0.9, center_x=True)


def scene_display(canvas, glow, tl, t):
    sp = sprites()["front"]
    center = (W / 2 + 40, H * 0.47 + floating(t, 8, 0.5))
    bottom_scrim(canvas, 0.55, 0.55)
    sp.draw(canvas, center, lerp(-6, 4, smooth(tl / 6)), lerp(0.9, 1.0, smooth(tl / 6)),
            seg(t, S3, S3 + 5.9, 0.45, 0.5) * 0.96)
    add_glow_layer(glow, rc.radial_glow(460, (26, 130, 120), 2.0), center, 0.45)

    # giant number, left-aligned, sitting over the darkness
    op = seg(t, S3 + 0.35, S3 + 5.6, 0.6, 0.6)
    num = text_img('6.8"', EN_XB, 210, INK, lang="en", tracking=-0.02)
    blit(canvas, num, (74, H * 0.685 - num.height * 0.5), op)
    unit = label("INCH  •  EDGE-TO-EDGE", 19, (134, 142, 154), 0.44)
    blit(canvas, unit, (80, H * 0.685 + num.height * 0.5 + 6), op * 0.9)

    np_l1 = text_img("छ दशमलव आठ इन्चको", NP_REG, 40, (206, 212, 220), max_w=560)
    blit(canvas, np_l1, (78, H * 0.685 - num.height * 0.5 - 108), seg(t, S3 + 1.0, S3 + 5.5, 0.6, 0.6))
    np_l2 = text_img("डिस्प्ले", NP_BOLD, 40, MINT, max_w=560)
    blit(canvas, np_l2, (78, H * 0.685 - num.height * 0.5 - 108 + np_l1.height + 2),
         seg(t, S3 + 1.0, S3 + 5.5, 0.6, 0.6))

    hz = text_img("144Hz", EN_XB, 74, AMBER, lang="en", tracking=0.0)
    blit(canvas, hz, (80, H * 0.80), seg(t, S3 + 2.2, S3 + 5.5, 0.6, 0.6))
    hz_l = label("PRO MOTION DISPLAY", 17, (150, 142, 130), 0.40)
    blit(canvas, hz_l, (84, H * 0.80 + 84), seg(t, S3 + 2.4, S3 + 5.5, 0.6, 0.6) * 0.9)


def scene_camera(canvas, glow, tl, t):
    sp = sprites()["back"]
    center = (W / 2 - 30, H * 0.45 + floating(t, 9, 0.42, 1.0))
    ang = lerp(-13, 5, smooth(tl / 5.2))
    add_glow_layer(glow, rc.radial_glow(430, (150, 96, 40), 2.2), center, 0.42)
    bottom_scrim(canvas, 0.55, 0.55)
    sp.draw(canvas, center, ang, lerp(0.95, 1.02, smooth(tl / 5.2)),
            seg(t, S4, S4 + 5.2, 0.45, 0.5))

    op = seg(t, S4 + 0.45, S4 + 5.0, 0.6, 0.6)
    mp = text_img("200", EN_XB, 250, INK, lang="en")
    blit(canvas, mp, (72, H * 0.665), op)
    mpl = text_img("MP", EN_XB, 96, AMBER, lang="en")
    blit(canvas, mpl, (72 + mp.width + 14, H * 0.665 + mp.height - mpl.height - 10),
         seg(t, S4 + 0.75, S4 + 5.0, 0.6, 0.6))

    np_t = text_img("दुई सय मेगापिक्सेलको", NP_REG, 40, (208, 214, 222), max_w=640)
    blit(canvas, np_t, (76, H * 0.665 - 96), seg(t, S4 + 1.15, S4 + 5.0, 0.6, 0.6))
    np_t2 = text_img("क्यामेरा। रात पनि दिन जस्तै।", NP_BOLD, 40, MINT, max_w=700)
    blit(canvas, np_t2, (76, H * 0.665 - 96 + np_t.height + 4),
         seg(t, S4 + 1.35, S4 + 5.0, 0.6, 0.6))

    # lens flare dots
    for k, (dx, dy, ph) in enumerate([(-52, -20, 0.0), (10, 26, 1.2), (-30, 58, 2.1)]):
        a = seg(t, S4 + 1.6 + k * 0.25, S4 + 5.0, 0.5, 0.5)
        p = (center[0] + dx, center[1] - 60 + dy)
        add_glow_layer(glow, rc.radial_glow(90, (255, 214, 170), 2.4), p,
                       a * (0.5 + 0.15 * math.sin(t * 3 + ph)))


def scene_metal(canvas, glow, tl, t):
    src = sprites()["macro"]
    full = src.resize((W, int(src.height * W / src.width)), Image.LANCZOS)
    zoom = lerp(1.32, 1.04, smooth(tl / 6.6))
    # scale so the frame is always covered, then crop a zoomed window
    cover = max(W / full.width, H / full.height)
    full = full.resize((int(full.width * cover) + 2, int(full.height * cover) + 2), Image.LANCZOS)
    cw, ch = int(W / zoom), int(H / zoom)
    cx = int(W / 2 + 55 * math.sin(tl * 0.35))
    cy = int(H / 2 + (tl / 6.6 - 0.5) * 110)
    cx = int(clamp(cx, cw // 2, full.width - cw // 2))
    cy = int(clamp(cy, ch // 2, full.height - ch // 2))
    box = (cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2)
    crop = full.crop(box).resize((W, H), Image.BICUBIC)
    crop = Image.blend(crop, Image.new("RGB", (W, H), (10, 11, 12)), 0.34)
    fade = seg(t, S5, S5 + 6.8, 0.5, 0.5)
    canvas.paste(crop, (0, 0)) if fade >= 0.999 else None
    bottom_scrim(canvas, 0.62, 0.50)
    if fade < 0.999:
        tmp = canvas.copy()
        tmp.paste(crop, (0, 0))
        crop = Image.blend(tmp, crop, fade)
    canvas.paste(crop, (0, 0))

    add_glow_layer(glow, rc.radial_glow(500, (60, 120, 140), 2.4), (W / 2, H * 0.40),
                   0.30 * fade)

    op = seg(t, S5 + 0.6, S5 + 6.4, 0.7, 0.7)
    mm = text_img("6.9", EN_XB, 220, INK, lang="en")
    blit(canvas, mm, (76, H * 0.60), op)
    mml = text_img("MM", EN_XB, 82, MINT, lang="en", tracking=0.05)
    blit(canvas, mml, (76 + mm.width + 18, H * 0.60 + mm.height - mml.height - 14),
         seg(t, S5 + 0.9, S5 + 6.4, 0.7, 0.7))

    l1 = text_img("एयरोस्पेस ग्रेड", NP_REG, 42, (210, 216, 224), max_w=640)
    blit(canvas, l1, (80, H * 0.60 - 110), seg(t, S5 + 1.2, S5 + 6.4, 0.7, 0.7))
    l2 = text_img("टाइटेनियम", NP_BOLD, 58, INK, max_w=640)
    blit(canvas, l2, (80, H * 0.60 - 110 + l1.height + 2), seg(t, S5 + 1.3, S5 + 6.4, 0.7, 0.7))
    l3 = text_img("छ दशमलव नौ मिलिमिटर मात्र पातलो।", NP_REG, 30, (150, 158, 170), max_w=760)
    blit(canvas, l3, (82, H * 0.60 + mm.height + 28), seg(t, S5 + 2.2, S5 + 6.4, 0.7, 0.7) * 0.95)

    # rim light sweep
    sweep_band(glow, tl, 0.5, 2.4, strength=0.070, width=380, angle=14)


def scene_date(canvas, glow, tl, t):
    op = seg(t, S6 + 0.15, S6 + 3.1, 0.55, 0.35)

    # device silhouette rising from the bottom edge
    sp = sprites()["back"]
    sp.draw(canvas, (W / 2 + 30, H * 1.12), lerp(-15, -9, smooth(tl / 3.2)),
            lerp(0.95, 1.05, smooth(tl / 3.2)), 0.30 * op)
    add_glow_layer(glow, rc.radial_glow(520, (40, 110, 130), 2.2), (W / 2, H * 0.48),
                   0.42 * op)

    a = text_img("आउँदो महिना", NP_REG, 44, (196, 204, 214), max_w=700)
    blit(canvas, a, (W / 2, H * 0.40), op, center_x=True)
    b = mixed_mask("डिसेम्बर 2026", NP_BOLD, EN_XB, 92, INK)
    blit(canvas, b, (W / 2, H * 0.40 + a.height + 18), seg(t, S6 + 0.35, S6 + 3.1, 0.5, 0.35),
         center_x=True)
    c = label("DECEMBER 2026  •  WORLDWIDE", 20, MINT, 0.46)
    blit(canvas, c, (W / 2, H * 0.40 + a.height + b.height + 62),
         seg(t, S6 + 0.75, S6 + 3.1, 0.5, 0.35) * 0.95, center_x=True)

    # thin horizon line
    y = H * 0.58
    light_streak(canvas, glow, W / 2, y, 560 * ease_out(tl / 1.2), 1.4, MINT, 0.35 * op)


def scene_lockup(canvas, glow, tl, t):
    op = seg(t, S7 + 0.05, DURATION + 1, 0.5, 0.4)
    add_glow_layer(glow, rc.radial_glow(560, (34, 120, 140), 2.3), (W / 2, H * 0.47),
                   0.5 * op)

    # product silhouette fading in behind the logo, very dark
    sp = sprites()["front"]
    scrim = rc.radial_glow(620, (3, 4, 6), 1.4)
    m = scrim.getchannel("A").point(lambda v: int(v * 0.60 * op))
    canvas.paste(scrim.convert("RGB"), (int(W / 2 - 620), int(H * 0.44 - 620)), m)

    name = text_img("AURA X1", EN_XB, 132, INK, lang="en", tracking=0.05)
    s = ease_out_back(clamp((tl - 0.25) / 1.1), 1.1)
    scaled = name.resize((max(int(name.width * (0.86 + 0.14 * s)), 1),
                          max(int(name.height * (0.86 + 0.14 * s)), 1)), Image.LANCZOS)
    blit(canvas, scaled, (W / 2, H * 0.44 - scaled.height / 2), seg(t, S7 + 0.2, DURATION + 1, 0.8, 0.4),
         center_x=True)

    tag = mixed_mask("भोलिको फोन। आज।", NP_BOLD, EN_XB, 48, MINT)
    blit(canvas, tag, (W / 2, H * 0.44 + scaled.height / 2 + 16),
         seg(t, S7 + 1.1, DURATION + 1, 0.7, 0.4), center_x=True)

    fine = mixed_mask("अवधारणा नमुना  •  CONCEPT TEASER", NP_REG, EN_SB, 22, (126, 134, 146), en_px=15)
    blit(canvas, fine, (W / 2, H * 0.44 + scaled.height / 2 + 104),
         seg(t, S7 + 2.0, DURATION + 1, 0.8, 0.4) * 0.9, center_x=True)

    # closing streak
    k = clamp((tl - 0.1) / 1.4)
    light_streak(canvas, glow, W / 2, H * 0.44 - scaled.height / 2 - 46, 700 * ease_out(k), 1.6,
                 MINT, 0.55 * seg(t, S7 + 0.05, DURATION + 1, 0.4, 0.4))


SCENE_FN = [scene_intro, scene_hero, scene_display, scene_camera, scene_metal, scene_date, scene_lockup]


# ----------------------------------------------------------------- render ----
def render_frame(t):
    arr, si = base_frame(t)
    canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    glow = Image.new("RGB", (W, H), (0, 0, 0))

    tl = t - SCENES[si]
    SCENE_FN[si](canvas, glow, tl, t)
    wordmark(canvas, 0.45 * seg(t, 0.6, DURATION, 0.8, 1.0))
    progress_ticks(canvas, t, 0.6)

    # flashes at each cut
    for cut in (S2, S3, S4, S5, S6, S7):
        flash(glow, t, cut - 0.16, 1.0, 0.5)

    canvas = ImageChops.add(canvas, glow)
    canvas = ImageChops.multiply(canvas, rc.vignette())

    # animated grain
    tiles = rc.grain_tiles()
    frame_i = int(t * FPS)
    g = tiles[frame_i % len(tiles)]
    a = np.asarray(canvas, dtype=np.float32) + g
    canvas = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=str, default="", help="comma separated times -> PNG stills")
    ap.add_argument("--out", default=os.path.join(ROOT, "aura_x1_teaser.mp4"))
    ap.add_argument("--audio", default=os.path.join(BUILD, "audio_mix.wav"))
    args = ap.parse_args()

    os.makedirs(os.path.join(BUILD, "stills"), exist_ok=True)

    if args.preview:
        for s in args.preview.split(","):
            t = float(s)
            img = render_frame(t)
            p = os.path.join(BUILD, "stills", f"t{t:05.2f}.png")
            img.save(p)
            print("wrote", p)
        return

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ff, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", args.audio,
        "-c:v", "libx264", "-preset", "slow", "-crf", "23", "-tune", "film",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest", args.out,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(NFRAMES):
            t = i / FPS
            frame = render_frame(t)
            proc.stdin.write(frame.tobytes())
            if i % 60 == 0:
                print(f"frame {i}/{NFRAMES}", flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    print("done ->", args.out, "exit", proc.returncode)


if __name__ == "__main__":
    main()
