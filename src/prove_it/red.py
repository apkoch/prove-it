"""prove-red: every new or changed test must fail on the code before the change.

1. Find tests added or changed since the base, comparing each test function's own source,
   decorators included. The working tree counts, so it runs before you commit.
2. Build a temporary worktree at the base: production code from the base, and the tests, test
   infrastructure and requirements (`from_change`) from the change.
3. Run only those tests there. Each must fail for the right reason: an assertion, pytest.fail,
   or NotImplementedError from a stub. Import, collection and fixture errors don't count.
4. Run them on the change itself, where each must pass.

Tests marked @pytest.mark.characterization(reason=...) pin existing behaviour, so they must pass
on the base instead.

Base: PROVE_IT_BASE if set; otherwise the merge base with origin/main, or HEAD~1 on main itself.
"""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from prove_it.config import Config

RIGHT_REASONS = ("AssertionError", "NotImplementedError", "Failed")  # Failed: pytest.fail/raises


@dataclass(frozen=True)
class Selected:
    file: str  # relative to the project root
    name: str  # function name, or Class::function
    characterization: bool = False

    @property
    def node_id(self) -> str:
        return f"{self.file}::{self.name}"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def rev(root: Path, name: str) -> str | None:
    found = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return found.stdout.strip() if found.returncode == 0 else None


def resolve_base(root: Path) -> str | None:
    """The commit to compare against; None when there is nothing before this one."""
    if base := os.environ.get("PROVE_IT_BASE"):
        return git("rev-parse", base, cwd=root).strip()
    head = rev(root, "HEAD")
    if head is None:
        return None
    found = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"], cwd=root, capture_output=True, text=True
    )
    base = found.stdout.strip() if found.returncode == 0 else ""
    if base and base != head:
        return base
    # On main itself: uncommitted work is the change (base HEAD); a clean tree is the last commit
    # (base its first parent).
    if git("status", "--porcelain", "--untracked-files=normal", ".", cwd=root).strip():
        return head
    return rev(root, "HEAD~1")


def changed_files(root: Path, base: str) -> list[str]:
    """Paths relative to the project root, which may sit anywhere inside the repository."""
    tracked = git("diff", "--name-only", "--relative", base, "--", ".", cwd=root).split()
    untracked = git("ls-files", "--others", "--exclude-standard", ".", cwd=root).split()
    return sorted({f for f in tracked + untracked if (root / f).is_file()})


def base_source(root: Path, base: str, path: str) -> str:
    shown = subprocess.run(
        ["git", "show", f"{base}:./{path}"], cwd=root, capture_output=True, text=True
    )
    return shown.stdout if shown.returncode == 0 else ""


def python_tests(source: str) -> dict[str, tuple[str, bool]]:
    """Test name → (a dump of its source, decorators included; marked characterization?)."""
    tests: dict[str, tuple[str, bool]] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return tests
    for node in tree.body:
        found: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]] = []
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        ):
            found.append((node.name, node))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            found += [
                (f"{node.name}::{n.name}", n)
                for n in node.body
                if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
                and n.name.startswith("test")
            ]
        for name, fn in found:
            marked = any("characterization" in ast.dump(d) for d in fn.decorator_list)
            tests[name] = (ast.dump(fn, include_attributes=False), marked)
    return tests


def is_test_file(cfg: Config, path: str) -> bool:
    p = Path(path)
    in_tests = any(p.is_relative_to(d) for d in cfg.tests)
    return in_tests and p.name.startswith("test_") and p.suffix == ".py"


def select(cfg: Config, base: str, files: list[str]) -> list[Selected]:
    selected: list[Selected] = []
    for f in files:
        if not is_test_file(cfg, f):
            continue
        old = python_tests(base_source(cfg.root, base, f))
        for test, (dump, marked) in python_tests((cfg.root / f).read_text()).items():
            if old.get(test, ("", False))[0] != dump:
                selected.append(Selected(f, test, marked))
    return selected


