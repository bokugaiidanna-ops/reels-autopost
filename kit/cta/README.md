# 締めのコメント誘導（LINEプレゼント）

決定：2026-11-13（ヨウヘイさん）「これから投稿するものは、最後にコメント誘導してLINE登録させたい」
導線：リールにコメント → DM（LINEのリンク・当面は手動） → LINE友だち追加ですぐまとめが届く

## やること（キューに入れる前に必ず）
```
python3 kit/cta/add_comment_cta.py 完成.mp4 完成_cta.mp4 --genre okane|fukugyo|ai
```
- 動画の最後に約5秒の締めカード（声つき）が付く：「＼無料プレゼント／ コメントに「お金」と書いてね → お金のしくみまとめをLINEでお届けします」
- キャプションの最後にも足す：
  `🎁プレゼント` / `コメントに「お金」と書いてくれた人に、お金のしくみまとめをDMでお送りします（LINEで受け取れます）`
- 済んだら投稿フォルダに `.cta_done` を置く（二重がけ防止）

| アカウント | --genre | コメントの言葉 | プレゼント |
|---|---|---|---|
| お金 @tokusuru_okane（queue/okane） | okane | お金 | お金のしくみまとめ |
| 在宅ワーク @tokusuru_zaitaku（queue/tenshoku） | fukugyo | 副業 | 副業のしくみまとめ |
| 生成AI @tokusuru_seiseiai（queue/seiseiai） | ai | AI | AIのしくみまとめ |

もしも（queue/toushi・@moshimo_kietara）は対象外（プレゼントが決まっていないため）
効果音を入れる場合は、効果音 → 締めカードの順で
