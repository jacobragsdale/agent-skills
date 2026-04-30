#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "site-packages",
    "venv",
}

DEFAULT_ENVS = ("qa", "prod")
CONFIDENCE_ORDER = {"low": 1, "medium": 2, "high": 3}

DB_SCHEMES = {
    "mssql",
    "mssql+pyodbc",
    "mssql+pymssql",
    "mysql",
    "mysql+pymysql",
    "oracle",
    "oracle+cx_oracle",
    "postgres",
    "postgresql",
    "postgresql+psycopg2",
    "sqlite",
}

STOP_WORDS = {
    "arg",
    "args",
    "client",
    "config",
    "connect",
    "connection",
    "create",
    "default",
    "defaults",
    "delete",
    "engine",
    "get",
    "kwargs",
    "open",
    "post",
    "put",
    "request",
    "requests",
    "self",
    "settings",
    "value",
}

NAME_HINTS = {
    "database": {
        "conn",
        "connection",
        "connection_string",
        "database",
        "datasource",
        "db",
        "dsn",
        "mongo",
        "mssql",
        "odbc",
        "oracle",
        "sql",
        "sqlalchemy",
        "tns",
    },
    "secret": {
        "access_key",
        "api_key",
        "apikey",
        "auth",
        "bearer",
        "client_secret",
        "credential",
        "credentials",
        "key",
        "passwd",
        "password",
        "private_key",
        "pwd",
        "secret",
        "signature",
        "token",
    },
    "url": {
        "api",
        "base_url",
        "callback",
        "callback_url",
        "endpoint",
        "host_url",
        "uri",
        "url",
        "webhook",
        "webhook_url",
    },
    "path": {
        "archive",
        "archive_dir",
        "data_dir",
        "dir",
        "directory",
        "drive",
        "file",
        "folder",
        "input",
        "mount",
        "network_drive",
        "output",
        "path",
        "root",
        "share",
        "share_path",
    },
    "service": {
        "broker",
        "hostname",
        "host",
        "port",
        "queue",
        "redis",
        "server",
        "sftp",
        "smtp",
    },
}

URL_RE = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://")
ODBC_RE = re.compile(
    r"(?:^|;)\s*(?:DRIVER|SERVER|DATABASE|UID|USER|PWD|PASSWORD)\s*=",
    re.IGNORECASE,
)
ORACLE_RE = re.compile(
    r"(\(DESCRIPTION\s*=|\bSERVICE_NAME\s*=|\bSID\s*=|\bHOST\s*=|\bPORT\s*=|^[\w.-]+:\d{2,5}/[\w.$-]+$)",
    re.IGNORECASE,
)
UNC_RE = re.compile(r"^\\\\[^\\/\s]+[\\/][^\\/\s]+")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
MOUNT_RE = re.compile(r"^/(?:mnt|mount|media|Volumes|data|opt|srv|shares?|var)(?:/|$)")
ABSOLUTE_PATH_RE = re.compile(r"^/(?!/)(?:[^/\s]+/)+[^/\s]*$")
DOMAIN_RE = re.compile(r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?::\d{2,5})?$")
IP_PORT_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?$")
JWT_RE = re.compile(r"^[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}$")
HEX_SECRET_RE = re.compile(r"^[A-Fa-f0-9]{32,}$")
BASE64ISH_SECRET_RE = re.compile(r"^[A-Za-z0-9_+/=-]{32,}$")


