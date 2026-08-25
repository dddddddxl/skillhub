#!/usr/bin/env python3
"""Shared catalog parsing and validation helpers."""

from __future__ import print_function

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

import yaml


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_GITHUB_OWNER = "HYGON-AI"
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
)


class CatalogError(Exception):
    pass


def load_yaml(path):
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CatalogError("{}: invalid YAML: {}".format(path.relative_to(ROOT), exc))
    if not isinstance(value, dict):
        raise CatalogError("{}: expected a YAML mapping".format(path.relative_to(ROOT)))
    return value


def safe_relative_path(value, label):
    if not isinstance(value, str) or not value.strip():
        raise CatalogError("{} must be a non-empty string".format(label))
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        raise CatalogError("{} must be a safe repository-relative POSIX path".format(label))
    return value


def load_components(root=ROOT):
    component_dir = root / "components.d"
    paths = sorted(list(component_dir.glob("*.yml")) + list(component_dir.glob("*.yaml")))
    if not paths:
        raise CatalogError("components.d contains no component definitions")

    components = []
    seen_catalog_dirs = {}
    for path in paths:
        data = load_yaml(path)
        for field in ("name", "repo", "description", "skills"):
            if field not in data:
                raise CatalogError("{}: missing required field '{}'".format(path.relative_to(root), field))
        if not isinstance(data["name"], str) or not data["name"].strip():
            raise CatalogError("{}: name must be a non-empty string".format(path.relative_to(root)))
        repo = str(data["repo"])
        if not REPO_RE.match(repo):
            raise CatalogError("{}: repo must use owner/name form".format(path.relative_to(root)))
        owner, _ = repo.split("/", 1)
        if owner != OFFICIAL_GITHUB_OWNER:
            raise CatalogError("{}: repo must be owned by {}".format(
                path.relative_to(root), OFFICIAL_GITHUB_OWNER))
        ref = data.get("ref", "main")
        if not isinstance(ref, str) or not REF_RE.match(ref) or ".." in ref:
            raise CatalogError("{}: ref contains unsafe characters".format(path.relative_to(root)))
        if not isinstance(data["description"], str) or not data["description"].strip():
            raise CatalogError("{}: description must be a non-empty string".format(path.relative_to(root)))
        if not isinstance(data["skills"], list) or not data["skills"]:
            raise CatalogError("{}: skills must be a non-empty list".format(path.relative_to(root)))
        if "local" in data and not isinstance(data["local"], bool):
            raise CatalogError("{}: local must be true or false".format(path.relative_to(root)))

        normalized = dict(data)
        normalized["ref"] = ref
        normalized["local"] = data.get("local", False)
        normalized["file"] = path
        normalized_skills = []
        for index, skill in enumerate(data["skills"]):
            label = "{}: skills[{}]".format(path.relative_to(root), index)
            if not isinstance(skill, dict):
                raise CatalogError("{} must be a mapping".format(label))
            for field in ("path", "catalog_dir", "category"):
                if field not in skill:
                    raise CatalogError("{}: missing '{}'".format(label, field))
            source_path = safe_relative_path(skill["path"], "{}.path".format(label))
            catalog_dir = skill["catalog_dir"]
            if not isinstance(catalog_dir, str) or len(catalog_dir) > 64 or not SKILL_NAME_RE.match(catalog_dir):
                raise CatalogError("{}.catalog_dir must be lowercase hyphen-case and at most 64 characters".format(label))
            category = skill["category"]
            if not isinstance(category, str) or not category.strip():
                raise CatalogError("{}.category must be a non-empty string".format(label))
            if catalog_dir in seen_catalog_dirs:
                raise CatalogError("duplicate catalog_dir '{}': {} and {}".format(
                    catalog_dir, seen_catalog_dirs[catalog_dir], path.relative_to(root)))
            seen_catalog_dirs[catalog_dir] = path.relative_to(root)
            item = dict(skill)
            item["path"] = source_path
            normalized_skills.append(item)
        normalized["skills"] = normalized_skills
        components.append(normalized)
    return components


