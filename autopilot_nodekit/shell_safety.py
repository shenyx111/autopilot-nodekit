from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class ShellSafetyFinding:
    severity: str  # error | warning
    code: str
    message: str
    hint: str = ""

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


# Commands that should never appear inside deterministic verifiers or bootstrap
# read-only checks unless the operator explicitly opts in. These are not banned
# for Codex worker tasks themselves; they are banned from verifier commands where
# accidental shell expansion can submit/cancel jobs or mutate state.
MUTATING_COMMANDS = {
    "sbatch": "Slurm job submission",
    "scancel": "Slurm job cancellation",
    "srun": "Slurm interactive/batch launch",
    "qsub": "PBS job submission",
    "qdel": "PBS job cancellation",
    "docker": "Docker mutation risk",
    "podman": "container mutation risk",
    "kubectl": "cluster mutation risk",
}

DANGEROUS_REGEXES = [
    (re.compile(r"`[^`]+`"), "shell_command_substitution_backticks", "Backtick command substitution can execute text inside quotes."),
    (re.compile(r"\$\([^)]*\)"), "shell_command_substitution_dollar_paren", "$(...) command substitution can execute nested commands."),
    (re.compile(r"(^|\s)rm\s+(-[A-Za-z]*[rf][A-Za-z]*|-[A-Za-z]*[fr][A-Za-z]*)\b"), "destructive_rm", "rm -rf style deletion is not allowed in verifier/bootstrap commands."),
    (re.compile(r"(^|\s)mkfs(\.|\s|$)"), "filesystem_format", "Filesystem formatting commands are never allowed."),
]

READ_ONLY_DOCKER_PATTERNS = [
    re.compile(r"^docker\s+(ps|version|info)\b"),
    re.compile(r"^docker\s+compose\s+(ps|version|config|logs)\b"),
    re.compile(r"^docker\s+inspect\b"),
    re.compile(r"^docker\s+logs\b"),
]


def lint_shell_command(command: str, *, purpose: str = "verifier", platform: str | None = None) -> List[ShellSafetyFinding]:
    """Return shell-safety findings for a command string.

    The linter is intentionally strict for deterministic verifier/bootstrap
    commands because those commands should be read-only and reproducible. It is
    intentionally softer for worker commands, since the worker is the agent's
    actual action surface.
    """
    command = command or ""
    findings: List[ShellSafetyFinding] = []
    stripped = command.strip()

    if not stripped:
        return findings

    for rx, code, message in DANGEROUS_REGEXES:
        if rx.search(command):
            findings.append(ShellSafetyFinding("error", code, message, "Move the text into a file or use single quotes / Python checks; do not rely on shell expansion."))

    tokens = _safe_tokens(command)
    first_tokens = _command_positions(tokens)
    purpose_strict = purpose in {"verifier", "bootstrap", "preflight", "doctor"}

    if purpose_strict:
        for idx, tok in first_tokens:
            base = tok.lower()
            if base in {"squeue", "sacct", "scontrol", "sinfol", "sinfo"}:
                continue
            if base in MUTATING_COMMANDS:
                if base == "docker" and _is_read_only_docker(stripped):
                    continue
                findings.append(
                    ShellSafetyFinding(
                        "error",
                        f"mutating_command_in_{purpose}",
                        f"{base!r} appears in a {purpose} command ({MUTATING_COMMANDS.get(base, 'mutation risk')}).",
                        "Use a read-only probe in the verifier. Put mutations/submissions in explicit tasks with human/Slurm gates.",
                    )
                )

    # Windows-specific hints: glob expansion and POSIX shell assumptions are common
    # sources of false verifier failures. Warn, do not block, because some users run
    # Git Bash/WSL intentionally.
    if platform and platform.lower().startswith("win"):
        if "/bin/sh" in command or "bash -lc" in command:
            findings.append(ShellSafetyFinding("warning", "posix_shell_on_windows", "POSIX shell command appears in a Windows command.", "Prefer direct Python verifier scripts or PowerShell-compatible wrappers."))
        if re.search(r"['\"]?[^\s'\"]*\*[^\s'\"]*['\"]?", command) and not re.search(r"python(\.exe)?\s+(-c|-)\b", command, re.I):
            findings.append(ShellSafetyFinding("warning", "glob_in_windows_shell", "Shell glob found in a Windows command.", "Prefer Python pathlib glob checks to avoid quoting/expansion differences."))

    return findings


def should_block(findings: List[ShellSafetyFinding]) -> bool:
    return any(f.severity == "error" for f in findings)


def render_findings(findings: List[ShellSafetyFinding]) -> str:
    if not findings:
        return "No shell-safety findings."
    lines = []
    for f in findings:
        lines.append(f"- {f.severity.upper()} {f.code}: {f.message}" + (f" Hint: {f.hint}" if f.hint else ""))
    return "\n".join(lines)


def _safe_tokens(command: str) -> List[str]:
    try:
        return shlex.split(command, posix=True)
    except Exception:
        # Fall back to whitespace. The regex checks above still catch the main
        # dangerous cases. Returning something is better than failing open.
        return command.replace(";", " ; ").replace("&&", " && ").replace("||", " || ").split()


def _command_positions(tokens: List[str]) -> List[tuple[int, str]]:
    positions: List[tuple[int, str]] = []
    expect_cmd = True
    skip_next = False
    for i, tok in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        if tok in {";", "&&", "||", "|"}:
            expect_cmd = True
            continue
        if tok in {"env", "command", "time", "timeout"} and expect_cmd:
            expect_cmd = True
            if tok == "timeout" and i + 1 < len(tokens):
                skip_next = True
            continue
        if "=" in tok and expect_cmd and not tok.startswith("="):
            continue
        if expect_cmd:
            positions.append((i, tok.rsplit("/", 1)[-1]))
            expect_cmd = False
    return positions


def _is_read_only_docker(command: str) -> bool:
    return any(rx.search(command.strip()) for rx in READ_ONLY_DOCKER_PATTERNS)