@dataclass
class Candidate:
    file: str
    line: int
    column: int
    category: str
    confidence: str
    suggested_name: str
    secret_like: bool
    value_preview: str
    reason: str
    context: str
    value: str

    def report_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "category": self.category,
            "confidence": self.confidence,
            "suggested_name": self.suggested_name,
            "secret_like": self.secret_like,
            "value_preview": self.value_preview,
            "reason": self.reason,
            "context": self.context,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan Python source for hardcoded env-dependent values and draft .env files."
    )
    parser.add_argument("--project-root", type=Path, default=Path("."), help="Python project root.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment profile to generate, without dot prefix. Defaults to qa and prod.",
    )
    parser.add_argument(
        "--active-env",
        default=None,
        help="Profile rendered into .env. Defaults to --source-env.",
    )
    parser.add_argument(
        "--source-env",
        default="qa",
        help="Profile that receives discovered literal values. Defaults to qa.",
    )
    parser.add_argument("--prefix", help="Optional prefix for generated env var names.")
    parser.add_argument(
        "--min-env-confidence",
        choices=("low", "medium", "high"),
        default="medium",
        help="Minimum confidence included in generated env files. Defaults to medium.",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        help="Write a Markdown report to this path. Markdown is also printed to stdout.",
    )
    parser.add_argument("--json-report", type=Path, help="Write a JSON report to this path.")
    parser.add_argument(
        "--max-file-bytes",
        type=int,
        default=2_000_000,
        help="Skip Python files larger than this many bytes. Defaults to 2000000.",
    )
    parser.add_argument("--write", action="store_true", help="Write .env files.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing generated keys in .env files.",
    )
    args = parser.parse_args()

    args.envs = [normalize_env_name(env) for env in (args.env or DEFAULT_ENVS)]
    for required in DEFAULT_ENVS:
        if required not in args.envs:
            args.envs.append(required)

    args.source_env = normalize_env_name(args.source_env)
    if args.source_env not in args.envs:
        args.envs.append(args.source_env)

    args.active_env = normalize_env_name(args.active_env or args.source_env)
    if args.active_env not in args.envs:
        args.envs.append(args.active_env)

    args.prefix = normalize_prefix(args.prefix)
    return args


def normalize_env_name(value: str) -> str:
    env = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]+", env):
        raise SystemExit(f"Invalid env profile name: {value!r}")
    return env


def normalize_prefix(value: str | None) -> str:
    if not value:
        return ""
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").upper()
    if not prefix:
        return ""
    return f"{prefix}_"


def iter_python_files(project_root: Path, max_file_bytes: int) -> Iterable[Path]:
    for path in sorted(project_root.rglob("*.py")):
        parts = set(path.relative_to(project_root).parts[:-1])
        if parts & EXCLUDED_DIRS:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue
        yield path


class CandidateVisitor(ast.NodeVisitor):
    def __init__(self, *, project_root: Path, file_path: Path, prefix: str):
        self.project_root = project_root
        self.file_path = file_path
        self.prefix = prefix
        self.candidates: list[Candidate] = []
        self.seen: set[tuple[int, int, str, tuple[str, ...]]] = set()

    def visit_Assign(self, node: ast.Assign) -> None:
        context = []
        for target in node.targets:
            context.extend(target_names(target))
        self.scan_value(node.value, context, "assignment")

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is None:
            return
        self.scan_value(node.value, target_names(node.target), "annotated assignment")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scan_function_defaults(node)
        for child in node.body:
            self.visit(child)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scan_function_defaults(node)
        for child in node.body:
            self.visit(child)

    def visit_Call(self, node: ast.Call) -> None:
        function_context = [call_name(node.func)]
        for arg in node.args:
            self.scan_value(arg, function_context, "call argument")
        for keyword in node.keywords:
            if keyword.arg:
                self.scan_value(keyword.value, function_context + [keyword.arg], "keyword argument")

    def visit_Dict(self, node: ast.Dict) -> None:
        self.scan_dict(node, [], "dict value")

    def scan_function_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        positional_args = node.args.posonlyargs + node.args.args
        default_offset = len(positional_args) - len(node.args.defaults)
        for arg, default in zip(positional_args[default_offset:], node.args.defaults):
            self.scan_value(default, [node.name, arg.arg], "function default")
        for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
            if default is not None:
                self.scan_value(default, [node.name, arg.arg], "keyword-only default")

    def scan_value(self, node: ast.AST, context: list[str], source: str) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            self.add_candidate(node.value, node, context, source)
            return
        if isinstance(node, ast.Dict):
            self.scan_dict(node, context, source)
            return
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for item in node.elts:
                self.scan_value(item, context, source)
            return
        if isinstance(node, ast.Call):
            self.visit_Call(node)
            return
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    def scan_dict(self, node: ast.Dict, context: list[str], source: str) -> None:
        for key, value in zip(node.keys, node.values):
            key_name = literal_key_name(key)
            next_context = context + ([key_name] if key_name else [])
            self.scan_value(value, next_context, source)

    def add_candidate(
        self,
        value: str,
        node: ast.AST,
        context_parts: list[str],
        source: str,
    ) -> None:
        if not value or value.strip() != value or len(value.strip()) < 2:
            return
        context_parts = [part for part in context_parts if part]
        key = (
            getattr(node, "lineno", 0),
            getattr(node, "col_offset", 0),
            value,
            tuple(context_parts),
        )
        if key in self.seen:
            return
        self.seen.add(key)

        analysis = analyze_value(value, context_parts)
        if analysis is None:
            return
        category, confidence, secret_like, reason = analysis
        suggested_name = suggest_name(value, context_parts, category, self.prefix)
        self.candidates.append(
            Candidate(
                file=str(self.file_path.relative_to(self.project_root)),
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0),
                category=category,
                confidence=confidence,
                suggested_name=suggested_name,
                secret_like=secret_like,
                value_preview=preview_value(value, secret_like),
                reason=f"{source}; {reason}",
                context=".".join(context_parts),
                value=value,
            )
        )


