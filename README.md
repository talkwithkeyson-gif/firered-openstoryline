# AURA X1 — “Upcoming Phone” Concept Teaser

A 35.6-second, vertical (1080×1920, 30 fps) product teaser for a fictional upcoming
flagship phone — **AURA X1** — narrated in **Nepali** with an original synthesised
soundtrack, Nepali + English subtitles, and fully procedural motion-graphics.

Everything here is generated from code in this repo: no stock footage, no external
editing app. The device renders are AI-generated concept art (`assets/img/`), and the
piece is explicitly a **concept sample**, not a real product announcement.

## Deliverables

| File | What it is |
| --- | --- |
| `aura_x1_teaser.mp4` | The video — 1080×1920, 30 fps, H.264 + AAC, ~35.6 s |
| `aura_x1_teaser.srt` | Bilingual (Nepali / English) captions timed to the voice-over |
| `poster.png` | 1080×1920 poster frame |
| `endcard.jpg` | End-card still |

## Storyboard

| Time | Scene | Copy (Nepali) | English |
| --- | --- | --- | --- |
| 0.0–3.2 | Cold open | केही नयाँ आउँदैछ। | Something new is coming. |
| 3.2–8.8 | Hero reveal | औरा एक्स वान — हाम्रो सबैभन्दा पातलो, सबैभन्दा बलियो फोन। | AURA X1 — our thinnest, strongest phone yet |
| 8.8–14.8 | Display | छ दशमलव आठ इन्चको डिस्प्ले, १४४ हर्ज | 6.8" edge-to-edge, 144Hz |
| 14.8–20.0 | Camera | दुई सय मेगापिक्सेलको क्यामेरा। रात पनि दिन जस्तै। | 200MP, night looks like day |
| 20.0–27.0 | Build | एयरोस्पेस ग्रेड टाइटेनियम — ६.९ मिलिमिटर | Aerospace titanium, 6.9mm |
| 27.0–30.3 | Launch | आउँदो महिना — डिसेम्बर 2026 | December 2026 |
| 30.3–35.6 | Lockup | भोलिको फोन। आज। | Tomorrow's phone, today. |

## Rebuild it

```bash
pip install pillow numpy uharfbuzz freetype-py fonttools brotli imageio-ffmpeg

python scripts/audio.py        # voice-over bed + synthesised score -> build/audio_mix.wav
python scripts/render.py       # every frame -> aura_x1_teaser.mp4
python scripts/subtitles.py    # -> aura_x1_teaser.srt
python scripts/render.py --preview 2,6,12,18,24,29,34   # quick PNG stills
```

Fonts (Inter and Noto Sans Devanagari, both OFL) are vendored under `assets/fonts/`.

### Notes on the pipeline

- **Devanagari shaping.** Pillow here has no libraqm, so matras and conjuncts would
  render incorrectly. `scripts/textrender.py` shapes with HarfBuzz (`uharfbuzz`) and
  rasterises with FreeType (`freetype-py`), so `दृ`, `न्यू`, `छन्` etc. come out right.
- **Mixed scripts.** `render_core.mixed_mask()` splits a line into Devanagari and
  Latin runs so "डिसेम्बर 2026" uses each script's proper face and digit style.
- **Product cutouts.** The AI renders sit on black; `load_product()` auto-crops to the
  device and derives a luminance-based matte, so the phone composites over the
  animated gradient backgrounds.
- **Soundtrack.** `scripts/audio.py` builds a minor-key drone + pad, soft heartbeat
  kick, noise risers, whooshes and a short convolution reverb, then ducks the music
  under the narration (measured ≈12 dB voice-over-over-bed separation).
- **Look.** Vignette, additive light streaks, soft glare sweeps, subtle film grain,
  scene-to-scene background crossfades and white flashes on each cut.

## Changing copy or timing

Narration lines and their start times live in `scripts/audio.py` (`VO_PLAN`), and the
matching on-screen copy lives in `scripts/render.py` (one function per scene) plus
`scripts/subtitles.py` (`LINES`). Scene boundaries are the `S1…S7` constants.

Device facts are invented for the demo (6.8" 144Hz, 200MP, 6.9mm titanium,
December 2026) — swap them for your real specs.
