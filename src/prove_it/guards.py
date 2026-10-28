"""prove-guards: every guard must fire on a deliberate violation.

Each guard in guards.toml names a command and a canary: a patch that breaks the rule the guard
exists to enforce. For each guard this copies the working tree to a sandbox, applies the canary,
runs the command and requires it to fail with every expected message. It also requires each
guard's command to pass on the clean tree, every guard to have a canary, and every canary to
belong to a guard.

    [[guard]]
    name = "float-ban"
    command = "python -m pytest"
    paths = ["tests/test_rules.py"]   # optional: appended to the command for the canary run only
    canary = "float-in-allocator.patch"
    expect = ["float is banned in money code"]
    requirement = "REQ-NFR-01"   # optional, for the report

`paths` narrows the canary run to what should fire, including files the canary itself adds;
the clean-tree run always uses the bare command.
"""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from prove_it.config import Config, resolve_command

TIMEOUT_SECONDS = int(os.environ.get("PROVE_IT_GUARD_TIMEOUT", "900"))
JOBS = int(os.environ.get("PROVE_IT_JOBS", os.cpu_count() or 4))


@dataclass(frozen=True)
class Guard:
    name: str
    command: tuple[str, ...]
    canary: Path
    expect: tuple[str, ...]
    requirement: str = ""
    paths: tuple[str, ...] = ()


def load(cfg: Config) -> list[Guard]:
    data = tomllib.loads(cfg.guards.read_text())
    guards = []
    for g in data.get("guard", []):
        guards.append(
            Guard(
                name=g["name"],
                command=resolve_command(g["command"]),
                canary=cfg.canaries / g["canary"],
                expect=tuple(g["expect"]),
                requirement=g.get("requirement", ""),
                paths=tuple(g.get("paths", ())),
            )
        )
    return guards


def sandbox(cfg: Config) -> Path:
    """Copy tracked and untracked-but-not-ignored files, as the working tree has them now, into a
    fresh repository whose one commit is that tree. prove-red run inside it compares against that
    commit (PROVE_IT_BASE=HEAD), so a canary that adds a test is the change."""
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=cfg.root,
        check=True,
        capture_output=True,
    ).stdout.decode()
    box = Path(tempfile.mkdtemp(prefix="prove-guards-"))
    for rel in filter(None, listing.split("\0")):
        src = cfg.root / rel
        if src.is_file():
            dst = box / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    identity = ["-c", "user.name=prove-guards", "-c", "user.email=prove-guards@localhost"]
    subprocess.run(["git", "init", "-q"], cwd=box, check=True)
    for args in (["add", "-A"], ["commit", "-q", "--no-verify", "-m", "sandbox"]):
        subprocess.run(["git", *identity, *args], cwd=box, check=True, capture_output=True)
    return box


def run(command: tuple[str, ...], cwd: Path) -> tuple[int, str]:
    """A timeout is a failure of that job, never of prove-guards."""
    env = {**os.environ, "PROVE_IT_BASE": "HEAD"}
    env.pop("PROVE_IT_RESULTS", None)
    try:
        done = subprocess.run(
            command, cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return 124, f"`{shown_as(command)}` timed out after {TIMEOUT_SECONDS}s"
    return done.returncode, done.stdout + done.stderr


def shown_as(command: tuple[str, ...]) -> str:
    """The command as guards.toml spells it, not as resolve_command rewrote it."""
    return (
        shlex.join(command)
        .replace(f"{sys.executable} -m prove_it.cli", "prove-it")
        .replace(sys.executable, "python")
    )


def check_clean(cfg: Config, command: tuple[str, ...]) -> tuple[str, list[str]]:
    box = sandbox(cfg)
    try:
        code, output = run(command, box)
    finally:
        shutil.rmtree(box)
    shown = shown_as(command)
    if code == 0:
        return f"clean tree · {shown}: passes", []
    return f"clean tree · {shown}: FAILS", [f"clean tree fails `{shown}`:\n{output[-4000:]}"]


def check_guard(cfg: Config, g: Guard) -> tuple[str, list[str]]:
    label = f"{g.name} ({g.requirement})" if g.requirement else g.name
    box = sandbox(cfg)
    try:
        applied = subprocess.run(
            ["git", "apply", str(g.canary)], cwd=box, capture_output=True, text=True
        )
        if applied.returncode != 0:
            return f"{label}: canary does not apply", [
                f"{g.name}: canary no longer applies:\n{applied.stderr}"
            ]
        code, output = run((*g.command, *g.paths), box)
    finally:
        shutil.rmtree(box)
    missing = [e for e in g.expect if e not in output]
    if code == 0:
        return f"{label}: DID NOT FIRE", [f"{g.name}: command passed with the canary applied"]
    if missing:
        return f"{label}: DID NOT FIRE", [
            f"{g.name}: failed, but without the expected message {missing}:\n{output[-4000:]}"
        ]
    return f"{label}: fires", []


def main(cfg: Config) -> int:
    guards = load(cfg)
    failures: list[str] = []
    referenced = {g.canary for g in guards}
    for g in guards:
        if not g.canary.is_file():
            failures.append(f"{g.name}: canary {g.canary.name} is missing")
    for orphan in sorted(set(cfg.canaries.glob("*.patch")) - referenced):
        failures.append(f"canary {orphan.name} belongs to no guard")

    # Every sandbox is an independent copy, so the jobs run in parallel; results print in order.
    commands = sorted({g.command for g in guards})
    jobs = [lambda c=c: check_clean(cfg, c) for c in commands] + [
        lambda g=g: check_guard(cfg, g) for g in guards if g.canary.is_file()
    ]
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=JOBS) as pool:
        results = list(pool.map(lambda job: job(), jobs))
    for line, found in results:
        print(line)
        failures += found
    print(f"\n{len(jobs)} jobs on {JOBS} workers in {time.monotonic() - started:.0f}s")

    if failures:
        print("\nprove-guards FAILED:\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    print(f"\nprove-guards passed: all {len(guards)} guards fire, and the clean tree passes.")
    return 0