def target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return target_names(node.value) + [node.attr]
    if isinstance(node, ast.Subscript):
        names = target_names(node.value)
        key = literal_key_name(node.slice)
        return names + ([key] if key else [])
    if isinstance(node, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in node.elts:
            names.extend(target_names(item))
        return names
    return []


def literal_key_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return str(node.value)
    if isinstance(node, ast.Name):
        return node.id
    return None


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def split_words(value: str) -> list[str]:
    raw = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return [word.lower() for word in re.split(r"[^A-Za-z0-9]+", raw) if word]


def context_words(context_parts: list[str]) -> list[str]:
    words: list[str] = []
    for part in context_parts:
        words.extend(split_words(part))
    return words


def context_has(words: list[str], category: str) -> bool:
    joined = "_".join(words)
    for hint in NAME_HINTS[category]:
        if "_" in hint and hint in joined:
            return True
        if "_" not in hint and hint in words:
            return True
    return False


def analyze_value(
    value: str,
    context_parts: list[str],
) -> tuple[str, str, bool, str] | None:
    words = context_words(context_parts)
    scores = {category: 0 for category in NAME_HINTS}
    reasons: list[str] = []
    secret_like = False

    url_match = URL_RE.match(value)
    if url_match:
        scheme = url_match.group("scheme").lower()
        netloc = value.split("://", 1)[1].split("/", 1)[0]
        if "@" in netloc:
            secret_like = True
            reasons.append("URL embeds credentials")
        if scheme in DB_SCHEMES:
            scores["database"] += 4
            reasons.append(f"matches database URL scheme {scheme}")
        elif scheme in {"mongodb", "mongodb+srv"}:
            scores["database"] += 4
            reasons.append(f"matches MongoDB URL scheme {scheme}")
        elif scheme in {"http", "https"}:
            scores["url"] += 3
            reasons.append("matches HTTP URL")
        else:
            scores["service"] += 2
            reasons.append(f"matches URL-like scheme {scheme}")

    if ODBC_RE.search(value):
        scores["database"] += 4
        reasons.append("matches ODBC connection-string keys")
        if re.search(r"(?:PWD|PASSWORD)\s*=", value, re.IGNORECASE):
            secret_like = True

    if ORACLE_RE.search(value):
        scores["database"] += 3
        reasons.append("matches Oracle DSN pattern")

    if UNC_RE.search(value):
        scores["path"] += 4
        reasons.append("matches UNC network path")
    elif WINDOWS_DRIVE_RE.search(value):
        scores["path"] += 3
        reasons.append("matches Windows drive path")
    elif MOUNT_RE.search(value):
        scores["path"] += 3
        reasons.append("matches mounted or shared absolute path")
    elif ABSOLUTE_PATH_RE.search(value) and context_has(words, "path"):
        scores["path"] += 2
        reasons.append("matches absolute path with path-like context")

    if DOMAIN_RE.search(value) or IP_PORT_RE.search(value):
        scores["service"] += 2 if context_has(words, "service") else 1
        reasons.append("matches host or IP pattern")

    if value.isdigit() and context_has(words, "service") and any(word == "port" for word in words):
        scores["service"] += 2
        reasons.append("numeric value in port-like context")

    for category in NAME_HINTS:
        if context_has(words, category):
            scores[category] += 2
            reasons.append(f"context contains {category}-like name")

    if context_has(words, "secret"):
        secret_like = True
        scores["secret"] += 3
    elif is_secret_shaped(value):
        secret_like = True
        scores["secret"] += 3
        reasons.append("value shape looks credential-like")

    category, score = max(scores.items(), key=lambda item: item[1])
    if score < 2:
        return None

    if score >= 5:
        confidence = "high"
    elif score >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    if secret_like and category != "secret" and scores["secret"] >= score:
        category = "secret"

    return category, confidence, secret_like, "; ".join(dict.fromkeys(reasons))


def is_secret_shaped(value: str) -> bool:
    if JWT_RE.fullmatch(value) or HEX_SECRET_RE.fullmatch(value):
        return True
    if value.startswith(("sk_", "pk_", "ghp_", "gho_", "xoxb-", "xoxp-")):
        return True
    if BASE64ISH_SECRET_RE.fullmatch(value) and any(char.isdigit() for char in value):
        return True
    return False


def suggest_name(value: str, context_parts: list[str], category: str, prefix: str) -> str:
    words = [
        word
        for word in context_words(context_parts)
        if word not in STOP_WORDS and not word.isdigit() and len(word) > 1
    ]
    if not words:
        words = fallback_words(value, category)

    name = "_".join(words).upper()
    name = re.sub(r"[^A-Z0-9_]+", "_", name).strip("_")

    if category == "url" and not name.endswith(("URL", "URI", "ENDPOINT")):
        name = f"{name}_URL" if name else "SERVICE_URL"
    elif category == "database" and not any(
        token in name.split("_") for token in ("DB", "DATABASE", "DSN", "MONGO", "MSSQL", "ORACLE")
    ):
        name = f"{name}_DATABASE_URL" if name else "DATABASE_URL"
    elif category == "path" and not name.endswith(("PATH", "DIR", "DIRECTORY", "FILE", "SHARE", "MOUNT")):
        name = f"{name}_PATH" if name else "DATA_PATH"
    elif category == "secret" and not any(
        token in name.split("_")
        for token in ("KEY", "PASSWORD", "PWD", "SECRET", "TOKEN", "CREDENTIAL")
    ):
        name = f"{name}_SECRET" if name else "SECRET_VALUE"

    if not name:
        name = category.upper()
    if prefix and not name.startswith(prefix):
        name = f"{prefix}{name}"
    return name


def fallback_words(value: str, category: str) -> list[str]:
    if category == "url":
        match = URL_RE.match(value)
        if match:
            rest = value[len(match.group(0)) :]
            host = rest.split("/", 1)[0].split("@")[-1].split(":", 1)[0]
            host_words = [word for word in split_words(host) if word not in {"com", "net", "org"}]
            if host_words:
                return host_words + ["url"]
        return ["service", "url"]
    if category == "database":
        return ["database", "url"]
    if category == "path":
        return ["data", "path"]
    if category == "secret":
        return ["secret", "value"]
    return ["service", "value"]


def preview_value(value: str, secret_like: bool) -> str:
    if secret_like:
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}***{value[-2:]}"
    if len(value) <= 96:
        return value
    return f"{value[:80]}...{value[-12:]}"


