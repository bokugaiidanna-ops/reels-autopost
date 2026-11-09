"""queue/<account>/<item>/ にある動画を、予約時刻が来たらインスタにトライアルリールとして投稿する。
item フォルダの中身：
  video.mp4    動画（縦 1080x1920）
  caption.txt  キャプション
  meta.json    {"publish_at": "2026-11-10T19:00:00+09:00", "trial": true, "graduation": "MANUAL", "approved": true}
投稿できたら posted/<account>/<item>/ に移して result.json を残す。
"""
import json, os, sys, time, shutil, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

API = 'https://graph.instagram.com/' + os.environ.get('IG_API_VERSION', 'v23.0')  # Instagram Login 用
ACCOUNTS = {  # account フォルダ名 -> (シークレットの接尾辞, インスタのユーザーID)
    'okane': ('OKANE', '17841477284747057'),        # @tokusuru_okane
    'tenshoku': ('TENSHOKU', '17841476511960111'),  # @tokusuru_tenshoku
}
DRY = os.environ.get('DRY_RUN') == '1'


def req(method, url, data=None, headers=None, raw=None):
    body = raw if raw is not None else (urllib.parse.urlencode(data).encode() if data else None)
    r = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=300) as res:
            return json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{method} {url.split("?")[0]} -> {e.code}: {e.read().decode()[:500]}')


def publish(user_id, token, item_dir, meta):
    caption = open(os.path.join(item_dir, 'caption.txt'), encoding='utf-8').read().strip()
    # Instagram Login の API は動画を「公開URL」から取りに来る。公開リポジトリの raw URL を渡す
    repo, sha = os.environ['GITHUB_REPOSITORY'], os.environ.get('GITHUB_SHA', 'main')
    video_url = f'https://raw.githubusercontent.com/{repo}/{sha}/' + urllib.parse.quote(item_dir.replace(os.sep, '/') + '/video.mp4')
    params = {'media_type': 'REELS', 'video_url': video_url, 'caption': caption,
              'share_to_feed': 'true', 'access_token': token}
    if meta.get('trial', True):
        params['trial_params'] = json.dumps({'graduation_strategy': meta.get('graduation', 'MANUAL')})
    if DRY:
        print('  [dry-run]', video_url); return {'dry_run': True}
    # 1) 入れ物を作る（Meta が video_url から動画を取りに行く）
    cid = req('POST', f'{API}/{user_id}/media', params)['id']
    # 2) 処理が終わるのを待つ（最大10分）
    for _ in range(60):
        s = req('GET', f'{API}/{cid}?fields=status_code,status&access_token={token}')
        st = s.get('status_code')
        print('  status', st)
        if st == 'FINISHED': break
        if st in ('ERROR', 'EXPIRED'): raise RuntimeError(f'container {cid}: {s}')
        time.sleep(10)
    else:
        raise RuntimeError('timeout waiting for container')
    # 3) 公開
    p = req('POST', f'{API}/{user_id}/media_publish', {'creation_id': cid, 'access_token': token})
    return {'container_id': cid, 'media_id': p.get('id'), 'video_url': video_url}


def main():
    now = datetime.now(timezone.utc)
    posted_any, errors = False, []
    for acct, (sfx, default_id) in ACCOUNTS.items():
        qdir = os.path.join('queue', acct)
        if not os.path.isdir(qdir): continue
        token, user_id = os.environ.get('IG_TOKEN_' + sfx), os.environ.get('IG_USER_ID_' + sfx) or default_id
        for name in sorted(os.listdir(qdir)):
            item = os.path.join(qdir, name)
            mp = os.path.join(item, 'meta.json')
            if not os.path.isfile(mp): continue
            meta = json.load(open(mp, encoding='utf-8'))
            if not meta.get('approved'):
                print(f'[{acct}] {name}: 未承認なのでスキップ'); continue
            when = datetime.fromisoformat(meta['publish_at'])
            if when > now:
                print(f'[{acct}] {name}: {meta["publish_at"]} まで待つ'); continue
            if not token or not user_id:
                errors.append(f'{acct}: シークレット IG_TOKEN_{sfx} が設定されていない'); break
            print(f'[{acct}] {name}: 投稿します')
            try:
                res = publish(user_id, token, item, meta)
            except Exception as e:
                errors.append(f'{acct}/{name}: {e}'); continue
            if DRY: continue
            dest = os.path.join('posted', acct, name)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(item, dest)
            os.remove(os.path.join(dest, 'video.mp4'))  # リポジトリを軽くする
            res['posted_at'] = now.isoformat()
            json.dump(res, open(os.path.join(dest, 'result.json'), 'w'), ensure_ascii=False, indent=1)
            posted_any = True
            print(f'  -> posted {res}')
    open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a').write(f'posted={"true" if posted_any else "false"}\n')
    if errors:
        print('\n'.join(errors)); sys.exit(1)


if __name__ == '__main__':
    main()
