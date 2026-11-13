"""reelkit — 台本(JSON)から縦型リールを組み立てる部品キット

使い方:
  python3 kit/reelkit.py script.json out.mp4 [--hook A] [--stills 1.0,5.2]
  - script.json の scenes を順番に並べて 1080x1920 / 30fps の mp4 を作る
  - 各シーンの長さ = 声ファイル(audio/<id>.wav)の長さ + pad。声がなければ "dur" 秒
  - hooks: {"A": scene, "B": scene, ...} を先頭に差し込める（A/Bテスト用）
シーンの型（type）:
  title    大きい文字のフック        lines:[[text,color,size],...], sub
  bars     横棒グラフ（確率・比較）  title, sub, items:[{label,value,max?,suffix,color?}], note
  cards    カード比較（料金など）    title, items:[{name,big,sub,bullets,color}]
  chat     チャット画面＋ツッコミ    messages:[{who:"me"|"ai",text}], impact, impact_sub
  zoom     サイズ比較ズームアウト    title, sub, items:[{name,value,label,color}]（小→大の順）
  people   100人の棒人間             title, total, highlight, label
  kinetic  文字だけ（跳ねる文字）    lines:[[text,size,color],...], bg
  tier     ティア表が埋まる          title, tiers:{"S":[...],...}
  point    結論ボックス              lines:[[text,color,size],...], color
  network  光るネットワーク          title, sub
  noise    ノイズから絵              title, sub, steps
  cta      フォロー・保存の呼びかけ  follow, save
  screen   実際の画面キャプチャ      img(パス), label(上の見出し), focus:[x0,y0,x1,y1](0〜1で切り出し)
  prompt   指示文をカードにタイピング text(\n改行), label, type_dur, note, size
共通: id, voice(読み上げ文), sub(下字幕), dur, pad, bg("dark"|"black"|"light"|"yellow"|"paper")
"""
import sys, os, json, math, random, subprocess, argparse
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
FD = "/usr/share/fonts/opentype/noto/"
FONTS = {"B": FD + "NotoSansCJK-Bold.ttc", "K": FD + "NotoSansCJK-Black.ttc", "R": FD + "NotoSansCJK-Regular.ttc", "S": FD + "NotoSerifCJK-Bold.ttc"}
_fc = {}
def font(k, s):
    if (k, s) not in _fc: _fc[(k, s)] = ImageFont.truetype(FONTS[k], int(s), index=0)
    return _fc[(k, s)]

# ---------- theme ----------
THEMES = {
    "seiseiai": {"accent": (80, 220, 255), "accent2": (255, 120, 170), "gold": (240, 196, 92), "good": (80, 230, 150), "brand": "得する生成AIのしくみ", "dark": ((8, 26, 40), (14, 44, 62))},
    "okane":    {"accent": (255, 200, 60), "accent2": (255, 120, 120), "gold": (240, 196, 92), "good": (80, 230, 150), "brand": "得するお金のしくみ", "dark": ((20, 18, 36), (36, 30, 60))},
    "default":  {"accent": (90, 200, 255), "accent2": (255, 120, 170), "gold": (240, 196, 92), "good": (80, 230, 150), "brand": "", "dark": ((16, 16, 30), (30, 30, 52))},
}
WHITE, DIM, INK = (245, 245, 250), (160, 175, 195), (30, 30, 36)
PALETTE = [(80, 220, 255), (255, 120, 170), (240, 196, 92), (80, 230, 150), (170, 140, 255), (255, 160, 90)]
def col(c, th):
    if c is None: return th["accent"]
    if isinstance(c, str): return {"accent": th["accent"], "accent2": th["accent2"], "gold": th["gold"], "good": th["good"], "white": WHITE, "dim": DIM, "ink": INK, "red": (230, 50, 70)}.get(c, th["accent"])
    return tuple(c)

# ---------- easing ----------
def clamp(x, a=0., b=1.): return max(a, min(b, x))
def ease(x): x = clamp(x); return 1 - (1 - x) ** 3
def back(x):
    x = clamp(x); c = 1.7; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2
def P(t, t0, d=0.4): return ease((t - t0) / d)

# ---------- drawing helpers ----------
def L(): return Image.new("RGBA", (W, H), (0, 0, 0, 0))
def fade(img, lay, a):
    if a <= 0: return
    if a < 1: lay = lay.copy(); lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
    img.alpha_composite(lay)
