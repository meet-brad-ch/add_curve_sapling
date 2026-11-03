# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of tools/: requirements check."""

import tempfile
import unittest
from pathlib import Path

import requirements_check as rc

GOOD = "When the user runs *Sapling: Add Tree*, the Sapling Tree Gen extension shall create a tree."


def requirement(statement=GOOD, method="test"):
    fields = {"Statement": statement, "Rationale": "r", "Method": method, "Criteria": "c"}
    return rc.Requirement("SWR-9999", "Title", 1, fields)


def rules_broken(statement=GOOD, method="test"):
    return {finding.rule for finding in rc.StatementRules().check(requirement(statement, method))}


class StatementRules(unittest.TestCase):
    def test_good_statement_passes(self):
        self.assertEqual(rules_broken(), set())

    def test_every_ears_form_passes(self):
        for statement in (
            "The Sapling Tree Gen extension shall store the settings.",
            "If a value is unknown, then the Sapling Tree Gen extension shall refuse the tree.",
            "While *Fast Preview* is on, the Sapling Tree Gen extension shall draw curves.",
            "Where *Prune* is on, the Sapling Tree Gen extension shall cut the branches.",
            "Where *Wind* is on, while it plays, when a frame changes, the Sapling Tree Gen extension shall sway.",
        ):
            with self.subTest(statement=statement):
                self.assertEqual(rules_broken(statement), set())

    def test_no_shall_breaks_the_form(self):
        self.assertIn("form", rules_broken("The Sapling Tree Gen extension creates a tree."))

    def test_clauses_out_of_order_break_the_form(self):
        statement = "When a tree is added, where *Prune* is on, the Sapling Tree Gen extension shall cut."
        self.assertIn("form", rules_broken(statement))

    def test_two_sentences(self):
        self.assertIn("sentence", rules_broken(GOOD + " It is green."))

    def test_more_than_25_words(self):
        long = "The Sapling Tree Gen extension shall " + " ".join(["grow"] * 20) + " trees."
        self.assertIn("length", rules_broken(long))

    def test_semicolon(self):
        self.assertIn("semicolon", rules_broken("The Sapling Tree Gen extension shall grow trees; and leaves."))

    def test_banned_word(self):
        self.assertIn("word", rules_broken("The Sapling Tree Gen extension shall grow many trees."))

    def test_banned_word_in_an_interface_name_is_allowed(self):
        statement = "While *Fast Preview* is on, the Sapling Tree Gen extension shall draw curves."
        self.assertEqual(rules_broken(statement), set())

    def test_unknown_method(self):
        self.assertIn("method", rules_broken(method="guess"))

    def test_missing_field(self):
        broken = requirement()
        del broken.fields["Criteria"]
        found = rc.StatementRules().check(broken)
        self.assertIn("no Criteria", [finding.message for finding in found])


class Document(unittest.TestCase):
    TEXT = (
        f"### SWR-0001 One\n- **Statement:** {GOOD}\n- **Rationale:** r\n- **Method:** test\n- **Criteria:** first\n"
        f"  second line\n\n### SWR-0001 Again\n- **Statement:** {GOOD}\n- **Rationale:** r\n- **Method:** test\n"
        "- **Criteria:** c\n\n### SWR-12 Bad\n\n## Appendix A - settings\n\n## Appendix B - x\n"
    )

    def document(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "requirements.md"
            path.write_text(self.TEXT, encoding="utf-8")
            return rc.RequirementsDocument(path)

    def test_fields_and_continuation_lines(self):
        first = self.document().requirements()[0]
        self.assertEqual(first.fields["Criteria"], "first second line")

    def test_duplicate_id(self):
        found = rc.Checker.duplicate_ids(self.document().requirements())
        self.assertEqual([finding.where for finding in found], ["SWR-0001"])

    def test_malformed_heading(self):
        found = self.document().malformed_headings()
        self.assertEqual([finding.rule for finding in found], ["id"])

    def test_missing_document_fails(self):
        with self.assertRaises(SystemExit):
            rc.RequirementsDocument(Path("no such file.md"))


class AppendixA(unittest.TestCase):
    def test_document_matches_the_code(self):
        document = rc.RequirementsDocument(rc.DOCUMENT)
        self.assertEqual(rc.Checker(document).findings(), [])

    def test_a_changed_default_is_found(self):
        document = rc.RequirementsDocument(rc.DOCUMENT)
        rows = document.appendix_rows()
        changed = rows[0].row().replace(f"| {rows[0].default} |", "| 12345 |")
        index = document.lines.index(rows[0].row())
        document.lines[index] = changed
        found = rc.Checker(document).appendix_findings()
        self.assertEqual(len(found), 1)
        self.assertIn(rows[0].prop, found[0].message)

    def test_a_setting_missing_from_the_table_is_found(self):
        document = rc.RequirementsDocument(rc.DOCUMENT)
        first = document.appendix_rows()[0]
        document.lines.remove(first.row())
        found = rc.Checker(document).appendix_findings()
        self.assertEqual([finding.message for finding in found], [f"`{first.prop}` is in the code, not in the table"])


class Trace(unittest.TestCase):
    MODULE = (
        "from support.verifies import Verifies\n\n\n"
        '@Verifies("SWR-0001")\n'
        "class Whole(unittest.TestCase):\n"
        '    @Verifies("SWR-0002")\n'
        "    def test_both(self):\n        pass\n\n"
        "    def test_class_only(self):\n        pass\n\n\n"
        "class Bare(unittest.TestCase):\n"
        "    def test_none(self):\n        pass\n\n"
        "    def helper(self):\n        pass\n"
    )

    def refs(self):
        with tempfile.TemporaryDirectory() as folder:
            tests = Path(folder) / "tests"
            module = tests / "requirements" / "area" / "test_trace.py"
            module.parent.mkdir(parents=True)
            module.write_text(self.MODULE, encoding="utf-8")
            trace = rc.TestTrace(tests / "requirements")
            trace.TESTS = tests
            return {ref.name.split("::")[1]: ref.ids for ref in trace.refs()}

    def test_class_and_method_ids_add_up(self):
        refs = self.refs()
        self.assertEqual(refs["Whole.test_both"], ("SWR-0001", "SWR-0002"))
        self.assertEqual(refs["Whole.test_class_only"], ("SWR-0001",))

    def test_a_test_without_ids_and_no_helper(self):
        refs = self.refs()
        self.assertEqual(refs["Bare.test_none"], ())
        self.assertNotIn("Bare.helper", refs)

    def test_the_repository_traces_cleanly(self):
        requirements = rc.RequirementsDocument(rc.DOCUMENT).requirements()
        self.assertEqual(rc.Checker.trace_findings(requirements), [])

    def test_coverage_finds_a_requirement_without_a_test(self):
        requirement = rc.Requirement("SWR-9998", "Untested", 1, {"Method": "test"})
        coverage = rc.Checker.coverage([requirement])
        self.assertEqual(coverage.gaps, ["SWR-9998"])
        self.assertIn("0 of 1", coverage.summary())
