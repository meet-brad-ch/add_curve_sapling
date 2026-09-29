# SPDX-License-Identifier: GPL-3.0-or-later

"""The package's structure rules, checked on the source (no Blender state involved)."""

import ast
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "source"
LAYERS = {
    # package: project packages/modules it must not import
    "model": {"build", "ui", "generator", "presets", "settings"},
    "build": {"ui", "generator", "presets"},
}
BLENDER_ENTRY_POINTS = {"register", "unregister"}


def modules():
    return [p for p in SOURCE.rglob("*.py") if "presets" not in p.relative_to(SOURCE).parts]


def parse(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def project_imports(path, tree):
    """(top-level project module, imported names) for every relative import of a module."""
    package = path.relative_to(SOURCE).parent.parts
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            base = package[: len(package) - (node.level - 1)]
            target = (*base, *(node.module.split(".") if node.module else ()))
            yield target, [alias.name for alias in node.names]


class Architecture(unittest.TestCase):
    def test_layers(self):
        for path in modules():
            layer = path.relative_to(SOURCE).parts[0]
            forbidden = LAYERS.get(layer, set())
            for target, _names in project_imports(path, parse(path)):
                with self.subTest(module=str(path.relative_to(SOURCE))):
                    self.assertNotIn(target[0] if target else "", forbidden, f"imports {'.'.join(target)}")

    def test_project_imports_are_classes(self):
        for path in modules():
            for target, names in project_imports(path, parse(path)):
                for name in names:
                    with self.subTest(module=str(path.relative_to(SOURCE)), name=name):
                        self.assertTrue(name[:1].isupper() and not name.isupper(), f"{'.'.join(target)}.{name}")

    def test_no_module_level_state_or_functions(self):
        for path in modules():
            is_root = path == SOURCE / "__init__.py"
            for node in parse(path).body:
                with self.subTest(module=str(path.relative_to(SOURCE)), line=node.lineno):
                    if isinstance(node, ast.FunctionDef):
                        self.assertTrue(is_root and node.name in BLENDER_ENTRY_POINTS, node.name)
                    else:
                        docstring = isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                        allowed = (ast.Import, ast.ImportFrom, ast.ClassDef)
                        self.assertTrue(docstring or isinstance(node, allowed), ast.dump(node)[:80])

    def test_no_print(self):
        for path in modules():
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    with self.subTest(module=str(path.relative_to(SOURCE)), line=node.lineno):
                        self.assertNotEqual(node.func.id, "print")