def gtext(img, xy, s, f, fill, anchor="mt", r=16, a=170):
    lay = L(); ImageDraw.Draw(lay).text(xy, s, font=f, fill=fill + (a,), anchor=anchor)
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(r))); ImageDraw.Draw(img).text(xy, s, font=f, fill=fill, anchor=anchor)
def box(img, b, outline, fill=(14, 12, 28, 225), w=4, r=26, glow=True):
    lay = L(); d = ImageDraw.Draw(lay)
    if glow:
        d.rounded_rectangle(b, r, outline=outline + (190,), width=w + 8); lay = lay.filter(ImageFilter.GaussianBlur(12)); d = ImageDraw.Draw(lay)
    d.rounded_rectangle(b, r, fill=fill, outline=outline + (255,), width=w); img.alpha_composite(lay)
def outline_text(d, xy, s, f, fill, stroke=(0, 0, 0), sw=8, anchor="mm"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=sw, stroke_fill=stroke)
def wrap(s, f, maxw, d):
    if "\n" in s: return [l for part in s.split("\n") for l in (wrap(part, f, maxw, d) or [""])]
    out, cur = [], ""
    for ch in s:
        if d.textlength(cur + ch, font=f) > maxw and cur: out.append(cur); cur = ch
        else: cur += ch
    if cur: out.append(cur)
    return out

# ---------- backgrounds ----------
_bgc = {}
def background(kind, th):
    key = (kind, th["brand"])
    if key in _bgc: return _bgc[key]
    if kind in ("dark", None):
        c0, c1 = th["dark"]; y = np.linspace(0, 1, H)[:, None]; f = 1 - np.abs(y - .35) * 2
        arr = np.dstack([np.repeat(c0[i] + (c1[i] - c0[i]) * f, W, 1) for i in range(3)])
        g = Image.new("L", (W, H), 0); ImageDraw.Draw(g).ellipse([W * .1, H * .12, W * .9, H * .55], fill=255)
        g = np.asarray(g.filter(ImageFilter.GaussianBlur(170)), float)[:, :, None] / 255
        arr = arr + g * np.array(th["accent"]) * .22
        bg = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")); d = ImageDraw.Draw(bg, "RGBA"); hz = int(H * .74)
        gc = th["accent"] + (34,)
        for i in range(14): yy = hz + int((H - hz) * (i / 13) ** 1.8); d.line([(0, yy), (W, yy)], fill=gc, width=2)
        for i in range(-12, 13): d.line([(W / 2 + i * 60, hz), (W / 2 + i * 260, H)], fill=gc, width=2)
    elif kind == "black": bg = Image.new("RGB", (W, H), (0, 0, 0))
    elif kind == "light": bg = Image.new("RGB", (W, H), (246, 246, 250))
    elif kind == "yellow": bg = Image.new("RGB", (W, H), (255, 214, 0))
    elif kind == "paper": bg = Image.new("RGB", (W, H), (252, 249, 240))
    else: bg = Image.new("RGB", (W, H), tuple(kind))
    bg = bg.convert("RGBA")
    if th["brand"]:
        light = kind in ("light", "yellow", "paper")
        ImageDraw.Draw(bg).text((44, 52), th["brand"], font=font("B", 30), fill=(90, 90, 100) if light else (190, 210, 225))
    _bgc[key] = bg; return bg
def is_light(sc): return sc.get("bg") in ("light", "yellow", "paper")
def fg(sc): return INK if is_light(sc) else WHITE

def heading(d, sc, y=300):
    if sc.get("title"): d.text((W / 2, y), sc["title"], font=font("K", sc.get("title_size", 62)), fill=fg(sc), anchor="mt")
    if sc.get("subtitle"): d.text((W / 2, y + 92), sc["subtitle"], font=font("B", 36), fill=(110, 110, 120) if is_light(sc) else DIM, anchor="mt")

# ============ scene renderers: draw(img, t, sc, th) where t = seconds since scene start ============
def s_title(img, t, sc, th):
    lines = sc["lines"]; total = sum(l[2] if len(l) > 2 else 100 for l in lines) + 36 * (len(lines) - 1)
    y = sc.get("y", 860 - total / 2)
    for i, l in enumerate(lines):
        s, c, sz = l[0], col(l[1] if len(l) > 1 else "white", th), (l[2] if len(l) > 2 else 100)
        p = P(t, .1 + i * .28, .35)
        if p > 0:
            lay = L(); yy = y + (1 - p) * 50
            if c != WHITE and c != INK: gtext(lay, (W / 2, yy), s, font("K", sz), c, r=20)
            else: ImageDraw.Draw(lay).text((W / 2, yy), s, font=font("K", sz), fill=fg(sc) if c == WHITE else c, anchor="mt")
            fade(img, lay, p)
        y += sz + 36

