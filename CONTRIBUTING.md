# Contributing

Hygon SkillHub is a publication catalog. Product teams own their source skills so documentation and product changes evolve together.

## Publication boundary

SkillHub publishes skills whose source-of-truth repository is owned by the `HYGON-AI` GitHub organization. Organization ownership alone is not sufficient: each published skill must be either HYGON-authored or substantively adapted and validated for HCU, with a HYGON team responsible for ongoing maintenance.

Do not register or mirror an unchanged third-party or upstream skill as a HYGON-AI skill. Link to the canonical upstream skill instead, then request catalog admission after the product team has added and tested the HCU-specific workflow. Preserve all applicable third-party copyright, license, and NOTICE material in an adapted skill.

## Add a product-owned skill

1. Add a portable `skills/<skill-name>/SKILL.md` directory to the product repository.
2. Confirm the owning team approved public release and the source license permits redistribution.
3. Add `components.d/<product>.yml` here. Use one file per product team; do not edit another team's registry file.
4. Preview the mirror with `python3 scripts/sync_sources.py --check --component <product>`.
5. Apply the mirror, regenerate the catalog, and validate:

   ```bash
   python3 scripts/sync_sources.py --component <product>
   python3 scripts/generate_catalog.py
   python3 scripts/validate_skills.py
   python3 scripts/generate_catalog.py --check
   ```

6. Open a pull request with the owning team as reviewers.

## Add a catalog-owned skill

Use catalog ownership only for SkillHub-wide workflows. Initialize a standard skill under `skills/`, add `local: true` to its component definition, generate the catalog, and validate.

## Skill requirements

- Folder and frontmatter names use lowercase hyphen-case and match exactly.
- YAML frontmatter contains only `name` and `description`.
- The description explains capability and trigger conditions.
- Keep `SKILL.md` at or below 500 lines; move details into `references/`.
- Bundle every required dependency inside the skill directory. Do not depend on sibling skills or source-repository files that an installer will not copy.
- Put repeatable deterministic operations in tested `scripts/`.
- Do not include credentials, private endpoints, personal data, generated caches, or unrelated documentation.
- Do not request broader permissions than the workflow requires.

## Pull request checklist

- [ ] The source-of-truth repository is owned by `HYGON-AI`.
- [ ] The skill is HYGON-authored or documents substantive, tested HCU adaptations.
- [ ] A HYGON team owns ongoing maintenance and approved publication.
- [ ] Third-party attribution, license, and NOTICE requirements are preserved.
- [ ] The source and catalog licenses are compatible.
- [ ] Scripts were reviewed and tested.
- [ ] `python3 scripts/validate_skills.py` passes.
- [ ] `python3 scripts/generate_catalog.py --check` passes.
- [ ] No mirrored files were edited only in the catalog.

Use `git commit --signoff` so the contribution records Developer Certificate of Origin agreement.
