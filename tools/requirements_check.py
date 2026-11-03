# SPDX-License-Identifier: GPL-3.0-or-later

"""Check docs/requirements.md: the form of each requirement and the settings table against the code.

python tools/requirements_check.py              # the checks; FAILED and exit 1 on any finding
python tools/requirements_check.py --appendix   # print Appendix A as the code gives it

The form rules are the document's own "Rules" section: one EARS sentence with "shall", at most 25 words, no
semicolon, none of the banned words (outside *interface names* and `code`), and every field. Appendix A must list
the same settings, pages, defaults and ranges as source/ui/properties.py and source/ui/pages.py.
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCUMENT = ROOT / "docs" / "requirements.md"
PROPERTIES = ROOT / "source" / "ui" / "properties.py"
PAGES = ROOT / "source" / "ui" / "pages.py"


@dataclass(frozen=True)
class Finding:
    """One rule a requirement or the document breaks."""

    where: str
    rule: str
    message: str

    def __str__(self) -> str:
        """The finding as one line of the report."""
        return f"{self.where}: {self.rule}: {self.message}"


@dataclass
class Requirement:
    """One requirement block of the document: its ID line and its fields."""

    ident: str
    title: str
    line: int
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SettingRow:
    """One setting as Appendix A lists it, or as the code gives it."""

    page: str
    label: str
    prop: str
    default: str
    span: str

    def row(self) -> str:
        """The setting as a row of the Appendix A table."""
        return f"| {self.page} | {self.label} | `{self.prop}` | {self.default} | {self.span} |"


class StatementRules:
    """The rules of one requirement statement and of its fields."""

    SYSTEM = "the Sapling Tree Gen extension shall "
    MAX_WORDS = 25
    METHODS = frozenset({"test", "analysis", "inspection", "review"})
    FIELDS = ("Statement", "Rationale", "Method", "Criteria")
    BANNED = (
        "fast", "quickly", "slow", "appropriate", "adequate", "sufficient", "user-friendly", "easy", "etc",
        "and/or", "as needed", "as appropriate", "if possible", "usually", "normally", "minimal",
        "maximum possible", "state of the art", "robust", "flexible", "efficient", "may", "should", "could",
        "some", "several", "many",
    )  # fmt: skip
    # Where -> While -> When/If, then the main clause (the order of EARS's complex form). A clause's text must
    # not run over the start of another clause, or "When ..., where ..." would pass as one When clause.
    CLAUSE = r"(?:(?!, (?:where|while|when|if) ).)+?"
    FORM = re.compile(
        rf"^(?:Where {CLAUSE}, )?(?:While {CLAUSE}, )?(?:When {CLAUSE}, |If {CLAUSE}, then )?" + re.escape(SYSTEM),
        re.IGNORECASE,
    )
    MARKUP = re.compile(r"\*[^*]+\*|`[^`]+`")

    def check(self, requirement: Requirement) -> list[Finding]:
        """Every rule the requirement breaks."""
        findings = self.missing_fields(requirement)
        statement = requirement.fields.get("Statement", "")
        if statement:
            findings += self.statement_findings(requirement.ident, statement)
        method = requirement.fields.get("Method", "")
        if method and method not in self.METHODS:
            findings.append(Finding(requirement.ident, "method", f"'{method}' is not one of {sorted(self.METHODS)}"))
        return findings

    def missing_fields(self, requirement: Requirement) -> list[Finding]:
        """A finding for each field the requirement lacks or leaves empty."""
        findings = []
        for name in self.FIELDS:
            if not requirement.fields.get(name, "").strip():
                findings.append(Finding(requirement.ident, "fields", f"no {name}"))
        return findings

    def statement_findings(self, ident: str, statement: str) -> list[Finding]:
        """The findings on the statement's form and words."""
        findings = []
        plain = self.MARKUP.sub("X", statement)
        if not self.FORM.match(statement):
            findings.append(Finding(ident, "form", "not an EARS form with 'the Sapling Tree Gen extension shall'"))
        sentences = len(re.findall(r"[.!?](?:\s|$)", plain))
        if sentences != 1:
            findings.append(Finding(ident, "sentence", f"{sentences} sentences, EARS wants one"))
        words = len(statement.split())
        if words > self.MAX_WORDS:
            findings.append(Finding(ident, "length", f"{words} words, at most {self.MAX_WORDS}"))
        if ";" in plain:
            findings.append(Finding(ident, "semicolon", "a semicolon"))
        for word in self.banned_words(plain):
            findings.append(Finding(ident, "word", f"'{word}' is a banned word"))
        return findings

    def banned_words(self, plain: str) -> list[str]:
        """The banned words and phrases in the statement, interface names and code removed."""
        lower = plain.lower()
        found = []
        for word in self.BANNED:
            pattern = r"(?<![\w-])" + re.escape(word) + r"(?![\w-])"
            if re.search(pattern, lower):
                found.append(word)
        return found


