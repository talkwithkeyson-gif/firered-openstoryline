"""Renders the 'AURA X1' teaser: 1080x1920 @ 30fps, piped straight into ffmpeg.

Usage:  python scripts/render.py [--preview N]   (N = render only N frames)
"""
import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textrender as tr  # noqa: E402
import imageio_ffmpeg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
BUILD = os.path.join(ROOT, "build")
FONTS = os.path.join(ASSETS, "fonts")

W, H = 1080, 1920
FPS = 30
DURATION = 35.6
NFRAMES = int(DURATION * FPS)

NP_BOLD = os.path.join(FONTS, "NotoSansDevanagari-Bold.ttf")
NP_REG = os.path.join(FONTS, "NotoSansDevanagari-Regular.ttf")
EN_XB = os.path.join(FONTS, "Inter-ExtraBold.ttf")
EN_SB = os.path.join(FONTS, "Inter-SemiBold.ttf")
EN_RG = os.path.join(FONTS, "Inter-Regular.ttf")
EN_LT = os.path.join(FONTS, "Inter-Light.ttf")

INK = (243, 245, 247)
MINT = (110, 240, 214)
AMBER = (255, 186, 120)
DIM = (150, 158, 170)

# ---------------------------------------------------------------- easing ----
def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t, p=3):
    return 1 - (1 - clamp(t)) ** p


def ease_in(t, p=3):
    return clamp(t) ** p


def ease_out_back(t, s=1.5):
    t = clamp(t) - 1
    return 1 + t * t * ((s + 1) * t + s)


def seg(t, a, b, fin=0.5, fout=0.5):
    """Opacity for an element visible in [a,b] with soft in/out."""
    if t < a or t > b:
        return 0.0
    i = smooth((t - a) / max(fin, 1e-6))
    o = smooth((b - t) / max(fout, 1e-6))
    return min(i, o)


# ------------------------------------------------------------- resources ----
_cache = {}


def radial_glow(radius, color, power=2.2, alpha=255):
    key = ("glow", radius, color, power, alpha)
    if key in _cache:
        return _cache[key]
    size = radius * 2
    y, x = np.mgrid[0:size, 0:size]
    d = np.sqrt((x - radius) ** 2 + (y - radius) ** 2) / radius
    a = np.clip(1 - d, 0, 1) ** power * alpha
    img = Image.new("RGBA", (size, size), color + (0,))
    img.putalpha(Image.fromarray(a.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius * 0.06)))
    _cache[key] = img
    return img


def background(tint_top, tint_bottom, seed=0):
    """Soft vertical gradient + faint blob lighting, generated in float."""
    key = ("bg", tint_top, tint_bottom, seed)
    if key in _cache:
        return _cache[key]
    small_w, small_h = 54, 96
    yy = np.linspace(0, 1, small_h)[:, None]
    xx = np.linspace(0, 1, small_w)[None, :]
    top = np.array(tint_top, dtype=float)
    bot = np.array(tint_bottom, dtype=float)
    g = top[None, None, :] * (1 - yy[..., None]) + bot[None, None, :] * yy[..., None]
    g = np.repeat(g, small_w, axis=1)
    # two soft light blobs
    for (cx, cy, r, col, amp) in [
        (0.24, 0.26, 0.55, np.array([26, 60, 74]), 0.9),
        (0.82, 0.68, 0.6, np.array([70, 46, 30]), 0.85),
        (0.5, 0.05, 0.5, np.array([20, 26, 34]), 1.0),
    ]:
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2 * 0.62) / r
        fall = np.clip(1 - d, 0, 1)[..., None] ** 2
        g = g + col[None, None, :] * fall * amp
    g = np.clip(g, 0, 255)
    img = Image.fromarray(g.astype(np.uint8), "RGB").resize((W, H), Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(28))
    _cache[key] = img
    return img


