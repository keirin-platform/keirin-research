#!/usr/bin/env python3
"""keirin-research の知識の検査と問い合わせ（Python 3.12 標準ライブラリのみ）。

    python3 tools/kb.py check [--root DIR] [--observations PATH]
    python3 tools/kb.py dependents <ID> [--root DIR]
    python3 tools/kb.py next-id <PREFIX> [--root DIR]
    python3 tools/kb.py vocab-regex [--root DIR]

知識1件の書式は knowledge/README.md を参照。
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

# --- 書式の表（ここに1回だけ書く） -------------------------------------------

# 接頭辞 → 置き場所（根からの相対パス）
FILE_FOR_PREFIX = {
    "RULE": "knowledge/domain/rules.md",
    "MECH": "knowledge/domain/mechanisms.md",
    "LAW": "knowledge/domain/laws.md",
    "TERM": "knowledge/domain/vocabulary.md",
    "METH": "knowledge/methodology.md",
    "COMMIT": "knowledge/commitments.md",
    "SRC-KJ": "knowledge/sources/keirin-jp.md",
    "SRC-OP": "knowledge/sources/oddspark.md",
    "DATA-KD": "knowledge/data/keirin-data.md",
    "FIELD": "knowledge/field-dictionary.md",
    "BLIND": "knowledge/blind-spots.md",
}

# 禁止語: TERM の「避ける言い方」。置き場所の vocabulary.md 自身は禁止語の検査から外す
VOCAB_PREFIX = "TERM"
VOCAB_KEY = "避ける言い方"

# すべての接頭辞に共通する必須キー
COMMON_KEYS = ("内容", "種別", "根拠", "成立期間", "出典", "最終確認日", "依存")

# 接頭辞 → 共通の必須キーに足す必須キー
EXTRA_KEYS = {
    "LAW": ("状態", "検証の記録", "判断が変わりうる条件"),
    "FIELD": ("ファンの言葉", "項目", "測っているもの", "区別できないこと", "照合"),
    "BLIND": ("歪みの向き",),
    "COMMIT": ("適用範囲",),
    VOCAB_PREFIX: (VOCAB_KEY,),
}

# 種別 → さらに足す必須キー（個人差の有無は、件数と検出力がないと読めない）
EXTRA_KEYS_FOR_KIND = {
    "個人差の有無": ("選手あたりの件数", "検出力"),
}

_FACT_KINDS = ("規則・事実", "データで確かめた事実")

# 接頭辞 → 許される 種別
KINDS_FOR_PREFIX = {
    "RULE": _FACT_KINDS,
    "MECH": ("仕組み",),
    "LAW": ("全体の傾向", "個人差の有無"),
    "TERM": ("用語",),
    "METH": ("方法論",),
    "COMMIT": ("取り決め",),
    "SRC-KJ": _FACT_KINDS,
    "SRC-OP": _FACT_KINDS,
    "DATA-KD": _FACT_KINDS,
    "FIELD": _FACT_KINDS,
    "BLIND": _FACT_KINDS,
}

STATES = ("確認済み", "否定")
COLLATIONS = ("照合済み", "未照合")
DATE_KEYS = ("最終確認日",)

# 保留の候補（知識ではない）。根の candidates/ にテーマごとのファイルで置き、知識はこれに依存できない
CANDIDATES_DIR = "candidates"
CANDIDATE_PREFIX = "CAND"
CANDIDATE_KEYS = ("内容", "文献の根拠", "保留の理由", "前回の試算", "判断に要るデータ", "見直しの時期", "最終確認日", "関係する知識")

# 観察記録（Private の keirin-data に置く）。`check --observations` のときだけ読む
OBSERVATION_PREFIX = "OBS"
OBS_KEYS = ("日付", "場", "レース", "内容", "関係する知識", "記録日")
OBS_DATE_KEYS = ("日付", "記録日")

# Public のリポジトリに書かないもの: 説明 → 正規表現
PUBLIC_PATTERNS = {
    "選手登録番号に見える6桁の数字": r"(?<![0-9A-Za-z])[0-9]{6}(?![0-9A-Za-z])",
    "ビューアの URL": r"streamlit\.app",
    "内部 API の場所": r"/pc/json",
    "内部 API の種類の番号": r"JSJ[0-9]{3}",
}
PUBLIC_ROOT_FILES = ("AGENTS.md", "CLAUDE.md", "README.md")
PUBLIC_FOLDERS = ("knowledge", CANDIDATES_DIR, "skills", "evals")

KNOWLEDGE_MAX_BYTES = 30_000
SKILL_MAX_BYTES = 12_000

# --- 構文 --------------------------------------------------------------------

ID_RE = re.compile(r"(" + "|".join(re.escape(p) for p in FILE_FOR_PREFIX) + r")-[0-9]{3}")
CANDIDATE_ID_RE = re.compile(CANDIDATE_PREFIX + r"-[0-9]{3}")
OBSERVATION_ID_RE = re.compile(OBSERVATION_PREFIX + r"-[0-9]{3}")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
KEY_RE = re.compile(r"- ([^:：\s]+):[ \t]*(.*)")
PLATFORM_SOURCE_RE = re.compile(r"keirin-platform:[^\s@]+@[0-9a-f]{7,40} +\S.*")
OBSERVATION_SOURCE_RE = re.compile(r"keirin-data:observations\.md OBS-[0-9]{3}")
OWNER_SOURCE_RE = re.compile(r"オーナー（(.+) の会話）")
URL_SOURCE_RE = re.compile(r"https://\S+( +\S.*)?")
SOURCE_FORMS = "`keirin-platform:<パス>@<コミット> <節>`・`https://…`・`オーナー（YYYY-MM-DD の会話）`・`keirin-data:observations.md OBS-<3桁>`"
DEP_SEPARATOR_RE = re.compile(r"[、,]")
NO_DEPENDENCY = "なし"
NO_TERMS = "なし"  # 避ける言い方がひとつもない


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    fields: dict[str, str]
    path: Path  # 根からの相対パス
    line: int  # 見出しの行番号（1始まり）


def parse_file(path: Path, root: Path) -> list[Entry]:
    """1ファイルの `## <ID> <題>` ごとの知識を読む。見出しより前の行は無視する。"""
    rel = path.relative_to(root)
    entries: list[Entry] = []
    heading: tuple[str, str, int] | None = None
    parts: dict[str, list[str]] = {}
    key: str | None = None

    def flush() -> None:
        if heading is not None:
            id_, title, line = heading
            fields = {k: "\n".join(p for p in v if p) for k, v in parts.items()}
            entries.append(Entry(id_, title, fields, rel, line))

    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.startswith("## "):
            flush()
            id_, _, title = raw[3:].strip().partition(" ")
            heading, parts, key = (id_, title.strip(), number), {}, None
        elif heading is None or not raw.strip():
            continue
        elif raw.startswith("  ") and key is not None:
            parts[key].append(raw.strip())
        elif m := KEY_RE.fullmatch(raw.rstrip()):
            key = m.group(1)
            parts[key] = [m.group(2)]
        else:
            key = None
    flush()
    return entries


def _markdown_files(root: Path) -> list[Path]:
    return sorted((root / "knowledge").rglob("*.md"))


def load(root: Path) -> list[Entry]:
    """knowledge/**/*.md（README.md を除く）の知識をすべて読む。"""
    entries: list[Entry] = []
    for path in _markdown_files(root):
        if path.name != "README.md":
            entries.extend(parse_file(path, root))
    return entries


def _candidate_files(root: Path) -> list[Path]:
    return sorted(p for p in (Path(root) / CANDIDATES_DIR).glob("*.md") if p.name != "README.md")


def load_candidates(root: Path) -> list[Entry]:
    """candidates/*.md（README.md を除く）の候補（保留したもの）をすべて読む。"""
    entries: list[Entry] = []
    for path in _candidate_files(root):
        entries.extend(parse_file(path, Path(root)))
    return entries


def _id_list(value: str) -> list[str]:
    value = value.strip()
    if value in ("", NO_DEPENDENCY):
        return []
    return [d for d in (s.strip() for s in DEP_SEPARATOR_RE.split(value)) if d]


def deps(entry: Entry) -> list[str]:
    """`依存` の ID の並び。`なし` や欠けている場合は空。"""
    return _id_list(entry.fields.get("依存", ""))


# --- 問い合わせ ---------------------------------------------------------------


def dependents(entries: list[Entry], target: str) -> list[Entry]:
    """`target` に直接・間接に依存する知識。`target` 自身は含めない。ID 順。"""
    by_dependency: dict[str, list[Entry]] = {}
    for entry in entries:
        for dep in deps(entry):
            by_dependency.setdefault(dep, []).append(entry)
    found: dict[str, Entry] = {}
    pending = [target]
    while pending:
        for entry in by_dependency.get(pending.pop(), []):
            if entry.id != target and entry.id not in found:
                found[entry.id] = entry
                pending.append(entry.id)
    return sorted(found.values(), key=lambda e: e.id)


def next_id(entries: list[Entry], prefix: str) -> str:
    """`prefix` の次の ID（最大の番号＋1、3桁0埋め）。まだ無ければ `<prefix>-001`。"""
    pattern = re.compile(re.escape(prefix) + r"-([0-9]{3})")
    numbers = [int(m.group(1)) for e in entries if (m := pattern.fullmatch(e.id))]
    return f"{prefix}-{max(numbers, default=0) + 1:03d}"


def _entry_patterns(entry: Entry) -> list[str]:
    """TERM 1件の `避ける言い方` を正規表現の並びにする。`/…/` は中身をそのまま、他は文字どおり。"""
    value = entry.fields.get(VOCAB_KEY, "").replace("\n", " ").strip()
    if value == NO_TERMS:
        return []
    patterns = []
    for item in (s.strip() for s in value.split("、")):
        if len(item) >= 2 and item.startswith("/") and item.endswith("/"):
            patterns.append(item[1:-1])
        elif item:
            patterns.append(re.escape(item))
    return patterns


def vocab_patterns(entries: list[Entry]) -> list[str]:
    """すべての TERM の `避ける言い方` を、正規表現の並びにして返す（正しいかどうかは見ない）。"""
    return [p for e in entries if e.id.startswith(VOCAB_PREFIX + "-") for p in _entry_patterns(e)]


def vocab_regex(entries: list[Entry]) -> str:
    """禁止語すべてにマッチする1つの正規表現。TERM が無ければ空文字。"""
    return "|".join(vocab_patterns(entries))


# --- 検査 --------------------------------------------------------------------


def _pattern_problem(pattern: str) -> str | None:
    """禁止語の正規表現として使えない理由。使えるなら None。"""
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        return f"正規表現として不正（{e}）"
    if compiled.search(""):
        return "空の文字列に当たる（どの行にも当たってしまう）"
    return None


def _valid_date(text: str) -> bool:
    if not DATE_RE.fullmatch(text):
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _valid_source(item: str) -> bool:
    if m := OWNER_SOURCE_RE.fullmatch(item):
        return _valid_date(m.group(1))
    return any(
        r.fullmatch(item) is not None
        for r in (PLATFORM_SOURCE_RE, OBSERVATION_SOURCE_RE, URL_SOURCE_RE)
    )


def _check_sizes(root: Path) -> list[str]:
    errors = []
    targets = [(p, KNOWLEDGE_MAX_BYTES) for p in _markdown_files(root) + _candidate_files(root)]
    targets += [(p, SKILL_MAX_BYTES) for p in sorted((root / "skills").glob("*/SKILL.md"))]
    for path, limit in targets:
        size = path.stat().st_size
        if size > limit:
            rel = path.relative_to(root).as_posix()
            errors.append(f"{rel}:1: ファイルが大きすぎる（{size} バイト、上限 {limit} バイト）")
    return errors


