import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import kb  # noqa: E402

VALID_RULE = """## RULE-001 級班

- 内容: S級、A級、L級がある。
  - L級はガールズ。
- 種別: 規則・事実
- 根拠: 公式の制度
- 成立期間: 期間の制約なし
- 出典: keirin-platform:docs/score-correction.md@0850049 §1
- 最終確認日: 2026-11-01
- 依存: なし
"""

VALID_LAW = """## LAW-001 ラインの連動

- 内容: 同じラインの2人は、得点だけで見込むより一緒に3着以内に入りやすい。
- 種別: 全体の傾向
- 根拠: 自分たちのデータでの検証
- 成立期間: 2026-10-05 以降の並び
- 出典: keirin-platform:docs/prediction.md@0850049 試作と検証
- 最終確認日: 2026-11-01
- 依存: RULE-001
- 状態: 確認済み
- 検証の記録: keirin-platform:src/keirin/research.py@0850049、2,000 レース
- 判断が変わりうる条件: 本物の並びが1年分そろったら確かめ直す
"""

VALID_FIELD = """## FIELD-001 先行

- 内容: ファンが「先行」と言うときの対応。
- 種別: データで確かめた事実
- 根拠: 項目の定義
- 成立期間: 期間の制約なし
- 出典: keirin-platform:docs/data-schema.md@0850049 entries
- 最終確認日: 2026-11-01
- 依存: なし
- ファンの言葉: 先行
- 項目: style
- 測っているもの: 出走表の脚質
- 区別できないこと: 実際にそのレースで先行したか
- 照合: 未照合
"""

VALID_TERM = """## TERM-001 車番

- 内容: 号車ではなく1番車と言う。9頭ではなく9車。
- 種別: 用語
- 根拠: 競輪の言い方
- 成立期間: 期間の制約なし
- 出典: keirin-platform:docs/data-schema.md@0850049 entries
- 最終確認日: 2026-11-01
- 依存: なし
- 避ける言い方: 号車、/[0-9]頭/
"""

_TMP_DIRS: list[str] = []


def make_tree(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="kb-test-"))
    _TMP_DIRS.append(str(root))
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def tearDownModule() -> None:
    for d in _TMP_DIRS:
        shutil.rmtree(d, ignore_errors=True)


def pad_to(text: str, size: int) -> str:
    """text の後ろに空でない行を足して、UTF-8 でちょうど size バイトにする。"""
    need = size - len(text.encode("utf-8"))
    assert need >= 0
    return text + "x" * need


def ent(id_: str, dep: str = "なし", **fields: str) -> kb.Entry:
    """問い合わせの単体テスト用に、依存だけを持つ知識を作る。"""
    return kb.Entry(id_, "題 " + id_, {"依存": dep, **fields}, Path("x"), 1)


def term_with(avoid: str, number: int = 1) -> str:
    """VALID_TERM の 避ける言い方 と ID だけを差し替えた TERM。"""
    text = VALID_TERM.replace("号車、/[0-9]頭/", avoid)
    return text.replace("TERM-001", f"TERM-{number:03d}")


def drop_line(text: str, prefix: str) -> str:
    return "".join(l for l in text.splitlines(keepends=True) if not l.startswith(prefix))


class ParseTests(unittest.TestCase):
    def test_parse_continuation_with_bullet(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE})
        [e] = kb.load(root)
        self.assertEqual((e.id, e.title), ("RULE-001", "級班"))
        self.assertIn("L級はガールズ", e.fields["内容"])
        self.assertEqual(e.fields["種別"], "規則・事実")

    def test_parse_records_relative_path_and_heading_line(self):
        root = make_tree({"knowledge/domain/rules.md": "# 規則\n\n" + VALID_RULE})
        [e] = kb.load(root)
        self.assertEqual(e.path, Path("knowledge/domain/rules.md"))
        self.assertEqual(e.line, 3)

    def test_parse_file_returns_every_entry_in_the_file(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE + "\n" + VALID_RULE.replace("001", "002")})
        entries = kb.parse_file(root / "knowledge/domain/rules.md", root)
        self.assertEqual([e.id for e in entries], ["RULE-001", "RULE-002"])
        self.assertEqual(entries[1].fields["依存"], "なし")

    def test_load_skips_readme_and_walks_subfolders(self):
        root = make_tree({
            "knowledge/README.md": VALID_RULE,
            "knowledge/domain/rules.md": VALID_RULE,
            "knowledge/domain/notes.txt": VALID_RULE,
        })
        self.assertEqual([e.id for e in kb.load(root)], ["RULE-001"])

    def test_load_without_knowledge_folder_is_empty(self):
        self.assertEqual(kb.load(make_tree({})), [])

    def test_deps_mixed_separators(self):
        e = kb.Entry("MECH-001", "t", {"依存": "RULE-001、RULE-002, LAW-003"}, Path("x"), 1)
        self.assertEqual(kb.deps(e), ["RULE-001", "RULE-002", "LAW-003"])
        self.assertEqual(kb.deps(kb.Entry("MECH-002", "t", {"依存": "なし"}, Path("x"), 1)), [])

    def test_deps_missing_key_is_empty(self):
        self.assertEqual(kb.deps(kb.Entry("MECH-003", "t", {}, Path("x"), 1)), [])


