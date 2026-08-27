# Component registry

Each YAML file registers one product repository. Product teams change only their own file, which avoids a shared manifest conflict. Registered repositories must be owned by `HYGON-AI`; unchanged third-party or upstream skills are not eligible for publication as HYGON-AI skills.

Required fields are `name`, `repo`, `description`, and a non-empty `skills` list. Each skill needs `path`, globally unique `catalog_dir`, and `category`. `ref` defaults to `main`; `local` defaults to `false`.

`category` groups the skill in the generated README index and in `skills.sh.json`. Reuse an existing category name when one fits, so the index stays navigable as the catalog grows.

Remote entries are mirrored by `scripts/sync_sources.py`. Local entries are validated in place and are never cloned.
