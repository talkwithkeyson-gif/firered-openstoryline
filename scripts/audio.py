"""Builds the soundtrack: synthesised cinematic bed + Nepali voice-over.

Output: build/audio_mix.wav (48 kHz, stereo, 16-bit)
"""
import os
import subprocess
import sys

import numpy as np
import imageio_ffmpeg

SR = 48000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
VO = os.path.join(ROOT, "assets", "vo")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Voice-over segments: (file, start seconds). Timings follow the visual beats.
VO_PLAN = [
    ("np_s1.mp3", 0.60),    # केही नयाँ आउँदैछ।
    ("np_s2.mp3", 3.35),    # औरा एक्स वान...
    ("np_s3.mp3", 8.90),    # डिस्प्ले
    ("np_s4.mp3", 14.90),   # क्यामेरा
    ("np_s5.mp3", 20.10),   # टाइटेनियम
    ("np_s6.mp3", 27.10),   # आउँदो महिना
    ("np_s7.mp3", 30.40),   # लकअप
]
TOTAL = 35.6


def decode_mp3(path):
    cmd = [FFMPEG, "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(SR),
           "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def env_adsr(n, a, d, s, r):
    e = np.zeros(n)
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    ai, di, ri = max(ai, 1), max(di, 1), max(ri, 1)
    ai, di, ri = min(ai, n), min(di, n - ai), min(ri, n - ai - di)
    e[:ai] = np.linspace(0, 1, ai)
    e[ai:ai + di] = np.linspace(1, s, di)
    e[ai + di:ai + di + ri] = np.linspace(s, 0, ri)
    return e


def lowpass(x, cutoff, sr=SR, order=2):
    """Simple one-pole cascade low-pass (cheap, smooth)."""
    a = np.exp(-2 * np.pi * cutoff / sr)
    y = x.copy()
    for _ in range(order):
        out = np.empty_like(y)
        acc = 0.0
        for i in range(len(y)):  # per-sample; segments are short
            acc = (1 - a) * y[i] + a * acc
            out[i] = acc
        y = out
    return y


def fft_lowpass(x, cutoff, sr=SR):
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    H = 1.0 / np.sqrt(1 + (freqs / cutoff) ** 4)
    return np.fft.irfft(X * H, n=len(x))


def fft_highpass(x, cutoff, sr=SR):
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    H = 1.0 / np.sqrt(1 + (cutoff / np.maximum(freqs, 1e-6)) ** 4)
    return np.fft.irfft(X * H, n=len(x))


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def drone(n, t):
    """Dark sustained bed: stacked fifths with slow beating + filtered noise air."""
    sig = np.zeros(n)
    base = 55.0
    for mult, amp, det in [(1, 0.55, 0.0), (2, 0.22, 0.35), (3, 0.14, -0.25),
                           (4, 0.07, 0.5), (6, 0.035, -0.4)]:
        freq = base * mult + det
        lfo = 1 + 0.12 * np.sin(2 * np.pi * (0.07 + 0.02 * mult) * t + mult)
        sig += amp * lfo * np.sin(2 * np.pi * freq * t)
    air = fft_lowpass(noise(n, 1), 900) * 0.30
    air = fft_highpass(air, 120)
    swell = 0.55 + 0.45 * np.sin(2 * np.pi * 0.045 * t - 1.2)
    sig = sig * 0.55 + air * swell
    return sig


def pad_chords(n, t):
    """Slow minor-key pad that blooms at scene changes."""
    notes = [110.0, 130.81, 164.81, 220.0, 261.63]  # A minor-ish
    sig = np.zeros(n)
    for i, f in enumerate(notes):
        amp = 0.13 / (1 + 0.35 * i)
        vib = 1 + 0.0015 * np.sin(2 * np.pi * (0.15 + 0.03 * i) * t)
        sig += amp * np.sin(2 * np.pi * f * vib * t + i) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.04 * t + i * 1.7))
    sig = fft_lowpass(sig, 2400)
    return sig


def kick(t):
    """Soft sub kick: 52 Hz body with fast pitch drop, quiet attack click."""
    n = len(t)
    body = np.sin(2 * np.pi * (52 * t - 14 * t ** 2)) * np.exp(-t * 11)
    click = fft_highpass(noise(n, 7), 2500) * np.exp(-t * 260) * 0.10
    return body * 0.9 + click


def heartbeat_track(n, t, beat=0.62, start=8.4, end=35.0, gain=0.55):
    sig = np.zeros(n)
    i = start
    k = 0
    while i < end:
        dur = 0.55
        m = int(dur * SR)
        s = int(i * SR)
        if s + m <= n:
            kk = kick(np.arange(m) / SR)
            amp = gain * (0.7 + 0.3 * np.sin(i * 0.7))
            sig[s:s + m] += kk * amp
        i += beat
        k += 1
    return sig


def riser(n, t, starts, length=1.6, gain=0.22):
    """Noise risers into scene changes."""
    sig = np.zeros(n)
    for st in starts:
        m = int(length * SR)
        s = int((st - length * 0.85) * SR)
        if s < 0 or s + m > n:
            continue
        idx = np.arange(m)
        tt = idx / SR
        envn = (tt / (m / SR)) ** 2.2
        nz = noise(m, int(st * 100) % 9999)
        # sweep brightness upward by crossfading two bands
        lo = fft_lowpass(nz, 700) * (1 - envn)
        hi = fft_highpass(nz, 2600) * envn
        sig[s:s + m] += (lo + hi) * envn * gain
    return sig


