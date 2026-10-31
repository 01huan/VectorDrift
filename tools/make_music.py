"""Synthesize the game's three music tracks into assets/music/*.wav.

    python tools/make_music.py              # all three
    python tools/make_music.py menu         # just one

menu     synthwave: four-on-the-floor, pumping bass, arpeggio, the main theme (loops)
opening  sovietwave: slow, warm and wistful, the theme on a brassy synth (plays once)
level    spacewave: drifting pads, sparse plucks, almost no drums (loops)

Everything is numpy: band-limited oscillators, FFT filters, envelopes and an
FFT reverb. A looping track is rendered with extra room at the end and that
tail is folded back onto the start, so the loop point has no gap or click.
Random choices use fixed seeds, so the files come out the same every time.
"""

import sys
import wave
from pathlib import Path

import numpy as np

RATE = 22050
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
TAIL_S = 7.0                    # rendered past the loop end for reverb / delay tails


# --- oscillators ---------------------------------------------------------------------
def n_of(seconds):
    return int(round(seconds * RATE))


def midi_hz(n):
    return 440.0 * 2 ** ((np.asarray(n, dtype=float) - 69) / 12)


def _phase(freq, n, phase0=0.0):
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    dt = f / RATE
    return (phase0 + np.cumsum(dt) - dt) % 1.0, dt


def _blep(t, dt):
    """PolyBLEP correction that removes the aliasing of a hard edge."""
    out = np.zeros_like(t)
    m = t < dt
    x = t[m] / dt[m]
    out[m] = x + x - x * x - 1
    m = t > 1 - dt
    x = (t[m] - 1) / dt[m]
    out[m] = x * x + x + x + 1
    return out


def saw(freq, n, phase0=0.0):
    ph, dt = _phase(freq, n, phase0)
    return 2 * ph - 1 - _blep(ph, dt)


def square(freq, n, pw=0.5, phase0=0.0):
    ph, dt = _phase(freq, n, phase0)
    s = np.where(ph < pw, 1.0, -1.0)
    return s + _blep(ph, dt) - _blep((ph + 1 - pw) % 1.0, dt)


def sine(freq, n, phase0=0.0):
    ph, _ = _phase(freq, n, phase0)
    return np.sin(2 * np.pi * ph)


def supersaw(freq, n, detune_cents=(-11, -4, 0, 5, 12), rng=None):
    """Several slightly detuned saws: the wide synthwave pad / lead."""
    rng = rng or np.random.default_rng(0)
    return sum(saw(freq * 2 ** (c / 1200), n, rng.random()) for c in detune_cents) / len(detune_cents)


# --- filters and envelopes -----------------------------------------------------------
def _fft_filter(x, response):
    pad = n_of(0.05)
    size = 1 << int(np.ceil(np.log2(len(x) + 2 * pad)))
    spec = np.fft.rfft(np.concatenate([np.zeros(pad), x]), size)
    freqs = np.fft.rfftfreq(size, 1 / RATE)
    return np.fft.irfft(spec * response(freqs), size)[pad:pad + len(x)]


def lowpass(x, cutoff, order=2):
    return _fft_filter(x, lambda f: 1 / np.sqrt(1 + (f / cutoff) ** (2 * order)))


def highpass(x, cutoff, order=2):
    return _fft_filter(x, lambda f: 1 / np.sqrt(1 + (cutoff / np.maximum(f, 1e-6)) ** (2 * order)))


def swept(x, dark, bright, env):
    """A filter that opens with ``env`` (0..1): crossfade of two fixed low-passes."""
    return lowpass(x, dark) * (1 - env) + lowpass(x, bright) * env


def adsr(gate_s, attack, decay, sustain, release):
    """Envelope for a note held ``gate_s`` seconds; its length includes the release."""
    n_gate, n_rel = n_of(gate_s), n_of(release)
    t = np.arange(n_gate) / RATE
    on = np.where(t < attack, t / max(attack, 1e-4),
                  sustain + (1 - sustain) * np.exp(-(t - attack) / max(decay, 1e-4)))
    level = on[-1] if n_gate else 0.0
    off = level * np.exp(-np.arange(n_rel) / RATE / (release / 5))
    return np.concatenate([on, off])


def exp_decay(n, tau):
    t = np.arange(n) / RATE
    return np.exp(-t / tau) * np.minimum(1.0, t / 0.002)


