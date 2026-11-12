"""効果音を数式で作る（著作権フリー・自前）。python3 kit/sfx/gen_sfx.py で kit/sfx/*.wav を作り直す"""
import numpy as np, wave, os
SR = 48000; D = os.path.dirname(os.path.abspath(__file__))
def env(n, a=.005, r=None):
    t = np.arange(n) / SR; e = np.minimum(1, t / a)
    return e * (np.exp(-t / r) if r else 1)
def save(name, x, g=.8):
    x = x / (np.abs(x).max() + 1e-9) * g; y = (x * 32767).astype(np.int16)
    with wave.open(os.path.join(D, name + ".wav"), "w") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(y.tobytes())
def tone(f, dur, r, a=.003, harm=(1,)):
    n = int(SR * dur); t = np.arange(n) / SR; f = np.broadcast_to(f, (n,)) if np.ndim(f) else np.full(n, f)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return sum(np.sin(ph * h) / h for h in harm) * env(n, a, r)
rng = np.random.default_rng(3)
def noise(n): return rng.standard_normal(n)
def bp(x, lo, hi):  # FFTで帯域を残す
    X = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR); X[(fr < lo) | (fr > hi)] = 0; return np.fft.irfft(X, len(x))
# pop：要素がポンと出る
n = int(SR * .12); save("pop", tone(np.linspace(900, 420, n), .12, .035, harm=(1, 2)), .7)
# tick：カウントダウン
save("tick", bp(noise(int(SR * .04)), 2500, 7000) * env(int(SR * .04), .001, .006) + tone(1800, .04, .01) * .5, .6)
# whoosh：場面転換
n = int(SR * .45); t = np.arange(n) / SR; sh = np.sin(np.pi * t / t[-1]) ** 2
x = sum(bp(noise(n), lo, lo * 1.6) * np.clip(1 - abs(t / t[-1] - k) * 3, 0, 1) for lo, k in [(400, .2), (800, .4), (1500, .6), (2600, .8)])
save("whoosh", x * sh, .55)
# up：数字が上がる（明るいピロン）
save("up", np.concatenate([tone(880, .09, .06, harm=(1, 3)), tone(1320, .22, .09, harm=(1, 3))]), .6)
# down：数字が下がる（ブブッ）
n = int(SR * .35); save("down", tone(np.linspace(260, 150, n), .35, .2, harm=(1, 2, 3, 4)) * (0.6 + .4 * np.sign(np.sin(2 * np.pi * 9 * np.arange(n) / SR))), .55)
# thud：言い切り・ドン
n = int(SR * .35); save("thud", tone(np.linspace(110, 45, n), .35, .12) + bp(noise(n), 60, 400) * env(n, .001, .03) * .6, .85)
# coin：お金・収入
save("coin", np.concatenate([tone(1976, .07, .05, harm=(1, 2)), tone(2637, .35, .12, harm=(1, 2))]), .5)
# sparkle：キラッ（ひらめき・答え）
x = np.zeros(int(SR * .5))
for i, f in enumerate([2093, 2637, 3136, 4186]): s = int(SR * .05 * i); y = tone(f, .3, .08); x[s:s + len(y)] += y
save("sparkle", x, .45)
# type：文字がカタカタ（テロップ）
x = np.zeros(int(SR * .3))
for k in range(5): s = int(SR * .055 * k); y = bp(noise(int(SR * .02)), 1500, 5000) * env(int(SR * .02), .0005, .004); x[s:s + len(y)] += y
save("type", x, .45)
print("ok", sorted(f for f in os.listdir(D) if f.endswith(".wav")))
