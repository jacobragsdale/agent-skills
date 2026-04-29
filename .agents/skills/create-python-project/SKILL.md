---
name: create-python-project
description: Scaffold a new uv-managed Python application project with pyproject.toml private PyPI TODOs, git initialization, Dockerfile templates for jobs or deployment services, and build.yaml templates. Use when the user explicitly invokes /create-python-project or asks to create a new Python job, service, API, or deployable app project from scratch.
disable-model-invocation: true
---

# Create Python Project

## Workflow

Interview the user before scaffolding. Use defaults when the user accepts them, but do not create files until the required answers are known.

Read `references/interview.md` when you need the exact question set.

Required answers:

- Target directory. Default to the current directory only when it is empty or contains only `.git`.
- App/deployment name. Default to the target folder name.
- Project kind: `job` or `deployment`.
- Python version. Default to `3.11`.
- Runtime entrypoint: job command for `job`, or ASGI app/port for `deployment`.
- Docker extras: any of `oracle`, `mssql`, `azcopy`, or none.

After the interview, run:

```bash
uv run --script .agents/skills/create-python-project/scripts/create_python_project.py \
  --target <target-dir> \
  --name <app-name> \
  --kind <job|deployment> \
  --python-version <version>
```

Add `--docker-extra <oracle|mssql|azcopy>` for optional Docker features. Repeat `--docker-extra` for multiple extras.

## Defaults

- Use `.agents/skills/create-python-project/assets/Dockerfile.job.template` for jobs.
- Use `.agents/skills/create-python-project/assets/Dockerfile.deployment.template` for deployments and APIs.
- Use the matching `build.*.yaml.template` asset to create `build.yaml`.
- Use `uv_build` with a flat `src/` layout.
- Initialize git when the target is not already inside a git worktree.
- Leave private PyPI configuration as TODO comments in `pyproject.toml`; do not invent the user's private index URL.

## Docker Extras

Dockerfiles include feature flags for optional system tools:

- `INSTALL_ORACLE`
- `INSTALL_MSSQL`
- `INSTALL_AZCOPY`

Keep new optional tools in the same pattern: add an `ARG INSTALL_<FEATURE>=false`, keep the install block isolated, and expose the build arg in `build.yaml`.

Oracle requires the user to provide an approved `ORACLE_INSTANTCLIENT_URL` artifact URL. Leave that as a TODO unless the user provides a real URL.

## Validation

After scaffolding:

1. Inspect the generated `pyproject.toml`, `Dockerfile`, and `build.yaml`.
2. Confirm the private PyPI TODO block is present.
3. Run `uv lock` if it was skipped and private index settings are not needed yet.
4. Skip `uv run pytest` unless the user has added tests.
5. Run `git status --short` in the target project and tell the user what was created.

If the target directory is not empty, stop and ask before using `--force`.
