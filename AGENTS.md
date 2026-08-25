# Repository guidance

- Treat `components.d/*.yml` as the source registry and `skills/` as the published catalog.
- Do not hand-edit a remotely mirrored skill. Change its product repository and synchronize it.
- Run `python3 scripts/validate_skills.py` after skill or registry changes.
- Run `python3 scripts/generate_catalog.py` after changes, then verify with `--check`.
- Keep `SKILL.md` concise and move detailed material to one-level references.
- Never add credentials, private product data, or tokens to examples, remotes, or workflow logs.
