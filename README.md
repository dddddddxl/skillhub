# HYGON-AI Agent Skills

Portable Agent Skills for HYGON-AI software, infrastructure, training, and inference workflows. This repository is the organization-level catalog: product teams own their source skills, while this hub validates, mirrors, and publishes approved versions.

## Quick start

After the repository is published, browse or install skills with the standard `skills` CLI:

```bash
npx skills add HYGON-AI/skills --list
npx skills add HYGON-AI/skills
```

Install one skill for Codex without prompts:

```bash
npx skills add HYGON-AI/skills --skill skillhub-contributor --agent codex --yes
```

## Skill catalog

<!-- catalog:start -->

| Product | Description | Skills |
|---|---|---|
| **Inference Cookbook DAS** | Add and maintain model recipes in the Hygon inference cookbook. | [`bulk-add-model`](skills/bulk-add-model) |
| **SkillHub** | Author, validate, onboard, and publish portable Agent Skills across HYGON-AI projects. | [`skillhub-contributor`](skills/skillhub-contributor) |

<!-- catalog:end -->

## How publication works

1. Product teams maintain source skills in `skills/<skill-name>/` in their own repository.
2. A small `components.d/<product>.yml` file registers source paths and catalog names.
3. The synchronization workflow mirrors registered content into this repository.
4. Validation checks naming, frontmatter, links, metadata, secrets, and generated catalog drift.
5. Approved changes land through pull requests and become installable from this repository.

Catalog maintainers can run:

```bash
python3 scripts/validate_skills.py
python3 scripts/generate_catalog.py --check
python3 scripts/sync_sources.py --check --component <product>
```

See [CONTRIBUTING.md](CONTRIBUTING.md) to onboard a product or skill.

## Trust model

The catalog publishes reviewed source content; it does not make arbitrary third-party skills trusted. Every product entry records its repository, ref, and source path in `catalog.json`, and synchronized commits are recorded in `.skillhub-lock.json`. Consumers should still review executable scripts and permissions before installation.

## Source attribution

Product repositories remain the source of truth for mirrored skills. The catalog preserves upstream authorship and license terms, records each source repository, ref, and path in `catalog.json`, and does not treat an unchanged third-party skill as a HYGON-AI adaptation.

## License

Repository code is licensed under Apache License 2.0 unless stated otherwise. Mirrored skill content remains under its source license; `bulk-add-model` is distributed under the [inference-cookbook-das MIT License](LICENSES/inference-cookbook-das-MIT.txt). Imported skills must carry a license compatible with public redistribution.
