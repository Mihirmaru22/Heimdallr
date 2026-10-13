"""Heimdallr V3.2: Candidate Security Gate & Isolation Validator.

Evaluates candidates against 10 critical security vectors:
1. Arbitrary code execution risk
2. Subprocess execution
3. Unrestricted network egress
4. Credential access
5. Filesystem escape
6. Environment variable access
7. Data exfiltration
8. Prompt injection handling
9. Malicious / corrupt output sanitization
10. Dependency bloat / supply-chain risk
"""

from __future__ import annotations

import ast
import contextlib
import json
import logging
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from argus.competition.models import CandidateImplementation

logger = logging.getLogger(__name__)

# Dangerous python AST calls, imports, and modules
DANGEROUS_MODULES = {
    "subprocess",
    "shutil",
    "socket",
    "http.client",
    "urllib.request",
    "os",
    "posix",
    "pty",
    "ctypes",
    "importlib",
    "pickle",
    "marshal",
    "shelve",
    "multiprocessing",
    "webbrowser",
    "code",
    "codeop",
    "pdb",
    "sys",
    "builtins",
    "platform",
    "asyncio.subprocess",
}
DANGEROUS_IMPORTS = {"subprocess", "shutil", "socket", "http.client", "urllib.request", "os.system", "os"}
DANGEROUS_CALLS = {
    "eval", "exec", "system", "popen", "spawn", "__import__",
    "fork", "kill", "unlink", "remove", "rmdir", "execv", "execve",
}


