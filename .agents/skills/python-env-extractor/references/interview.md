# Interview Guide

Ask concise questions and accept defaults explicitly. Do not request secrets unless the user volunteers them; the scanner can move already-hardcoded values into ignored local files.

## Required Questions

1. What Python project root should be scanned?
   - Default: current working directory when it contains Python source.
2. Should optional `.env.dev` and/or `.env.uat` be created?
   - Default: no; always create `.env.qa` and `.env.prod`.
3. Which profile should become the active local `.env`?
   - Default: `qa`.
4. Which profile do the currently hardcoded values represent?
   - Default: same as the active local profile.
5. Should generated env var names use a prefix?
   - Default: no prefix.
6. Where should dotenv loading be added?
   - Default: the single obvious app startup entrypoint found by repo inspection.
   - If there are multiple entrypoints, ask the user to choose one.

## Follow-Up Checks

- Ask before using `--force`; existing `.env*` values should be preserved by default.
- If the scanner reports low-confidence values, ask whether to migrate them or leave them in code.
- If a value looks like a real credential, do not print it back to the user. Refer to the variable name and file location instead.
- If the project has multiple runnable apps in one repo, scan and rewrite one app at a time unless the user asks for a repo-wide pass.

## Expected User Prompts

- "Use /python-env-extractor to move hardcoded DB strings into env files."
- "Scan this Python job for hardcoded network paths and URLs."
- "I usually run QA locally but need prod env files too."
- "Externalize Oracle, MSSQL, Mongo, API keys, and file mounts from this Python service."
