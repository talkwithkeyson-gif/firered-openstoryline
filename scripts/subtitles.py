"""Writes Nepali + English .srt captions using the real voice-over timings.

python scripts/subtitles.py            # short cut  -> aura_x1_teaser.srt
python scripts/subtitles.py --full     # full film  -> aura_x1_full.srt
"""
import argparse
import os
import re
import subprocess
import sys

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio import VO_PLAN as SHORT_PLAN, ROOT  # noqa: E402

# --- short teaser (35.6 s) -------------------------------------------------
SHORT_LINES = [
    ("केही नयाँ आउँदैछ।", "Something new is coming."),
    ("औरा एक्स वान। हाम्रो सबैभन्दा पातलो, सबैभन्दा बलियो फोन।",
     "AURA X1. Our thinnest, strongest phone yet."),
    ("छ दशमलव आठ इन्चको डिस्प्ले, जुन एक सय चवालीस हर्जमा बग्छ।",
     "A 6.8-inch display that flows at 144Hz."),
    ("दुई सय मेगापिक्सेलको क्यामेरा। रात पनि दिन जस्तै।",
     "A 200MP camera. Night looks like day."),
    ("एयरोस्पेस ग्रेड टाइटेनियम। छ दशमलव नौ मिलिमिटर मात्र पातलो।",
     "Aerospace-grade titanium. Just 6.9mm thin."),
    ("आउँदो महिना, तपाईंको हातमा।", "In your hands next month."),
    ("औरा एक्स वान। भोलिको फोन, आज।", "AURA X1. Tomorrow's phone, today."),
]

# --- full film (73.2 s) ----------------------------------------------------
FULL_LINES = [
    ("केही नयाँ आउँदैछ।", "Something new is coming."),
    ("औरा एक्स वान। हाम्रो सबैभन्दा पातलो, सबैभन्दा बलियो फोन।",
     "AURA X1. Our thinnest, strongest phone yet."),
    ("हरेक विवरण, हातले बनाए जस्तै।", "Every detail, as if made by hand."),
    ("छ दशमलव आठ इन्चको डिस्प्ले, जुन एक सय चवालीस हर्जमा बग्छ।",
     "A 6.8-inch display that flows at 144Hz."),
    ("दुई सय मेगापिक्सेलको क्यामेरा। रात पनि दिन जस्तै।",
     "A 200MP camera. Night looks like day."),
    ("आँखाले देख्न नसक्ने रातमा पनि।", "Even in nights the eye can't see."),
    ("एयरोस्पेस ग्रेड टाइटेनियम। छ दशमलव नौ मिलिमिटर मात्र पातलो।",
     "Aerospace-grade titanium. Just 6.9mm thin."),
    ("पानी र धुलोबाट सुरक्षित। आई पी अठसट्ठी।", "Protected from water and dust. IP68."),
    ("पाँच हजार एम ए एच ब्याट्री। एक चार्जमा पूरा दिन।",
     "A 5,000 mAh battery. A whole day on one charge."),
    ("नयाँ चिपसेट। दुई गुणा छिटो, धेरै कम तात्ने।",
     "A new chipset. Twice as fast, far cooler."),
    ("सात वर्षको अपडेट। हरेक दिन नयाँ जस्तै।",
     "Seven years of updates. Like new, every day."),
    ("चार रङ। एउटै विरासत।", "Four colours. One legacy."),
    ("आउँदो महिना, तपाईंको हातमा।", "In your hands next month."),
    ("अहिले नै दर्ता गर्नुहोस्, पहिलो पाउनेमा।", "Register now — be first in line."),
    ("औरा एक्स वान। भोलिको फोन, आज।", "AURA X1. Tomorrow's phone, today."),
]


def duration(path):
    out = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", path],
                         capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def stamp(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write(plan, lines, out):
    blocks = []
    for i, ((name, start), (np_text, en_text)) in enumerate(zip(plan, lines), start=1):
        d = duration(os.path.join(ROOT, "assets", "vo", name))
        blocks.append(f"{i}\n{stamp(start)} --> {stamp(start + d)}\n{np_text}\n{en_text}\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    print("wrote", out, f"({len(blocks)} cues)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    if args.full:
        from long_render import VO_PLAN as FULL_PLAN
        write(FULL_PLAN, FULL_LINES, os.path.join(ROOT, "aura_x1_full.srt"))
    else:
        write(SHORT_PLAN, SHORT_LINES, os.path.join(ROOT, "aura_x1_teaser.srt"))


if __name__ == "__main__":
    main()
