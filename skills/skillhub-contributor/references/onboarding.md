# Skill onboarding reference

## Component schema

Create `components.d/<slug>.yml`:

```yaml
name: Product display name
repo: HYGON-AI/product-repository
ref: main
description: One sentence describing the product and its skills.
skills:
  - path: skills/example-skill
    catalog_dir: example-skill
    category: Inference
```

Use `local: true` only for a skill whose source of truth is the SkillHub repository itself. Remote components are cloned from GitHub during synchronization.

Each `catalog_dir` must be unique across the catalog. Keep it equal to the skill frontmatter `name` unless a temporary compatibility alias is unavoidable.

## Release checklist

- The owning team approved public release.
- `SKILL.md` has only `name` and `description` in YAML frontmatter.
- The description says both what the skill does and when it should trigger.
- Relative Markdown links resolve inside the skill directory.
- Scripts contain no embedded credentials and have been executed on a representative input.
- The source repository has an explicit compatible license.
- The component registry points to an immutable release branch or the team's maintained default branch.
- Local validation and catalog generation checks pass.

## Commands

```bash
python3 scripts/validate_skills.py
python3 scripts/generate_catalog.py
python3 scripts/generate_catalog.py --check
python3 scripts/sync_sources.py --check --component product-slug
python3 scripts/sync_sources.py --component product-slug
```

After publication, verify discovery without installing:

```bash
npx skills add HYGON-AI/skills --list
```

Install one skill non-interactively:

```bash
npx skills add HYGON-AI/skills --skill example-skill --yes
```

## Common failures

- **Unregistered directory**: add the skill to exactly one component file or remove the orphaned catalog directory.
- **Name mismatch**: make `skills/<directory>` and frontmatter `name` identical.
- **Catalog drift**: run `python3 scripts/generate_catalog.py` and commit all generated files.
- **Private clone failure**: grant the synchronization token read access to the product repository without placing the token in a URL.
- **Mirrored edit overwritten**: make the change in the source repository, merge it there, then synchronize again.
