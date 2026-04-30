---
name: python-env-extractor
description: Move hardcoded Python configuration into local dotenv files. Use when the user explicitly invokes /python-env-extractor or asks to externalize hardcoded URLs, database connection strings, passwords, tokens, API keys, network mounts, file paths, hosts, ports, or other environment-dependent Python values into .env files.
disable-model-invocation: true
---

# Python Env Extractor

## Workflow

Interview the user before editing a project. Read `references/interview.md` for the question set.

Required answers:

- Target Python project root.
- Whether to create optional `.env.dev` and `.env.uat`.
- Active local profile to copy into `.env`; default to `qa`.
- Source profile for discovered hardcoded values; default to the active profile.
- Optional env var prefix, such as an app name.
- Startup entrypoint if repo inspection finds more than one plausible startup path.

Run the scanner before changing code:

```bash
uv run --script .agents/skills/python-env-extractor/scripts/scan_python_env_candidates.py \
  --project-root <project-root> \
  --env qa \
  --env prod \
  --active-env <qa|prod|dev|uat> \
  --source-env <qa|prod|dev|uat> \
  --markdown-report <project-root>/env-candidates.md \
  --json-report <project-root>/env-candidates.json
```

Add `--env dev` and/or `--env uat` only when requested. Add `--prefix <PREFIX>` when the user wants prefixed variable names. Review the report, then rerun with `--write` to create or update `.env*` files.

## Scanner Contract

`scripts/scan_python_env_candidates.py` scans Python source only. It detects candidate literals in assignments, dicts, function defaults, class settings, dataclass/Pydantic-style defaults, and call arguments.

The scanner categorizes likely environment-dependent values:

- URLs and API endpoints.
- Oracle, MSSQL/ODBC, MongoDB, SQLAlchemy, and other database connection values.
- Passwords, tokens, API keys, secrets, and credential-like values.
- Network drives, UNC paths, mounted shares, and absolute file paths.
- Hosts, ports, queues, SMTP, SFTP/FTP, Redis, and broker settings.

Treat scanner output as a worklist, not proof. It ranks findings as `high`, `medium`, or `low`; env files include `high` and `medium` findings by default. Manually inspect low-confidence findings before adding them.

The scanner must not rewrite Python code, perform network calls, validate credentials, print full secret values in reports, or overwrite existing `.env*` entries unless `--force` is used.

## Env Files

Always create local `.env.qa` and `.env.prod`. Create `.env.dev` and `.env.uat` only when requested. Create `.env` from the active local profile. Do not create `.env.example`.

Discovered literal values go only into the source profile and into `.env` when the active profile matches the source profile. Other profiles receive `TODO` placeholders. Existing keys are preserved by default.

Add or confirm `.gitignore` entries:

```gitignore
.env
.env.*
```

Switch profiles manually:

```bash
cp .env.qa .env
cp .env.prod .env
```

## Code Rewrite

After reviewing candidates, rewrite application code manually:

- Add `python-dotenv` using the project's existing dependency manager.
- Load only project-local `.env` at startup before migrated config is read:

```python
from dotenv import load_dotenv

load_dotenv(".env", override=False)
```

- Replace required config values with `os.environ["VAR_NAME"]`.
- Do not use `os.environ.get`, `os.getenv`, or silent defaults for required config.
- Keep explicit type conversions after required reads, such as `int(os.environ["PORT"])` or `Path(os.environ["DATA_DIR"])`.
- Missing `.env` is acceptable; platform-provided environment variables can still satisfy `os.environ[]`.

## Validation

After changes:

1. Run the project's tests or the smallest relevant smoke command.
2. Run the app with `.env` copied from the chosen active profile.
3. Confirm no migrated hardcoded values remain in Python source.
4. Run `git status --short` and confirm real `.env*` files are ignored.
