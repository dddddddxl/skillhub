# Copyright (c) 2026 Hygon Information Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path

from scripts.skillhub import (
    CatalogError,
    load_components,
    validate_inline_skill_dependencies,
)


COMPONENT = """\
name: Example
repo: {repo}
description: Example component.
skills:
  - path: skills/example
    catalog_dir: example
    category: Testing
"""


class ComponentOwnerTests(unittest.TestCase):
    def load_repo(self, repo):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            component_dir = root / "components.d"
            component_dir.mkdir()
            (component_dir / "example.yml").write_text(
                COMPONENT.format(repo=repo), encoding="utf-8"
            )
            return load_components(root)

    def test_accepts_hygon_ai_repository(self):
        components = self.load_repo("HYGON-AI/example")
        self.assertEqual(components[0]["repo"], "HYGON-AI/example")

    def test_rejects_third_party_repository(self):
        with self.assertRaisesRegex(CatalogError, "repo must be owned by HYGON-AI"):
            self.load_repo("third-party/example")


class StandaloneSkillTests(unittest.TestCase):
    def test_rejects_dependency_on_sibling_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill_dir = root / "skills" / "bulk-example"
            skill_dir.mkdir(parents=True)
            errors = validate_inline_skill_dependencies(
                skill_dir,
                "Load `../required-skill/SKILL.md` before continuing.",
                root,
            )
            self.assertEqual(len(errors), 1)
            self.assertIn("inline dependency escapes skill directory", errors[0])

    def test_accepts_bundled_skill_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill_dir = root / "skills" / "self-contained"
            bundled = skill_dir / "references" / "rules" / "SKILL.md"
            bundled.parent.mkdir(parents=True)
            bundled.write_text("# Rules\n", encoding="utf-8")
            errors = validate_inline_skill_dependencies(
                skill_dir,
                "Load `references/rules/SKILL.md` before continuing.",
                root,
            )
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
