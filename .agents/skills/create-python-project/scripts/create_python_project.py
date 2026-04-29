#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


FEATURES = {"oracle", "mssql", "azcopy"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a uv-managed Python job or deployment project."
    )
    parser.add_argument("--target", type=Path, default=Path("."), help="Project directory.")
    parser.add_argument("--name", help="App/deployment name. Defaults to target folder name.")
    parser.add_argument("--kind", choices=("job", "deployment"), required=True)
    parser.add_argument("--python-version", default="3.11")
    parser.add_argument("--description", help="Project description.")
    parser.add_argument(
        "--dev-dependency",
        action="append",
        default=[],
        help="Dev dependency. Defaults to pytest and ruff when omitted.",
    )
    parser.add_argument(
        "--docker-extra",
        action="append",
        default=[],
        help="Optional Docker feature: oracle, mssql, azcopy. Repeat or comma-separate.",
    )
    parser.add_argument("--job-command", help="Job command. Defaults to the project script name.")
    parser.add_argument("--port", default="8000", help="Deployment port.")
    parser.add_argument("--health-path", default="/healthz", help="Deployment health endpoint.")
    parser.add_argument("--replicas", default="2", help="Deployment replica count for build.yaml.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated files.")
    parser.add_argument("--skip-lock", action="store_true", help="Do not run uv lock.")
    parser.add_argument("--no-git", action="store_true", help="Do not initialize git.")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing files.")
    args = parser.parse_args()

    extras = set()
    for item in args.docker_extra:
        extras.update(part for part in re.split(r"[,\s]+", item.strip().lower()) if part)
    unknown = extras - FEATURES
    if unknown:
        parser.error(f"unknown Docker extras: {', '.join(sorted(unknown))}")
    args.docker_extras = extras

    if args.job_command and re.search(r"\s", args.job_command):
        parser.error("--job-command must be a single executable name; edit Dockerfile for shell commands")

    return args


