# AGENTS.md (keirin-research)

競輪の検証と予想で使う共通認識（知識とスキル）のリポジトリ。Claude Code と Codex のどちらからも読む。

- AI が持つ競輪の知識は実用的とは言えない。ラインのような基本を、作業を始める時点で知っているために置く。
- 中身は、公式の資料かデータの構造で確かめた規則・事実と、自分たちのデータで判断がついた法則。判断がつかないものは候補として保留する。
- データが増えるのに合わせて、候補を確かめ直して少しずつ登録を増やしていく。

設計は keirin-platform の `docs/superpowers/specs/2026-11-01-keirin-research-design.md`。

## 構成

```
knowledge/        知識（書き方は knowledge/README.md）
candidates/       保留の候補（テーマごと。結論の根拠に使わない）
skills/           作業の段階ごとのスキル（SKILL.md）
tools/kb.py       知識の検査と問い合わせ（Python 3.12 標準ライブラリだけ）
tests/            kb.py・知識・スキルのテスト（unittest）
evals/            評価ケース（過去の失敗の再現）
.claude-plugin/   Claude Code のプラグイン宣言（薄い包み）
```

## 読み方

- スキルが使えるツールでは、競輪の話題で `keirin-knowledge` などのスキルが読み込まれる。
- スキルが使えないときは、まず `skills/keirin-knowledge/SKILL.md` を読み、その「知識の地図」から必要なファイルを読む。作業の段階に応じて、同じフォルダのほかのスキルの手順に従う。
- 最初に読むのは `knowledge/commitments.md`（取り決め）と `knowledge/domain/vocabulary.md`（言い方）。

## 知識の足し方

`skills/registering-keirin-knowledge/SKILL.md` の手順に従う。下書きをオーナーに見せ、承認を得てから書き込む。書式は `knowledge/README.md`。

## 公開してよいもの

このリポジトリは **Public**。置いてよいのは、自分たちで集計した統計と、データのスキーマだけ（`COMMIT-004`）。
収集データとその抜き出し、選手名、選手登録番号、レースを特定できる観察、ビューアの URL、内部 API の呼び出し方、オッズパークの文言は置かない。
観察記録は Private の keirin-data に置く。`kb.py check` が、選手登録番号に見える数字などの一部を検査する（名前は検査できないので、書く前に自分で確かめる）。

## コマンド

```bash
python3 tools/kb.py check                       # 書式・ID・依存・出典・避ける言い方・公開の範囲・大きさ
python3 tools/kb.py check --observations ../keirin-data/observations.md   # 観察記録も検査する
python3 tools/kb.py dependents RULE-004         # その知識に依存する知識（訂正のとき）
python3 tools/kb.py next-id LAW                 # 次の ID（候補は CAND）
python3 -m unittest discover -s tests -v        # テスト
```

## 開発ルール

組織（keirin-platform）のルールに従う。

- `main` へ直接コミットしない。ブランチ名は `feat/...`、`fix/...`、`docs/...`、`chore/...`。
- コミットは GPG 署名つき（署名の設定を変えない）。メッセージは Conventional Commits 形式の英語。
- PR の CI（`kb.py check` とテスト）が通ったら、Claude がマージする（merge commit 方式）。
- 知識・スキル・評価ケースの文章は日本語で書く。
