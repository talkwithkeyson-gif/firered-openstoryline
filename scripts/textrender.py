"""Shaped text rendering helpers (HarfBuzz shaping + FreeType rasterizing).

Pillow in this environment is built without libraqm, so Devanagari would render
with broken conjuncts / misplaced matras. We shape with HarfBuzz and rasterize
with FreeType directly, then composite into Pillow images.
"""
import freetype
import numpy as np
import uharfbuzz as hb
from PIL import Image

_FACE_CACHE = {}
_HB_CACHE = {}


def _hb(path):
    if path not in _HB_CACHE:
        blob = hb.Blob.from_file_path(path)
        face = hb.Face(blob)
        _HB_CACHE[path] = hb.Font(face)
    return _HB_CACHE[path]


def _ft(path, px):
    """Return a FreeType face sized so that 1 font unit maps to `px`/upem pixels."""
    hbfont = _hb(path)
    upem = hbfont.face.upem
    key = (path, round(px, 4))
    if key not in _FACE_CACHE:
        f = freetype.Face(path)
        f.set_char_size(int(round(px * 64)))  # 72dpi => em size == px
        _FACE_CACHE[key] = f
    return _FACE_CACHE[key]


def shape(text, font_path, px, language="ne"):
    """Shape text. Returns (glyph bitmaps, total advance, ascender_px, descender_px, upem)."""
    hbfont = _hb(font_path)
    upem = hbfont.face.upem
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {})
    ft = _ft(font_path, px)

    scale = px / upem
    items = []
    chars = []
    pen_x = 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        ft.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_TARGET_NORMAL)
        if True:
            bm = ft.glyph.bitmap
            w, h = bm.width, bm.rows
            if w and h:
                arr = np.array(bm.buffer, dtype=np.uint8).reshape(h, bm.pitch)[:, :w]
                glyph = Image.fromarray(arr.copy(), mode="L")
                x = pen_x + pos.x_offset * scale + ft.glyph.bitmap_left
                y = -(pos.y_offset * scale + ft.glyph.bitmap_top)
                items.append((glyph, x, y))
                chars.append(text[info.cluster] if info.cluster < len(text) else "")
        pen_x += pos.x_advance * scale

    return (items, chars), pen_x, upem, upem, upem


def layout(text, font_path, px, language="ne"):
    """Lay out text; returns list of (glyph_img, x, y) relative to a top-left origin
    of the shaping origin, plus measured width."""
    (items, chars), adv, asc, desc, upem = shape(text, font_path, px, language)
    return items, adv, asc, desc, upem, chars


def draw_block(canvas, items, ox, oy, fill=(255, 255, 255), opacity=1.0):
    """Composite shaped glyphs onto a Pillow 'RGB'/'RGBA' canvas at origin (ox, oy)."""
    if opacity <= 0:
        return canvas
    for glyph, x, y in items:
        a = glyph
        if opacity < 1.0:
            a = a.point(lambda v: int(v * opacity))
        solid = Image.new("RGB", glyph.size, fill)
        canvas.paste(solid, (int(round(ox + x)), int(round(oy + y))), a)
    return canvas


def measure(text, font_path, px, language="ne"):
    items, adv, asc, desc, upem, _ = layout(text, font_path, px, language)
    top = min([y for _, _, y in items] or [0])
    bottom = max([y + g.size[1] for g, _, y in items] or [0])
    return adv, top, bottom


def draw_centered(canvas, text, font_path, px, cy, fill=(255, 255, 255), opacity=1.0,
                  language="ne", tracking=0.0):
    """Draw text horizontally centred, with its optical middle at pixel row `cy`."""
    items, adv, _, _, _, chars = layout(text, font_path, px, language)
    if tracking:
        items = [(g, x + i * tracking * px, y) for i, (g, x, y) in enumerate(items)]
        adv += tracking * px * max(len(items) - 1, 0)
    top = min([y for _, _, y in items] or [0])
    bottom = max([y + g.size[1] for g, _, y in items] or [0])
    h = bottom - top
    cx = canvas.size[0] / 2
    ox = cx - adv / 2
    oy = cy - (top + h / 2)
    draw_block(canvas, items, ox, oy, fill, opacity)
    return ox, oy, adv, h


def text_mask(text, font_path, px, fill=(255, 255, 255), language="ne"):
    """Render text to a tight RGBA image (used for cached overlays)."""
    items, adv, _, _, _, _ = layout(text, font_path, px, language)
    if not items:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    top = min(y for _, _, y in items)
    left = min(x for _, x, _ in items)
    bottom = max(y + g.size[1] for g, _, y in items)
    right = max(x + g.size[0] for g, x, _ in items)
    w, h = int(np.ceil(right - left)) + 2, int(np.ceil(bottom - top)) + 2
    mask = Image.new("L", (w, h), 0)
    for g, x, y in items:
        mask.paste(g, (int(round(x - left)) + 1, int(round(y - top)) + 1), g)
    img = Image.new("RGBA", (w, h), fill + (0,))
    img.putalpha(mask)
    return img
