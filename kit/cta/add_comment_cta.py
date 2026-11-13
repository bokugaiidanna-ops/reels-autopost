"""完成した動画の最後に「コメントで〇〇→LINEでまとめプレゼント」の締めカードを足す（約5秒・声つき）
  python3 kit/cta/add_comment_cta.py in.mp4 out.mp4 --genre ai|okane|fukugyo
導線：コメント → DM（LINEのリンク） → 友だち追加ですぐまとめが届く"""
import sys, os, argparse, subprocess, json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from reelkit import font
D = os.path.dirname(os.path.abspath(__file__))
GENRES = {"ai": ("AI", "AIのしくみまとめ", (80, 220, 255)), "okane": ("お金", "お金のしくみまとめ", (255, 200, 60)), "fukugyo": ("副業", "副業のしくみまとめ", (120, 230, 150))}
def clamp(x): return max(0., min(1., x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def back(x): x = clamp(x); c = 1.4; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
def card(t, W, H, kw, gift, acc):
    s = W / 1080
    im = Image.new("RGB", (W, H)); a = np.linspace(0, 1, H)[:, None]
    top, bot = np.array([10, 14, 32]), np.array([28, 24, 60])
    im = Image.fromarray(np.repeat((top + (bot - top) * a)[:, None, :], W, 1).reshape(H, W, 3).astype(np.uint8))
    d = ImageDraw.Draw(im); F = lambda k, z: font(k, int(z * s)); cx = W / 2
    p1 = ease(t / .3); d.text((cx, (430 - 40 * (1 - p1)) * s), "＼ 無料プレゼント ／", font=F("B", 58), fill=tuple(int(v * p1) for v in acc), anchor="mm")
    p2 = ease((t - .15) / .3); d.text((cx, 600 * s), "コメントに", font=F("K", 96), fill=(int(255 * p2),) * 3, anchor="mm")
    p3 = back((t - .35) / .45)
    if p3 > 0:
        z = .5 + .5 * p3; fk = F("K", 230 * z); tw = d.textlength(f"「{kw}」", font=fk)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        dl.rounded_rectangle([cx - tw / 2 - 50 * s, 830 * s - 170 * s * z, cx + tw / 2 + 50 * s, 830 * s + 170 * s * z], int(40 * s), fill=acc + (255,))
        glow = lay.filter(ImageFilter.GaussianBlur(30 * s)); im.paste(glow, (0, 0), glow); im.paste(lay, (0, 0), lay)
        d = ImageDraw.Draw(im); d.text((cx, 830 * s), f"「{kw}」", font=fk, fill=(15, 15, 25), anchor="mm")
    p4 = ease((t - .6) / .3); d.text((cx, 1060 * s), "と書いてね", font=F("K", 96), fill=(int(255 * p4),) * 3, anchor="mm")
    p5 = ease((t - 1.1) / .35); yo = 50 * (1 - p5) * s
    if p5 > 0:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
        dl.rounded_rectangle([110 * s, 1220 * s + yo, W - 110 * s, 1500 * s + yo], int(36 * s), fill=(255, 255, 255, int(245 * p5)))
        dl.text((cx, 1305 * s + yo), gift + "を", font=F("K", 62), fill=(20, 20, 30, int(255 * p5)), anchor="mm")
        dl.text((cx, 1410 * s + yo), "LINEでお届けします", font=F("B", 56), fill=(6, 170, 70, int(255 * p5)), anchor="mm")
        im.paste(lay, (0, 0), lay)
    p6 = ease((t - 1.6) / .4)
    d = ImageDraw.Draw(im); d.text((cx, 1620 * s), "DMでLINEのリンクを送ります", font=F("B", 40), fill=(int(200 * p6),) * 3, anchor="mm")
    # pulsing hint arrow to comment icon side
    if t > 2.0:
        k = .5 + .5 * math.sin((t - 2) * 6); d.text((W - 150 * s, 1220 * s), "→", font=F("K", 90), fill=tuple(int(v * (.5 + .5 * k)) for v in acc), anchor="mm")
    return im
def probe(p):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", p], capture_output=True, text=True).stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video"); n, dd = map(int, v["r_frame_rate"].split("/"))
    return v["width"], v["height"], n / dd, float(j["format"]["duration"]), any(s["codec_type"] == "audio" for s in j["streams"])
if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("inp"); ap.add_argument("out"); ap.add_argument("--genre", required=True); a = ap.parse_args()
    kw, gift, acc = GENRES[a.genre]; voice = os.path.join(D, f"voice_{a.genre}.wav")
    W, H, fps, dur, has_a = probe(a.inp)
    vl = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", voice], capture_output=True, text=True).stdout)
    cd = vl + 1.2; n = int(cd * fps); cardmp4 = a.out + ".card.mp4"
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-", "-i", voice, "-filter_complex", f"[1]adelay=250:all=1,apad,atrim=0:{cd:.2f},aresample=48000,aformat=channel_layouts=stereo[a]", "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", cardmp4], stdin=subprocess.PIPE)
    for i in range(n): p.stdin.write(card(i / fps, W, H, kw, gift, acc).tobytes())
    p.stdin.close(); p.wait()
    ain = "[0:a]" if has_a else f"anullsrc=r=48000:cl=stereo,atrim=0:{dur}[sil];[sil]"
    fc = (("" if has_a else f"anullsrc=r=48000:cl=stereo,atrim=0:{dur:.3f}[s0];") + f"[0:v]fps={fps},format=yuv420p[v0];{'[0:a]' if has_a else '[s0]'}aresample=48000,aformat=channel_layouts=stereo[a0];[1:v]format=yuv420p[v1];[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    tmp = a.out + ".part.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", a.inp, "-i", cardmp4, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, a.out); os.remove(cardmp4); print("ok", a.out, f"+{cd:.1f}s")