def shimmer(n, t, gain=0.10, start=3.0, end=35.0, step=0.31):
    """High bell-ish arpeggio, very quiet, adds sparkle over product shots."""
    scale = [880.0, 987.77, 1174.66, 1318.51, 1567.98, 1760.0]
    sig = np.zeros(n)
    i = start
    k = 0
    while i < end:
        f = scale[k % len(scale)] * (2 if (k // len(scale)) % 2 else 1)
        dur = 1.4
        m = int(dur * SR)
        s = int(i * SR)
        if s + m <= n:
            tt = np.arange(m) / SR
            e = np.exp(-tt * 4.2) * (1 - np.exp(-tt * 300))
            sig[s:s + m] += np.sin(2 * np.pi * f * tt) * e * gain * (0.65 + 0.35 * np.sin(k))
        i += step
        k += 1
    return sig


def whoosh(n, t, at, gain=0.30, length=1.1):
    m = int(length * SR)
    s = int(at * SR)
    if s + m > n:
        return np.zeros(n)
    out = np.zeros(n)
    idx = np.arange(m) / SR
    envn = np.sin(np.pi * idx / length) ** 2
    nz = noise(m, 31)
    band = fft_highpass(fft_lowpass(nz, 4200), 400)
    out[s:s + m] = band * envn * gain
    return out


def stereoize(sig, width=0.5, seed=5):
    """Turn mono into a wide-ish stereo pair via a tiny Haas + noise decorrelation."""
    d = int(0.011 * SR)
    left = np.copy(sig)
    right = np.roll(sig, d) * 0.92
    right += noise(len(sig), seed) * 0.004
    return np.stack([left * (1 - 0.15 * width), right * (1 + 0.03 * width)], axis=1)


def smooth_env(mask, ms=120):
    k = max(int(ms * SR / 1000), 1)
    ker = np.hanning(k)
    ker /= ker.sum()
    return np.convolve(mask, ker, mode="same")


def build(vo_plan=None, total=None, out_name="audio_mix.wav", seed=1):
    vo_plan = vo_plan or VO_PLAN
    total = total or TOTAL
    n = int(total * SR)
    t = np.arange(n) / SR
    os.makedirs(BUILD, exist_ok=True)

    # ---- voice-over -------------------------------------------------------
    vo = np.zeros(n)
    vo_mask = np.zeros(n)
    for name, start in vo_plan:
        clip = decode_mp3(os.path.join(VO, name))
        clip = clip / (np.max(np.abs(clip)) + 1e-9) * 0.95
        # tiny fades to avoid clicks
        f = int(0.012 * SR)
        clip[:f] *= np.linspace(0, 1, f)
        clip[-f:] *= np.linspace(1, 0, f)
        s = int(start * SR)
        e = min(s + len(clip), n)
        vo[s:e] += clip[:e - s]
        vo_mask[s:e] = 1.0

    # ---- music ------------------------------------------------------------
    music = drone(n, t) * 0.85 + pad_chords(n, t)
    music += heartbeat_track(n, t, end=total)
    music += shimmer(n, t, end=total)
    music += riser(n, t, [3.2, 8.8, 14.8, 20.0, 27.0, 30.3])
    music += whoosh(n, t, 30.3, gain=0.30)
    music += whoosh(n, t, 3.2, gain=0.16)
    music += whoosh(n, t, 20.0, gain=0.20)

    # intro fade + outro fade
    music *= np.clip(t / 1.2, 0, 1)
    music *= np.clip((total - t) / 2.2, 0, 1)
    music = np.tanh(music * 1.15) * 0.9  # gentle saturation

    # ---- ducking ----------------------------------------------------------
    duck = 1.0 - 0.55 * smooth_env(vo_mask, 260)
    music *= duck * 0.42

    # ---- reverb tail on music (short, cheap FFT convolution) --------------
    ir_len = int(1.6 * SR)
    ir_t = np.arange(ir_len) / SR
    ir = noise(ir_len, 99) * np.exp(-ir_t * 3.1)
    ir = fft_lowpass(ir, 3200)
    ir /= np.sqrt(np.sum(ir ** 2))
    m = len(music) + ir_len - 1
    nfft = 1 << (m - 1).bit_length()
    wet = np.fft.irfft(np.fft.rfft(music, nfft) * np.fft.rfft(ir, nfft), nfft)[:len(music)]
    music = music + wet * 0.20

    mix = music * 0.55 + vo * 0.95
    mix = np.tanh(mix * 1.05)

    # master: normalise to -1 dBFS, then tame the extreme peaks a touch
    mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.89
    stereo = stereoize(mix, width=0.6)
    stereo = np.stack([np.tanh(stereo[:, 0] * 1.02), np.tanh(stereo[:, 1] * 1.02)], axis=1)
    stereo = stereo / (np.max(np.abs(stereo)) + 1e-9) * 0.89

    out = os.path.join(BUILD, out_name)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
    import wave
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", out, "dur", round(total, 2), "lines", len(vo_plan))
    return total


def main():
    return build()


if __name__ == "__main__":
    main()
