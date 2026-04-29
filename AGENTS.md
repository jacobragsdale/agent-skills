# Skill Factory Instructions

This repository is a factory for authoring, reviewing, and maintaining Agent Skills. Treat every change as work on reusable agent capability, not as ordinary application code.

## Repository Purpose

- Build skills that package procedural knowledge, deterministic scripts, references, and reusable assets for agents.
- Place every skill under `.agents/skills/<skill-name>/`.
- Keep root-level `AGENTS.md` guidance focused on how agents should create skills. Put skill-specific instructions inside each skill's `SKILL.md`.

## Skill Layout

Use this structure by default:

```text
.agents/skills/<skill-name>/
  SKILL.md
  scripts/
  references/
  assets/
```

Only create optional directories that the skill actually needs.

- `SKILL.md`: required. Contains frontmatter plus concise operating instructions.
- `scripts/`: executable helpers for repeated, fragile, or deterministic work.
- `references/`: documentation the agent should load only when needed.
- `assets/`: static files used as inputs or output templates, such as images, fonts, boilerplate, sample data, or document templates.

Do not add extra docs like `README.md`, `QUICKSTART.md`, `CHANGELOG.md`, or `NOTES.md` inside a skill unless the user explicitly asks. The skill itself is the agent-facing documentation.

## Skill Creation Workflow

1. Clarify the intended use with concrete examples before writing a skill. Identify what a user would say to invoke it, what outputs they expect, and what failure modes matter.
2. Decide whether the work belongs in instructions, a script, a reference file, or an asset.
3. Create the smallest useful skill folder. Use lowercase kebab-case for the folder and `name`.
4. Write `SKILL.md` first enough to establish the workflow, then add resources that remove real repetition or risk.
5. Test every script by running it. Test the skill mentally against at least two realistic user prompts.
6. Remove placeholders, stale examples, and unused folders before finishing.

## SKILL.md Frontmatter

Every skill must start with YAML frontmatter.

Use this default for most skills:

```markdown
---
name: example-skill
description: Do a specific reusable job. Use when the user explicitly asks to run /example-skill or requests the exact workflow this skill supports.
disable-model-invocation: true
---
```

Field rules:

- `name` must match the skill folder name exactly.
- `description` must say what the skill does and when it should be used. This is the primary discovery text, so include trigger phrases and scope boundaries.
- `disable-model-invocation: true` makes the skill explicit-only. Use it by default.
- Omit `disable-model-invocation` only when automatic invocation is clearly beneficial, low risk, and high signal.

Automatic invocation is appropriate only when all are true:

- The skill is broadly useful for natural user requests.
- The `description` can distinguish relevant tasks without ambiguity.
- The skill does not perform risky, costly, destructive, or surprising actions.
- Loading the skill will not waste substantial context for unrelated requests.

Keep frontmatter minimal. Add optional fields such as `license`, `compatibility`, or `metadata` only when they convey information another agent needs.

## Writing SKILL.md

Write for a capable agent that needs specialized procedure, not general teaching.

- Use imperative instructions.
- Keep the body concise. Aim under 500 lines.
- Put only always-needed workflow in `SKILL.md`.
- Move long examples, schemas, API details, policy text, and variant-specific instructions to `references/`.
- Link directly from `SKILL.md` to every reference file and state when to read it.
- Prefer checklists and compact examples over broad explanation.
- Include commands exactly as the agent should run them.
- State assumptions, required inputs, and validation steps.
- Include failure handling for the cases that matter.

Avoid vague advice such as "be careful" or "make it good." Say what to inspect, what to run, what to preserve, and how to decide.

## Scripts

Use `scripts/` when a task should be reliable, repeatable, or easier to execute than re-create from prose.

All new scripts should be Python run with `uv` and PEP 723 inline metadata unless there is a strong reason to use another language.

Use this script header:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
```

Run scripts with one of:

```bash
uv run --script scripts/tool.py --help
./scripts/tool.py --help
```

Script standards:

- Use `argparse` for command-line interfaces.
- Print helpful errors to stderr and exit nonzero on failure.
- Keep dependencies explicit in the PEP 723 block.
- Avoid hidden network calls unless the skill explicitly requires them.
- Avoid writing outside user-specified output paths.
- Make scripts idempotent where practical.
- Add `--dry-run` for destructive or broad changes.
- Include `--help` text that is enough for an agent to use the script without reading the source.
- Prefer structured parsers and libraries over ad hoc string manipulation.

Test each script at least once before declaring the skill done. If sample data is needed, put small fixtures under `assets/` or explain the required input in `SKILL.md`.

## References

Use `references/` for information that is useful but not always needed in context.

Good reference files include:

- API details
- database schemas
- domain glossaries
- style guides
- long examples
- decision matrices
- troubleshooting notes
- provider-specific variants

Reference standards:

- Keep references one level below the skill root.
- Give files descriptive lowercase names, such as `references/aws.md` or `references/schema.md`.
- Add a short table of contents to files longer than about 100 lines.
- Do not duplicate the same guidance in `SKILL.md` and `references/`.
- In `SKILL.md`, say exactly when to read each reference.

## Assets

Use `assets/` for files the agent should use, copy, transform, or include in outputs. Assets are not meant to be read into context by default.

Good assets include:

- templates
- fonts
- icons
- images
- sample spreadsheets or documents
- boilerplate projects
- small fixture files

Asset standards:

- Keep assets organized by purpose.
- Preserve source filenames when provenance matters.
- Document required licenses or attribution in `SKILL.md` or a concise reference file.
- Prefer small, representative assets over large dumps.

## Quality Bar

A good skill should make the next agent faster, more reliable, and less dependent on hidden context.

Before finishing a skill, verify:

- The skill name is short, lowercase, kebab-case, and action-oriented.
- The frontmatter is valid YAML.
- The description contains clear trigger conditions.
- Explicit invocation is the default via `disable-model-invocation: true`, unless an automatic trigger is justified.
- The body tells the agent what to do, what to read, what to run, and how to validate.
- Scripts run with `uv` from the skill root or documented paths.
- References are discoverable from `SKILL.md`.
- Assets are necessary and organized.
- No placeholder files remain.
- No unrelated repo files were changed.

## Review Stance

When reviewing or improving a skill, prioritize:

- incorrect trigger behavior
- missing or misleading frontmatter
- overlong `SKILL.md` content that should be progressive disclosure
- scripts that are untested, non-idempotent, or environment-coupled
- references that are orphaned or duplicated
- assets with unclear purpose or licensing
- instructions that assume unstated user input

Prefer small, surgical edits that improve agent behavior. If a skill is ambiguous, add a concrete example or a sharper trigger description instead of adding broad prose.
