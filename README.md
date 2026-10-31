# keirin-research

競輪の検証と予想で使う共通認識（知識とスキル）。Claude Code と Codex のどちらからも読める形にしている。
知識（`knowledge/`）と保留の候補（`candidates/`）を1か所にだけ置き、作業の段階ごとのスキル（`skills/`）がそれを参照する。
目的は、ラインのような競輪の基本を、AI が作業を始める時点で知っていること。

使い方と開発ルールは [AGENTS.md](AGENTS.md)。

## 導入（Claude Code）

このリポジトリをそのまま skills-dir のプラグインとして入れる。

```bash
ln -s ~/github/keirin-platform/keirin-research ~/.claude/skills/keirin-research
claude plugin list
```

`keirin-research@skills-dir` が並べば入っている。無効なら `claude plugin enable keirin-research@skills-dir`。シンボリックリンクなので、知識を足せばそのまま次のセッションから効く。

## 導入（Codex）

> まだ手元の Codex で確かめていない（2026-11-01 時点で、このマシンに Codex が入っていない）。手順は Codex の公式の文書（https://learn.chatgpt.com/docs/build-skills ）による。

Codex はユーザー単位のスキルを `~/.agents/skills` から読み、シンボリックリンクをたどる。サブディレクトリを再帰的に探すかは文書に書かれていないので、スキルを1つずつリンクする。

```bash
mkdir -p ~/.agents/skills
for s in ~/github/keirin-platform/keirin-research/skills/*/; do ln -s "$s" ~/.agents/skills/"$(basename "$s")"; done
```

- スキルは知識を `../../knowledge/` で指す。リンクを実体の場所で解決すれば（`cat` などのふつうのファイルの読み方なら実体になる）、リポジトリの `knowledge/` に届く。届かないときは、リポジトリの根の `AGENTS.md` から読ませる。
- 使う側のリポジトリ（keirin-platform など）で Codex を使うなら、そのリポジトリの `AGENTS.md` に「競輪のドメイン知識は keirin-research にある」と書いておく。

## スキル

| スキル | いつ使われるか |
|---|---|
| `keirin-knowledge` | 競輪の話題全般の入口 |
| `designing-keirin-analysis` | 調べる・集計する・予想を組み立てる前 |
| `concluding-keirin-analysis` | 結論やまとめを書くとき |
| `handling-keirin-observation-conflicts` | 映像での観察とデータが食い違ったとき |
| `registering-keirin-knowledge` | 知識を足す・保留する・直すとき |

## 検査と評価

```bash
python3 tools/kb.py check
python3 -m unittest discover -s tests -v
claude plugin validate .
claude plugin eval . --ablation with-without --no-publish --trust-plugin --threshold 0.8 --json evals/results/run.json
```

評価は `--no-publish` を必ず付ける（レポートを claude.ai に公開しない）。評価の子プロセスには API キーが要る。

## ライセンス

MIT（[LICENSE](LICENSE)）。データは含まない。