def vignette():
    if "vig" in _cache:
        return _cache["vig"]
    y, x = np.mgrid[0:H, 0:W]
    cx, cy = W / 2, H * 0.46
    d = np.sqrt(((x - cx) / (W * 0.78)) ** 2 + ((y - cy) / (H * 0.82)) ** 2)
    v = np.clip(1.06 - 0.55 * np.clip(d - 0.34, 0, None) ** 1.5, 0.34, 1.0)
    v = v[..., None] * np.array([1.0, 1.0, 1.02])
    img = Image.fromarray((np.clip(v, 0, 1) * 255).astype(np.uint8), "RGB")
    _cache["vig"] = img.filter(ImageFilter.GaussianBlur(6))
    return _cache["vig"]


def grain_tiles(n=6):
    if "grain" in _cache:
        return _cache["grain"]
    rng = np.random.default_rng(4)
    tiles = []
    for i in range(n):
        g = rng.normal(0, 3.2, (H, W, 1))
        g = np.repeat(g, 3, axis=2)
        tiles.append(g.astype(np.float32))
    _cache["grain"] = tiles
    return tiles


def load_product(path, target_h=None):
    """Load a black-background product shot, auto-crop it to the device and derive a
    soft luminance alpha so it composites cleanly over any background."""
    img = Image.open(path).convert("RGB")
    lum = np.asarray(ImageOps.grayscale(img), dtype=np.float32) / 255.0
    # light blur -> smooth, noise-tolerant coverage map
    cov = np.asarray(Image.fromarray((lum * 255).astype(np.uint8), "L")
                     .filter(ImageFilter.GaussianBlur(6)), dtype=np.float32) / 255.0
    ys, xs = np.where(cov > 0.055)
    if len(xs):
        pad = 10
        x0, x1 = max(int(xs.min()) - pad, 0), min(int(xs.max()) + pad, img.width)
        y0, y1 = max(int(ys.min()) - pad, 0), min(int(ys.max()) + pad, img.height)
        img = img.crop((x0, y0, x1, y1))
        lum = np.asarray(ImageOps.grayscale(img), dtype=np.float32) / 255.0
    if target_h:
        sc = target_h / img.height
        img = img.resize((max(int(img.width * sc), 1), int(target_h)), Image.LANCZOS)
        lum = np.asarray(ImageOps.grayscale(img), dtype=np.float32) / 255.0
    a = np.clip((lum - 0.035) / 0.965, 0, 1) ** 0.62
    mask = Image.fromarray((a * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(1.0))
    rgba = img.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


_scrim_cache = {}


def bottom_scrim(canvas, strength=0.55, top=0.45, bottom=1.0):
    """Vertical dark gradient for lower-third legibility."""
    key = ("scrim", round(strength, 2), round(top, 2))
    if key not in _scrim_cache:
        y = np.linspace(0, 1, H)[:, None]
        a = np.clip((y - top) / max(1 - top, 1e-6), 0, 1) ** 1.6 * strength
        col = np.array([4, 5, 7], dtype=np.float32)[None, None, :]
        arr = np.repeat(a[..., None] * col, W, axis=1)
        _scrim_cache[key] = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    canvas.paste(ImageChops.subtract(canvas, _scrim_cache[key]), (0, 0))


def text_img(text, font, px, color=INK, lang="ne", max_w=None, tracking=0.0):
    size = px
    if max_w:
        while size > 12:
            w = tr.measure(text, font, size, lang)[0]
            if w <= max_w:
                break
            size -= 1
    key = ("txt", text, font, size, color, lang, tracking)
    if key in _cache:
        return _cache[key]
    if not tracking:
        im = tr.text_mask(text, font, size, color, lang)
    else:
        # re-lay glyphs with extra tracking (spaces get tracking but no ink)
        items, adv, _, _, _, chars = tr.layout(text, font, size, lang)
        extra = tracking * size
        xs = []
        shift = 0.0
        for (g, x, y), ch in zip(items, chars):
            xs.append((g, x + shift, y))
            if ch:
                shift += extra
        top = min(y for _, _, y in xs)
        left = min(x for _, x, _ in xs)
        bottom = max(y + g.size[1] for g, _, y in xs)
        right = max(x + g.size[0] for g, x, _ in xs)
        cw = int(math.ceil(right - left)) + 4
        chh = int(math.ceil(bottom - top)) + 4
        canvas = Image.new("L", (cw, chh), 0)
        for g, x, y in xs:
            canvas.paste(g, (int(round(x - left + 2)), int(round(y - top + 2))), g)
        im = Image.new("RGBA", (cw, chh), color + (0,))
        im.putalpha(canvas)
    _cache[key] = im
    return im


EN_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,•·-—:;/()'\"&%+!?")


def mixed_mask(text, dev_font, en_font, px, color=INK, en_px=None, gap=None):
    """Render a string where Devanagari runs use dev_font and Latin runs en_font."""
    en_px = en_px or px
    # split into runs by script
    runs, cur, cur_dev = [], "", None
    for ch in text:
        if ch in " ,.;:।":
            # neutral separators ride with the run they follow but keep their advance
            cur += ch
            continue
        is_dev = ch not in EN_CHARS
        if cur_dev is None or is_dev == cur_dev:
            cur += ch
            cur_dev = is_dev
        else:
            runs.append((cur, cur_dev))
            cur, cur_dev = ch, is_dev
    if cur:
        runs.append((cur, cur_dev))

    pieces = []
    for txt, is_dev in runs:
        lead = len(txt) - len(txt.lstrip(" "))
        trail = len(txt) - len(txt.rstrip(" "))
        core_txt = txt.strip(" ")
        if lead:
            pieces.append(("space", (px if is_dev else en_px) * 0.30 * lead))
        txt = core_txt
        if not txt:
            if trail:
                pieces.append(("space", (px if is_dev else en_px) * 0.30 * trail))
            continue
        key = ("mix", txt, is_dev, px, en_px)
        if key not in _cache:
            if not txt.strip():
                w = (px if is_dev else en_px) * 0.28 * len(txt)
                _cache[key] = ("space", w)
            else:
                im = tr.text_mask(txt, dev_font if is_dev else en_font,
                                  px if is_dev else en_px, color, "ne" if is_dev else "en")
                _cache[key] = ("img", im)
        pieces.append(_cache[key])
        if trail:
            pieces.append(("space", (px if is_dev else en_px) * 0.30 * trail))

    total_w = sum(p[1].width if p[0] == "img" else p[1] for p in pieces)
    asc = max([p[1].height for p in pieces if p[0] == "img"] or [px])
    # baseline-ish alignment: centre each run on a common middle
    mid = asc * 0.56
    height = int(max(mid + asc * 0.62, asc)) + 4
    canvas = Image.new("L", (int(total_w) + 4, height), 0)
    x = 2
    for kind, val in pieces:
        if kind == "space":
            x += val
            continue
        im = val
        y = int(mid - im.height / 2 + 2)
        canvas.paste(im.getchannel("A"), (int(x), y), im.getchannel("A"))
        x += im.width
    out = Image.new("RGBA", canvas.size, color + (0,))
    out.putalpha(canvas)
    return out


def blit(canvas, img, pos, opacity=1.0, center_x=False, anchor="top"):
    if opacity <= 0.003:
        return
    if opacity < 1.0:
        m = img.getchannel("A").point(lambda v: int(v * opacity))
    else:
        m = img.getchannel("A")
    x, y = pos
    if center_x:
        x = W / 2 - img.width / 2
    if anchor == "center":
        x = x - img.width / 2
        y = y - img.height / 2
    canvas.paste(img, (int(x), int(y)), m)


def add_glow_layer(glow, img, center, strength=1.0):
    """Additive blend of a soft glow sprite onto an RGB 'glow' accumulation layer."""
    if strength <= 0.002:
        return
    cx, cy = center
    r = img.width // 2
    box = (int(cx - r), int(cy - r), int(cx + r), int(cy + r))
    clip = (max(box[0], 0), max(box[1], 0), min(box[2], W), min(box[3], H))
    if clip[2] <= clip[0] or clip[3] <= clip[1]:
        return
    piece = img.crop((clip[0] - box[0], clip[1] - box[1], clip[2] - box[0], clip[3] - box[1]))
    flat = Image.new("RGB", piece.size, (0, 0, 0))
    flat.paste(piece, (0, 0), piece)
    src = flat
    if strength < 1.0:
        src = src.point(lambda v: int(v * strength))
    region = glow.crop(clip)
    region = ImageChops.add(region, src)
    glow.paste(region, (clip[0], clip[1]))


def light_streak(canvas, glow, cx, cy, length, thickness, color=MINT, strength=1.0):
    """A thin horizontal lens streak with a hot core."""
    if length < 2:
        return
    y = int(cy)
    x0 = int(cx - length / 2)
    x1 = int(cx + length / 2)
    strip = Image.new("RGB", (max(x1 - x0, 1), max(int(thickness * 6), 3)), (0, 0, 0))
    d = ImageDraw.Draw(strip)
    mid = strip.height // 2
    d.rectangle([0, mid, strip.width, mid + max(int(thickness), 1)], fill=color)
    strip = strip.filter(ImageFilter.GaussianBlur(max(thickness * 1.8, 1.6)))
    box = (x0, y - mid, x1, y - mid + strip.height)
    clip = (max(box[0], 0), max(box[1], 0), min(box[2], W), min(box[3], H))
    if clip[2] > clip[0] and clip[3] > clip[1]:
        src = strip.crop((clip[0] - box[0], clip[1] - box[1], clip[2] - box[0], clip[3] - box[1]))
        if strength < 1.0:
            src = src.point(lambda v: int(v * strength))
        region = glow.crop(clip)
        glow.paste(ImageChops.add(region, src), (clip[0], clip[1]))
    core = Image.new("RGB", (max(x1 - x0, 1), 3), (255, 255, 255))
    box = (x0, y, x1, y + 2)
    clip = (max(box[0], 0), max(box[1], 0), min(box[2], W), min(box[3], H))
    if clip[2] > clip[0]:
        src = core.crop((clip[0] - box[0], 0, clip[2] - box[0], 2))
        if strength < 1.0:
            src = src.point(lambda v: int(v * strength))
        region = glow.crop(clip)
        glow.paste(ImageChops.add(region, src), (clip[0], clip[1]))


class Sprite:
    """A product image that can be rotated / scaled / faded per frame."""

    def __init__(self, img):
        self.img = img
        self._cache = {}

    def get(self, angle=0.0, scale=1.0):
        key = (round(angle * 2) / 2, round(scale, 3))
        if key in self._cache:
            return self._cache[key]
        im = self.img
        if abs(angle) > 0.01:
            im = im.rotate(angle, resample=Image.BICUBIC, expand=True)
        if abs(scale - 1.0) > 0.001:
            im = im.resize((max(int(im.width * scale), 1), max(int(im.height * scale), 1)), Image.LANCZOS)
        if len(self._cache) > 220:
            self._cache.clear()
        self._cache[key] = im
        return im

    def draw(self, canvas, center, angle=0.0, scale=1.0, opacity=1.0):
        im = self.get(angle, scale)
        blit(canvas, im, (center[0], center[1]), opacity, anchor="center")


def ken_burns(canvas, src, t, zoom_from=1.0, zoom_to=1.12, pan=(0, 0), fade=1.0, blur=0.0):
    """Crop a slowly zooming/pwning window out of a full-bleed image."""
    z = lerp(zoom_from, zoom_to, smooth(t))
    cw = int(src.width / z)
    ch = int(src.height / z)
    cx = int(src.width / 2 + pan[0] * (src.width - cw) / 2)
    cy = int(src.height / 2 + pan[1] * (src.height - ch) / 2)
    cx = int(clamp(cx, cw // 2, src.width - cw // 2))
    cy = int(clamp(cy, ch // 2, src.height - ch // 2))
    box = (cx - cw // 2, cy - ch // 2, cx + cw // 2, cy + ch // 2)
    crop = src.crop(box).resize((W, H), Image.BICUBIC)
    if blur:
        crop = crop.filter(ImageFilter.GaussianBlur(blur))
    if fade < 0.999:
        canvas.paste(crop, (0, 0))
        canvas.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0))
        canvas = Image.blend(canvas, crop, fade)
    else:
        canvas.paste(crop, (0, 0))
    return canvas