class CheckTests(unittest.TestCase):
    def errors_for(self, text: str, path: str = "knowledge/domain/rules.md") -> list[str]:
        return kb.check(make_tree({path: text}))

    def assert_error(self, errors: list[str], *needles: str) -> None:
        self.assertTrue(
            any(all(n in e for n in needles) for e in errors),
            f"{needles} を含む誤りがない: {errors}",
        )

    def test_check_valid_tree_has_no_errors(self):
        self.assertEqual(kb.check(make_tree({"knowledge/domain/rules.md": VALID_RULE})), [])

    def test_check_empty_tree_has_no_errors(self):
        self.assertEqual(kb.check(make_tree({})), [])

    def test_check_accepts_every_kind_of_entry(self):
        root = make_tree({
            "knowledge/domain/rules.md": VALID_RULE,
            "knowledge/domain/laws.md": VALID_LAW,
            "knowledge/field-dictionary.md": VALID_FIELD,
            "knowledge/domain/vocabulary.md": VALID_TERM,
        })
        self.assertEqual(kb.check(root), [])

    def test_check_error_format_is_path_line_message(self):
        errors = self.errors_for("# 規則\n\n" + drop_line(VALID_RULE, "- 出典:"))
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("knowledge/domain/rules.md:3: "), errors[0])

    def test_check_reports_missing_required_key(self):
        errors = self.errors_for(drop_line(VALID_RULE, "- 出典:"))
        self.assert_error(errors, "RULE-001", "出典")

    def test_check_reports_empty_required_key(self):
        errors = self.errors_for(VALID_RULE.replace("- 根拠: 公式の制度", "- 根拠:"))
        self.assert_error(errors, "RULE-001", "根拠")

    def test_law_requires_state_record_and_conditions(self):
        text = drop_line(drop_line(drop_line(VALID_LAW, "- 状態:"), "- 検証の記録:"), "- 判断が変わりうる条件:")
        errors = self.errors_for(text.replace("- 依存: RULE-001", "- 依存: なし"), "knowledge/domain/laws.md")
        self.assertEqual(len(errors), 3, errors)
        self.assert_error(errors, "LAW-001", "必須キー「状態」")
        self.assert_error(errors, "LAW-001", "必須キー「検証の記録」")
        self.assert_error(errors, "LAW-001", "必須キー「判断が変わりうる条件」")

    def test_individual_law_requires_counts_and_power(self):
        individual = VALID_LAW.replace("- 種別: 全体の傾向", "- 種別: 個人差の有無")
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "knowledge/domain/laws.md": individual})
        errors = kb.check(root)
        self.assertEqual(len(errors), 2, errors)
        self.assert_error(errors, "LAW-001", "必須キー「選手あたりの件数」")
        self.assert_error(errors, "LAW-001", "必須キー「検出力」")
        overall = make_tree({"knowledge/domain/rules.md": VALID_RULE, "knowledge/domain/laws.md": VALID_LAW})
        self.assertEqual(kb.check(overall), [])

    def test_law_state_choices(self):
        root = make_tree({
            "knowledge/domain/rules.md": VALID_RULE,
            "knowledge/domain/laws.md": VALID_LAW.replace("- 状態: 確認済み", "- 状態: 未検証"),
        })
        self.assert_error(kb.check(root), "LAW-001", "状態「未検証」は不正（確認済み・否定 のどれか）")

    def test_prefix_file_mismatch(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE + "\n" + VALID_LAW})
        self.assert_error(kb.check(root), "LAW-001", "LAW の知識は knowledge/domain/laws.md に置く")

    def test_check_reports_duplicate_id(self):
        errors = self.errors_for(VALID_RULE + "\n" + VALID_RULE)
        self.assert_error(errors, "RULE-001", "重複")

    def test_check_reports_unresolved_dependency(self):
        errors = self.errors_for(VALID_RULE.replace("- 依存: なし", "- 依存: RULE-999"))
        self.assert_error(errors, "RULE-999")

    def test_check_resolves_dependency_across_files(self):
        root = make_tree({
            "knowledge/domain/rules.md": VALID_RULE,
            "knowledge/domain/laws.md": VALID_LAW,
        })
        self.assertEqual(kb.check(root), [])

    def test_check_reports_invalid_collation_enum(self):
        errors = self.errors_for(VALID_FIELD.replace("- 照合: 未照合", "- 照合: 多分"), "knowledge/field-dictionary.md")
        self.assert_error(errors, "FIELD-001", "照合")

    def test_check_reports_kind_mismatch(self):
        root = make_tree({
            "knowledge/domain/rules.md": VALID_RULE,
            "knowledge/domain/laws.md": VALID_LAW.replace("- 種別: 全体の傾向", "- 種別: 規則・事実"),
        })
        self.assert_error(kb.check(root), "LAW-001", "種別")

    def test_check_reports_kind_not_allowed_for_rule(self):
        errors = self.errors_for(VALID_RULE.replace("- 種別: 規則・事実", "- 種別: 全体の傾向"))
        self.assert_error(errors, "RULE-001", "種別")

    def test_check_accepts_data_checked_fact_for_rule(self):
        errors = self.errors_for(VALID_RULE.replace("- 種別: 規則・事実", "- 種別: データで確かめた事実"))
        self.assertEqual(errors, [])

    def test_check_reports_wrong_file_for_prefix(self):
        errors = self.errors_for(VALID_RULE, "knowledge/methodology.md")
        self.assert_error(errors, "RULE-001")

    def test_check_reports_bad_date(self):
        errors = self.errors_for(VALID_RULE.replace("2026-11-01", "2026/11/01"))
        self.assert_error(errors, "RULE-001", "最終確認日")

    def test_check_reports_impossible_date(self):
        errors = self.errors_for(VALID_RULE.replace("2026-11-01", "2026-13-45"))
        self.assert_error(errors, "RULE-001", "最終確認日")

    def test_check_reports_bad_id(self):
        errors = self.errors_for(VALID_RULE.replace("RULE-001", "RULE-1"))
        self.assert_error(errors, "RULE-1")

    def test_check_reports_unknown_prefix(self):
        errors = self.errors_for(VALID_RULE.replace("RULE-001", "LORE-001"))
        self.assert_error(errors, "LORE-001")

    def test_check_reports_oversized_files(self):
        knowledge = pad_to(VALID_RULE, 30001)
        skill = pad_to("# スキル\n", 12001)
        root = make_tree({
            "knowledge/domain/rules.md": knowledge,
            "skills/some-skill/SKILL.md": skill,
        })
        errors = kb.check(root)
        self.assert_error(errors, "knowledge/domain/rules.md")
        self.assert_error(errors, "skills/some-skill/SKILL.md")

    def test_check_files_at_the_limit_pass(self):
        root = make_tree({
            "knowledge/domain/rules.md": pad_to(VALID_RULE, 30000),
            "skills/some-skill/SKILL.md": pad_to("# スキル\n", 12000),
        })
        self.assertEqual(kb.check(root), [])

    def test_check_size_limits_count_bytes_not_characters(self):
        # 日本語は1文字3バイト。10,001 文字は 30,003 バイトなので上限を超える。
        text = VALID_RULE + "あ" * 10001 + "\n"
        errors = self.errors_for(text)
        self.assert_error(errors, "knowledge/domain/rules.md", "バイト")


