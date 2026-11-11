"""posted/<account>/*/result.json の media_id ごとに、リールの数字を取って insights/<account>.json に保存する。"""
import json, os, glob, urllib.request, urllib.error
from datetime import datetime, timezone
VER = 'v23.0'
HOSTS = ['https://graph.facebook.com/' + VER, 'https://graph.instagram.com/' + VER]
ACC = {'okane': 'OKANE', 'tenshoku': 'TENSHOKU', 'toushi': 'TOUSHI', 'seiseiai': 'SEISEIAI'}
METRICS = ['views', 'reach', 'saved', 'shares', 'likes', 'comments', 'total_interactions', 'ig_reels_avg_watch_time', 'ig_reels_video_view_total_time']

def get(path):
    errs = []
    for h in HOSTS:
        try:
            with urllib.request.urlopen(f'{h}/{path}', timeout=60) as r: return json.loads(r.read().decode())
        except urllib.error.HTTPError as e: errs.append(f'{h.split("/")[2]} {e.code} {e.read().decode()[:200]}')
    raise RuntimeError(' || '.join(errs))

for acct, sfx in ACC.items():
    tok = os.environ.get('IG_TOKEN_' + sfx)
    if not tok: continue
    want = os.environ.get('ACCOUNTS', 'okane').split(',')
    if acct not in want: continue
    rows = []
    for f in sorted(glob.glob(f'posted/{acct}/*/result.json')):
        name = f.split('/')[-2]; mid = json.load(open(f)).get('media_id')
        if not mid: continue
        row = {'item': name, 'media_id': mid}
        try:
            row.update(get(f'{mid}?fields=timestamp,permalink,like_count,comments_count&access_token={tok}'))
        except Exception as e: row['err_fields'] = str(e)
        for m in METRICS:  # 1つずつ（使えない指標があっても他は取れるように）
            try:
                d = get(f'{mid}/insights?metric={m}&access_token={tok}')
                row[m] = d['data'][0]['values'][0]['value']
            except Exception as e: row.setdefault('err', {})[m] = str(e)[:500]
        rows.append(row); print(name, {k: row.get(k) for k in ['views', 'reach', 'saved', 'shares', 'likes', 'ig_reels_avg_watch_time']})
    os.makedirs('insights', exist_ok=True)
    json.dump({'fetched_at': datetime.now(timezone.utc).isoformat(), 'rows': rows}, open(f'insights/{acct}.json', 'w'), ensure_ascii=False, indent=1)
