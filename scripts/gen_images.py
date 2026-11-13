"""Cloudflare Workers AI（無料枠）で画像を作る。GitHub Actions から呼ばれる。
imagejobs/<名前>/job.json:
 {"model": "@cf/black-forest-labs/flux-2-klein-4b", "width": 768, "height": 1344, "ref": "ref.png"(任意: 同じキャラにする元絵),
  "style": "全プロンプトの後ろに付ける共通の画風", "items": [{"name": "s01", "prompt": "..."}]}
できた画像は同じフォルダに <name>.jpg、結果は log.txt。できている画像は作り直さない"""
import os, sys, json, base64, time, glob, requests
ACC, TOK = os.environ["CF_ACCOUNT_ID"], os.environ["CF_API_TOKEN"]
def run(model, prompt, w, h, ref=None):
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACC}/ai/run/{model}"; hd = {"Authorization": f"Bearer {TOK}"}
    if "flux-1-schnell" in model:
        r = requests.post(url, headers=hd, json={"prompt": prompt, "steps": 8}, timeout=180)
    else:  # flux-2 系は multipart
        files = {"prompt": (None, prompt), "width": (None, str(w)), "height": (None, str(h))}
        if ref: files["input_image_0"] = ("ref.png", open(ref, "rb"), "image/png")
        r = requests.post(url, headers=hd, files=files, timeout=300)
    try: j = r.json()
    except Exception: return None, f"HTTP {r.status_code} {r.text[:300]}"
    img = (j.get("result") or {}).get("image") if isinstance(j, dict) else None
    if not img: return None, f"HTTP {r.status_code} {json.dumps(j, ensure_ascii=False)[:400]}"
    return base64.b64decode(img), "ok"
changed = False
for jf in sorted(glob.glob("imagejobs/*/job.json")):
    d = os.path.dirname(jf); job = json.load(open(jf)); log = open(os.path.join(d, "log.txt"), "a")
    ref = os.path.join(d, job["ref"]) if job.get("ref") and os.path.exists(os.path.join(d, job["ref"])) else None
    for it in job["items"]:
        out = os.path.join(d, it["name"] + ".jpg")
        if os.path.exists(out): continue
        p = it["prompt"] + ("。" + job["style"] if job.get("style") else "")
        model = it.get("model", job.get("model", "@cf/black-forest-labs/flux-2-klein-4b"))
        data, msg = None, ""
        for k in range(2):
            r_it = os.path.join(d, it["ref"]) if it.get("ref") else ref
            data, msg = run(model, p, job.get("width", 768), job.get("height", 1344), None if it.get("no_ref") else r_it)
            if data: break
            time.sleep(3)
        log.write(f"{time.strftime('%H:%M:%S')} {it['name']} {model} {msg}\n"); log.flush(); print(it["name"], msg)
        if data: open(out, "wb").write(data); changed = True
print("changed" if changed else "nothing")
