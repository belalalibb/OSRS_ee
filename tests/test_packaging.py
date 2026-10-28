"""Packaging guard: every importable subpackage must be declared in pyproject
so a non-editable `pip install .` ships the whole tree (bug found in a clean venv:
osrs_ee.adapters/transports/providers were missing from the wheel)."""
from __future__ import annotations

import pathlib
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class Packaging(unittest.TestCase):
    def test_every_package_dir_is_declared(self):
        declared = set(_pyproject()["tool"]["setuptools"]["packages"])
        found = set()
        for init in (ROOT / "osrs_ee").rglob("__init__.py"):
            rel = init.parent.relative_to(ROOT)
            found.add(".".join(rel.parts))
        self.assertEqual(found, declared)

    def test_package_data_and_script(self):
        pp = _pyproject()
        self.assertIn("store_schema.sql", " ".join(pp["tool"]["setuptools"]["package-data"]["osrs_ee"]))
        self.assertEqual(pp["project"]["scripts"]["osrs-ee"], "osrs_ee.cli:main")
