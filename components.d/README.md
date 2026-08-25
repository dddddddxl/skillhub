# Component registry

Each YAML file registers one product repository. Product teams change only their own file, which avoids a shared manifest conflict.

Required fields are `name`, `repo`, `description`, and a non-empty `skills` list. Each skill needs `path`, globally unique `catalog_dir`, and `category`. `ref` defaults to `main`; `local` defaults to `false`.

Remote entries are mirrored by `scripts/sync_sources.py`. Local entries are validated in place and are never cloned.