def s_bars(img, t, sc, th):
    lay = L(); d = ImageDraw.Draw(lay); heading(d, sc, 300)
    items = sc["items"]; mx = sc.get("max") or max(it["value"] for it in items)
    top = sc.get("top", 560); gap = min(170, 820 / max(1, len(items)))
    for i, it in enumerate(items):
        p = P(t, .3 + i * .25, .7); y = top + i * gap
        c = col(it.get("color"), th) if it.get("color") else (th["accent"] if i == 0 else (100, 140, 180))
        d.text((110, y), it["label"], font=font("B", 46), fill=fg(sc))
        x0, x1 = 110, W - 230; by = y + 66
        d.rounded_rectangle([x0, by, x1, by + 42], 21, fill=(225, 225, 232) if is_light(sc) else (40, 52, 72))
        if p > .03: d.rounded_rectangle([x0, by, x0 + max(42, (x1 - x0) * it["value"] / mx * p), by + 42], 21, fill=c)
        v = it["value"] * p; txt = (f"{v:,.0f}" if it["value"] >= 10 or float(it["value"]).is_integer() else f"{v:.1f}") + it.get("suffix", "")
        d.text((W - 100, by + 21), it.get("text", txt) if p >= 1 else txt, font=font("K", 46), fill=fg(sc), anchor="rm")
    if sc.get("note"): d.text((W / 2, top + len(items) * gap + 20), sc["note"], font=font("R", 30), fill=DIM, anchor="mt")
    img.alpha_composite(lay)

def s_cards(img, t, sc, th):
    lay = L(); d = ImageDraw.Draw(lay); heading(d, sc, 230)
    items = sc["items"]; n = len(items); h = min(280, (1200 - 20 * n) / n); per = sc.get("per", None)
    for i, it in enumerate(items):
        t0 = (per * i) if per else .2 + i * .5
        p = P(t, t0, .4)
        if p <= 0: continue
        c = col(it.get("color") or PALETTE[i % len(PALETTE)], th); y0 = 360 + i * (h + 20)
        l2 = L(); box(l2, [70, y0, W - 70, y0 + h], c, r=24); dd = ImageDraw.Draw(l2)
        dd.text((115, y0 + 30), it["name"], font=font("K", 50), fill=WHITE)
        if it.get("sub"): dd.text((115, y0 + 100), it["sub"], font=font("B", 32), fill=DIM)
        if it.get("big"): gtext(l2, (W - 110, y0 + 20), it["big"], font("K", 96), c, anchor="ra", r=10)
        for j, b in enumerate(it.get("bullets", [])[:2]): dd.text((115 + j * 440, y0 + h - 70), "・" + b, font=font("B", 34), fill=WHITE)
        fade(lay, l2, p)
    img.alpha_composite(lay)

def s_chat(img, t, sc, th):
    lay = L(); d = ImageDraw.Draw(lay)
    d.rectangle([0, 120, W, 230], fill=(255, 255, 255, 255)); d.line([(0, 230), (W, 230)], fill=(220, 220, 228), width=2)
    d.text((W / 2, 175), sc.get("app", "AIアシスタント"), font=font("B", 40), fill=INK, anchor="mm")
    y = 280; f = font("R", 42); per = sc.get("per", .7)
    for i, m in enumerate(sc["messages"]):
        p = P(t, .2 + i * per, .25)
        if p <= 0: break
        me = m["who"] == "me"; lines = wrap(m["text"], f, 660, d)
        w = max(d.textlength(l, font=f) for l in lines) + 64; h = 60 * len(lines) + 36
        x0 = W - 60 - w if me else 60
        if not me and p < 1 and m.get("typing", True) and t < .2 + i * per + .25:
            pass
        l2 = L(); dd = ImageDraw.Draw(l2)
        dd.rounded_rectangle([x0, y + (1 - p) * 30, x0 + w, y + h + (1 - p) * 30], 34, fill=th["accent"] if me else (255, 255, 255), outline=None if me else (225, 225, 232), width=2)
        for k, l in enumerate(lines): dd.text((x0 + 32, y + 18 + k * 60 + (1 - p) * 30), l, font=f, fill=(10, 30, 40) if me else INK)
        fade(lay, l2, p); y += h + 34
    img.alpha_composite(lay)
    if sc.get("impact"):
        t0 = sc.get("impact_at", .2 + len(sc["messages"]) * per + .3); p = clamp((t - t0) / .18)
        if p > 0:
            ov = L(); ImageDraw.Draw(ov).rectangle([0, 1020, W, 1480], fill=(0, 0, 0, int(175 * p))); img.alpha_composite(ov)
            s = 1 + (1 - back(p)) * .6; sz = int(sc.get("impact_size", 150) * max(.4, s))
            d2 = ImageDraw.Draw(img); outline_text(d2, (W / 2, 1200), sc["impact"], font("K", sz), (255, 230, 0), sw=10)
            if sc.get("impact_sub"): d2.text((W / 2, 1390), sc["impact_sub"], font=font("B", 40), fill=WHITE, anchor="mm")