def kebab_name(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "python-app"


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def ruff_target_version(python_version: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)", python_version)
    if not match:
        return "py312"
    major, minor = match.groups()
    return f"py{major}{minor}"


def toml_array(items: list[str], indent: str = "    ") -> str:
    return "\n".join(f"{indent}{json.dumps(item)}," for item in items)


def render_template(path: Path, values: dict[str, str]) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def is_empty_target(path: Path) -> bool:
    if not path.exists():
        return True
    return all(child.name == ".git" for child in path.iterdir())


def write_file(path: Path, content: str, *, force: bool, dry_run: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"Refusing to overwrite existing file: {path}")
    if dry_run:
        print(f"would write {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run(command: list[str], cwd: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"would run in {cwd}: {' '.join(command)}")
        return
    subprocess.run(command, cwd=cwd, check=True)


def inside_git_worktree(path: Path) -> bool:
    if not shutil.which("git"):
        return False
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def pyproject(
    *,
    project_name: str,
    source_module: str,
    description: str,
    python_version: str,
    dev_dependencies: list[str],
    kind: str,
    job_command: str,
) -> str:
    script_block = ""
    if kind == "job":
        script_block = f'\n[project.scripts]\n{json.dumps(job_command)} = "main:main"\n'

    return f"""[project]
name = {json.dumps(project_name)}
version = "0.1.0"
description = {json.dumps(description)}
requires-python = ">={python_version}"
dependencies = []
{script_block}
[dependency-groups]
dev = [
{toml_array(dev_dependencies)}
]

[build-system]
requires = ["uv_build>=0.11.8,<0.12"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = {json.dumps(source_module)}

[tool.ruff]
line-length = 100
target-version = "{ruff_target_version(python_version)}"

[tool.pytest.ini_options]
testpaths = ["tests"]

# TODO(private-pypi): Fill in private package index settings before adding
# private dependencies. Keep credentials out of this file; pass them through
# environment variables or your build system's secret store.
#
# [[tool.uv.index]]
# name = "private"
# url = "https://pypi.example.com/simple"
# authenticate = "always"
#
# TODO(private-pypi): Pin packages that must resolve from the private index.
# [tool.uv.sources]
# internal-package = {{ index = "private" }}
"""


def job_main(app_name: str) -> str:
    return f'''def main() -> None:
    """Run the {app_name} job."""
    print("TODO: implement {app_name} job")


if __name__ == "__main__":
    main()
'''


def api_module(app_name: str, health_path: str) -> str:
    return f'''import json


async def app(scope, receive, send) -> None:
    if scope["type"] != "http":
        raise RuntimeError("Only HTTP connections are supported.")

    if scope["path"] == {json.dumps(health_path)}:
        body = json.dumps({{"status": "ok"}}).encode("utf-8")
        await send({{
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }})
        await send({{"type": "http.response.body", "body": body}})
        return

    body = json.dumps({{"service": {json.dumps(app_name)}, "status": "running"}}).encode("utf-8")
    await send({{
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"application/json")],
    }})
    await send({{"type": "http.response.body", "body": body}})
'''


def gitignore() -> str:
    return """.venv/
.pytest_cache/
.ruff_cache/
__pycache__/
*.py[cod]
dist/
build/
.env
.env.*
!.env.example
"""


def dockerignore() -> str:
    return """.git
.venv
.pytest_cache
.ruff_cache
__pycache__
*.py[cod]
dist
build
.env
.env.*
"""


def main() -> int:
    args = parse_args()
    target = args.target.expanduser().resolve()
    if target.exists() and not is_empty_target(target) and not args.force:
        raise SystemExit(
            f"Target is not empty: {target}. Choose an empty folder or rerun with --force."
        )
    if args.dry_run:
        print(f"would create target directory {target}")
    else:
        target.mkdir(parents=True, exist_ok=True)

    project_name = kebab_name(args.name or target.name)
    source_module = "main" if args.kind == "job" else "api"
    description = args.description or f"{project_name} Python {args.kind}"
    job_command = args.job_command or project_name
    dev_dependencies = args.dev_dependency or ["pytest", "ruff"]

    skill_root = Path(__file__).resolve().parents[1]
    assets = skill_root / "assets"
    template_values = {
        "APP_NAME": project_name,
        "PYTHON_VERSION": args.python_version,
        "JOB_COMMAND": job_command,
        "ASGI_APP": "api:app",
        "PORT": str(args.port),
        "HEALTH_PATH": args.health_path,
        "REPLICAS": str(args.replicas),
        "INSTALL_ORACLE": bool_text("oracle" in args.docker_extras),
        "INSTALL_MSSQL": bool_text("mssql" in args.docker_extras),
        "INSTALL_AZCOPY": bool_text("azcopy" in args.docker_extras),
    }

    docker_template = assets / f"Dockerfile.{args.kind}.template"
    build_template = assets / f"build.{args.kind}.yaml.template"

    files = {
        ".python-version": f"{args.python_version}\n",
        "pyproject.toml": pyproject(
            project_name=project_name,
            source_module=source_module,
            description=description,
            python_version=args.python_version,
            dev_dependencies=dev_dependencies,
            kind=args.kind,
            job_command=job_command,
        ),
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        "Dockerfile": render_template(docker_template, template_values),
        "build.yaml": render_template(build_template, template_values),
    }
    if args.kind == "job":
        files["src/main.py"] = job_main(project_name)
    else:
        files["src/api.py"] = api_module(project_name, args.health_path)

    for relative_path, content in files.items():
        write_file(target / relative_path, content, force=args.force, dry_run=args.dry_run)

    if not args.no_git and not inside_git_worktree(target):
        if shutil.which("git"):
            run(["git", "init"], cwd=target, dry_run=args.dry_run)
        else:
            print("warning: git not found; skipped git init", file=sys.stderr)

    if not args.skip_lock:
        if shutil.which("uv"):
            run(["uv", "lock"], cwd=target, dry_run=args.dry_run)
        else:
            print("warning: uv not found; skipped uv lock", file=sys.stderr)

    print(f"Created {args.kind} project at {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