def copy_from_change(cfg: Config, project: Path) -> None:
    """Overlay the change's tests and test infrastructure onto the base checkout."""
    listed = git("ls-files", "--cached", "--others", "--exclude-standard", cwd=cfg.root).split()
    paths = set(cfg.from_change) | {
        f for f in listed if any(Path(f).is_relative_to(d) for d in cfg.tests)
    }
    for rel in sorted(paths):
        src, dst = cfg.root / rel, project / rel
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def run_file(cfg: Config, where: Path, tests: list[Selected]) -> tuple[dict, str]:
    """One file's selected tests in one pytest run: results by node id, and pytest's output."""
    fd, name = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    out = Path(name)
    env = {**os.environ, "PROVE_IT_RESULTS": str(out)}
    # The checkout under test comes first on the path, so its code is the code imported.
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(where), str(where / "src"), env.get("PYTHONPATH", "")) if p
    )
    done = subprocess.run(
        [*cfg.test_command, "-q", "-p", "no:cacheprovider", *[t.node_id for t in tests]],
        cwd=where,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    raw = json.loads(out.read_text()) if out.stat().st_size else {}
    out.unlink()
    return raw, (done.stdout + done.stderr)[-1500:]


def run(cfg: Config, where: Path, tests: list[Selected]) -> dict[str, dict[str, object]]:
    """Run the selected tests; per-test results keyed by node id.

    One pytest run per file, in parallel: pytest aborts a whole run when a node id it was given
    lives in a file it can't import, so one such file must not hide every other result.
    """
    by_file: dict[str, list[Selected]] = {}
    for t in tests:
        by_file.setdefault(t.file, []).append(t)
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        runs = dict(
            zip(by_file, pool.map(lambda f: run_file(cfg, where, by_file[f]), by_file), strict=True)
        )
    merged: dict[str, dict[str, object]] = {}
    for t in tests:
        raw, output = runs[t.file]
        found = [r for n, r in raw.items() if n == t.node_id or n.startswith(t.node_id + "[")]
        merged[t.node_id] = {"ran": bool(found), "runs": found, "output": output}
    return merged


def verdict_on_base(t: Selected, result: dict[str, object]) -> str | None:
    """None when the base run proves the test; otherwise why it doesn't."""
    runs = result["runs"]
    assert isinstance(runs, list)
    if not result["ran"]:
        tail = str(result.get("output", "")).strip().splitlines()[-3:]
        detail = f" [{' / '.join(tail)}]" if tail else ""
        return f"did not run on the base (import or collection error); add a stub first{detail}"
    if t.characterization:
        return (
            None
            if all(r["outcome"] == "passed" for r in runs)
            else ("characterization test fails on the base")
        )
    if any(r["outcome"] == "passed" for r in runs):
        return "passes on the code before the change: it tests nothing new"
    for r in runs:
        types = r.get("types", [])
        # A stub's NotImplementedError counts in any phase: a fixture that builds data through a
        # stubbed function fails in setup for exactly the right reason.
        if r.get("phase") != "call" and "NotImplementedError" not in types:
            phase, message = r.get("phase"), r.get("message")
            return f"errored in {phase} on the base ({message}), not a real failure"
        if not any(name in RIGHT_REASONS for name in types):
            return f"failed for the wrong reason on the base: {types[:1]} {r.get('message')}"
    return None


def summarize(rows: list[tuple[Selected, str, str]]) -> None:
    lines = ["| Test | Base (must be red) | Change (must be green) |", "|---|---|---|"]
    lines += [f"| `{t.node_id}` | {red} | {green} |" for t, red, green in rows]
    table = "\n".join(lines)
    print(table)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write("## prove-red\n\n" + table + "\n")


def main(cfg: Config) -> int:
    base = resolve_base(cfg.root)
    if base is None:
        print("prove-red: no earlier commit to compare against; nothing to prove yet.")
        return 0
    selected = select(cfg, base, changed_files(cfg.root, base))
    if not selected:
        print(f"prove-red: no new or changed tests since {base[:10]}.")
        return 0
    print(f"prove-red: {len(selected)} new or changed tests since {base[:10]}.")

    # The project may sit below the repository's top level; the worktree holds the whole repo.
    prefix = git("rev-parse", "--show-prefix", cwd=cfg.root).strip()
    sandbox = Path(tempfile.mkdtemp(prefix="prove-red-")) / "base"
    git("worktree", "add", "--detach", "--quiet", str(sandbox), base, cwd=cfg.root)
    try:
        project = sandbox / prefix
        copy_from_change(cfg, project)
        on_base = run(cfg, project, selected)
    finally:
        git("worktree", "remove", "--force", str(sandbox), cwd=cfg.root)
    on_change = run(cfg, cfg.root, selected)

    failures: list[str] = []
    rows: list[tuple[Selected, str, str]] = []
    for t in selected:
        why = verdict_on_base(t, on_base[t.node_id])
        head = on_change[t.node_id]
        runs = head["runs"]
        assert isinstance(runs, list)
        green = bool(head["ran"]) and all(r["outcome"] == "passed" for r in runs)
        rows.append((t, "✅ red" if why is None else f"❌ {why}", "✅" if green else "❌ fails"))
        if why is not None:
            failures.append(f"{t.node_id}: {why}")
        if not green:
            failures.append(f"{t.node_id}: does not pass on the change")
    summarize(rows)
    if failures:
        print("\nprove-red FAILED:\n- " + "\n- ".join(failures), file=sys.stderr)
        return 1
    print(f"\nprove-red passed: {len(selected)} tests fail before the change and pass after it.")
    return 0
