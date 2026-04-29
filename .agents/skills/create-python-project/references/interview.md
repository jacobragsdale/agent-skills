# Interview Guide

Ask concise questions and accept defaults explicitly. The goal is to collect enough information to run `scripts/create_python_project.py` once.

## Required Questions

1. What directory should contain the new project?
   - Default: current directory, only if it is empty or contains only `.git`.
2. What should the app or deployment be named?
   - Default: target folder name.
3. Is this a `job` or a `deployment`?
   - `job`: container runs a command and exits.
   - `deployment`: long-running service/API container in a cluster.
4. What Python version should be used?
   - Default: `3.11`.
5. Which Docker extras should be enabled?
   - Options: `oracle`, `mssql`, `azcopy`, none.
## Kind-Specific Questions

For `job`:

- What command should the container run?
  - Default: generated project script matching the app name.
- Should the build config include a schedule placeholder?
  - Default: TODO placeholder.

For `deployment`:

- What port should the service listen on?
  - Default: `8000`.
- What health endpoint should be used?
  - Default: `/healthz`.
- How many replicas should the template suggest?
  - Default: `2`.

## Private PyPI

Do not ask for secrets. The generated `pyproject.toml` includes TODO comments for private package index configuration. If the user knows the private index name and URL, add only non-secret values and keep credentials in environment variables or secret stores.
