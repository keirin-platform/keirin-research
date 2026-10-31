"""v1 の最初の知識が knowledge/ と candidates.md に揃っているかのテスト。

kb.py の単体テスト（test_kb.py）と違い、実際のリポジトリの知識を読む。
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import kb  # noqa: E402


def matching(prefix: str, entries: list[kb.Entry] | None = None, **contains: list[str]) -> list[kb.Entry]:
    """ID が prefix- で始まり、各キーの値に指定の文字列をすべて含むもの"""
    found = []
    for entry in kb.load(ROOT) if entries is None else entries:
        if not entry.id.startswith(prefix + "-"):
            continue
        if all(
            all(text in entry.fields.get(key, "") for text in texts)
            for key, texts in contains.items()
        ):
            found.append(entry)
    return found


class TestVocabularySeed(unittest.TestCase):
    def test_vocab_regex_matches_other_sport_terms(self):
        rx = re.compile(kb.vocab_regex(kb.load(ROOT)))
        for s in ["1号車", "試走", "ハンデ", "騎手", "9頭", "頭立て", "馬券", "馬身", "斤量"]:
            self.assertRegex(s, rx)

    def test_vocab_regex_has_no_false_positives(self):
        rx = re.compile(kb.vocab_regex(kb.load(ROOT)))
        for s in ["先頭", "番手", "1番車", "9車立て", "車身", "頭で買う", "冒頭"]:
            self.assertNotRegex(s, rx)


class TestDomainSeed(unittest.TestCase):
    def test_midnight_rule(self):
        self.assertTrue(matching("RULE", 内容=["ミッドナイト", "得点", "1番車"]))

    def test_line_mechanism(self):
        self.assertTrue(matching("MECH", 内容=["番手", "単騎", "競り"]))

    def test_probability_commitment(self):
        self.assertTrue(matching("COMMIT", 内容=["1着", "3着以内", "車券"], 適用範囲=["予想"]))

    def test_registration_criteria(self):
        self.assertTrue(matching("COMMIT", 内容=["95%", "前半", "0.05", "0.03"]))


if __name__ == "__main__":
    unittest.main()
