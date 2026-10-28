"""The [tool.prove-it] table in a project's pyproject.toml."""

import shlex
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    root: Path  # the directory holding pyproject.toml
    requirements: Path  # markdown table of requirements
    test_command: tuple[str, ...]  # runs the suite; node ids are appended for prove-red
    tests: tuple[str, ...]  # directories whose test_*.py files prove-red compares
    # Taken from the change, not the base, when prove-red builds the base checkout: the tests'
    # own infrastructure, fixtures and the requirement IDs they cite.
    from_change: tuple[str, ...]
    guards: Path
    canaries: Path


def resolve_command(command: str | list[str]) -> tuple[str, ...]:
    """Split a command, and run `python` and `prove-it` with this interpreter, so commands work
    whether or not a virtualenv is activated."""
    parts = shlex.split(command) if isinstance(command, str) else list(command)
    if parts and parts[0] in ("python", "python3"):
        parts[0] = sys.executable
    elif parts and parts[0] == "prove-it":
        parts[:1] = [sys.executable, "-m", "prove_it.cli"]
    return tuple(parts)


def find_root(start: Path) -> Path:
    """The nearest directory at or above `start` whose pyproject.toml has [tool.prove-it]."""
    for d in [start, *start.parents]:
        pyproject = d / "pyproject.toml"
        if pyproject.is_file() and "prove-it" in tomllib.loads(pyproject.read_text()).get(
            "tool", {}
        ):
            return d
    raise SystemExit(f"No pyproject.toml with a [tool.prove-it] table at or above {start}")


def load(start: Path | None = None) -> Config:
    root = find_root((start or Path.cwd()).resolve())
    table = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["prove-it"]
    return Config(
        root=root,
        requirements=root / table.get("requirements", "requirements.md"),
        test_command=resolve_command(table.get("test_command", ["python", "-m", "pytest"])),
        tests=tuple(table.get("tests", ["tests"])),
        from_change=tuple(
            table.get("from_change", ["pyproject.toml", "conftest.py", "requirements.md"])
        ),
        guards=root / table.get("guards", "guards/guards.toml"),
        canaries=root / table.get("canaries", "guards/canaries"),
    )
