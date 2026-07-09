from pathlib import Path

from autopilot_nodekit.cli import main
from autopilot_nodekit.shell_safety import lint_shell_command, should_block


def test_shell_safety_blocks_backticks_in_verifier():
    findings = lint_shell_command('rg "`sbatch`" outputs/report.md', purpose='verifier')
    assert should_block(findings)
    assert any(f.code == 'shell_command_substitution_backticks' for f in findings)


def test_shell_safety_blocks_sbatch_in_verifier():
    findings = lint_shell_command('sbatch run.slurm', purpose='verifier')
    assert should_block(findings)
    assert any(f.code.startswith('mutating_command') for f in findings)


def test_shell_safety_allows_squeue_in_verifier():
    findings = lint_shell_command('squeue -u user', purpose='verifier')
    assert not should_block(findings)


def test_shell_safety_warns_windows_glob():
    findings = lint_shell_command('test -s outputs/*.md', purpose='verifier', platform='windows')
    assert any(f.code == 'glob_in_windows_shell' for f in findings)
    assert not should_block(findings)


def test_shell_safety_cli_allows_safe_command(capsys):
    code = main(["shell-safety-lint", "--command", "python -m pytest -q"])
    assert code == 0
    assert "No shell-safety findings" in capsys.readouterr().out


def test_shell_safety_cli_blocks_unsafe_verifier(capsys):
    code = main(["shell-safety-lint", "--command", "sbatch run.slurm"])
    assert code == 2
    assert "mutating_command_in_verifier" in capsys.readouterr().out