def s_zoom(img, t, sc, th):
    """circles with area ∝ value, bottom-aligned; camera zooms out from smallest to largest"""
    items = sc["items"]; vals = [it["value"] for it in items]
    radii = [math.sqrt(v) for v in vals]; R = radii[-1]
    n = len(items); hold = .7
    seg = sc.get("per", max(1.0, (sc["_dur"] - hold * 2) / max(1, n - 1)))
    target = lambda j: 420 / radii[j]  # px per unit so circle j has radius 420
    kk = clamp((t - hold) / seg, 0, n - 1); ii = min(int(kk), n - 2) if n > 1 else 0; ff = ease(kk - ii) if n > 1 else 0
    scale = math.exp(math.log(target(ii)) + (math.log(target(min(ii + 1, n - 1))) - math.log(target(ii))) * ff)
    lay = L(); d = ImageDraw.Draw(lay); base = 1500
    for j in range(n - 1, -1, -1):
        r = radii[j] * scale; c = col(items[j].get("color") or PALETTE[j % len(PALETTE)], th)
        if r > 3000: continue
        cx = W / 2; d.ellipse([cx - r, base - 2 * r, cx + r, base], fill=tuple(int(v * .25) for v in c) + (255,), outline=c, width=max(3, int(min(8, r / 12))))
        if r > 110:
            d.text((cx, base - r - 40), items[j]["name"], font=font("K", 64), fill=c, anchor="mm")
            d.text((cx, base - r + 40), items[j].get("label", f"{vals[j]:,}"), font=font("K", 56), fill=WHITE, anchor="mm")
        elif r > 4:
            d.line([(cx + r, base - r), (cx + 150, base - r - 140)], fill=c, width=4)
            d.text((cx + 160, base - r - 160), f'{items[j]["name"]}　{items[j].get("label", vals[j])}', font=font("B", 42), fill=c, anchor="lm")
    img.alpha_composite(lay); d = ImageDraw.Draw(img); heading(d, sc, 250)

def stick(d, x, y, s, c):
    w = max(2, int(5 * s)); r = 22 * s
    d.ellipse([x - r, y - r, x + r, y + r], outline=c, width=w); d.line([(x, y + r), (x, y + r + 70 * s)], fill=c, width=w)
    for sx in (-1, 1):
        d.line([(x, y + r + 25 * s), (x + sx * 30 * s, y + r + 55 * s)], fill=c, width=w); d.line([(x, y + r + 70 * s), (x + sx * 25 * s, y + r + 115 * s)], fill=c, width=w)
def s_people(img, t, sc, th):
    lay = L(); d = ImageDraw.Draw(lay); heading(d, sc, 250)
    total, hi = sc.get("total", 100), sc["highlight"]; cols = 10; rows = math.ceil(total / cols)
    on = int(hi * P(t, .5, sc.get("fill", 1.6))); hc = col(sc.get("color", "accent2"), th); base_c = (90, 90, 100) if is_light(sc) else (110, 125, 150)
    for k in range(total):
        r_, c_ = divmod(k, cols); p = P(t, .02 * k / 3, .3)
        if p <= 0: continue
        stick(d, 140 + c_ * 89, 480 + r_ * (820 / rows), .42, hc if k < on else base_c)
    if sc.get("label") and t > .5 + sc.get("fill", 1.6):
        l2 = L(); box(l2, [140, 1330, W - 140, 1470], hc, fill=(255, 255, 255, 240) if is_light(sc) else (14, 12, 28, 230), r=22)
        ImageDraw.Draw(l2).text((W / 2, 1400), sc["label"].replace("{n}", str(hi)), font=font("K", 50), fill=fg(sc), anchor="mm"); fade(lay, l2, P(t, .5 + sc.get("fill", 1.6), .3))
    img.alpha_composite(lay)

