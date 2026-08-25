#!/usr/bin/env python3
"""Mirror registered product-owned skills into the catalog."""

from __future__ import print_function

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from skillhub import ROOT, CatalogError, dump_json, file_tree_digest, load_components


def run(command, cwd=None):
    return subprocess.check_output(command, cwd=str(cwd) if cwd else None, universal_newlines=True).strip()


def write_utf8(path, content):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def clone_component(component, destination):
    url = "https://github.com/{}.git".format(component["repo"])
    subprocess.check_call([
        "git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
        "--branch", component["ref"], url, str(destination),
    ])
    paths = [spec["path"] for spec in component["skills"]]
    subprocess.check_call(["git", "-C", str(destination), "sparse-checkout", "set"] + paths)
    return run(["git", "-C", str(destination), "rev-parse", "HEAD"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report drift without changing the catalog")
    parser.add_argument("--component", action="append", default=[], help="sync only this components.d file stem")
    args = parser.parse_args()

    try:
        components = load_components()
    except CatalogError as exc:
        print("ERROR: {}".format(exc))
        return 1

    selected = set(args.component)
    known = set(component["file"].stem for component in components)
    unknown = selected - known
    if unknown:
        print("ERROR: unknown component(s): {}".format(", ".join(sorted(unknown))))
        return 1

    lock = {}
    lock_path = ROOT / ".skillhub-lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock.setdefault("schema_version", 1)
    lock.setdefault("skills", {})

    changed = []
    with tempfile.TemporaryDirectory(prefix="skillhub-sync-") as temp:
        temp_root = Path(temp)
        for component in components:
            slug = component["file"].stem
            if selected and slug not in selected:
                continue
            if component["local"]:
                print("skip local component {}".format(slug))
                continue
            checkout = temp_root / slug
            print("clone {}@{}".format(component["repo"], component["ref"]))
            commit = clone_component(component, checkout)
            for spec in component["skills"]:
                source = checkout / Path(spec["path"])
                if not source.is_dir() or not (source / "SKILL.md").is_file():
                    raise CatalogError("{}:{} does not contain SKILL.md".format(component["repo"], spec["path"]))
                destination = ROOT / "skills" / spec["catalog_dir"]
                source_digest = file_tree_digest(source)
                destination_digest = file_tree_digest(destination) if destination.exists() else None
                if source_digest != destination_digest:
                    changed.append(spec["catalog_dir"])
                    print("{} {}".format("would update" if args.check else "update", destination.relative_to(ROOT)))
                    if not args.check:
                        staged = temp_root / "staged" / spec["catalog_dir"]
                        staged.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(str(source), str(staged))
                        if destination.exists():
                            shutil.rmtree(str(destination))
                        shutil.copytree(str(staged), str(destination))
                if not args.check:
                    lock["skills"][spec["catalog_dir"]] = {
                        "repo": component["repo"],
                        "ref": component["ref"],
                        "commit": commit,
                        "path": spec["path"],
                    }

    if args.check and changed:
        print("{} mirrored skill(s) differ from their source.".format(len(changed)))
        return 1
    if not args.check:
        registered_remote = set(
            spec["catalog_dir"]
            for component in components
            if not component["local"]
            for spec in component["skills"]
        )
        lock["skills"] = {
            name: value for name, value in lock["skills"].items()
            if name in registered_remote
        }
        write_utf8(lock_path, dump_json(lock))
    print("Synchronization complete; {} skill(s) changed.".format(len(changed)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CatalogError, subprocess.CalledProcessError) as exc:
        print("ERROR: {}".format(exc))
        sys.exit(1)