def _vocab_scan_files(root: Path) -> list[Path]:
    knowledge = [
        p
        for p in _markdown_files(root)
        if p.name != "README.md" and p.relative_to(root).as_posix() != FILE_FOR_PREFIX[VOCAB_PREFIX]
    ]
    return knowledge + _candidate_files(root) + sorted((root / "skills").rglob("*.md"))


def public_scan_files(root: Path) -> list[Path]:
    """公開の検査をかけるファイル（知識・スキル・評価の Markdown と、根の入口のファイル）。"""
    files = [root / name for name in PUBLIC_ROOT_FILES if (root / name).exists()]
    for folder in PUBLIC_FOLDERS:
        files += sorted((root / folder).rglob("*.md"))
    return files


def _check_public(root: Path) -> list[str]:
    """Public のリポジトリに書かないもの（選手登録番号、ビューアの URL、内部 API）が出てこないか。"""
    patterns = [(desc, re.compile(p)) for desc, p in PUBLIC_PATTERNS.items()]
    errors = []
    for path in public_scan_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for desc, regex in patterns:
                if m := regex.search(line):
                    errors.append(f"{rel}:{number}: 公開しないもの（{desc}）「{m.group(0)}」")
    return errors


def _check_vocabulary(root: Path, entries: list[Entry]) -> list[str]:
    """知識とスキルの各行に、禁止語（避ける言い方）が出てこないか。正規表現として使えないものは飛ばす。"""
    patterns = [p for p in vocab_patterns(entries) if _pattern_problem(p) is None]
    if not patterns:
        return []
    regex = re.compile("|".join(patterns))
    errors = []
    for path in _vocab_scan_files(root):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if m := regex.search(line):
                errors.append(f"{rel}:{number}: 避ける言い方「{m.group(0)}」")
    return errors