def s_kinetic(img, t, sc, th):
    d = ImageDraw.Draw(img); y = sc.get("y", 380); per = sc.get("per", .32)
    for i, l in enumerate(sc["lines"]):
        s, sz = l[0], l[1] if len(l) > 1 else 160; c = col(l[2] if len(l) > 2 else "ink" if is_light(sc) else "white", th)
        p = clamp((t - i * per) / .22)
        if p > 0:
            k = back(p); f = font("K", max(8, sz * (0.6 + 0.4 * k)))
            d.text((80, y + sz * (1 - k) * .3), s, font=f, fill=c)
        y += sz * 1.12

def s_tier(img, t, sc, th):
    lay = L(); d = ImageDraw.Draw(lay); heading(d, sc, 230)
    names = list(sc["tiers"].keys()); tc = [(255, 110, 110), (255, 180, 100), (255, 230, 110), (150, 230, 120), (120, 190, 255), (190, 150, 255)]
    seq = [(ti, j, n) for ti, k in enumerate(names) for j, n in enumerate(sc["tiers"][k])]
    order = sc.get("order"); seq = [seq[i] for i in order] if order else seq
    per = sc.get("per", (sc["_dur"] - .8) / max(1, len(seq)))
    h = min(230, 1150 / len(names))
    for ti, k in enumerate(names):
        y = 400 + ti * h; d.rectangle([60, y, 240, y + h - 20], fill=tc[ti % 6]); d.text((150, y + (h - 20) / 2), k, font=font("K", 100), fill=INK, anchor="mm")
        d.rectangle([240, y, W - 60, y + h - 20], fill=(45, 45, 55) if not is_light(sc) else (230, 230, 236))
    slots = {}
    for idx, (ti, j, n) in enumerate(seq):
        p = P(t, .4 + idx * per, .35)
        if p <= 0: continue
        cnt = slots.get(ti, 0); slots[ti] = cnt + 1
        x = 260 + cnt * 265; y = 400 + ti * h + (h - 20) / 2; fy = 1700 + (y - 1700) * back(p)
        d.rounded_rectangle([x, fy - 70, x + 245, fy + 70], 16, fill=(245, 245, 250))
        d.text((x + 122, fy), n, font=font("B", 40 if len(n) < 8 else 32), fill=INK, anchor="mm")
    img.alpha_composite(lay)

