import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parents[1] / "example"
IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@localhost"]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A copy of the example project as a git repository with one commit on main."""
    root = tmp_path / "project"
    shutil.copytree(
        EXAMPLE, root, ignore=shutil.ignore_patterns(".prove-it", ".hypothesis", "__pycache__")
    )
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "initial")
    return root


def prove_it(cwd: Path, *args: str, base: str | None = "HEAD") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PROVE_IT_")}
    if base:
        env["PROVE_IT_BASE"] = base
    return subprocess.run(
        [sys.executable, "-m", "prove_it.cli", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