class DependentsTests(unittest.TestCase):
    def test_dependents_transitive(self):
        entries = [ent("RULE-001"), ent("MECH-001", "RULE-001"), ent("LAW-001", "MECH-001")]
        self.assertEqual([e.id for e in kb.dependents(entries, "RULE-001")], ["LAW-001", "MECH-001"])
        self.assertEqual([e.id for e in kb.dependents(entries, "MECH-001")], ["LAW-001"])

    def test_dependents_excludes_target_and_unrelated_entries(self):
        entries = [ent("RULE-001"), ent("RULE-002"), ent("MECH-001", "RULE-002"), ent("LAW-001", "RULE-001")]
        self.assertEqual([e.id for e in kb.dependents(entries, "RULE-001")], ["LAW-001"])

    def test_dependents_lists_each_entry_once_in_id_order(self):
        # LAW-002 は MECH-001 と MECH-002 の両方を通って RULE-001 に届く。依存の区切りは「、」でも「,」でもよい。
        entries = [
            ent("MECH-002", "RULE-001"),
            ent("LAW-002", "MECH-002, MECH-001"),
            ent("MECH-001", "RULE-001"),
            ent("RULE-001"),
        ]
        self.assertEqual(
            [e.id for e in kb.dependents(entries, "RULE-001")], ["LAW-002", "MECH-001", "MECH-002"]
        )

    def test_dependents_survives_a_cycle_without_listing_the_target(self):
        entries = [ent("RULE-001", "MECH-001"), ent("MECH-001", "RULE-001")]
        self.assertEqual([e.id for e in kb.dependents(entries, "RULE-001")], ["MECH-001"])

    def test_dependents_of_a_leaf_or_unknown_id_is_empty(self):
        entries = [ent("RULE-001"), ent("MECH-001", "RULE-001")]
        self.assertEqual(kb.dependents(entries, "MECH-001"), [])
        self.assertEqual(kb.dependents(entries, "RULE-999"), [])


