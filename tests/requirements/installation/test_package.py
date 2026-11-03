# SPDX-License-Identifier: GPL-3.0-or-later

"""Installation and compatibility: the Blender version, the package and the files it writes."""

import ast
import subprocess
import tomllib
import unittest
from pathlib import Path

import bpy
from support.addon import Addon
from support.paths import Paths
from support.verifies import Verifies


@Verifies("SWR-0001")
class BlenderVersion(unittest.TestCase):
    """The tests run in each supported Blender (the gate on 5.2 and on 5.3); this one states which."""

    MINIMUM = (5, 2, 0)

    def test_the_manifest_names_the_minimum(self):
        manifest = tomllib.loads((Paths.SOURCE / "blender_manifest.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["blender_version_min"], ".".join(str(part) for part in self.MINIMUM))

    def test_this_blender_is_a_supported_one(self):
        running = tuple(bpy.app.version)
        self.assertGreaterEqual(running, self.MINIMUM, f"Blender {bpy.app.version_string} is older than 5.2")


@Verifies("SWR-0002")
class PlatformPackage(unittest.TestCase):
    def test_extension_validate_accepts_the_source(self):
        command = [bpy.app.binary_path, "--factory-startup", "--command", "extension", "validate", str(Paths.SOURCE)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@Verifies("SWR-0004")
class UserFiles(unittest.TestCase):
    # calls that write or remove a file or a folder: Path's writing methods, the builtin open with a mode, os and
    # shutil. Not unlink/rename/replace: Blender's collections unlink objects, and str.replace is everywhere.
    WRITES = frozenset({"write_text", "write_bytes", "mkdir", "rmdir", "touch"})
    MODULES = frozenset({"os", "shutil"})
    # the one place the package writes: the preset store's save, into the user folder
    ALLOWED = frozenset({("presets.py", "save")})

    def test_the_user_folder_is_the_extensions_user_path(self):
        store = Addon.preset_store()
        expected = Path(bpy.utils.extension_path_user(Addon.MODULE, path="presets", create=False))
        self.assertEqual(store.user_folder(create=False), expected)

    def test_only_the_preset_store_writes_files(self):
        found = set()
        for path in sorted(Paths.SOURCE.rglob("*.py")):
            if "presets" in path.relative_to(Paths.SOURCE).parts[:-1]:
                continue
            for function, call in self.write_calls(path):
                found.add((path.relative_to(Paths.SOURCE).as_posix(), function, call))
        places = {(module, function) for module, function, _ in found}
        self.assertEqual(places, self.ALLOWED, f"file writes found: {sorted(found)}")

    def write_calls(self, path):
        """(the enclosing function, the call) for each call in a module that writes or removes a file."""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef):
                continue
            for node in ast.walk(function):
                name = self.write_name(node)
                if name is not None:
                    yield function.name, name

    def write_name(self, node):
        """The call's name when it writes or removes a file, else None."""
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in self.WRITES:
            return func.attr
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in self.MODULES:
            return f"{func.value.id}.{func.attr}"
        if isinstance(func, ast.Name) and func.id == "open" and len(node.args) > 1:
            return "open"
        return None
