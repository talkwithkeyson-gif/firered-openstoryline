"""Writes Nepali + English .srt captions using the real voice-over timings."""
import os
import re
import subprocess
import sys

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from audio import VO_PLAN, ROOT  # noqa: E402

# (nepali, english) per voice-over line, in the same order as VO_PLAN
LINES = [
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


def main():
    out = os.path.join(ROOT, "aura_x1_teaser.srt")
    blocks = []
    for i, ((name, start), (np_text, en_text)) in enumerate(zip(VO_PLAN, LINES), start=1):
        d = duration(os.path.join(ROOT, "assets", "vo", name))
        end = start + d
        blocks.append(f"{i}\n{stamp(start)} --> {stamp(end)}\n{np_text}\n{en_text}\n")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks))
    print("wrote", out)


if __name__ == "__main__":
    main()
