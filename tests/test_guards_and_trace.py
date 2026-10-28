from pathlib import Path

from conftest import prove_it

from prove_it.requirements import parse
from prove_it.trace import coverage


def test_every_example_guard_fires(project: Path):
    done = prove_it(project, "guards", base=None)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "all 8 guards fire" in done.stdout


def test_a_guard_whose_canary_no_longer_breaks_anything_fails(project: Path):
    """The canary edits a test file the guard doesn't run, so the guard passes: not proven."""
    guards = project / "guards" / "guards.toml"
    guards.write_text(
        guards.read_text().replace(
            'paths = ["tests/test_canary_skip.py"]', 'paths = ["tests/test_parse.py"]'
        )
    )
    done = prove_it(project, "guards", base=None)
    assert done.returncode == 1
    assert "skip-marker-ban: DID NOT FIRE" in done.stdout


def test_orphan_and_missing_canaries_fail(project: Path):
    canaries = project / "guards" / "canaries"
    (canaries / "skip-marker.patch").rename(canaries / "orphan.patch")
    done = prove_it(project, "guards", base=None)
    assert done.returncode == 1
    assert "skip-marker-ban: canary skip-marker.patch is missing" in done.stderr
    assert "canary orphan.patch belongs to no guard" in done.stderr


def test_requirements_table():
    reqs = parse(
        "| ID | Text | Pri |\n|---|---|---|\n"
        "| REQ-A-1 | must | M |\n| REQ-A-2 | could | C |\n| REQ-A-3 | *Retired*: old | M |\n"
    )
    assert [r.id for r in reqs.values() if r.due] == ["REQ-A-1"]


def test_coverage_counts_only_passing_tests():
    reqs = parse("| REQ-A-1 | one | M |\n| REQ-A-2 | two | S |\n| REQ-A-3 | three | C |\n")
    results = {
        "t1": {"reqs": ["REQ-A-1"], "outcome": "passed"},
        "t2": {"reqs": ["REQ-A-2"], "outcome": "failed"},
    }
    rows, problems = coverage(reqs, results)
    assert dict((r.id, s) for r, s in rows) == {
        "REQ-A-1": "1 passing",
        "REQ-A-2": "FAILING",
        "REQ-A-3": "no test",
    }
    assert problems == ["REQ-A-2 (priority S): FAILING"]


def test_trace_on_the_example(project: Path):
    done = prove_it(project, "trace", base=None)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (project / ".prove-it" / "traceability.md").is_file()