class RequirementsDocument:
    """docs/requirements.md read into requirement blocks and the Appendix A table."""

    HEADING = re.compile(r"^### (SWR-\d{4}) (.+)$")
    FIELD = re.compile(r"^- \*\*(\w+):\*\* ?(.*)$")
    ID_LINE = re.compile(r"^### SWR-")

    def __init__(self, path: Path) -> None:
        """Read the document; raises SystemExit when it cannot be read."""
        if not path.is_file():
            raise SystemExit(f"FAILED requirements_check: no document {path}")
        self.lines = path.read_text(encoding="utf-8").splitlines()

    def requirements(self) -> list[Requirement]:
        """The requirement blocks in document order."""
        blocks: list[Requirement] = []
        last_field = ""
        for number, text in enumerate(self.lines, start=1):
            heading = self.HEADING.match(text)
            if heading:
                blocks.append(Requirement(heading.group(1), heading.group(2), number))
                last_field = ""
                continue
            if not blocks or text.startswith("#"):
                last_field = ""
                continue
            last_field = self.read_field(blocks[-1], text, last_field)
        return blocks

    def read_field(self, block: Requirement, text: str, last_field: str) -> str:
        """Add a field line, or a continuation line of the last field, to the block; the field now open."""
        match = self.FIELD.match(text)
        if match:
            block.fields[match.group(1)] = match.group(2).strip()
            return match.group(1)
        if last_field and text.startswith("  ") and text.strip():
            block.fields[last_field] += " " + text.strip()
            return last_field
        return ""

    def malformed_headings(self) -> list[Finding]:
        """A finding for each requirement heading that does not read '### SWR-nnnn Title'."""
        findings = []
        for number, text in enumerate(self.lines, start=1):
            if self.ID_LINE.match(text) and not self.HEADING.match(text):
                findings.append(Finding(f"line {number}", "id", f"'{text}' is not '### SWR-nnnn Title'"))
        return findings

    def appendix_rows(self) -> list[SettingRow]:
        """The settings of the Appendix A table."""
        start = self.lines.index("## Appendix A - settings")
        rows = []
        for text in self.lines[start:]:
            if text.startswith("## Appendix B"):
                break
            cells = [cell.strip() for cell in text.strip("|").split("|")]
            if len(cells) == 5 and cells[2].startswith("`"):
                rows.append(SettingRow(cells[0], cells[1], cells[2].strip("`"), cells[3], cells[4]))
        return rows


