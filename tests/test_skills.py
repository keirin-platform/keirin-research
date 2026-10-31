"""skills/*/SKILL.md と入口のファイルが設計の決まりを守っているかのテスト。"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
NAMES = (
    "keirin-knowledge",
    "designing-keirin-analysis",
    "concluding-keirin-analysis",
    "handling-keirin-observation-conflicts",
    "registering-keirin-knowledge",
)

# `knowledge/` や `candidates/` で始まる参照（`keirin-knowledge/` のような名前の一部は除く）
BARE_REF_RE = re.compile(r"(?<![\w/.-])(knowledge|candidates)/")
RELATIVE_REF_RE = re.compile(r"\.\./\.\./((?:knowledge|candidates)/[\w./-]*)")


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def frontmatter(name: str) -> dict[str, str]:
    lines = skill_text(name).splitlines()
    assert lines[0] == "---", name
    out = {}
    for line in lines[1:]:
        if line == "---":
            return out
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    raise AssertionError(f"{name}: front matter が閉じていない")


def section(text: str, heading: str) -> str:
    """`## <heading>` から次の `## ` までの本文"""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return match.group(1) if match else ""


class TestSkillRules(unittest.TestCase):
    def test_every_skill_exists(self):
        self.assertEqual(sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md")), sorted(NAMES))

    def test_frontmatter_name_matches_directory(self):
        for name in NAMES:
            with self.subTest(name=name):
                self.assertEqual(frontmatter(name)["name"], name)

    def test_descriptions_name_keirin_only(self):
        for name in NAMES:
            with self.subTest(name=name):
                description = frontmatter(name)["description"]
                self.assertIn("競輪", description)
                self.assertNotIn("オートレース", description)

    def test_no_plugin_root_variable(self):
        for name in NAMES:
            with self.subTest(name=name):
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", skill_text(name))

    def test_knowledge_paths_are_relative_and_exist(self):
        for name in NAMES:
            for number, line in enumerate(skill_text(name).splitlines(), 1):
                with self.subTest(name=name, line=number):
                    self.assertNotRegex(line, BARE_REF_RE)
                    for ref in RELATIVE_REF_RE.findall(line):
                        self.assertTrue((ROOT / ref).exists(), ref)
        self.assertTrue((ROOT / "candidates").is_dir())

    def test_entry_skill_maps_every_knowledge_file(self):
        text = skill_text("keirin-knowledge")
        for path in sorted((ROOT / "knowledge").rglob("*.md")):
            if path.name == "README.md":
                continue
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn("../../" + path.relative_to(ROOT).as_posix(), text)
        self.assertIn("../../candidates/", text)

    def test_designing_lists_keirin_factors(self):
        memo = section(skill_text("designing-keirin-analysis"), "設計メモ（7項目）")
        for word in ("ライン", "車番", "得点", "構成", "COMMIT-001", "COMMIT-002"):
            with self.subTest(word=word):
                self.assertIn(word, memo)

    def test_registering_keeps_names_out(self):
        text = skill_text("registering-keirin-knowledge")
        for word in ("kb.py check", "名前", "COMMIT-004"):
            with self.subTest(word=word):
                self.assertIn(word, text)

    def test_conflicts_point_to_keirin_data(self):
        text = skill_text("handling-keirin-observation-conflicts")
        self.assertIn("keirin-data", text)
        self.assertIn("observations.md", text)

    def test_claude_md_imports_agents(self):
        self.assertEqual((ROOT / "CLAUDE.md").read_text(encoding="utf-8").strip(), "@AGENTS.md")


if __name__ == "__main__":
    unittest.main()