def parse_skill_frontmatter(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise CatalogError("{}: SKILL.md must start with YAML frontmatter".format(path.relative_to(ROOT)))
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise CatalogError("{}: SKILL.md frontmatter is not closed".format(path.relative_to(ROOT)))
    try:
        metadata = yaml.safe_load("\n".join(lines[1:end]))
    except Exception as exc:
        raise CatalogError("{}: invalid frontmatter: {}".format(path.relative_to(ROOT), exc))
    if not isinstance(metadata, dict):
        raise CatalogError("{}: frontmatter must be a mapping".format(path.relative_to(ROOT)))
    return metadata, text, len(lines)


def registered_skills(components, root=ROOT):
    records = []
    for component in components:
        for spec in component["skills"]:
            skill_dir = root / "skills" / spec["catalog_dir"]
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                raise CatalogError("{}: registered skill is missing SKILL.md".format(skill_dir.relative_to(root)))
            metadata, text, line_count = parse_skill_frontmatter(skill_file)
            record = {
                "component": component,
                "spec": spec,
                "dir": skill_dir,
                "metadata": metadata,
                "text": text,
                "line_count": line_count,
            }
            records.append(record)
    return records


def file_tree_digest(path):
    digest = hashlib.sha256()
    for file_path in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(str(file_path.relative_to(path)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_catalog(root=ROOT):
    errors = []
    warnings = []
    try:
        components = load_components(root)
        records = registered_skills(components, root)
    except CatalogError as exc:
        return [str(exc)], warnings, [], []

    registered = set(record["spec"]["catalog_dir"] for record in records)
    skills_dir = root / "skills"
    actual = set(p.name for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else set()
    for orphan in sorted(actual - registered):
        errors.append("skills/{} is not registered in components.d".format(orphan))

    for record in records:
        rel = record["dir"].relative_to(root)
        metadata = record["metadata"]
        extra = sorted(set(metadata) - {"name", "description"})
        if extra:
            errors.append("{}/SKILL.md: unsupported frontmatter fields: {}".format(rel, ", ".join(extra)))
        if metadata.get("name") != record["spec"]["catalog_dir"]:
            errors.append("{}/SKILL.md: name must equal catalog_dir '{}'".format(rel, record["spec"]["catalog_dir"]))
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append("{}/SKILL.md: description must be a non-empty string".format(rel))
        elif len(description) > 1024:
            errors.append("{}/SKILL.md: description exceeds 1024 characters".format(rel))
        elif "<" in description or ">" in description:
            errors.append("{}/SKILL.md: description cannot contain angle brackets".format(rel))
        if record["line_count"] > 500:
            errors.append("{}/SKILL.md: {} lines; keep it at or below 500".format(rel, record["line_count"]))

        for path in record["dir"].rglob("*"):
            if path.is_symlink():
                errors.append("{}: symbolic links are not allowed in published skills".format(path.relative_to(root)))
            if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
                try:
                    content = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for label, pattern in SECRET_PATTERNS:
                    if pattern.search(content):
                        errors.append("{}: possible hard-coded {}".format(path.relative_to(root), label))

        for target in MARKDOWN_LINK_RE.findall(record["text"]):
            target = target.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            candidate = (record["dir"] / target).resolve()
            try:
                candidate.relative_to(record["dir"].resolve())
            except ValueError:
                errors.append("{}/SKILL.md: link escapes skill directory: {}".format(rel, target))
                continue
            if not candidate.exists():
                errors.append("{}/SKILL.md: broken relative link: {}".format(rel, target))

        openai_yaml = record["dir"] / "agents" / "openai.yaml"
        if openai_yaml.exists():
            try:
                interface = load_yaml(openai_yaml).get("interface", {})
                for field in ("display_name", "short_description", "default_prompt"):
                    if not isinstance(interface.get(field), str) or not interface[field].strip():
                        errors.append("{}: interface.{} must be a non-empty string".format(openai_yaml.relative_to(root), field))
            except CatalogError as exc:
                errors.append(str(exc))
        else:
            warnings.append("{}: agents/openai.yaml is recommended".format(rel))

    return errors, warnings, components, records


def dump_json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