# --- instruments (each returns samples starting at the note-on) ----------------------
def pad(notes, gate_s, bright=1800.0, attack=0.6, release=1.5, wobble=0.0, seed=0):
    env = adsr(gate_s, attack, 1.0, 0.85, release)
    n = len(env)
    t = np.arange(n) / RATE
    drift = 1 + wobble * np.sin(2 * np.pi * 0.35 * t)               # worn tape wow
    rng = np.random.default_rng(seed)
    x = sum(supersaw(midi_hz(m) * drift, n, rng=rng) for m in notes) / len(notes)
    return lowpass(x, bright) * env


def bass(note, gate_s, dark=250.0, bright=1400.0, pluck=0.12):
    env = adsr(gate_s, 0.004, 0.25, 0.6, 0.06)
    n = len(env)
    x = 0.7 * saw(midi_hz(note), n) + 0.5 * square(midi_hz(note - 12), n)
    return swept(x, dark, bright, exp_decay(n, pluck)) * env


def sub(note, gate_s, release=0.6):
    env = adsr(gate_s, 0.05, 1.0, 1.0, release)
    return sine(midi_hz(note), len(env)) * env


def pluck(note, gate_s, dark=700.0, bright=4500.0, tau=0.09, pw=0.3):
    env = adsr(gate_s, 0.002, 0.18, 0.25, 0.12)
    n = len(env)
    x = 0.6 * square(midi_hz(note), n, pw) + 0.4 * saw(midi_hz(note) * 1.003, n)
    return swept(x, dark, bright, exp_decay(n, tau)) * env


def lead(note, gate_s, cutoff=3200.0, vibrato_delay=0.25):
    env = adsr(gate_s, 0.015, 0.3, 0.8, 0.18)
    n = len(env)
    t = np.arange(n) / RATE
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - vibrato_delay) / 0.3, 0, 1)
    x = supersaw(midi_hz(note) * vib, n, (-7, 0, 7))
    return lowpass(x, cutoff) * env


def brass(note, gate_s):
    """Slow-opening saw stack: the sovietwave 'synth brass'."""
    env = adsr(gate_s, 0.12, 0.6, 0.75, 0.5)
    n = len(env)
    t = np.arange(n) / RATE
    vib = 1 + 0.004 * np.sin(2 * np.pi * 4.8 * t) * np.clip((t - 0.4) / 0.4, 0, 1)
    x = supersaw(midi_hz(note) * vib, n, (-9, -3, 3, 9))
    opening = 1 - np.exp(-t / 0.25)
    return swept(x, 500, 2600, opening) * env


def bell(note, gate_s, tau=0.9):
    n = n_of(gate_s + 3 * tau)
    f = midi_hz(note)
    parts = ((1.0, 1.0, 1.0), (2.0, 0.35, 0.7), (3.01, 0.18, 0.45), (4.17, 0.08, 0.3))
    return sum(g * sine(f * r, n) * exp_decay(n, tau * d) for r, g, d in parts)


def kick(n_s=0.45, punch=1.0):
    n = n_of(n_s)
    t = np.arange(n) / RATE
    freq = 45 + 95 * np.exp(-t / 0.035)
    body = sine(freq, n) * np.exp(-t / 0.16)
    click = highpass(np.random.default_rng(1).uniform(-1, 1, n), 2000) * np.exp(-t / 0.004)
    return body + 0.25 * punch * click


def snare(seed=2):
    n = n_of(0.3)
    t = np.arange(n) / RATE
    noise = np.random.default_rng(seed).uniform(-1, 1, n)
    rattle = lowpass(highpass(noise, 1200), 7000) * np.exp(-t / 0.07)
    body = sine(185, n) * np.exp(-t / 0.05)
    return 0.8 * rattle + 0.5 * body


def hat(open_=False, seed=3):
    n = n_of(0.25 if open_ else 0.06)
    t = np.arange(n) / RATE
    noise = np.random.default_rng(seed).uniform(-1, 1, n)
    return highpass(noise, 7000) * np.exp(-t / (0.08 if open_ else 0.015))