def _check_entry(entry: Entry, known_ids: set[str], first_seen: dict[str, Entry]) -> list[str]:
    where = f"{entry.path.as_posix()}:{entry.line}: {entry.id or '(IDなし)'}"
    m = ID_RE.fullmatch(entry.id)
    if not m:
        return [f"{where}: ID が不正（`<接頭辞>-<3桁の数字>` の形にする。接頭辞は {'・'.join(FILE_FOR_PREFIX)}）"]
    prefix = m.group(1)

    errors: list[str] = []
    if entry.id in first_seen:
        first = first_seen[entry.id]
        errors.append(f"{where}: ID が重複している（初出 {first.path.as_posix()}:{first.line}）")
    else:
        first_seen[entry.id] = entry

    expected = FILE_FOR_PREFIX[prefix]
    if entry.path.as_posix() != expected:
        errors.append(f"{where}: {prefix} の知識は {expected} に置く（ここは {entry.path.as_posix()}）")

    required = COMMON_KEYS + EXTRA_KEYS.get(prefix, ())
    required += EXTRA_KEYS_FOR_KIND.get(entry.fields.get("種別", ""), ())
    for key in required:
        if not entry.fields.get(key, "").strip():
            errors.append(f"{where}: 必須キー「{key}」がない（または空）")

    def check_choice(key: str, allowed: tuple[str, ...]) -> None:
        value = entry.fields.get(key)
        if value and value not in allowed:
            errors.append(f"{where}: {key}「{value}」は不正（{'・'.join(allowed)} のどれか）")

    check_choice("種別", KINDS_FOR_PREFIX[prefix])
    check_choice("状態", STATES)
    check_choice("照合", COLLATIONS)

    for key in DATE_KEYS:
        value = entry.fields.get(key)
        if value and not _valid_date(value):
            errors.append(f"{where}: {key}「{value}」は YYYY-MM-DD の日付ではない")

    if prefix == VOCAB_PREFIX:
        for pattern in _entry_patterns(entry):
            if problem := _pattern_problem(pattern):
                errors.append(f"{where}: {VOCAB_KEY}「/{pattern}/」は{problem}")

    for dep in deps(entry):
        if CANDIDATE_ID_RE.fullmatch(dep):
            errors.append(f"{where}: 依存「{dep}」は候補（候補には依存できない）")
        elif dep not in known_ids:
            errors.append(f"{where}: 依存「{dep}」が見つからない")

    source = entry.fields.get("出典", "").replace("\n", " ")
    for item in (s.strip() for s in source.split("、")):
        if item and not _valid_source(item):
            errors.append(f"{where}: 出典「{item}」は不正（{SOURCE_FORMS} のどれか。複数なら「、」で区切る）")
    return errors