class NextIdTests(unittest.TestCase):
    def test_next_id(self):
        self.assertEqual(kb.next_id([ent("RULE-001"), ent("RULE-003")], "RULE"), "RULE-004")
        self.assertEqual(kb.next_id([], "LAW"), "LAW-001")

    def test_next_id_uses_the_largest_number_not_the_count_and_pads_to_three_digits(self):
        self.assertEqual(kb.next_id([ent("RULE-009")], "RULE"), "RULE-010")
        self.assertEqual(kb.next_id([ent("RULE-099")], "RULE"), "RULE-100")

    def test_next_id_ignores_other_prefixes_even_when_one_contains_the_other(self):
        entries = [ent("SRC-KJ-009"), ent("DATA-KD-004"), ent("RULE-002")]
        self.assertEqual(kb.next_id(entries, "SRC-OP"), "SRC-OP-001")
        self.assertEqual(kb.next_id(entries, "SRC-KJ"), "SRC-KJ-010")
        self.assertEqual(kb.next_id(entries, "RULE"), "RULE-003")


class VocabularyTests(unittest.TestCase):
    def test_vocab_regex(self):
        entries = [kb.Entry("TERM-001", "t", {"避ける言い方": "号車、/[0-9]頭/"}, Path("x"), 1)]
        self.assertEqual(kb.vocab_regex(entries), "号車|[0-9]頭")

    def test_vocab_patterns_escape_literals_and_keep_regex_bodies_as_they_are(self):
        entries = [
            kb.Entry("TERM-001", "t", {"避ける言い方": "1.5倍、/a|b+/"}, Path("x"), 1),
            kb.Entry("TERM-002", "t", {"避ける言い方": "(特)"}, Path("x"), 1),
        ]
        self.assertEqual(kb.vocab_patterns(entries), [r"1\.5倍", "a|b+", r"\(特\)"])

    def test_vocab_none_value_contributes_no_pattern(self):
        entries = [
            kb.Entry("TERM-001", "t", {"避ける言い方": "なし"}, Path("x"), 1),
            kb.Entry("TERM-002", "t", {"避ける言い方": "号車"}, Path("x"), 1),
        ]
        self.assertEqual(kb.vocab_patterns(entries), ["号車"])

    def test_vocab_regex_without_terms_is_empty(self):
        self.assertEqual(kb.vocab_regex([]), "")
        self.assertEqual(kb.vocab_regex([ent("RULE-001", **{"避ける言い方": "号車"})]), "")

    def test_vocab_reads_a_value_that_continues_on_the_next_line(self):
        text = VALID_TERM.replace("号車、/[0-9]頭/", "号車、\n  /[0-9]頭/")
        [e] = kb.load(make_tree({"knowledge/domain/vocabulary.md": text}))
        self.assertEqual(kb.vocab_regex([e]), "号車|[0-9]頭")


