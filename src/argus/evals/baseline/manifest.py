"""Manifest, environment, and security utilities for reproducible baselines."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent


def get_git_commit(cwd: Path | None = None) -> str:
    """Return the full HEAD git commit SHA."""
    target_cwd = cwd or WORKSPACE_ROOT
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target_cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown_commit"


def get_git_branch(cwd: Path | None = None) -> str:
    """Return the current git branch name."""
    target_cwd = cwd or WORKSPACE_ROOT
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(target_cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown_branch"


def get_working_tree_status(cwd: Path | None = None) -> tuple[bool, list[dict[str, str]]]:
    """Inspect git working tree cleanliness.
    
    Returns (is_clean, dirty_files).
    """
    target_cwd = cwd or WORKSPACE_ROOT
    dirty_files: list[dict[str, str]] = []
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(target_cwd),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines:
                if not line.strip():
                    continue
                status_code = line[:2].strip()
                file_path = line[3:].strip()
                dirty_files.append({"status": status_code, "path": file_path})
            is_clean = len(dirty_files) == 0
            return is_clean, dirty_files
    except Exception as e:
        dirty_files.append({"status": "ERR", "path": f"Failed to check git status: {e}"})
    return False, dirty_files


def file_sha256(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not path.exists():
        return "file_not_found"
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"auth", re.IGNORECASE),
    re.compile(r"private[_-]?key", re.IGNORECASE),
]

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
]


def sanitize_secrets(obj: Any) -> Any:
    """Recursively redact secrets, API keys, and sensitive tokens from dicts, lists, or strings."""
    if isinstance(obj, dict):
        sanitized: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                sanitized[k] = sanitize_secrets(v)
            elif any(p.search(str(k)) for p in SENSITIVE_KEY_PATTERNS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_secrets(v)
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_secrets(item) for item in obj]
    elif isinstance(obj, str):
        val = obj
        for p in SENSITIVE_VALUE_PATTERNS:
            val = p.sub("[REDACTED]", val)
        return val
    return obj


def get_environment_info() -> dict[str, Any]:
    """Capture runtime execution environment details."""
    safe_env = sanitize_secrets({
        k: v for k, v in os.environ.items()
        if not any(p.search(k) for p in SENSITIVE_KEY_PATTERNS)
    })

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "python_compiler": platform.python_compiler(),
        "operating_system": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "cwd": str(WORKSPACE_ROOT),
        "environment_variables_redacted": safe_env,
    }


def generate_manifest(
    run_id: str,
    evaluation_suites: list[str],
    execution_mode: str = "offline_frozen",
    run_status: str = "COMPLETED",
    additional_metadata: dict[str, Any] | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Generate canonical baseline manifest.json dictionary."""
    target_cwd = cwd or WORKSPACE_ROOT
    commit = get_git_commit(target_cwd)
    branch = get_git_branch(target_cwd)
    is_clean, dirty_files = get_working_tree_status(target_cwd)

    uv_lock_path = target_cwd / "uv.lock"
    pyproject_path = target_cwd / "pyproject.toml"

    dataset_ids = {
        "heimdallr_v2_tasks": {
            "path": "data/evals/v2/benchmark_tasks.json",
            "sha256": file_sha256(target_cwd / "data/evals/v2/benchmark_tasks.json"),
        },
        "argus_v1_core": {
            "path": "data/evals/baseline_v1_core.json",
            "sha256": file_sha256(target_cwd / "data/evals/baseline_v1_core.json"),
        },
    }

    manifest = {
        "run_id": run_id,
        "utc_timestamp": datetime.now(UTC).isoformat(),
        "git_commit": commit,
        "git_branch": branch,
        "working_tree_clean": is_clean,
        "dirty_files_count": len(dirty_files),
        "dirty_files": dirty_files,
        "python_version": platform.python_version(),
        "operating_system": platform.system(),
        "architecture": platform.machine(),
        "dependency_manifest": {
            "pyproject_sha256": file_sha256(pyproject_path),
            "uv_lock_sha256": file_sha256(uv_lock_path),
        },
        "evaluation_suites": evaluation_suites,
        "dataset_identifiers": dataset_ids,
        "configuration_fingerprint": sanitize_secrets({
            "model_provider": "deterministic_eval_offline",
            "llm_api_online": False,
            "search_api_online": False,
            "crawler_network_online": False,
            "isolation_guard": "GroundTruthAccessGuard",
        }),
        "model_provider_identifiers": {
            "llm_provider": "deterministic_eval_offline",
            "status": "OFFLINE_FROZEN_CORPUS",
        },
        "execution_mode": execution_mode,
        "run_status": run_status,
    }

    if additional_metadata:
        manifest["metadata"] = sanitize_secrets(additional_metadata)

    return manifest
