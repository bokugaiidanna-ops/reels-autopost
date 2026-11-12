"""完成した動画に効果音を足す。
  python3 kit/sfx/add_sfx.py in.mp4 out.mp4 --auto              動きを自動で見つけて音を置く
  python3 kit/sfx/add_sfx.py in.mp4 out.mp4 --cues cues.json     置く場所を指定 [{"t":1.2,"s":"pop"},...]
  --auto と --cues は併用可（cuesを優先し、近い自動の音は消す）。--dry で置く場所だけ表示
自動の決め方：画面全体が変わる＝whoosh（場面転換）／止まっていた画面に何かが出る＝pop、
  出たものが緑っぽい＝up、赤っぽい＝down
音量は声の邪魔をしない大きさ（--vol で全体を調整、既定0.35）"""
import sys, os, json, argparse, subprocess, numpy as np
D = os.path.dirname(os.path.abspath(__file__)); W, H, FPS = 108, 192, 30
def frames(path):
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, H, W, 3).astype(np.int16)
def auto_cues(path):
    from scipy.ndimage import binary_dilation
    f = frames(path); g = f.mean(3); d = np.abs(np.diff(g, axis=0)) > 18  # d[i]: フレームi→i+1で変わった画素
    whole = d.mean((1, 2)); cut = whole > .3
    # 場面ごとに「ずっと動いている所」（キャラの待機アニメ等）を除く
    m = np.zeros(len(d)); bounds = [0] + [i + 1 for i in range(len(d)) if cut[i] and (i == 0 or not cut[i - 1])] + [len(d)]
    for a, b in zip(bounds, bounds[1:]):
        seg = d[a:b][~cut[a:b]]
        if not len(seg): continue
        mask = binary_dilation(seg.sum(0) >= 6, iterations=2)  # 6回以上変わる所＝待機アニメ
        m[a:b] = (d[a:b] & ~mask).mean((1, 2))
    m[cut] = 0
    for i in np.nonzero(cut)[0]: m[i:i + 4] = 0  # 切り替え直後の揺れは無視
    cues = []
    for i in np.nonzero(cut)[0]:
        if i == 0 or not cut[i - 1]: cues.append({"t": round((i + 1) / FPS - .12, 2), "s": "whoosh"})
    i = 0
    while i < len(m):  # 2フレーム以上続く変化のかたまり＝何かが出た
        if m[i] > .0015:
            j = i
            while j + 1 < len(m) and m[j + 1] > .0015: j += 1
            if j > i and m[i:j + 1].sum() > .015 and m[i:j + 1].max() > .006:
                k = min(len(f) - 1, j + 6); ch = np.abs(f[k] - f[max(0, i - 1)]).sum(2) > 60
                px = f[k][ch]; s = "pop"
                if len(px) > 30:
                    r, gg, b = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
                    if gg > r + 25 and gg > b: s = "up"
                    elif r > gg + 50 and r > b + 30: s = "down"
                t = round((i + 1) / FPS, 2)
                if all(abs(t - c["t"]) > .3 for c in cues): cues.append({"t": t, "s": s})
            i = j + 1
        else: i += 1
    return cues
def mix(inp, out, cues, vol):
    ins, fl = ["-i", inp], []
    for k, c in enumerate(cues):
        ins += ["-i", os.path.join(D, c["s"] + ".wav")]
        fl.append(f"[{k+1}]adelay={int(max(0, c['t']) * 1000)}:all=1,volume={vol * c.get('v', 1):.2f}[s{k}]")
    n = len(cues)
    fl.append("[0:a]" + "".join(f"[s{k}]" for k in range(n)) + f"amix=inputs={n+1}:normalize=0:duration=first,alimiter=limit=0.95[a]")
    tmp = out + ".part.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fl), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, out)
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("--auto", action="store_true"); ap.add_argument("--cues"); ap.add_argument("--vol", type=float, default=.35); ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(); cues = auto_cues(a.inp) if a.auto else []
    if a.cues:
        man = json.load(open(a.cues)); cues = [c for c in cues if all(abs(c["t"] - m["t"]) > .3 for m in man)] + man
    cues.sort(key=lambda c: c["t"])
    for c in cues: print(f'{c["t"]:6.2f}s {c["s"]}')
    if not a.dry and cues: mix(a.inp, a.out, cues, a.vol)