class VocabularyCheckTests(unittest.TestCase):
    VOCABULARY = "knowledge/domain/vocabulary.md"

    def errors_for(self, files: dict[str, str]) -> list[str]:
        return kb.check(make_tree(files))

    def test_check_reports_forbidden_vocabulary(self):
        errors = self.errors_for({
            self.VOCABULARY: VALID_TERM,
            "skills/x/SKILL.md": "# スキル\n\n9頭で走る。\n",
        })
        self.assertEqual(errors, ["skills/x/SKILL.md:3: 避ける言い方「9頭」"])

    def test_check_scans_knowledge_files_and_every_markdown_file_under_skills(self):
        errors = self.errors_for({
            self.VOCABULARY: VALID_TERM,
            "knowledge/domain/rules.md": VALID_RULE.replace("- 内容: S級、", "- 内容: 1号車、"),
            "skills/x/references/detail.md": "# 補足\n号車\n",
        })
        self.assertEqual(sorted(errors), [
            "knowledge/domain/rules.md:3: 避ける言い方「号車」",
            "skills/x/references/detail.md:2: 避ける言い方「号車」",
        ])

    def test_vocabulary_file_is_exempt(self):
        # VALID_TERM の 内容 にも 避ける言い方 そのものにも「号車」「9頭」がある。
        self.assertEqual(self.errors_for({self.VOCABULARY: VALID_TERM}), [])

    def test_readme_in_knowledge_is_exempt(self):
        errors = self.errors_for({self.VOCABULARY: VALID_TERM, "knowledge/README.md": "# 書き方\n号車は避ける\n"})
        self.assertEqual(errors, [])

    def test_check_reports_one_error_per_line_with_the_first_match(self):
        errors = self.errors_for({self.VOCABULARY: VALID_TERM, "skills/x/SKILL.md": "9頭の1号車\n"})
        self.assertEqual(errors, ["skills/x/SKILL.md:1: 避ける言い方「9頭」"])

    def test_check_collects_patterns_from_every_term(self):
        errors = self.errors_for({
            self.VOCABULARY: VALID_TERM + "\n" + term_with("馬券", 2),
            "skills/x/SKILL.md": "馬券\n",
        })
        self.assertEqual(errors, ["skills/x/SKILL.md:1: 避ける言い方「馬券」"])

    def test_check_without_forbidden_terms_scans_nothing(self):
        for avoid in ("なし", None):
            files = {"skills/x/SKILL.md": "号車 9頭\n"}
            if avoid:
                files[self.VOCABULARY] = term_with(avoid)
            self.assertEqual(self.errors_for(files), [], avoid)

    def test_check_reports_invalid_regex_on_the_term_and_still_scans_the_rest(self):
        errors = self.errors_for({
            self.VOCABULARY: term_with("号車、/[0-9頭/、/馬券+/"),
            "skills/x/SKILL.md": "号車 馬券\n",
        })
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(errors[0].startswith("knowledge/domain/vocabulary.md:1: TERM-001: 避ける言い方「/[0-9頭/」"), errors[0])
        self.assertEqual(errors[1], "skills/x/SKILL.md:1: 避ける言い方「号車」")

    def test_check_reports_a_pattern_that_matches_the_empty_string(self):
        errors = self.errors_for({self.VOCABULARY: term_with("//"), "skills/x/SKILL.md": "何か\n"})
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("knowledge/domain/vocabulary.md:1: TERM-001: 避ける言い方"), errors[0])


VALID_CAND = """## CAND-001 雨に弱い選手がいるか

- 内容: 雨のレースで成績が落ちる選手がいるか。
- 文献の根拠: なし
- 保留の理由: 選手あたりの雨の走数が十数走で、検出力が足りない
- 前回の試算: 並べ替え検定で p=0.65
- 判断に要るデータ: 2024-01 までの遡り
- 見直しの時期: 2026-12 下旬
- 最終確認日: 2026-11-01
- 関係する知識: RULE-001
"""

VALID_OBS = """## OBS-001 先行ラインの番手が早めに離れた

- 日付: 2000-01-01
- 場: 架空
- レース: 7R
- 内容: 先行ラインの番手が、打鐘の前に離れた。
- 関係する知識: RULE-001
- 記録日: 2000-01-02
"""