def _check_simple(
    entry: Entry,
    where: str,
    id_re: re.Pattern[str],
    keys: tuple[str, ...],
    date_keys: tuple[str, ...],
    related_ids: set[str],
    first_seen: dict[str, Entry],
) -> list[str]:
    """候補と観察記録に共通の検査（ID、重複、必須キー、日付、関係する知識）。"""
    if not id_re.fullmatch(entry.id):
        return [f"{where}: ID が不正（`{id_re.pattern.split('-')[0]}-<3桁の数字>` の形にする）"]
    errors: list[str] = []
    if entry.id in first_seen:
        first = first_seen[entry.id]
        errors.append(f"{where}: ID が重複している（初出 {first.path.as_posix()}:{first.line}）")
    else:
        first_seen[entry.id] = entry
    for key in keys:
        if not entry.fields.get(key, "").strip():
            errors.append(f"{where}: 必須キー「{key}」がない（または空）")
    for key in date_keys:
        value = entry.fields.get(key)
        if value and not _valid_date(value):
            errors.append(f"{where}: {key}「{value}」は YYYY-MM-DD の日付ではない")
    for related in _id_list(entry.fields.get("関係する知識", "")):
        if related not in related_ids:
            errors.append(f"{where}: 関係する知識「{related}」が見つからない")
    return errors


