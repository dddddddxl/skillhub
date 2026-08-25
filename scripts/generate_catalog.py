#!/usr/bin/env python3
"""Generate human and machine-readable catalog files deterministically."""

from __future__ import print_function

import argparse
import sys
from collections import OrderedDict
from pathlib import Path

from skillhub import ROOT, dump_json, validate_catalog


START = "<!-- catalog:start -->"
END = "<!-- catalog:end -->"


def markdown_escape(value):
    return " ".join(value.split()).replace("|", "\\|")


def build_table(components):
    lines = [
        "| Product | Description | Skills |",
        "|---|---|---|",
    ]
    for component in sorted(components, key=lambda item: item["name"].lower()):
        links = []
        for spec in sorted(component["skills"], key=lambda item: item["catalog_dir"]):
            name = spec["catalog_dir"]
            links.append("[`{}`](skills/{})".format(name, name))
        lines.append("| **{}** | {} | {} |".format(
            markdown_escape(component["name"]),
            markdown_escape(component["description"]),
            ", ".join(links),
        ))
    return "\n".join(lines)


def replace_catalog(readme, table):
    if START not in readme or END not in readme:
        raise ValueError("README.md is missing catalog markers")
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    return before + START + "\n\n" + table + "\n\n" + END + after


def generated_files(components, records):
    catalog_skills = []
    categories = OrderedDict()
    for record in sorted(records, key=lambda item: item["spec"]["catalog_dir"]):
        component = record["component"]
        spec = record["spec"]
        name = spec["catalog_dir"]
        category = spec["category"]
        categories.setdefault(category, []).append(name)
        catalog_skills.append(OrderedDict([
            ("name", name),
            ("description", record["metadata"]["description"]),
            ("category", category),
            ("product", component["name"]),
            ("source", OrderedDict([
                ("repo", component["repo"]),
                ("ref", component["ref"]),
                ("path", spec["path"]),
            ])),
            ("catalog_path", "skills/{}".format(name)),
        ]))

    catalog = OrderedDict([
        ("schema_version", 1),
        ("organization", "HYGON-AI"),
        ("skills", catalog_skills),
    ])
    skills_sh = OrderedDict([
        ("$schema", "https://skills.sh/schemas/skills.sh.schema.json"),
        ("notGrouped", "bottom"),
        ("groupings", [
            OrderedDict([
                ("title", category),
                ("description", "HYGON-AI skills for {} workflows.".format(category.lower())),
                ("skills", sorted(names)),
            ])
            for category, names in sorted(categories.items(), key=lambda item: item[0].lower())
        ]),
    ])

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    return {
        readme_path: replace_catalog(readme, build_table(components)),
        ROOT / "catalog.json": dump_json(catalog),
        ROOT / "skills.sh.json": dump_json(skills_sh),
    }


def write_utf8(path, content):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    args = parser.parse_args()

    errors, warnings, components, records = validate_catalog()
    for warning in warnings:
        print("WARNING: {}".format(warning))
    if errors:
        for error in errors:
            print("ERROR: {}".format(error))
        return 1

    stale = []
    for path, content in generated_files(components, records).items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            stale.append(path)
            if not args.check:
                write_utf8(path, content)
                print("updated {}".format(path.relative_to(ROOT)))
    if args.check and stale:
        for path in stale:
            print("STALE: {} (run python3 scripts/generate_catalog.py)".format(path.relative_to(ROOT)))
        return 1
    if not stale:
        print("Catalog files are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
