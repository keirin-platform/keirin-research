"""公開してよい形と、知識の中身の食い違いのテスト（最終レビューの指摘から）。"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import kb  # noqa: E402

SIX_DIGITS = re.compile(kb.PUBLIC_PATTERNS["選手登録番号に見える6桁の数字"])
STREAMLIT_HOST = re.compile(r"[\w-]+\.streamlit\.app")


def entry(id_: str) -> kb.Entry:
    [found] = [e for e in kb.load(ROOT) if e.id == id_]
    return found


class TestFixturesAreFictional(unittest.TestCase):
    """tests/ は公開の検査（kb.py）の外なので、架空の値だけを使うことをここで確かめる。"""

    def test_test_fixtures_use_fictional_values(self):
        for path in sorted((ROOT / "tests").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertLessEqual(set(SIX_DIGITS.findall(text)), {"123456", "１２３４５６"})
                self.assertLessEqual(set(STREAMLIT_HOST.findall(text)), {"example.streamlit.app"})


class TestKnowledgeMatchesSources(unittest.TestCase):
    def test_t03_grader_follows_rule_003(self):
        grader = (ROOT / "evals/t03-score-scale/graders/delta.md").read_text(encoding="utf-8")
        self.assertIn("+6.18", entry("RULE-003").fields["内容"])
        self.assertIn("+6.18", grader)
        self.assertNotIn("下がる", grader)

    def test_rule_003_reports_the_reestimate_comparison(self):
        content = entry("RULE-003").fields["内容"]
        self.assertIn("旧値", content)
        self.assertIn("サンプル内", content)

    def test_twenty_two_day_figures_cite_their_source(self):
        for e in kb.load(ROOT):
            if "22日分" in e.fields.get("内容", ""):
                with self.subTest(id=e.id):
                    self.assertIn("keirin-platform:docs/keirin-theories.md@", e.fields["出典"])

    def test_mech_001_orders_bonds_explicitly(self):
        self.assertIn("隣接地区＜同じ地区＜同じ県＜同じ競輪場", entry("MECH-001").fields["内容"])

    def test_law_001_names_what_it_measured(self):
        self.assertIn("位置の効果", entry("LAW-001").fields["判断が変わりうる条件"])


if __name__ == "__main__":
    unittest.main()