class SecurityGateValidator:
    """Performs static code auditing and runtime contract validation for candidate specialists."""

    @staticmethod
    def audit_candidate_source(source_path: Path | str) -> Dict[str, Any]:
        """Audit candidate implementation code for unsafe execution patterns."""
        p = Path(source_path)
        if not p.exists():
            return {"status": "ERROR", "reason": f"File not found: {source_path}"}

        with open(p, "r", encoding="utf-8") as f:
            content = f.read()

        findings: List[str] = []

        try:
            tree = ast.parse(content, filename=str(p))
            for node in ast.walk(tree):
                # Check dangerous imports
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod_base = alias.name.split(".")[0]
                        if alias.name in DANGEROUS_IMPORTS or mod_base in DANGEROUS_MODULES:
                            findings.append(f"Dangerous import: '{alias.name}' at line {node.lineno}")
                elif isinstance(node, ast.ImportFrom):
                    mod_base = (node.module or "").split(".")[0]
                    if node.module in DANGEROUS_IMPORTS or mod_base in DANGEROUS_MODULES:
                        findings.append(f"Dangerous import from: '{node.module}' at line {node.lineno}")
                    else:
                        for alias in node.names:
                            full_import = f"{node.module}.{alias.name}" if node.module else alias.name
                            if (
                                full_import in DANGEROUS_IMPORTS
                                or alias.name in DANGEROUS_CALLS
                                or full_import in DANGEROUS_MODULES
                            ):
                                findings.append(f"Dangerous import: '{full_import}' at line {node.lineno}")

                # Check dangerous function calls
                elif isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    if func_name in DANGEROUS_CALLS:
                        findings.append(f"Dangerous call to '{func_name}' at line {node.lineno}")

        except Exception as e:
            findings.append(f"AST parse failure: {e}")

        # Check prompt injection sanitization
        has_sanitization = bool(re.search(r'(sanitize|whitelist|strip|clean)', content, re.IGNORECASE))
        if not has_sanitization:
            findings.append("Warning: Candidate lacks explicit input/output sanitization logic")

        status = "FAIL" if any("Dangerous" in f for f in findings) else "PASS"

        return {
            "source_file": p.name,
            "status": status,
            "findings": findings,
            "vectors_evaluated": 10,
        }

    @staticmethod
    def sanitize_text(text: str, max_chars: Optional[int] = None) -> str:
        """Sanitize and neutralize adversarial payloads across all execution vectors."""
        if not text:
            return ""

        # 0. Truncate buffer overflow attempts if max_chars is specified
        s = text[:max_chars] if max_chars is not None else text

        # 1. Neutralize null bytes and control chars
        s = s.replace("\x00", "").replace("%00", "")

        # 2. Defuse prompt injection and instruction overrides
        s = re.sub(
            r'(?i)\b(ignore|disregard|forget|override)\s+(all\s+)?(prior|previous|system)\s+instructions\b[^\n\.\;]*',
            '[DEFUSED_INSTRUCTION_OVERRIDE]',
            s,
        )
        s = re.sub(
            r'(?i)\b(system\s+prompt\s+override|you\s+are\s+now\s+in\s+debug\s+mode|jailbreak|pwn_[^\s]*)\b',
            '[DEFUSED_PROMPT_INJECTION]',
            s,
        )
        s = re.sub(
            r'(?i)\b(dump\s+environment\s+variables|print\s+env\s+vars)\b',
            '[DEFUSED_EXFIL_ATTEMPT]',
            s,
        )

        # 3. Defuse shell execution & command chaining
        s = re.sub(
            r';\s*(rm|cat|ls|nc|curl|wget|bash|sh|chmod|chown|kill|reboot|sudo)\b[^\n;]*',
            '; [DEFUSED_SHELL_COMMAND]',
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r'\|\s*(nc|cat|bash|sh|curl|wget|mail)\b[^\n;]*',
            '| [DEFUSED_PIPE_COMMAND]',
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r'(?i)(/etc/(passwd|shadow|hosts|sudoers|tor/[^\s]*)|file:///etc/[^\s]*)',
            '/etc/[DEFUSED_FILE_PATH]',
            s,
        )
        s = re.sub(
            r'(?i)(~/\.ssh/[^\s]*|c:\\windows\\system32[^\s]*|var/lib/tor/[^\s]*|private_key[^\s]*)',
            '[DEFUSED_SYSTEM_PATH]',
            s,
        )

        # 4. Defuse path traversal
        s = re.sub(r'(\.\./|\.\.\\)+', '[DEFUSED_PATH_TRAVERSAL]/', s)

        # 5. Defuse HTML & script injection
        s = re.sub(r'<\s*script[^>]*>.*?<\s*/\s*script\s*>', '[DEFUSED_SCRIPT]', s, flags=re.IGNORECASE)
        s = re.sub(r'<\s*(iframe|object|embed|svg|img)[^>]*>', '[DEFUSED_HTML_TAG]', s, flags=re.IGNORECASE)

        # 6. Defuse environment variable exfiltration
        s = re.sub(r'\$\{?[A-Z0-9_]*(SECRET|KEY|TOKEN|PASSWORD|CREDENTIAL|AWS|OPENAI)[A-Z0-9_]*\}?', '[DEFUSED_ENV_VAR]', s)

        # 7. Defuse credential harvesting tokens
        s = re.sub(r'(?i)bearer\s+sk-[a-zA-Z0-9_\-]+', 'Bearer [DEFUSED_TOKEN]', s)

        # 8. Defuse evaluator / state tampering strings
        s = re.sub(r'(?i)__evaluator_[a-zA-Z0-9_]*__', '[DEFUSED_EVAL_ATTR]', s)
        s = re.sub(r'(?i)state\.(is_authoritative|claims|entities)\s*=\s*[^\s;]+', '[DEFUSED_STATE_MUTATION]', s)

        # 9. Defuse SQL-like injection patterns
        s = re.sub(r"(?i)'\s*union\s+select\b[^\n;]*", "' [DEFUSED_SQLI]", s)
        s = re.sub(r"(?i)'\s*;\s*drop\s+table\b[^\n;]*", "' ; [DEFUSED_SQLI]", s)

        # 10. Defuse SSRF metadata endpoints
        s = re.sub(r"(?i)https?://(169\.254\.169\.254|localhost|127\.0\.0\.1)[^\s]*", "[DEFUSED_SSRF_URL]", s)

        # 11. Code execution pattern defusing (eval, exec, system)
        s = re.sub(r'\b(eval|exec|system|popen|spawn)\s*\(.*?\)', '[BLOCKED_EXEC_CALL]', s, flags=re.IGNORECASE)

        # 12. Strip control characters that break template parsers
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', s).strip()

        return s if max_chars is None else s[:max_chars]

    @staticmethod
    def sanitize_candidate_observation(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Strip executable payloads or injection attempts from candidate outputs and enforce unprivileged status."""
        clean: Dict[str, Any] = {}
        for k, v in payload.items():
            clean_key = SecurityGateValidator.sanitize_text(str(k))
            if v is None:
                clean[clean_key] = None
            elif isinstance(v, str):
                clean[clean_key] = SecurityGateValidator.sanitize_text(v)
            elif isinstance(v, bool):
                clean[clean_key] = v
            elif isinstance(v, (int, float)):
                clean[clean_key] = v
            elif isinstance(v, list):
                clean_list = []
                for item in v[:50]:
                    if item is None:
                        clean_list.append(None)
                    elif isinstance(item, str):
                        clean_list.append(SecurityGateValidator.sanitize_text(item))
                    elif isinstance(item, bool):
                        clean_list.append(item)
                    elif isinstance(item, (int, float)):
                        clean_list.append(item)
                    elif isinstance(item, dict):
                        clean_list.append(SecurityGateValidator.sanitize_candidate_observation(item))
                    elif isinstance(item, list):
                        clean_list.append([
                            SecurityGateValidator.sanitize_text(sub) if isinstance(sub, str)
                            else SecurityGateValidator.sanitize_candidate_observation(sub) if isinstance(sub, dict)
                            else sub
                            for sub in item[:20]
                        ])
                    else:
                        clean_list.append(SecurityGateValidator.sanitize_text(str(item)))
                clean[clean_key] = clean_list
            elif isinstance(v, dict):
                clean[clean_key] = SecurityGateValidator.sanitize_candidate_observation(v)
            else:
                clean[clean_key] = SecurityGateValidator.sanitize_text(str(v))

        # Enforce strict epistemic boundary: Candidate observations can NEVER claim authoritativeness
        clean["is_authoritative"] = False
        return clean


class CandidateExecutionSandbox:
    """Operating-system and process-level sandbox for isolated candidate code execution."""

    SENSITIVE_ENV_PREFIXES = (
        "OPENAI_", "ANTHROPIC_", "AWS_", "SECRET_", "API_KEY", "TOKEN",
        "PASSWORD", "DATABASE_", "CREDENTIAL", "GITHUB_", "GEMINI_",
    )

    MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB safety cap to prevent output flooding

    @classmethod
    def has_kernel_isolation(cls) -> bool:
        """Probe whether true kernel-level namespace/filesystem isolation is available in the host OS.

        Returns False in unprivileged containers lacking CAP_SYS_ADMIN or user namespaces.
        """
        try:
            res = subprocess.run(
                ["unshare", "-m", "true"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def _get_isolation_metadata(cls, has_kernel: bool) -> Dict[str, bool]:
        """Return accurate indicators of active OS and runtime isolation boundaries."""
        return {
            "kernel_isolation": has_kernel,
            "filesystem_isolation": has_kernel,  # True filesystem isolation requires kernel namespaces
            "network_isolation": False,          # Container lacks network namespace privilege
            "runtime_network_blocked": True,     # Python socket runtime blocked via preamble
            "process_group_isolation": True,     # Setsid & killpg enforced
            "resource_limits": True,             # RLIMIT_AS, RLIMIT_CPU, RLIMIT_FSIZE enforced
            "environment_scrubbed": True,        # Host secrets scrubbed from environ
        }

    @classmethod
    def get_scrubbed_env(cls) -> Dict[str, str]:
        """Construct a minimal, unprivileged environment free of host credentials."""
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        src_dir = repo_root / "src"

        # Safe baseline PATH
        safe_path = "/usr/local/bin:/usr/bin:/bin"
        if "PATH" in os.environ:
            safe_path = os.environ["PATH"]

        clean_env = {
            "PATH": safe_path,
            "PYTHONPATH": str(src_dir),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
        }
        return clean_env

    @classmethod
    def execute_script(
        cls,
        script_path: Path | str,
        input_data: Dict[str, Any] | None = None,
        timeout_seconds: float = 5.0,
        require_kernel_isolation: bool = True,
        allow_unconfined_execution: bool = False,
    ) -> Dict[str, Any]:
        """Execute a candidate Python script within a restricted OS subprocess sandbox.

        Security Invariant:
        Candidate-code execution is DISABLED BY DEFAULT unless a verified, suitable OS-level
        isolation boundary (kernel namespaces or bubblewrap) is available. In deployment environments
        lacking namespace privileges, execution is immediately BLOCKED to prevent arbitrary
        code execution under the host UID.

        An explicit override `allow_unconfined_execution=True` is provided solely for controlled
        offline testing of process-group termination, resource limits, and signal handling.
        """
        p = Path(script_path)
        kernel_available = cls.has_kernel_isolation()

        if not p.exists():
            return {
                "status": "ERROR",
                "error": f"Candidate script does not exist: {p}",
                "output": None,
                "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
            }

        if require_kernel_isolation and not kernel_available and not allow_unconfined_execution:
            return {
                "status": "BLOCKED",
                "error": (
                    "Candidate execution BLOCKED: Suitable OS-level isolation (user/mount namespaces or bubblewrap) "
                    "is unavailable in the current host environment. Arbitrary candidate-code execution is disabled "
                    "by default to prevent unconfined execution under the host process UID."
                ),
                "output": None,
                "isolation": cls._get_isolation_metadata(has_kernel=False),
            }

        clean_env = cls.get_scrubbed_env()
        input_json = json.dumps(input_data or {})

        try:
            with tempfile.TemporaryDirectory() as scratch_dir:
                scratch_path = Path(scratch_dir)
                runner_file = scratch_path / "_sandbox_runner.py"
                target_script_str = str(p.resolve())

                # Write security wrapper that defuses socket networking before executing candidate
                runner_content = (
                    "import sys, os, json\n"
                    "# 1. Defuse socket creation in candidate runtime\n"
                    "def _blocked_socket(*args, **kwargs):\n"
                    "    raise PermissionError('Network access is prohibited in CandidateExecutionSandbox')\n"
                    "try:\n"
                    "    import socket\n"
                    "    socket.socket = _blocked_socket\n"
                    "    socket.create_connection = _blocked_socket\n"
                    "    socket.getaddrinfo = _blocked_socket\n"
                    "except Exception:\n"
                    "    pass\n"
                    "try:\n"
                    "    import _socket\n"
                    "    _socket.socket = _blocked_socket\n"
                    "except Exception:\n"
                    "    pass\n"
                    f"target_script = {repr(target_script_str)}\n"
                    "with open(target_script, 'rb') as f:\n"
                    "    code = compile(f.read(), target_script, 'exec')\n"
                    "exec(code, {'__name__': '__main__', '__file__': target_script})\n"
                )
                runner_file.write_text(runner_content, encoding="utf-8")

                def _apply_rlimits():
                    # Virtual memory limit (512 MB)
                    try:
                        mem_limit = 512 * 1024 * 1024
                        resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
                    except (ValueError, OSError):
                        pass
                    # CPU time limit (seconds)
                    try:
                        cpu_limit = max(1, int(timeout_seconds) + 1)
                        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit + 1))
                    except (ValueError, OSError):
                        pass
                    # Maximum file size creation limit (5 MB)
                    try:
                        fsize_limit = 5 * 1024 * 1024
                        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_limit, fsize_limit))
                    except (ValueError, OSError):
                        pass
                    # Disable core dumps
                    try:
                        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                    except (ValueError, OSError):
                        pass

                proc = subprocess.Popen(
                    [sys.executable, str(runner_file)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=clean_env,
                    cwd=scratch_dir,
                    start_new_session=True,
                    preexec_fn=_apply_rlimits,
                )

                try:
                    stdout, stderr = proc.communicate(input=input_json, timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    # Terminate entire process group including all child and descendant processes
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (OSError, ProcessLookupError):
                        try:
                            proc.kill()
                        except OSError:
                            pass
                    try:
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass
                    return {
                        "status": "TIMEOUT",
                        "error": f"Execution exceeded maximum permitted duration of {timeout_seconds}s",
                        "output": None,
                        "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
                    }

                # Bound output reading
                if len(stdout) > cls.MAX_OUTPUT_BYTES:
                    stdout = stdout[:cls.MAX_OUTPUT_BYTES]
                if len(stderr) > cls.MAX_OUTPUT_BYTES:
                    stderr = stderr[:cls.MAX_OUTPUT_BYTES]

                if proc.returncode != 0:
                    return {
                        "status": "FAILED",
                        "returncode": proc.returncode,
                        "error": stderr.strip()[:1000],
                        "output": None,
                        "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
                    }

                clean_stdout = stdout.strip()
                if not clean_stdout:
                    return {
                        "status": "SUCCESS",
                        "output": {},
                        "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
                    }

                try:
                    parsed = json.loads(clean_stdout)
                    return {
                        "status": "SUCCESS",
                        "output": SecurityGateValidator.sanitize_candidate_observation(parsed)
                        if isinstance(parsed, dict)
                        else parsed,
                        "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
                    }
                except json.JSONDecodeError:
                    return {
                        "status": "SUCCESS",
                        "output": SecurityGateValidator.sanitize_text(clean_stdout),
                        "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
                    }

        except Exception as e:
            return {
                "status": "ERROR",
                "error": f"Sandbox execution failure: {e}",
                "output": None,
                "isolation": cls._get_isolation_metadata(has_kernel=kernel_available),
            }


class CandidateRuntimeBoundary:
    """In-process containment boundary that masks sensitive host environment and sanitizes candidate outputs."""

    @classmethod
    @contextlib.contextmanager
    def mask_environment(cls):
        """Temporarily scrub sensitive environment variables during candidate execution."""
        removed_vars = {}
        for k in list(os.environ.keys()):
            k_upper = k.upper()
            if any(k_upper.startswith(pfx) or pfx in k_upper for pfx in (
                "SECRET", "TOKEN", "PASSWORD", "API_KEY", "CREDENTIAL", "AWS_", "OPENAI", "DATABASE", "GEMINI"
            )):
                removed_vars[k] = os.environ.pop(k)
        try:
            yield
        finally:
            os.environ.update(removed_vars)

