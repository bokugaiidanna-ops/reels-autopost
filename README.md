# reels-autopost
インスタのリールを、予約時刻にトライアルリールとして自動投稿する。

※ このリポジトリは**公開**にする。インスタのAPI（Instagram Login）は動画を公開URLから取りに来るため、raw.githubusercontent.com のURLを渡している。公開リポジトリなら GitHub Actions も無料・無制限。

- `queue/okane/` … @tokusuru_okane（得するお金のしくみ）
- `queue/tenshoku/` … @tokusuru_tenshoku（得する転職のしくみ）
- 1本 = 1フォルダ：`video.mp4` / `caption.txt` / `meta.json`
- `meta.json` の `approved` が true で、`publish_at` を過ぎたものだけ投稿される
- 投稿後は `posted/` に移る（動画ファイルは消して記録だけ残す）

## シークレット（Settings → Secrets and variables → Actions）
| 名前 | 中身 |
|---|---|
| IG_TOKEN_OKANE | お金アカウントのトークン（Meta アプリ「Reels Autopost」→ Instagram API → Generate token） |
| IG_TOKEN_TENSHOKU | 転職アカウントのトークン（同上） |

ユーザーIDは scripts/publish.py に直接書いてある（okane: 17841477284747057 / tenshoku: 17841476511960111）。
| GH_PAT | トークン自動更新用（このリポジトリの Secrets を書ける細かい権限のトークン） |
