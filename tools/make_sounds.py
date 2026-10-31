"""Synthesize the game's sound effects into assets/sounds/*.wav.

Every effect is made from sine waves, filtered noise and envelopes with numpy,
so the files are ours (no license to track) and can be remade at any time:

    python tools/make_sounds.py

The noise uses a fixed seed per sound, so running it twice gives the same files.
"""

import sys
import wave
from pathlib import Path

import numpy as np

RATE = 44100
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"


# --- building blocks -----------------------------------------------------------------
def t_axis(seconds):
    return np.arange(int(RATE * seconds)) / RATE


def tone(freq, seconds, shape="sine"):
    """A tone; ``freq`` may be a number or an array (a sweep), in Hz."""
    n = int(RATE * seconds)
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    if shape == "sine":
        return np.sin(phase)
    if shape == "triangle":
        return 2 / np.pi * np.arcsin(np.sin(phase))
    if shape == "soft_square":                      # odd harmonics, rounded edges
        return np.tanh(3.0 * np.sin(phase))
    raise ValueError(shape)


def sweep(f0, f1, seconds, curve="exp"):
    x = np.linspace(0.0, 1.0, int(RATE * seconds))
    return f0 * (f1 / f0) ** x if curve == "exp" else f0 + (f1 - f0) * x


def decay(seconds, tau):
    """exp(-t / tau) with a 2 ms fade-in so nothing clicks at the start."""
    t = t_axis(seconds)
    return np.exp(-t / tau) * np.minimum(1.0, t / 0.002)


def adsr(seconds, attack=0.005, release=0.05):
    t = t_axis(seconds)
    env = np.minimum(1.0, t / attack)
    return env * np.clip((seconds - t) / release, 0.0, 1.0)


def noise(seconds, rng):
    return rng.uniform(-1.0, 1.0, int(RATE * seconds))


def lowpass(x, cutoff):
    """One-pole low-pass; ``cutoff`` may be a number or an array (Hz)."""
    c = np.broadcast_to(np.asarray(cutoff, dtype=float), x.shape)
    a = 1.0 - np.exp(-2 * np.pi * c / RATE)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def highpass(x, cutoff):
    return x - lowpass(x, cutoff)


def bandpass(x, low, high):
    return lowpass(highpass(x, low), high)


def mix(*parts):
    """Sum parts of any lengths (each starts at 0) into one array."""
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[:len(p)] += p
    return out


def at(seconds, part):
    """Delay ``part`` by ``seconds`` (pad the front with silence)."""
    return np.concatenate([np.zeros(int(RATE * seconds)), part])


def note(freq, seconds, tau, shape="sine", harmonics=((2, 0.3), (3, 0.12))):
    """A plucked note with a few soft harmonics."""
    x = tone(freq, seconds, shape)
    for k, g in harmonics:
        x = x + g * tone(freq * k, seconds) * decay(seconds, tau * 0.6)
    return x * decay(seconds, tau)


def bell(freq, seconds, tau):
    """Metallic bell: inharmonic partials decaying at different speeds."""
    parts = ((1.0, 1.0, 1.0), (2.76, 0.45, 0.6), (5.40, 0.25, 0.35), (8.93, 0.12, 0.2))
    return sum(g * tone(freq * r, seconds) * decay(seconds, tau * d) for r, g, d in parts)


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


# --- the sounds ----------------------------------------------------------------------
# Each returns (samples, peak level in dBFS). Peaks are set per sound so the
# small UI ticks stay quieter than the big events.
def s_click(rng):
    x = tone(sweep(2200, 1500, 0.03), 0.03) * decay(0.03, 0.006)
    return mix(x, 0.3 * highpass(noise(0.006, rng), 3000) * decay(0.006, 0.002)), -12


def s_error(rng):
    buzz = lambda: tone(165, 0.09, "soft_square") * adsr(0.09, 0.004, 0.03)
    return lowpass(mix(buzz(), at(0.12, buzz())), 1800), -16


def s_launch(rng):
    d = 0.7
    whoosh = bandpass(noise(d, rng), 200, sweep(400, 3000, d)) * adsr(d, 0.04, 0.4)
    rise = tone(sweep(110, 420, d), d) * decay(d, 0.3)
    thump = tone(sweep(90, 45, 0.25), 0.25) * decay(0.25, 0.08)
    return mix(1.6 * whoosh, 0.5 * rise, 0.8 * thump), -4