def s_point(img, t, sc, th):
    c = col(sc.get("color", "good"), th); lines = sc["lines"]; hgt = sum((l[2] if len(l) > 2 else 64) + 40 for l in lines) + 80
    y0 = 860 - hgt / 2; p = P(t, 0, .4)
    lay = L(); box(lay, [80, y0, W - 80, y0 + hgt], c); y = y0 + 60
    for l in lines:
        sz = l[2] if len(l) > 2 else 64; cc = col(l[1] if len(l) > 1 else "white", th)
        if cc == WHITE: ImageDraw.Draw(lay).text((W / 2, y), l[0], font=font("K", sz), fill=WHITE, anchor="mt")
        else: gtext(lay, (W / 2, y), l[0], font("K", sz), cc, r=12)
        y += sz + 40
    s = .92 + .08 * back(p); lay = lay.resize((int(W * s), int(H * s))); off = ((W - lay.width) // 2, (H - lay.height) // 2)
    l2 = L(); l2.alpha_composite(lay, off); fade(img, l2, p)

_net = {}
def s_network(img, t, sc, th):
    key = id(sc)
    if key not in _net:
        rnd = random.Random(7); layers = sc.get("layers", [5, 8, 8, 6, 3]); xs = np.linspace(150, W - 150, len(layers))
        pts = [[(x, 560 + (j + .5) * (880 / n)) for j in range(n)] for x, n in zip(xs, layers)]
        edges = [(a, b, rnd.random()) for L1, L2 in zip(pts, pts[1:]) for a in L1 for b in L2]
        _net[key] = (pts, edges, xs)
    pts, edges, xs = _net[key]; c = th["accent"]
    wave = (t * 1.2) % 1.6 - .2  # 0..1 across layers
    lay = L(); d = ImageDraw.Draw(lay)
    for a, b, w in edges:
        lx = (a[0] - 150) / (W - 300); on = abs(lx - wave) < .18 and w > .45
        d.line([a, b], fill=c + (220,) if on else (60, 80, 130, 70 if w > .5 else 35), width=3 if on else 1)
    img.alpha_composite(lay)
    nl = L(); nd = ImageDraw.Draw(nl)
    for L1 in pts:
        for p in L1:
            lx = (p[0] - 150) / (W - 300); on = abs(lx - wave) < .12
            nd.ellipse([p[0] - 22, p[1] - 22, p[0] + 22, p[1] + 22], fill=c + (255,) if on else (40, 60, 110, 255))
    img.alpha_composite(nl.filter(ImageFilter.GaussianBlur(14))); img.alpha_composite(nl)
    d = ImageDraw.Draw(img); heading(d, sc, 300)

def _scene_img(sz):
    im = Image.new("RGB", (sz, sz)); d = ImageDraw.Draw(im)
    for y in range(sz): tt = y / sz; d.line([(0, y), (sz, y)], fill=(int(255 - 80 * tt), int(170 - 60 * tt), int(120 + 60 * tt)))
    d.ellipse([sz * .55, sz * .18, sz * .8, sz * .43], fill=(255, 245, 200))
    d.polygon([(0, sz * .8), (sz * .35, sz * .42), (sz * .7, sz * .8)], fill=(70, 60, 110)); d.polygon([(sz * .3, sz * .85), (sz * .7, sz * .5), (sz, sz * .85)], fill=(50, 45, 90))
    d.rectangle([0, sz * .8, sz, sz], fill=(40, 40, 70)); return np.asarray(im, float)
_noise = {}
def s_noise(img, t, sc, th):
    sz = 760
    if "base" not in _noise:
        _noise["base"] = _scene_img(sz); _noise["n"] = np.random.default_rng(1).uniform(0, 255, (sz, sz, 3))
    a = 1 - P(t, .4, max(.5, sc["_dur"] - 1.2))
    arr = np.clip(_noise["base"] * (1 - a) + _noise["n"] * a, 0, 255).astype("uint8")
    img.paste(Image.fromarray(arr).convert("RGBA"), (W // 2 - sz // 2, 520))
    d = ImageDraw.Draw(img); d.rounded_rectangle([W // 2 - sz // 2, 520, W // 2 + sz // 2, 520 + sz], 12, outline=fg(sc), width=6)
    steps = sc.get("steps", 50); d.text((W / 2, 1320), f"ステップ {max(1, int(steps * (1 - a)))} / {steps}", font=font("K", 54), fill=fg(sc), anchor="mt")
    heading(d, sc, 280)

def s_cta(img, t, sc, th):
    for k, (y, s, c, dt) in enumerate([(560, sc.get("follow", "ほかのしくみも、フォローしてね"), (120, 200, 255), 0), (1150, sc.get("save", "保存して、あとで見返してね"), th["accent2"], .5)]):
        p = P(t, dt, .4)
        if p <= 0: continue
        lay = L(); d = ImageDraw.Draw(lay); f = font("B", 46); tw = d.textlength(s, font=f) + 100
        box(lay, [(W - tw) / 2, y - 50, (W + tw) / 2, y + 50], c, fill=(30, 18, 50, 235), r=50)
        ImageDraw.Draw(lay).text((W / 2, y), s, font=f, fill=WHITE, anchor="mm"); fade(img, lay, p)

_scr = {}
def s_screen(img, t, sc, th):
    """実際の画面キャプチャ（img）をカードで見せる。focus=[x0,y0,x1,y1]（0〜1）の範囲を切り出し、ゆっくり寄る"""
    key = (sc["img"], tuple(sc.get("focus", [0, 0, 1, 1])))
    if key not in _scr:
        src = Image.open(sc["_imgpath"]).convert("RGB"); fx0, fy0, fx1, fy1 = sc.get("focus", [0, 0, 1, 1])
        crop = src.crop((int(fx0 * src.width), int(fy0 * src.height), int(fx1 * src.width), int(fy1 * src.height)))
        cw = 920; ch = min(1180, int(crop.height * cw / crop.width)); crop = crop.resize((cw, int(crop.height * cw / crop.width)), Image.LANCZOS)
        _scr[key] = (crop, cw, ch)
    crop, cw, ch = _scr[key]
    z = 1 + .07 * clamp(t / max(1, sc["_dur"]))  # slow push-in
    zc = crop.resize((int(cw * z), int(crop.height * z)), Image.BILINEAR)
    ox = (zc.width - cw) // 2; oy = int((min(zc.height, ch * z) - ch) * .3)
    view = zc.crop((ox, oy, ox + cw, oy + ch))
    p = P(t, 0, .45); x0 = (W - cw) // 2; y0 = int(330 + (1 - p) * 120)
    lay = L(); box(lay, [x0 - 6, y0 - 6, x0 + cw + 6, y0 + ch + 6], th["accent"], fill=(0, 0, 0, 255), w=4, r=30)
    m = Image.new("L", (cw, ch), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, cw, ch], 24, fill=255)
    lay.paste(view, (x0, y0), m); fade(img, lay, p)
    if sc.get("label"):
        q = P(t, .1, .35); lay = L(); d = ImageDraw.Draw(lay); f = font("K", 54); tw = d.textlength(sc["label"], font=f) + 90
        box(lay, [(W - tw) / 2, 170, (W + tw) / 2, 280], th["accent"], fill=(10, 30, 46, 240), r=55)
        ImageDraw.Draw(lay).text((W / 2, 225), sc["label"], font=f, fill=WHITE, anchor="mm"); fade(img, lay, q)

def s_prompt(img, t, sc, th):
    """プロンプト（指示文）を白いカードにタイピング表示。text は \\n で改行。type_dur 秒で打ち終わる"""
    if sc.get("label"):
        q = P(t, 0, .3); lay = L(); d = ImageDraw.Draw(lay); f = font("K", 54); tw = d.textlength(sc["label"], font=f) + 90
        box(lay, [(W - tw) / 2, 170, (W + tw) / 2, 280], th["accent"], fill=(10, 30, 46, 240), r=55)
        ImageDraw.Draw(lay).text((W / 2, 225), sc["label"], font=f, fill=WHITE, anchor="mm"); fade(img, lay, q)
    p = P(t, .1, .35); x0, x1, y0 = 70, W - 70, int(340 + (1 - p) * 60)
    f = font(sc.get("weight", "B"), sc.get("size", 50)); lh = int(sc.get("size", 50) * 1.55); d = ImageDraw.Draw(img)
    lines = []
    for para in sc["text"].split("\n"): lines += wrap(para, f, x1 - x0 - 110, d) if para else [""]
    y1 = y0 + 150 + lh * len(lines) + 40
    lay = L(); dl = ImageDraw.Draw(lay)
    dl.rounded_rectangle([x0, y0, x1, y1], 30, fill=(250, 250, 252, 255))
    dl.text((x0 + 50, y0 + 62), sc.get("card_title", "コピペ用"), font=font("B", 36), fill=(120, 130, 145), anchor="lm")
    dl.rounded_rectangle([x1 - 210, y0 + 30, x1 - 40, y0 + 94], 18, outline=(170, 175, 190), width=3)
    dl.text((x1 - 125, y0 + 62), "コピー", font=font("B", 32), fill=(120, 130, 145), anchor="mm")
    dl.line([(x0 + 40, y0 + 118), (x1 - 40, y0 + 118)], fill=(225, 228, 235), width=2)
    total = sum(len(l) for l in lines); n = int(total * clamp((t - .45) / sc.get("type_dur", 2.2)))
    y = y0 + 150; caret = None
    for l in lines:
        s = l[:max(0, n)]
        dl.text((x0 + 55, y), s, font=f, fill=INK)
        if caret is None and (n <= len(l)): caret = (x0 + 55 + dl.textlength(s, font=f) + 4, y)
        n -= len(l); y += lh
    if caret is None: caret = (x0 + 55 + dl.textlength(lines[-1], font=f) + 4, y - lh)
    if n < 0 or int(t * 2.5) % 2 == 0: dl.rectangle([caret[0], caret[1] + 6, caret[0] + 5, caret[1] + lh - 18], fill=th["accent"])
    fade(img, lay, p)
    if sc.get("note"):
        q = P(t, .45 + sc.get("type_dur", 2.2) + .2, .3)
        if q > 0: ImageDraw.Draw(img).text((W / 2, y1 + 70), sc["note"], font=font("B", 42), fill=th["accent"], anchor="mm")

RENDER = {"title": s_title, "screen": s_screen, "prompt": s_prompt, "bars": s_bars, "cards": s_cards, "chat": s_chat, "zoom": s_zoom, "people": s_people, "kinetic": s_kinetic,
          "tier": s_tier, "point": s_point, "network": s_network, "noise": s_noise, "cta": s_cta}

def subtitle(img, s, a, light):
    if a <= 0 or not s: return
    lay = L(); d = ImageDraw.Draw(lay); f = font("B", 44); lines = []
    for part in s.split("\n"): lines += wrap(part, f, 900, d)
    bw = max(d.textlength(l, font=f) for l in lines) + 80; bh = 66 * len(lines) + 40; x0 = (W - bw) / 2; y0 = 1700 - bh
    d.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], 18, fill=(14, 8, 26, 215), outline=(255, 255, 255, 60), width=2)
    for i, l in enumerate(lines): d.text((W / 2, y0 + 22 + 66 * i), l, font=f, fill=WHITE, anchor="mt")
    fade(img, lay, a)

# ---------- timeline ----------
def wav_len(p):
    try: return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p]).decode())
    except Exception: return None