def with_source(source: str) -> str:
    return VALID_RULE.replace("keirin-platform:docs/score-correction.md@0850049 §1", source)


class KeirinCheckTests(unittest.TestCase):
    def assert_error(self, errors: list[str], *needles: str) -> None:
        self.assertTrue(
            any(all(n in e for n in needles) for e in errors),
            f"{needles} を含む誤りがない: {errors}",
        )

    def test_candidates_are_checked(self):
        root = make_tree({"candidates.md": "## CAND-001 x\n"})
        errors = kb.check(root)
        self.assertEqual(len(errors), 8, errors)
        self.assert_error(errors, "candidates.md:1: CAND-001", "必須キー「文献の根拠」")

    def test_valid_candidate_passes(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "candidates.md": VALID_CAND})
        self.assertEqual(kb.check(root), [])
        self.assertEqual([e.id for e in kb.load_candidates(root)], ["CAND-001"])
        self.assertEqual([e.id for e in kb.load(root)], ["RULE-001"])

    def test_candidate_id_must_use_cand_prefix(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "candidates.md": VALID_CAND.replace("CAND-001", "RULE-009")})
        self.assert_error(kb.check(root), "candidates.md", "RULE-009", "CAND")

    def test_candidate_date_is_checked(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "candidates.md": VALID_CAND.replace("2026-11-01", "11月1日")})
        self.assert_error(kb.check(root), "CAND-001", "最終確認日")

    def test_knowledge_cannot_depend_on_candidate(self):
        root = make_tree({
            "knowledge/domain/rules.md": with_source("オーナー（2026-11-01 の会話）").replace("- 依存: なし", "- 依存: CAND-001"),
            "candidates.md": VALID_CAND.replace("- 関係する知識: RULE-001", "- 関係する知識: なし"),
        })
        self.assertEqual(kb.check(root), ["knowledge/domain/rules.md:1: RULE-001: 依存「CAND-001」は候補（候補には依存できない）"])

    def test_candidate_related_knowledge_must_exist(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "candidates.md": VALID_CAND.replace("RULE-001", "LAW-009")})
        self.assert_error(kb.check(root), "CAND-001", "関係する知識「LAW-009」が見つからない")

    def test_platform_source_requires_commit(self):
        bad = make_tree({"knowledge/domain/rules.md": with_source("keirin-platform:CLAUDE.md 分析するときの前提")})
        self.assert_error(kb.check(bad), "RULE-001", "出典「keirin-platform:CLAUDE.md 分析するときの前提」は不正")
        good = make_tree({"knowledge/domain/rules.md": with_source("keirin-platform:CLAUDE.md@0850049 分析するときの前提")})
        self.assertEqual(kb.check(good), [])

    def test_source_forms(self):
        for source in (
            "オーナー（2026-11-01 の会話）",
            "https://keirin.jp/pc/static/beginner/basics/lines.html 入門",
            "https://keirin.jp/pc/static/beginner/basics/lines.html",
            "keirin-data:observations.md OBS-001",
            "keirin-platform:docs/a.md@0850049 §1、\n  オーナー（2026-11-01 の会話）",
        ):
            with self.subTest(source=source):
                self.assertEqual(kb.check(make_tree({"knowledge/domain/rules.md": with_source(source)})), [])
        for source in ("オーナー（2026-13-01 の会話）", "ユーザー（2026-11-01 の会話）", "どこかで見た", "keirin-data:observations.md"):
            with self.subTest(source=source):
                self.assert_error(kb.check(make_tree({"knowledge/domain/rules.md": with_source(source)})), "RULE-001", "出典")

    def test_observation_source_does_not_need_keirin_data(self):
        root = make_tree({"knowledge/domain/rules.md": with_source("keirin-data:observations.md OBS-001")})
        self.assertFalse((root.parent / "keirin-data").exists())
        self.assertEqual(kb.check(root), [])

    def test_public_scan_flags_registration_numbers_and_urls(self):
        body = "- 内容: 123456 の選手。\n  https://example.streamlit.app/ を見る。\n  /pc/json を呼ぶ。\n  JSJ002 で取る。\n"
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE.replace("- 内容: S級、A級、L級がある。\n", body)})
        errors = kb.check(root)
        self.assertEqual(len(errors), 4, errors)
        self.assert_error(errors, "knowledge/domain/rules.md:3:", "選手登録番号に見える6桁の数字", "123456")
        self.assert_error(errors, "knowledge/domain/rules.md:4:", "ビューアの URL")
        self.assert_error(errors, "knowledge/domain/rules.md:5:", "内部 API の場所")
        self.assert_error(errors, "knowledge/domain/rules.md:6:", "内部 API の種類の番号", "JSJ002")

    def test_public_scan_ignores_dates_counts_and_commits(self):
        body = "- 内容: 2026-10-05 から 23,456 レース。@0850049 と @3f2a9c1、1234567。\n"
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE.replace("- 内容: S級、A級、L級がある。\n", body)})
        self.assertEqual(kb.check(root), [])

    def test_public_scan_covers_skills_evals_and_entry_files(self):
        root = make_tree({
            "skills/x/SKILL.md": "# x\n123456\n",
            "evals/t1/prompt.md": "123456\n",
            "candidates.md": VALID_CAND.replace("p=0.65", "p=0.65 123456").replace("RULE-001", "なし"),
            "AGENTS.md": "123456\n",
            "README.md": "123456\n",
            "CLAUDE.md": "123456\n",
        })
        errors = kb.check(root)
        for path in ("skills/x/SKILL.md:2:", "evals/t1/prompt.md:1:", "candidates.md:", "AGENTS.md:1:", "README.md:1:", "CLAUDE.md:1:"):
            self.assert_error(errors, path, "123456")

    def test_vocabulary_scan_covers_candidates(self):
        root = make_tree({
            "knowledge/domain/vocabulary.md": VALID_TERM,
            "candidates.md": VALID_CAND.replace("雨のレースで", "1号車は雨のレースで").replace("RULE-001", "なし"),
        })
        self.assertEqual(kb.check(root), ["candidates.md:3: 避ける言い方「号車」"])

    def test_observations_checked_only_when_given(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "obs/observations.md": "## OBS-001 x\n- 日付: 2000-01-01\n"})
        self.assertEqual(kb.check(root), [])
        errors = kb.check(root, observations=root / "obs/observations.md")
        self.assert_error(errors, "OBS-001", "必須キー「記録日」")
        self.assert_error(errors, "OBS-001", "必須キー「場」")

    def test_valid_observations_pass(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "obs/observations.md": "# 観察記録\n\n" + VALID_OBS})
        self.assertEqual(kb.check(root, observations=root / "obs/observations.md"), [])

    def test_observation_related_knowledge_and_dates_are_checked(self):
        text = VALID_OBS.replace("RULE-001", "LAW-009").replace("2000-01-02", "昨日")
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "obs/observations.md": text + "\n" + VALID_OBS})
        errors = kb.check(root, observations=root / "obs/observations.md")
        self.assert_error(errors, "OBS-001", "関係する知識「LAW-009」が見つからない")
        self.assert_error(errors, "OBS-001", "記録日")
        self.assert_error(errors, "OBS-001", "重複")

    def test_observation_may_relate_to_a_candidate(self):
        root = make_tree({
            "knowledge/domain/rules.md": VALID_RULE,
            "candidates.md": VALID_CAND,
            "obs/observations.md": VALID_OBS.replace("RULE-001", "CAND-001"),
        })
        self.assertEqual(kb.check(root, observations=root / "obs/observations.md"), [])

    def test_next_id_for_candidates(self):
        root = make_tree({"candidates.md": VALID_CAND + "\n" + VALID_CAND.replace("CAND-001", "CAND-003")})
        self.assertEqual(kb.next_id(kb.load_candidates(root), "CAND"), "CAND-004")