def assign_unique_names(candidates: list[Candidate]) -> None:
    grouped: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.suggested_name, []).append(candidate)

    for name, group in grouped.items():
        seen_values: dict[str, str] = {}
        next_suffix = 2
        for candidate in group:
            if candidate.value in seen_values:
                candidate.suggested_name = seen_values[candidate.value]
                continue
            if not seen_values:
                seen_values[candidate.value] = name
                continue
            new_name = f"{name}_{next_suffix}"
            next_suffix += 1
            seen_values[candidate.value] = new_name
            candidate.suggested_name = new_name


def scan_project(project_root: Path, prefix: str, max_file_bytes: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    for path in iter_python_files(project_root, max_file_bytes):
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            print(f"warning: skipped unparsable Python file {path}: {exc}", file=sys.stderr)
            continue
        visitor = CandidateVisitor(project_root=project_root, file_path=path, prefix=prefix)
        visitor.visit(tree)
        candidates.extend(visitor.candidates)
    candidates.sort(key=lambda item: (item.file, item.line, item.column, item.suggested_name))
    assign_unique_names(candidates)
    return candidates


def should_include_in_env(candidate: Candidate, min_confidence: str) -> bool:
    return CONFIDENCE_ORDER[candidate.confidence] >= CONFIDENCE_ORDER[min_confidence]


def selected_env_candidates(candidates: list[Candidate], min_confidence: str) -> list[Candidate]:
    selected: list[Candidate] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        if not should_include_in_env(candidate, min_confidence):
            continue
        if candidate.suggested_name in seen_names:
            continue
        seen_names.add(candidate.suggested_name)
        selected.append(candidate)
    return selected


def dotenv_value(value: str) -> str:
    if value == "":
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,;{}?&~-]+", value):
        return value
    return "'" + value.replace("'", "\\'") + "'"