def s_thruster_loop(rng):
    """2 s rumble that loops with no seam: every component repeats exactly."""
    d = 2.0
    n = int(RATE * d)
    spectrum = np.zeros(n // 2 + 1, dtype=complex)
    freqs = np.fft.rfftfreq(n, 1 / RATE)
    band = (freqs > 30) & (freqs < 900)
    shape = 1.0 / np.maximum(freqs[band], 30) ** 0.8          # darker toward the top
    spectrum[band] = shape * np.exp(2j * np.pi * rng.random(band.sum()))
    rumble = np.fft.irfft(spectrum, n)
    rumble /= np.max(np.abs(rumble))
    t = t_axis(d)
    hum = 0.25 * np.sin(2 * np.pi * 55 * t) + 0.1 * np.sin(2 * np.pi * 110 * t)
    flutter = 1.0 + 0.15 * np.sin(2 * np.pi * 6 * t)          # 6 Hz: 12 cycles per loop
    return (rumble + hum) * flutter, -14


def s_life_lost(rng):
    d = 0.55
    vib = 1.0 + 0.03 * np.sin(2 * np.pi * 9 * t_axis(d))
    x = tone(sweep(620, 150, d) * vib, d, "triangle") * adsr(d, 0.01, 0.2)
    return lowpass(x, 2500), -12


def s_win(rng):
    notes = (72, 76, 79, 84)                       # C E G C, up the arpeggio
    parts = [at(0.09 * i, note(midi(n), 0.5 if i < 3 else 1.1, 0.18 if i < 3 else 0.45, "triangle"))
             for i, n in enumerate(notes)]
    sparkle = at(0.27, 0.25 * bell(midi(96), 0.8, 0.25))
    return mix(*parts, sparkle), -5


def s_game_over(rng):
    notes = ((67, 0.0, 0.35), (63, 0.28, 0.35), (60, 0.56, 0.35), (48, 0.84, 1.0))
    parts = [at(start, note(midi(n), length + 0.3, length * 0.6, "triangle")) for n, start, length in notes]
    return lowpass(mix(*parts), 3000), -5


def s_shield_break(rng):
    d = 0.6
    crack = highpass(noise(0.08, rng), 2500) * decay(0.08, 0.02)
    shards = [at(rng.uniform(0, 0.12), 0.3 * tone(rng.uniform(2500, 7000), d) * decay(d, rng.uniform(0.04, 0.15)))
              for _ in range(14)]
    return mix(crack, *shards), -6


def s_shockwave(rng):
    d = 1.0
    boom = tone(sweep(85, 30, d), d) * decay(d, 0.28)
    blast = lowpass(noise(d, rng), sweep(2500, 150, d)) * decay(d, 0.22)
    return mix(1.0 * boom, 1.4 * blast), -3


def s_extratime(rng):
    tick = lambda f: bandpass(noise(0.03, rng), 2000, 6000) * decay(0.03, 0.006) + \
        0.5 * tone(f, 0.03) * decay(0.03, 0.01)
    chime = mix(at(0.2, note(midi(79), 0.4, 0.15)), at(0.28, note(midi(84), 0.6, 0.25)))
    return mix(tick(2400), at(0.1, tick(1800)), 0.8 * chime), -7


def s_shield(rng):
    d = 0.7
    t = t_axis(d)
    shimmer = 1.0 + 0.4 * np.sin(2 * np.pi * 18 * t)
    chord = sum(tone(sweep(f * 0.7, f, d), d) for f in (523, 659, 784))
    return chord * shimmer * adsr(d, 0.08, 0.35), -8


def s_life(rng):
    notes = (67, 72, 76, 79)                       # G C E G: bright and rising
    parts = [at(0.07 * i, note(midi(n), 0.35, 0.12, "soft_square", ())) for i, n in enumerate(notes)]
    return lowpass(mix(*parts, at(0.28, 0.4 * bell(midi(91), 0.6, 0.2))), 5000), -7


def s_money(rng):
    return mix(0.8 * bell(1320, 0.25, 0.06), at(0.06, bell(1760, 0.5, 0.15))), -8


def s_bounce(rng):
    d = 0.18
    thud = tone(sweep(170, 70, d), d) * decay(d, 0.05)
    knock = bandpass(noise(0.03, rng), 300, 2500) * decay(0.03, 0.008)
    return mix(thud, 0.6 * knock), -8


def s_warp(rng):
    d = 0.9
    x = np.linspace(0, 1, int(RATE * d))
    pitch = 300 * 2 ** (2.0 * np.sin(np.pi * x) - 1.0)        # down into the hole, up out of the other
    swirl = tone(pitch, d) * (1 + 0.5 * np.sin(2 * np.pi * 14 * t_axis(d)))
    air = bandpass(noise(d, rng), 300, pitch * 4)
    return (0.6 * swirl + 0.8 * air) * adsr(d, 0.05, 0.3), -7


def s_blip(rng):
    d = 0.045
    return tone(620, d, "soft_square") * decay(d, 0.015), -18


def s_purchase(rng):
    coins = [at(0.05 * i, 0.6 * bell(f, 0.3, 0.07)) for i, f in enumerate((1568, 1976, 2349))]
    ding = at(0.18, bell(1046, 0.8, 0.3))
    return mix(*coins, ding), -6


SOUNDS = {name[2:]: fn for name, fn in globals().items() if name.startswith("s_")}


# --- output --------------------------------------------------------------------------
def render(name):
    """The sound ``name`` as 16-bit samples (numpy int16)."""
    rng = np.random.default_rng(sum(map(ord, name)))
    samples, peak_db = SOUNDS[name](rng)
    samples = np.asarray(samples, dtype=float)
    if name != "thruster_loop":                    # a loop must not fade at its seam
        tail = min(len(samples), int(RATE * 0.01))
        samples[-tail:] *= np.linspace(1.0, 0.0, tail)
    samples *= 10 ** (peak_db / 20) / np.max(np.abs(samples))
    return np.round(samples * 32767).astype(np.int16)


def write_wav(path, samples):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(samples.tobytes())


def main(names=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in names or SOUNDS:
        path = OUT_DIR / f"{name}.wav"
        samples = render(name)
        write_wav(path, samples)
        print(f"{path.name:20s} {len(samples) / RATE:5.2f} s")


if __name__ == "__main__":
    main(sys.argv[1:])