class CodeSettings:
    """The settings of the Add Tree panel as the code defines them: properties and their pages."""

    PAGE_NAMES = {
        "geometry": "Geometry",
        "branch_radius": "Branch Radius",
        "branch_splitting": "Branch Splitting",
        "branch_growth": "Branch Growth",
        "pruning": "Pruning",
        "leaves": "Leaves",
        "armature": "Armature",
        "animation": "Animation",
    }

    def rows(self) -> list[SettingRow]:
        """Each property drawn on a page, in the order properties.py declares them."""
        page_of = self.pages()
        rows = []
        for prop, keywords in self.properties():
            page = page_of.get(prop)
            if page is not None:
                rows.append(self.row(page, prop, keywords))
        return rows

    def pages(self) -> dict[str, str]:
        """Each property name the page methods of pages.py draw, with the first page that draws it."""
        tree = ast.parse(PAGES.read_text(encoding="utf-8"))
        page_of: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in self.PAGE_NAMES:
                for constant in ast.walk(node):
                    if isinstance(constant, ast.Constant) and isinstance(constant.value, str):
                        page_of.setdefault(constant.value, self.PAGE_NAMES[node.name])
        return page_of

    def properties(self) -> list[tuple[str, dict[str, ast.expr]]]:
        """Each annotated Blender property of properties.py: its name and its keyword arguments."""
        tree = ast.parse(PROPERTIES.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
                continue
            if isinstance(node.annotation, ast.Call):
                keywords = {k.arg: k.value for k in node.annotation.keywords if k.arg}
                found.append((node.target.id, keywords))
        return found

    @staticmethod
    def text(keywords: dict[str, ast.expr], key: str) -> str:
        """A keyword's value as the table shows it: a constant's value, else its source."""
        value = keywords.get(key)
        if value is None:
            return ""
        if isinstance(value, ast.Constant):
            return str(value.value)
        return ast.unparse(value)

    def row(self, page: str, prop: str, keywords: dict[str, ast.expr]) -> SettingRow:
        """The table row of one property."""
        low = self.text(keywords, "min")
        high = self.text(keywords, "max")
        span = ""
        if low or high:
            span = f"{low or '-'} to {high or '-'}"
        return SettingRow(page, self.text(keywords, "name"), prop, self.text(keywords, "default"), span)


@dataclass(frozen=True)
class TestRef:
    """One test method and the requirement IDs it verifies (its own and its class's)."""

    name: str
    ids: tuple[str, ...]


class TestTrace:
    """The @Verifies references of the test sources, read without running them."""

    TESTS = ROOT / "tests"
    REQUIREMENT_TESTS = TESTS / "requirements"

    def __init__(self, folder: Path) -> None:
        """The trace of every test module below `folder`."""
        self.folder = folder

    def refs(self) -> list[TestRef]:
        """Every test method below the folder with the IDs it verifies, in path order."""
        found = []
        for path in sorted(self.folder.rglob("test_*.py")):
            found += self.module_refs(path)
        return found

    def module_refs(self, path: Path) -> list[TestRef]:
        """The test methods of one module with their IDs."""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = path.relative_to(self.TESTS).with_suffix("").as_posix()
        found = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_ids = self.verified_ids(node)
                for member in node.body:
                    if isinstance(member, ast.FunctionDef) and member.name.startswith("test_"):
                        ids = class_ids + self.verified_ids(member)
                        found.append(TestRef(f"{module}::{node.name}.{member.name}", ids))
        return found

    @staticmethod
    def verified_ids(node: ast.ClassDef | ast.FunctionDef) -> tuple[str, ...]:
        """The IDs of the node's @Verifies decorators."""
        ids: list[str] = []
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or getattr(decorator.func, "id", "") != "Verifies":
                continue
            for arg in decorator.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    ids.append(arg.value)
        return tuple(ids)


@dataclass
class Coverage:
    """Which requirements the tests verify: the tests per test-verified requirement, and the gaps."""

    tests: dict[str, list[str]]
    gaps: list[str]

    def summary(self) -> str:
        """One line: how many test-verified requirements have a test."""
        verified = len(self.tests) - len(self.gaps)
        return f"requirement coverage: {verified} of {len(self.tests)} test-verified requirements have a test"


class Checker:
    """All checks of the document, reported as findings."""

    def __init__(self, document: RequirementsDocument) -> None:
        """A checker of one read document."""
        self.document = document

    def findings(self) -> list[Finding]:
        """Every finding of the document."""
        requirements = self.document.requirements()
        found = self.document.malformed_headings()
        found += self.duplicate_ids(requirements)
        rules = StatementRules()
        for requirement in requirements:
            found += rules.check(requirement)
        found += self.appendix_findings()
        found += self.trace_findings(requirements)
        return found

    @staticmethod
    def trace_findings(requirements: list[Requirement]) -> list[Finding]:
        """A finding for each test that names an unknown ID, and each requirement test that verifies nothing."""
        known = {requirement.ident for requirement in requirements}
        found = []
        for ref in TestTrace(TestTrace.TESTS).refs():
            for ident in ref.ids:
                if ident not in known:
                    found.append(Finding(ref.name, "trace", f"verifies {ident}, which docs/requirements.md lacks"))
        for ref in TestTrace(TestTrace.REQUIREMENT_TESTS).refs():
            if not ref.ids:
                found.append(Finding(ref.name, "trace", "a requirement test that names no requirement (@Verifies)"))
        return found

    @staticmethod
    def coverage(requirements: list[Requirement]) -> Coverage:
        """The tests of each requirement whose method is test, and the ones without a test."""
        tests: dict[str, list[str]] = {}
        for requirement in requirements:
            if requirement.fields.get("Method") == "test":
                tests[requirement.ident] = []
        for ref in TestTrace(TestTrace.TESTS).refs():
            for ident in ref.ids:
                if ident in tests:
                    tests[ident].append(ref.name)
        gaps = [ident for ident, names in tests.items() if not names]
        return Coverage(tests, gaps)

    @staticmethod
    def duplicate_ids(requirements: list[Requirement]) -> list[Finding]:
        """A finding for each ID used by more than one requirement."""
        seen: set[str] = set()
        found = []
        for requirement in requirements:
            if requirement.ident in seen:
                found.append(Finding(requirement.ident, "id", f"used again on line {requirement.line}"))
            seen.add(requirement.ident)
        return found

    def appendix_findings(self) -> list[Finding]:
        """A finding for each setting where Appendix A and the code differ."""
        listed = {row.prop: row for row in self.document.appendix_rows()}
        coded = {row.prop: row for row in CodeSettings().rows()}
        found = []
        for prop in sorted(coded.keys() - listed.keys()):
            found.append(Finding("Appendix A", "settings", f"`{prop}` is in the code, not in the table"))
        for prop in sorted(listed.keys() - coded.keys()):
            found.append(Finding("Appendix A", "settings", f"`{prop}` is in the table, not in the code"))
        for prop in sorted(listed.keys() & coded.keys()):
            if listed[prop] != coded[prop]:
                found.append(Finding("Appendix A", "settings", f"`{prop}`: table {listed[prop]}, code {coded[prop]}"))
        return found


def main() -> int:
    """The command line: the checks, or the Appendix A table from the code."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--appendix", action="store_true", help="print Appendix A as the code gives it")
    parser.add_argument("--require-full", action="store_true", help="fail when a test-verified requirement has no test")
    args = parser.parse_args()
    if args.appendix:
        rows = CodeSettings().rows()
        print("| Page | Setting | Property | Default | Range |")
        print("| --- | --- | --- | --- | --- |")
        for row in rows:
            print(row.row())
        return 0
    document = RequirementsDocument(DOCUMENT)
    requirements = document.requirements()
    findings = Checker(document).findings()
    for finding in findings:
        print(finding)
    coverage = Checker.coverage(requirements)
    for ident in coverage.gaps:
        print(f"{ident}: NOT VERIFIED (no test names it)")
    print(coverage.summary())
    count = len(requirements)
    if findings:
        print(f"requirements_check: FAILED {len(findings)} findings in {count} requirements")
        return 1
    if args.require_full and coverage.gaps:
        print(f"requirements_check: FAILED {len(coverage.gaps)} requirements without a test (--require-full)")
        return 1
    print(f"requirements_check: ok, {count} requirements")
    return 0


if __name__ == "__main__":
    sys.exit(main())