def _check_candidates(root: Path, known_ids: set[str]) -> list[str]:
    errors: list[str] = []
    first_seen: dict[str, Entry] = {}
    for entry in load_candidates(root):
        where = f"{entry.path.as_posix()}:{entry.line}: {entry.id or '(IDなし)'}"
        errors += _check_simple(entry, where, CANDIDATE_ID_RE, CANDIDATE_KEYS, ("最終確認日",), known_ids, first_seen)
    return errors


def check_observations(path: Path, known_ids: set[str]) -> list[str]:
    """keirin-data の観察記録を検査する。`known_ids` は知識と候補の ID。"""
    path = Path(path)
    errors: list[str] = []
    first_seen: dict[str, Entry] = {}
    for entry in parse_file(path, path.parent):
        where = f"{path.as_posix()}:{entry.line}: {entry.id or '(IDなし)'}"
        errors += _check_simple(entry, where, OBSERVATION_ID_RE, OBS_KEYS, OBS_DATE_KEYS, known_ids, first_seen)
    return errors


def check(root: Path, observations: Path | None = None) -> list[str]:
    """知識を検査する。各要素は `<相対パス>:<行>: <内容>`。空なら合格。

    `observations` を渡したときだけ、keirin-data の観察記録も検査する。
    """
    root = Path(root)
    entries = load(root)
    known_ids = {e.id for e in entries}
    first_seen: dict[str, Entry] = {}
    errors = _check_sizes(root)
    for entry in entries:
        errors.extend(_check_entry(entry, known_ids, first_seen))
    errors.extend(_check_candidates(root, known_ids))
    errors.extend(_check_vocabulary(root, entries))
    errors.extend(_check_public(root))
    if observations is not None:
        candidate_ids = {e.id for e in load_candidates(root)}
        errors.extend(check_observations(observations, known_ids | candidate_ids))
    return errors


# --- CLI ---------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kb.py", description="keirin-research の知識の検査と問い合わせ")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_root(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="リポジトリの根（既定: tools/ の親）")

    p_check = sub.add_parser("check", help="knowledge/・candidates/・skills/ などを検査する")
    add_root(p_check)
    p_check.add_argument(
        "--observations", type=Path, default=None, help="keirin-data の observations.md も検査する"
    )

    p_dependents = sub.add_parser("dependents", help="指定した知識に直接・間接に依存する知識を挙げる")
    p_dependents.add_argument("id", metavar="ID", help="例: RULE-001")
    add_root(p_dependents)

    p_next = sub.add_parser("next-id", help="接頭辞の次の ID を表示する")
    p_next.add_argument("prefix", metavar="PREFIX", help="例: RULE")
    add_root(p_next)

    add_root(sub.add_parser("vocab-regex", help="避ける言い方すべてにマッチする正規表現を表示する"))
    return parser


def cmd_check(args: argparse.Namespace) -> int:
    errors = check(args.root, observations=args.observations)
    if errors:
        print("\n".join(errors))
        return 1
    print("OK")
    return 0


def cmd_dependents(args: argparse.Namespace) -> int:
    entries = load(args.root)
    if args.id not in {e.id for e in entries}:
        print(f"知識「{args.id}」が見つからない", file=sys.stderr)
        return 1
    for entry in dependents(entries, args.id):
        source = entry.fields.get("出典", "").replace("\n", " ")
        print(f"{entry.id}\t{entry.title}\t{source}")
    return 0


def cmd_next_id(args: argparse.Namespace) -> int:
    if args.prefix == CANDIDATE_PREFIX:
        print(next_id(load_candidates(args.root), CANDIDATE_PREFIX))
        return 0
    if args.prefix not in FILE_FOR_PREFIX:
        allowed = "・".join([*FILE_FOR_PREFIX, CANDIDATE_PREFIX])
        print(f"接頭辞「{args.prefix}」は不正（{allowed} のどれか）", file=sys.stderr)
        return 1
    print(next_id(load(args.root), args.prefix))
    return 0


def cmd_vocab_regex(args: argparse.Namespace) -> int:
    print(vocab_regex(load(args.root)))
    return 0


COMMANDS = {
    "check": cmd_check,
    "dependents": cmd_dependents,
    "next-id": cmd_next_id,
    "vocab-regex": cmd_vocab_regex,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