class CliTests(unittest.TestCase):
    def run_kb(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(TOOLS / "kb.py"), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def run_check(self, root: Path) -> subprocess.CompletedProcess:
        return self.run_kb("check", "--root", str(root))

    def test_cli_check_exit_codes(self):
        ok = self.run_check(make_tree({"knowledge/domain/rules.md": VALID_RULE}))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(ok.stdout.strip(), "OK")

        bad = self.run_check(make_tree({"knowledge/domain/rules.md": drop_line(VALID_RULE, "- 出典:")}))
        self.assertEqual(bad.returncode, 1)
        self.assertIn("RULE-001", bad.stdout)
        self.assertNotIn("OK", bad.stdout)

    def test_cli_check_prints_one_line_per_error(self):
        text = VALID_RULE + "\n" + VALID_RULE.replace("RULE-001", "RULE-002").replace("2026-11-01", "2026/11/01")
        out = self.run_check(make_tree({"knowledge/domain/rules.md": text})).stdout
        lines = out.splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("RULE-002", lines[0])

    def test_cli_default_root_is_the_parent_of_tools(self):
        args = kb.build_parser().parse_args(["check"])
        self.assertEqual(args.root, TOOLS.parent)
        self.assertEqual(kb.build_parser().parse_args(["check", "--root", "/x"]).root, Path("/x"))

    def test_cli_requires_a_subcommand(self):
        result = subprocess.run([sys.executable, str(TOOLS / "kb.py")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)

    def chain_tree(self) -> Path:
        """RULE-001 ← MECH-001 ← LAW-001。MECH-001 の出典は2つに分けて書いてある。"""
        mech = (
            VALID_RULE.replace("RULE-001", "MECH-001")
            .replace("級班", "仕組み")
            .replace("- 種別: 規則・事実", "- 種別: 仕組み")
            .replace("- 依存: なし", "- 依存: RULE-001")
            .replace(
                "keirin-platform:docs/score-correction.md@0850049 §1",
                "keirin-platform:docs/a.md@0850049 §1、\n  keirin-platform:docs/b.md@0850049 §2",
            )
        )
        return make_tree({
            "knowledge/domain/rules.md": VALID_RULE,
            "knowledge/domain/mechanisms.md": mech,
            "knowledge/domain/laws.md": VALID_LAW.replace("RULE-001", "MECH-001"),
        })

    def test_cli_dependents_prints_source(self):
        result = self.run_kb("dependents", "RULE-001", "--root", str(self.chain_tree()))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "LAW-001\tラインの連動\tkeirin-platform:docs/prediction.md@0850049 試作と検証",
            "MECH-001\t仕組み\tkeirin-platform:docs/a.md@0850049 §1、 keirin-platform:docs/b.md@0850049 §2",
        ])

    def test_cli_dependents_without_dependents_prints_nothing(self):
        result = self.run_kb("dependents", "LAW-001", "--root", str(self.chain_tree()))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_cli_dependents_unknown_id_is_an_error(self):
        result = self.run_kb("dependents", "RULE-999", "--root", str(self.chain_tree()))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("RULE-999", result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_cli_next_id(self):
        root = str(self.chain_tree())
        ok = self.run_kb("next-id", "RULE", "--root", root)
        self.assertEqual((ok.returncode, ok.stdout), (0, "RULE-002\n"))
        first = self.run_kb("next-id", "TERM", "--root", root)
        self.assertEqual((first.returncode, first.stdout), (0, "TERM-001\n"))

    def test_cli_next_id_unknown_prefix_is_an_error(self):
        result = self.run_kb("next-id", "FOO", "--root", str(self.chain_tree()))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("FOO", result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_cli_vocab_regex(self):
        with_terms = self.run_kb("vocab-regex", "--root", str(make_tree({"knowledge/domain/vocabulary.md": VALID_TERM})))
        self.assertEqual((with_terms.returncode, with_terms.stdout), (0, "号車|[0-9]頭\n"))
        without = self.run_kb("vocab-regex", "--root", str(make_tree({})))
        self.assertEqual((without.returncode, without.stdout), (0, "\n"))

    def test_cli_next_id_for_candidates(self):
        root = make_tree({"candidates.md": VALID_CAND.replace("RULE-001", "なし")})
        result = self.run_kb("next-id", "CAND", "--root", str(root))
        self.assertEqual((result.returncode, result.stdout), (0, "CAND-002\n"))

    def test_cli_check_with_observations(self):
        root = make_tree({"knowledge/domain/rules.md": VALID_RULE, "obs/observations.md": "## OBS-001 x\n"})
        result = self.run_kb("check", "--root", str(root), "--observations", str(root / "obs/observations.md"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("OBS-001", result.stdout)

    def test_cli_queries_default_to_the_parent_of_tools(self):
        for argv in (["dependents", "RULE-001"], ["next-id", "RULE"], ["vocab-regex"]):
            self.assertEqual(kb.build_parser().parse_args(argv).root, TOOLS.parent, argv)


if __name__ == "__main__":
    unittest.main()