def build_timeline(script, hook, base):
    scenes = []
    if hook and script.get("hooks"): scenes.append(dict(script["hooks"][hook], id=script["hooks"][hook].get("id", "hook" + hook)))
    scenes += [dict(s) for s in script["scenes"]]
    t = 0.
    for i, s in enumerate(scenes):
        s.setdefault("id", f"s{i}"); a = os.path.join(base, "audio", f"{s['id']}.wav")
        if s.get("img"): s["_imgpath"] = os.path.join(base, s["img"])
        vl = wav_len(a) if os.path.exists(a) else None
        s["_audio"] = a if vl else None
        s["_dur"] = s.get("dur") or ((vl + s.get("pad", .55)) if vl else 3.0)
        if s.get("type") == "title" and vl: s["_dur"] = max(s["_dur"], 2.2)
        s["_t0"] = t; t += s["_dur"]
    return scenes, t

def frame(T, scenes, th):
    cur = next((s for s in scenes if s["_t0"] <= T < s["_t0"] + s["_dur"]), scenes[-1])
    img = background(cur.get("bg", "dark"), th).copy()
    t = T - cur["_t0"]; RENDER[cur["type"]](img, t, cur, th)
    # transitions: quick fade-in from previous for the first .2s
    i = scenes.index(cur)
    if i > 0 and t < .2 and not cur.get("cut"):
        prev = scenes[i - 1]; pimg = background(prev.get("bg", "dark"), th).copy(); RENDER[prev["type"]](pimg, prev["_dur"], prev, th)
        img = Image.blend(pimg, img, ease(t / .2))
    if cur.get("sub"): subtitle(img, cur["sub"], P(t, 0, .2), is_light(cur))
    if cur.get("source"): ImageDraw.Draw(img).text((W / 2, 1880), cur["source"], font=font("R", 24), fill=(150, 150, 160), anchor="mb")
    return img

