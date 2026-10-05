# SPDX-License-Identifier: GPL-3.0-or-later

"""The package's structure rules, checked on the source (no Blender state involved)."""

import ast
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source"
LAYERS = {
    # package: project packages/modules it must not import
    "model": {"build", "ui", "generator", "presets", "settings"},
    "build": {"ui", "generator", "presets"},
}
BLENDER_ENTRY_POINTS = {"register", "unregister"}
# Modules that exist only inside Blender: the model must run without them
BLENDER_MODULES = {"bpy", "mathutils", "bpy_extras", "bmesh", "gpu", "blf", "aud", "bl_math", "idprop"}
# Where a tuple is Blender's own API: an EnumProperty takes its items as (identifier, name, description) tuples
TUPLE_BOUNDARIES = {
    ("ui/properties.py", "item"),
    ("ui/properties.py", "items"),
    ("ui/operators.py", "items"),
    ("ui/operators.py", "_items"),
}


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

    def test_model_does_not_use_blender_modules(self):
        """The model grows the tree in memory, without Blender (bpy, mathutils, ...); only build/ writes Blender data,
        in bulk."""
        for path in (SOURCE / "model").rglob("*.py"):
            for node in ast.walk(parse(path)):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level:
                    names = [node.module or ""]
                for name in names:
                    with self.subTest(module=str(path.relative_to(SOURCE)), name=name):
                        self.assertNotIn(name.split(".")[0], BLENDER_MODULES)

    def test_no_positional_records(self):
        """Every record is a named class: no tuple in an annotation, and no function returns several values as a
        tuple (only Blender's enum items are tuples, where its API takes them)."""
        for path in modules():
            relative = path.relative_to(SOURCE).as_posix()
            for node in ast.walk(parse(path)):
                if (relative, self.defined_name(node)) in TUPLE_BOUNDARIES:
                    continue
                with self.subTest(module=relative, line=getattr(node, "lineno", 0)):
                    self.assertFalse(self.is_tuple_annotation(node), ast.unparse(node)[:80])
                    if isinstance(node, ast.FunctionDef):
                        returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                        self.assertFalse(any(isinstance(r.value, ast.Tuple) for r in returns), node.name)

    @staticmethod
    def defined_name(node):
        """The name a function or an annotated assignment defines ("" for other nodes)."""
        if isinstance(node, ast.FunctionDef):
            return node.name
        if isinstance(node, ast.AnnAssign):
            target = node.target
            return target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        return ""

    @staticmethod
    def is_tuple_annotation(node):
        """An annotation (argument, return or variable) that names `tuple`."""
        annotations = []
        if isinstance(node, ast.FunctionDef):
            annotations = [node.returns, *(arg.annotation for arg in node.args.args)]
        elif isinstance(node, ast.AnnAssign):
            annotations = [node.annotation]
        return any(
            isinstance(part, ast.Name) and part.id == "tuple"
            for annotation in annotations
            if annotation is not None
            for part in ast.walk(annotation)
        )

    def test_every_test_module_is_in_the_mypy_override(self):
        """mypy's per-module patterns cannot match test_*: every test and in-Blender tool is listed by hand."""
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        listed = set()
        for override in config["tool"]["mypy"]["overrides"]:
            if "union-attr" in override.get("disable_error_code", []):
                listed |= set(override["module"])
        expected = {p.stem for p in (ROOT / "tests").glob("*.py")}
        expected |= {p.stem for p in (ROOT / "tools").glob("*_in_blender.py")}
        self.assertEqual(sorted(expected - listed), [], "add them to the override in pyproject.toml")

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
                        type_only = self.is_type_checking_block(node)
                        self.assertTrue(docstring or type_only or isinstance(node, allowed), ast.dump(node)[:80])

    @staticmethod
    def is_type_checking_block(node):
        """`if TYPE_CHECKING:` holding only imports (type-only imports, which avoid import cycles)."""
        return (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
            and not node.orelse
            and all(isinstance(child, ast.Import | ast.ImportFrom) for child in node.body)
        )

    def test_no_print(self):
        for path in modules():
            for node in ast.walk(parse(path)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    with self.subTest(module=str(path.relative_to(SOURCE)), line=node.lineno):
                        self.assertNotEqual(node.func.id, "print")