def parse_env_keys(lines: list[str]) -> set[str]:
    keys = set()
    for line in lines:
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match:
            keys.add(match.group(1))
    return keys


def replace_env_line(lines: list[str], key: str, value: str) -> list[str]:
    pattern = re.compile(rf"^(\s*){re.escape(key)}\s*=.*$")
    replacement = f"{key}={dotenv_value(value)}"
    return [replacement if pattern.match(line) else line for line in lines]


def write_env_file(path: Path, entries: dict[str, str], *, force: bool, write: bool) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    existing_keys = parse_env_keys(lines)

    if force:
        for key, value in entries.items():
            if key in existing_keys:
                lines = replace_env_line(lines, key, value)

    missing = [(key, value) for key, value in entries.items() if key not in existing_keys]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Generated by python-env-extractor. Review TODO values before use.")
        for key, value in missing:
            if force or key not in existing_keys:
                lines.append(f"{key}={dotenv_value(value)}")

    if write:
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print(f"wrote {path}")
    else:
        print(f"would write {path} with {len(missing)} new entr{'y' if len(missing) == 1 else 'ies'}")


def build_env_entries(
    candidates: list[Candidate],
    *,
    env_name: str,
    source_env: str,
) -> dict[str, str]:
    entries: dict[str, str] = {}
    for candidate in candidates:
        entries[candidate.suggested_name] = candidate.value if env_name == source_env else "TODO"
    return entries


def write_env_files(
    project_root: Path,
    envs: list[str],
    active_env: str,
    source_env: str,
    candidates: list[Candidate],
    *,
    force: bool,
    write: bool,
) -> None:
    for env in envs:
        entries = build_env_entries(candidates, env_name=env, source_env=source_env)
        write_env_file(project_root / f".env.{env}", entries, force=force, write=write)

    active_entries = build_env_entries(candidates, env_name=active_env, source_env=source_env)
    write_env_file(project_root / ".env", active_entries, force=force, write=write)


def markdown_report(candidates: list[Candidate], env_candidates: list[Candidate]) -> str:
    lines = [
        "# Python Env Candidate Report",
        "",
        f"Found {len(candidates)} candidate value(s).",
        f"{len(env_candidates)} candidate value(s) meet the env-file confidence threshold.",
        "",
    ]
    if not candidates:
        lines.append("No candidates found.")
        return "\n".join(lines) + "\n"

    by_category: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_category.setdefault(candidate.category, []).append(candidate)

    for category in sorted(by_category):
        lines.append(f"## {category.title()}")
        lines.append("")
        for candidate in by_category[category]:
            secret_note = " secret-like" if candidate.secret_like else ""
            lines.append(
                f"- `{candidate.suggested_name}` `{candidate.confidence}`{secret_note} "
                f"at `{candidate.file}:{candidate.line}`"
            )
            lines.append(f"  - preview: `{candidate.value_preview}`")
            lines.append(f"  - reason: {candidate.reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_reports(
    candidates: list[Candidate],
    env_candidates: list[Candidate],
    *,
    markdown_path: Path | None,
    json_path: Path | None,
) -> None:
    markdown = markdown_report(candidates, env_candidates)
    print(markdown)
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(markdown, encoding="utf-8")
        print(f"wrote {markdown_path}")
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps([candidate.report_dict() for candidate in candidates], indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {json_path}")


def main() -> int:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    if not project_root.exists():
        raise SystemExit(f"Project root does not exist: {project_root}")
    if not project_root.is_dir():
        raise SystemExit(f"Project root is not a directory: {project_root}")

    candidates = scan_project(project_root, args.prefix, args.max_file_bytes)
    env_candidates = selected_env_candidates(candidates, args.min_env_confidence)

    write_reports(
        candidates,
        env_candidates,
        markdown_path=args.markdown_report,
        json_path=args.json_report,
    )
    write_env_files(
        project_root,
        args.envs,
        args.active_env,
        args.source_env,
        env_candidates,
        force=args.force,
        write=args.write,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
