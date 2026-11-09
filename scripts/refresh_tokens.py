"""インスタの長期トークン（60日）を延長して、GitHub のシークレットを書きかえる。月1回動かす。"""
import json, os, subprocess, urllib.request
for sfx in ('OKANE', 'TENSHOKU', 'TOUSHI'):
    tok = os.environ.get('IG_TOKEN_' + sfx)
    if not tok: continue
    url = f'https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={tok}'
    new = json.loads(urllib.request.urlopen(url, timeout=60).read())['access_token']
    subprocess.run(['gh', 'secret', 'set', 'IG_TOKEN_' + sfx, '--body', new], check=True)
    print(sfx, 'refreshed')
