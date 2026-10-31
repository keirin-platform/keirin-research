# keirin-data の性質と期間

keirin-platform が集めたデータ（Private の keirin-data）の表、列の意味、空の値の意味、期間。データそのものはここに置かない。
詳しいスキーマは keirin-platform の docs/data-schema.md。

## DATA-KD-001 表と列

- 内容: 日ごとの CSV（`tables/<表>/YYYY/YYYY-MM-DD.csv`）で、キーは `date`＋`venue_code`＋`race_no`（＋`car_no`）。DuckDB でそのまま読める。
  - meetings（開催日）: `grade`（GP・G1・G2・G3・F1・F2）、`day_label`（初日・2日目・最終日など）、`time_slot`（DATA-KD-005）、`title`。
  - races（レース）: `race_class`（種目。例: Ａ級予選、Ｓ級決勝。全角）、`close_time`・`start_time`、`weather`・`wind_speed`（DATA-KD-007）、`entries`（出走数）。
  - entries（1行＝1選手×1レース）: `car_no`、`prefecture`・`age`・`term`、`class`・`prev_class`、`style`（脚質）、`score`、決まり手の回数 `nige`・`makuri`・`sashi`・`mark`、`back`・`home`・`start`、`win_rate`・`top2_rate`・`top3_rate`、`finish`・`finish_pos`（DATA-KD-004）、`margin`・`last_lap`、`kimarite`・`bh`、`notes`。
  - payouts（払戻）: `bet_type`、`combination`、`payout`（100円あたり）、`popularity`（DATA-KD-006）。未発売の券種は行がない。同着なら同じ券種が複数行。
  - lines（並び。1行＝1選手×1レース）: `line_no`、`line_pos`（1＝先頭、2＝番手…。競りは同じ位置）、`line_size`、`contested`、`formation`、`source`（DATA-KD-003）。
  詳細な出走表がないレースでは、`score` などの成績の列が空になる。
- 種別: データで確かめた事実
- 根拠: keirin-platform のパーサーとスキーマ
- 成立期間: 2026-10-04 以降の形式（それより前の raw も同じ表に読み替えている）
- 出典: keirin-platform:docs/data-schema.md@0850049 データスキーマ
- 最終確認日: 2026-11-01
- 依存: なし

## DATA-KD-002 収集の期間

- 内容: 2026-11-01 時点で、手元の keirin-data の entries は 2025-08-24 から 2026-10-30 まで（433日分）。
  収集は 2024-01-01 を目標に新しい日から遡っている途中で、2026-12 下旬に完了の見込み。完了までは、期間の始まりが日々前にずれる。
  期間を決める前に、実際にある日（`tables/entries/*/` のファイル）を確かめ、途切れがないかも見る。
- 種別: データで確かめた事実
- 根拠: keirin-data のファイルの一覧と、収集の設定
- 成立期間: 2026-11-01 時点。遡りが終わるまで変わり続ける
- 出典: keirin-platform:CLAUDE.md@0850049 構成、keirin-platform:CLAUDE.md@0850049 決定ログ 2026-10-25
- 最終確認日: 2026-11-01
- 依存: なし

## DATA-KD-003 lines 表は本物の並びだけ

- 内容: lines 表に入るのは、KEIRIN.JP のレース前の並び（2026-10-05 以降）と、オッズパークで取れた並びだけ。2026-11-01 時点では 2026-10-05〜10-31 の KEIRIN.JP 由来だけで、それより前の並びはない（SRC-OP-001）。
  府県（地区）から推定した並びは lines 表に入らず、予想の学習や表示のときだけその場で作る。推定の規則は、同じ地区の選手で1つのラインを作り、先頭は脚質（逃＞両＞追）、同じなら B の多い方、残りは得点の順。1人だけの追込は同じ方面のラインの後ろに付ける。
  推定の並びと本物の位置（先頭・番手・3番手以降・単騎）の一致は 82%（14レース）。推定の並びで学習すると、ラインの効果は控えめに出る。
  ラインを扱う検証は、本物の並びがあるレースに限るか、推定であることを明記する。
- 種別: データで確かめた事実
- 根拠: keirin-platform の並びの取得と推定の実装
- 成立期間: 2026-11-01 時点。オッズパークの取得が再開すれば過去分が増える
- 出典: keirin-platform:docs/lines.md@0850049 実装、keirin-platform:docs/prediction.md@0850049 モデル
- 最終確認日: 2026-11-01
- 依存: MECH-001、SRC-KJ-002、SRC-OP-001

## DATA-KD-004 着順の列

- 内容: `finish` は元の着順の文字列で、失格なども入る。`finish_pos` は数値にできたものだけの整数で、失格や落車などは空。欠場は `notes` に入る（「欠」を含む）。
  同着は同じ数値になる。上位3人を決めるときは、`finish_pos` と車番の順に並べて扱う（3着以内の同着は約1%のレース）。
- 種別: データで確かめた事実
- 根拠: keirin-platform のパーサーと予想の学習
- 成立期間: 期間の制約なし
- 出典: keirin-platform:docs/data-schema.md@0850049 entries、keirin-platform:docs/prediction.md@0850049 モデル
- 最終確認日: 2026-11-01
- 依存: なし

## DATA-KD-005 時間帯の列

- 内容: meetings の `time_slot`（day・night・midnight・morning）は、keirin-platform が持つ対応表から推定した値で、公式の項目ではない。
  ミッドナイトの車番の付け方（RULE-004）を使う分析では、この列でミッドナイトを分ける。
- 種別: データで確かめた事実
- 根拠: keirin-platform のパーサー
- 成立期間: 期間の制約なし
- 出典: keirin-platform:docs/data-schema.md@0850049 meetings
- 最終確認日: 2026-11-01
- 依存: なし

## DATA-KD-006 人気と払戻

- 内容: payouts の `popularity` は、的中した組番のその券種での人気順。「1番人気の目が的中した割合」としては使えるが、選手ごとのオッズや「1番人気の選手」は持っていない（BLIND-005）。
  「1番人気」の定義は出典によって違う（選手の単支持率、2車単のオッズ、3連単の1番人気の目など）ので、外部の数字と比べるときは定義をそろえる。
- 種別: データで確かめた事実
- 根拠: 払戻の取得元の項目
- 成立期間: 期間の制約なし
- 出典: keirin-platform:docs/keirin-theories.md@0850049 そのほかの注意
- 最終確認日: 2026-11-01
- 依存: なし

## DATA-KD-007 天候と風

- 内容: races の `weather` と `wind_speed`（m/s）はレースごとの値。風速はほとんどが 0〜2m/s で、強風のレースは少ない（2025-12-09〜2026-10-22 の約2.4万レースで、雨が約2,600、風速 3m/s 以上が約1,200）。
- 種別: データで確かめた事実
- 根拠: 収集データでの集計
- 成立期間: 2025-12-09〜2026-10-22 の集計
- 出典: keirin-platform:CLAUDE.md@0850049 オーナーの要望 10.
- 最終確認日: 2026-11-01
- 依存: なし