def render(script_path, out, hook=None, stills=None):
    base = os.path.dirname(os.path.abspath(script_path)); script = json.load(open(script_path))
    th = THEMES.get(script.get("theme", "default"), THEMES["default"])
    scenes, END = build_timeline(script, hook, base)
    for s in scenes:
        if script.get("source") and "source" not in s and s["type"] != "title": s["source"] = script["source"]
    if stills:
        for st in stills: frame(st, scenes, th).convert("RGB").save(out.replace(".mp4", f"_{st:.1f}.png"))
        return scenes, END
    tmp = out.replace(".mp4", ".v.mp4")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for i in range(int(END * FPS)): p.stdin.write(frame(i / FPS, scenes, th).convert("RGB").tobytes())
    p.stdin.close(); assert p.wait() == 0
    auds = [s for s in scenes if s["_audio"]]
    if auds:
        ins, fl = [], []
        for k, s in enumerate(auds):
            ins += ["-i", s["_audio"]]; fl.append(f"[{k}]adelay={int((s['_t0'] + .12) * 1000)}:all=1[a{k}]")
        mix = "".join(f"[a{k}]" for k in range(len(auds))) + f"amix=inputs={len(auds)}:normalize=0,apad,atrim=0:{END:.2f},loudnorm=I=-16:TP=-1.5,aresample=48000[a]"
        subprocess.check_call(["ffmpeg", "-nostdin", "-v", "error", "-y", *ins, "-filter_complex", ";".join(fl) + ";" + mix, "-map", "[a]", "-ac", "2", out + ".wav"])
        subprocess.check_call(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", tmp, "-i", out + ".wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out + ".part.mp4"])
        os.replace(out + ".part.mp4", out); os.remove(tmp); os.remove(out + ".wav")
    else: os.replace(tmp, out)
    return scenes, END

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("script"); ap.add_argument("out"); ap.add_argument("--hook"); ap.add_argument("--stills")
    a = ap.parse_args()
    sc, end = render(a.script, a.out, a.hook, [float(x) for x in a.stills.split(",")] if a.stills else None)
    print(f"{end:.1f}s", " / ".join(f"{s['id']}:{s['type']}@{s['_t0']:.1f}" for s in sc))
