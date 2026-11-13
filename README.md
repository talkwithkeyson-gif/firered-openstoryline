# AURA X1 — “Upcoming Phone” Concept Film

A **73-second full film** (plus a 35.6-second cut-down) for a fictional upcoming
flagship phone — **AURA X1**. Vertical 1080×1920, 30 fps, narrated in **Nepali** with an
original synthesised soundtrack, Nepali + English subtitles, and fully procedural
motion-graphics.

Everything here is generated from code in this repo: no stock footage, no external
editing app. The device renders are AI-generated concept art (`assets/img/`), and the
piece is explicitly a **concept sample**, not a real product announcement.

## Deliverables

| File | What it is |
| --- | --- |
| `aura_x1_full.mp4` | **The full film** — 1080×1920, 30 fps, H.264 + AAC, 1:13 |
| `aura_x1_full.srt` | Bilingual captions for the full film (15 cues) |
| `aura_x1_teaser.mp4` | The original 35.6 s teaser cut |
| `aura_x1_teaser.srt` | Bilingual captions for the teaser (7 cues) |
| `poster.png` | 1080×1920 poster frame |
| `endcard.jpg` | End-card still |

## Full film (73 s) — 15 beats

| Time | Scene | On screen |
| --- | --- | --- |
| 0:00 | Cold open | केही नयाँ आउँदैछ। |
| 0:03 | Hero reveal | AURA X1 · औरा एक्स वान |
| 0:09 | Craft | हरेक विवरण, हातले बनाए जस्तै (in-hand shot) |
| 0:14 | Display | 6.8" edge-to-edge · 144Hz |
| 0:20 | Camera | 200MP · रात पनि दिन जस्तै |
| 0:26 | Night mode | आँखाले देख्न नसक्ने रातमा पनि (night street photo) |
| 0:29 | Build | टाइटेनियम · 6.9MM |
| 0:35 | Durability | IP68 · पानी र धुलोबाट सुरक्षित |
| 0:40 | Battery | 5,000mAh · 80W · animated charge ring |
| 0:45 | Chip | 2× FASTER · animated silicon die + data pulses |
| 0:51 | Software | 7 YEARS · सात वर्षको अपडेट |
| 0:56 | Colours | चार रङ। एउटै विरासत। (four-finish lineup) |
| 1:00 | Launch | डिसेम्बर 2026 · worldwide |
| 1:04 | Pre-order | CTA pill · अहिले नै दर्ता गर्नुहोस् |
| 1:08 | Lockup | AURA X1 · भोलिको फोन। आज। |

## Teaser cut (35.6 s)

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

# full film
python scripts/long_render.py --audio-only      # -> build/audio_full.wav
python scripts/long_render.py                   # -> aura_x1_full.mp4  (~7 min on 2 cores)
python scripts/subtitles.py --full              # -> aura_x1_full.srt

# 35.6 s teaser cut
python scripts/audio.py
python scripts/render.py
python scripts/subtitles.py

# quick PNG stills at chosen timestamps
python scripts/long_render.py --preview 5,20,37,71
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

Narration lines and their start times live in `scripts/long_render.py` (`VO_PLAN`,
15 lines) for the full film and `scripts/audio.py` (`VO_PLAN`, 7 lines) for the teaser.
On-screen copy lives in `long_render.py` (one function per scene) and the caption text
in `scripts/subtitles.py` (`FULL_LINES` / `SHORT_LINES`). Scene boundaries are the
`SCENES` list. Every scene duration is derived from those two lists, so retiming is a
matter of editing the numbers — the score, risers and flashes follow automatically.

Device facts are invented for the demo (6.8" 144Hz, 200MP, 6.9mm titanium, IP68,
5,000mAh/80W, 7 years of updates, four finishes, December 2026) — swap them for your
real specs. The film is labelled "CONCEPT FILM" on the end card.
