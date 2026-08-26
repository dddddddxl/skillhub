#!/usr/bin/env python3
"""Generate human and machine-readable catalog files deterministically."""

from __future__ import print_function

import argparse
import sys
from collections import OrderedDict
from pathlib import Path

from skillhub import ROOT, dump_json, validate_catalog


CATALOG_START = "<!-- catalog:start -->"
CATALOG_END = "<!-- catalog:end -->"
CATEGORY_START = "<!-- categories:start -->"
CATEGORY_END = "<!-- categories:end -->"


def markdown_escape(value):
    return " ".join(value.split()).replace("|", "\\|")


def count_label(count, singular, plural):
    return "{} {}".format(count, singular if count == 1 else plural)


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


def build_category_index(records):
    categories = OrderedDict()
    for record in sorted(records, key=lambda item: item["spec"]["catalog_dir"]):
        categories.setdefault(record["spec"]["category"], []).append(record)

    lines = ["{} across {}.".format(
        count_label(len(records), "skill", "skills"),
        count_label(len(categories), "category", "categories"),
    )]
    for category, items in sorted(categories.items(), key=lambda item: item[0].lower()):
        lines.extend([
            "",
            "### {}".format(markdown_escape(category)),
            "",
            "| Skill | Product | Description |",
            "|---|---|---|",
        ])
        for record in items:
            name = record["spec"]["catalog_dir"]
            lines.append("| [`{}`](skills/{}) | {} | {} |".format(
                name,
                name,
                markdown_escape(record["component"]["name"]),
                markdown_escape(record["metadata"]["description"]),
            ))
    return "\n".join(lines)


def replace_section(readme, start, end, body):
    if start not in readme or end not in readme:
        raise ValueError("README.md is missing {} and {} markers".format(start, end))
    before, rest = readme.split(start, 1)
    _, after = rest.split(end, 1)
    return before + start + "\n\n" + body + "\n\n" + end + after


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
    readme = replace_section(readme, CATALOG_START, CATALOG_END, build_table(components))
    readme = replace_section(readme, CATEGORY_START, CATEGORY_END, build_category_index(records))
    return {
        readme_path: readme,
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