# --- effects -------------------------------------------------------------------------
def reverb(x, seconds, damp=5000.0, seed=4):
    """FFT convolution with decaying, darkened noise (60 dB down after ``seconds``)."""
    n = n_of(seconds)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(seed)
    ir = lowpass(rng.standard_normal(n), damp) * np.exp(-6.9 * t / seconds)
    ir[:n_of(0.012)] = 0.0                                           # a little pre-delay
    ir /= np.sqrt(np.sum(ir ** 2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)
    return y[:len(x)]


def gated_reverb(x, seconds=0.28):
    """The big 80s snare: a dense room cut off sharply."""
    n = n_of(seconds)
    rng = np.random.default_rng(5)
    ir = lowpass(rng.standard_normal(n), 6000) * np.linspace(1.0, 0.6, n)
    ir[-n_of(0.02):] *= np.linspace(1, 0, n_of(0.02))
    ir /= np.sqrt(np.sum(ir ** 2))
    return np.convolve(x, ir)[:len(x) + n]


def delay(x, seconds, feedback=0.45, taps=6, tone=3500.0):
    out = x.copy()
    d = n_of(seconds)
    echo = x
    for k in range(1, taps + 1):
        echo = lowpass(echo, tone) * feedback
        if k * d >= len(x):
            break
        out[k * d:] += echo[:len(x) - k * d]
    return out


def sidechain(n, hit_times, depth=0.6, release=0.32):
    """Gain that ducks on every kick and swells back: the synthwave 'pump'."""
    g = np.ones(n)
    r = n_of(release)
    shape = 1 - depth * (1 - np.linspace(0, 1, r)) ** 2
    for ts in hit_times:
        i = n_of(ts)
        if i >= n:
            continue
        j = min(n, i + r)
        g[i:j] = np.minimum(g[i:j], shape[:j - i])
    return g


# --- arranging -----------------------------------------------------------------------
class Track:
    """A mono buffer with named buses, written note by note in beats."""

    def __init__(self, bpm, bars, tail=TAIL_S):
        self.beat = 60.0 / bpm
        self.bars = bars
        self.length = n_of(bars * 4 * self.beat)
        self.n = self.length + n_of(tail)
        self.buses = {}

    def time(self, bar, beat=0.0):
        return (bar * 4 + beat) * self.beat

    def add(self, bus, start_s, samples, gain=1.0):
        buf = self.buses.setdefault(bus, np.zeros(self.n))
        i = n_of(start_s)
        if i >= self.n:
            return
        j = min(self.n, i + len(samples))
        buf[i:j] += gain * samples[:j - i]

    def bus(self, name):
        return self.buses.get(name, np.zeros(self.n))


def fold_loop(x, length):
    """Fold everything past ``length`` back onto the start (seamless loop)."""
    out = x[:length].copy()
    rest = x[length:]
    while len(rest):
        k = min(len(rest), length)
        out[:k] += rest[:k]
        rest = rest[k:]
    return out


def master(x, peak_db=-1.0, drive=1.6):
    """Normalize, soft-limit, and set the final peak."""
    x = x / (np.max(np.abs(x)) + 1e-12)
    x = np.tanh(drive * x) / np.tanh(drive)
    return x * 10 ** (peak_db / 20) / np.max(np.abs(x))


# --- shared material -----------------------------------------------------------------
# The main theme, in A minor over Am - F - C - G (one chord per bar):
# (midi note, length in beats); None is a rest.
THEME = [
    [(76, 1), (81, 1), (79, 0.5), (76, 0.5), (74, 1)],
    [(72, 1.5), (74, 0.5), (76, 2)],
    [(79, 1), (76, 1), (72, 1), (76, 1)],
    [(74, 3), (71, 1)],
    [(76, 1), (81, 1), (79, 0.5), (76, 0.5), (74, 1)],
    [(72, 1), (77, 1), (76, 1), (72, 1)],
    [(79, 1.5), (81, 0.5), (79, 1), (76, 1)],
    [(74, 2), (None, 2)],
]
# Chords as (pad voicing, bass root) for i - VI - III - VII in A minor.
CHORDS_AM = [((57, 60, 64), 45), ((53, 57, 60), 41), ((55, 60, 64), 48), ((55, 59, 62), 43)]


def play_theme(track, bus, first_bar, instrument, transpose=0, gain=1.0):
    for bar, notes in enumerate(THEME):
        beat = 0.0
        for note, length in notes:
            if note is not None:
                track.add(bus, track.time(first_bar + bar, beat),
                          instrument(note + transpose, length * track.beat * 0.95), gain)
            beat += length


# --- the tracks ----------------------------------------------------------------------
def make_menu():
    """Synthwave, 100 BPM, 24 bars (57.6 s) that loop.

    0-3 pads + arpeggio | 4-11 + drums, bass | 12-19 + theme lead | 20-23 pads + arpeggio again
    """
    tr = Track(bpm=100, bars=24)
    kicks = []
    for bar in range(tr.bars):
        voicing, root = CHORDS_AM[bar % 4]
        full = 4 <= bar < 20
        tr.add("pad", tr.time(bar), pad(voicing, 4 * tr.beat, bright=2200, attack=0.25, release=0.8,
                                        seed=bar % 4), 0.55)
        tones = [m + 12 for m in voicing] + [voicing[0] + 24, voicing[1] + 24]
        opening = min(1.0, (bar + 1) / 4) if bar < 4 else 1.0           # intro arp brightens
        for i, k in enumerate([0, 1, 2, 3, 4, 3, 2, 1] * 2):
            tr.add("arp", tr.time(bar, i * 0.25),
                   pluck(tones[k], 0.25 * tr.beat, bright=1500 + 3500 * opening), 0.32)
        if not full:
            continue
        for b in range(4):
            kicks.append(tr.time(bar, b))
            tr.add("kick", tr.time(bar, b), kick())
            tr.add("hat", tr.time(bar, b + 0.5), hat(), 0.35)
        for b in (1, 3):
            tr.add("snare", tr.time(bar, b), snare())
        if bar == 11:                                                    # fill into the theme
            for i in range(4):
                tr.add("snare", tr.time(bar, 3 + i * 0.25), snare(seed=10 + i), 0.35 + 0.15 * i)
        for i in range(8):
            note = root - 12 if i % 2 == 0 else root
            tr.add("bass", tr.time(bar, i * 0.5), bass(note, 0.45 * tr.beat), 0.8)
    play_theme(tr, "lead", 12, lead, gain=0.55)

    pump = sidechain(tr.n, kicks)
    drums = tr.bus("kick") + 0.6 * gated_reverb(tr.bus("snare"))[:tr.n] + tr.bus("hat")
    synths = (tr.bus("pad") + tr.bus("bass")) * pump
    arp = delay(tr.bus("arp"), tr.beat * 0.75, 0.4)
    lead_bus = delay(tr.bus("lead"), tr.beat * 0.75, 0.3)
    dry = drums + synths + arp + lead_bus
    wet = reverb(0.5 * tr.bus("pad") * pump + 0.6 * arp + 0.7 * lead_bus + 0.3 * tr.bus("snare"), 2.2)
    return master(fold_loop(dry + 0.35 * wet, tr.length)), True


def make_opening():
    """Sovietwave, 76 BPM, about 47 s, plays once under the opening crawl.

    The theme moved to D minor (Dm - Bb - F - C) on slow synth brass over
    warm, slightly wobbly pads, ending on a long D major chord.
    """
    tr = Track(bpm=76, bars=15, tail=6.0)
    up = 5                                                               # A minor -> D minor
    for bar in range(12):
        voicing, root = CHORDS_AM[bar % 4]
        tr.add("pad", tr.time(bar), pad([m + up for m in voicing], 4 * tr.beat,
                                        bright=1300, attack=1.4 if bar < 4 else 0.5,
                                        release=2.0, wobble=0.003, seed=bar % 4), 0.6)
        tr.add("sub", tr.time(bar), sub(root + up - 12, 4 * tr.beat), 0.7)
        if bar >= 4:
            for i in range(8):                                          # soft 8th-note arpeggio
                tone = [m + up + 12 for m in voicing][i % 3]
                tr.add("arp", tr.time(bar, i * 0.5), pluck(tone, 0.4 * tr.beat, bright=2500), 0.18)
        if bar >= 8:                                                     # half-time drums
            tr.add("kick", tr.time(bar, 0), kick(punch=0.5), 0.8)
            tr.add("kick", tr.time(bar, 2.5), kick(punch=0.5), 0.5)
            tr.add("snare", tr.time(bar, 2), snare(), 0.8)
            for b in range(4):
                tr.add("hat", tr.time(bar, b + 0.5), hat(), 0.2)
    play_theme(tr, "brass", 4, brass, transpose=up - 12, gain=0.7)
    # Bar 12: Bb swells, then a long D major chord to the end.
    tr.add("pad", tr.time(12), pad((50, 53, 58, 62), 4 * tr.beat, bright=1600, attack=0.8,
                                   release=1.0, wobble=0.003, seed=7), 0.7)
    tr.add("brass", tr.time(12), brass(62, 3.5 * tr.beat), 0.5)
    tr.add("pad", tr.time(13), pad((50, 54, 57, 62, 66), 7 * tr.beat, bright=1800, attack=0.6,
                                   release=3.0, wobble=0.003, seed=8), 0.8)
    tr.add("brass", tr.time(13), brass(66, 6 * tr.beat), 0.45)
    tr.add("sub", tr.time(13), sub(38, 7 * tr.beat, release=2.5), 0.8)
    tr.add("kick", tr.time(13), kick(punch=0.5), 0.9)

    drums = tr.bus("kick") + 0.5 * gated_reverb(tr.bus("snare"))[:tr.n] + tr.bus("hat")
    arp = delay(tr.bus("arp"), tr.beat * 0.75, 0.45, tone=2500)
    dry = tr.bus("pad") + tr.bus("sub") + tr.bus("brass") + arp + drums
    wet = reverb(tr.bus("pad") + 0.8 * tr.bus("brass") + arp + 0.4 * tr.bus("snare"), 3.5, damp=3500)
    x = dry + 0.45 * wet
    swell = n_of(4 * 4 * tr.beat)                                        # rises over the first 4 bars
    x[:swell] *= np.linspace(0.15, 1, swell) ** 1.5
    fade = n_of(3.0)                                                     # gentle end
    x[-fade:] *= np.linspace(1, 0, fade) ** 2
    return master(lowpass(x, 7000), peak_db=-1.5), False


def make_level():
    """Spacewave, 80 BPM, 32 bars (96 s) that loop.

    Am9 - Fmaj7 - Cmaj7 - Em7, two bars each. Drifting pads, a soft sub,
    sparse plucks into long echoes, a bell now and then, and a quiet
    heartbeat kick only in the middle (bars 8-23) so the loop point is calm.
    """
    tr = Track(bpm=80, bars=32, tail=9.0)
    chords = [((57, 60, 64, 71), 45), ((53, 57, 60, 64), 41), ((55, 59, 60, 64), 48), ((55, 59, 62, 64), 40)]
    rng = np.random.default_rng(42)
    for half in range(16):                                               # one chord per 2 bars
        voicing, root = chords[half % 4]
        bar = 2 * half
        tr.add("pad", tr.time(bar), pad(voicing, 8 * tr.beat, bright=1100, attack=2.5, release=3.0,
                                        wobble=0.002, seed=half % 4), 0.6)
        tr.add("sub", tr.time(bar), sub(root - 12, 8 * tr.beat, release=2.0), 0.45)
        tones = [m + 12 for m in voicing] + [m + 24 for m in voicing[:2]]
        for beat in range(8):
            if rng.random() < 0.45:
                tr.add("pluck", tr.time(bar, beat + rng.choice([0, 0.5])),
                       pluck(tones[rng.integers(len(tones))], 0.3, dark=500, bright=2200, tau=0.05), 0.22)
        if half % 2 == 1:
            tr.add("bell", tr.time(bar, 4 + rng.choice([0, 1, 2])),
                   bell(tones[rng.integers(len(tones))] + 12, 0.5, tau=1.2), 0.12)
        if 4 <= half < 12:
            for b in (0, 4):
                tr.add("kick", tr.time(bar, b), lowpass(kick(0.5, punch=0.0), 200), 0.35)

    t = np.arange(tr.n) / RATE
    breathe = 0.5 + 0.5 * np.sin(2 * np.pi * t / (tr.length / RATE / 4))  # 4 slow swells per loop
    pads = tr.bus("pad")
    pads = pads * (0.75 + 0.25 * breathe)
    echoes = delay(tr.bus("pluck") + tr.bus("bell"), tr.beat * 0.75, 0.55, taps=8, tone=2200)
    dry = pads + tr.bus("sub") + echoes + tr.bus("kick")
    wet = reverb(pads + 1.2 * echoes, 5.5, damp=3000)
    return master(fold_loop(dry + 0.6 * wet, tr.length), peak_db=-5.0, drive=1.2), True


TRACKS = {"menu": make_menu, "opening": make_opening, "level": make_level}


# --- output --------------------------------------------------------------------------
def render(name):
    """(int16 samples, loops?) for track ``name``."""
    samples, loops = TRACKS[name]()
    return np.round(samples * 32767).astype(np.int16), loops


def write_wav(path, samples):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(samples.tobytes())


def main(names=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in names or TRACKS:
        samples, loops = render(name)
        path = OUT_DIR / f"{name}.wav"
        write_wav(path, samples)
        print(f"{path.name:12s} {len(samples) / RATE:6.1f} s  {'loop' if loops else 'once'}")


if __name__ == "__main__":
    main(sys.argv[1:])
