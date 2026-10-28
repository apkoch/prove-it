from pathlib import Path

from conftest import git, prove_it

from prove_it.red import Selected, python_tests, verdict_on_base

TIP_TEST = """

@pytest.mark.req("REQ-SPL-05")
def test_tip_is_added_to_the_total():
    from splitter.money import with_tip

    assert with_tip(10000, 15) == 11500
"""

TIP_STUB = """

def with_tip(total: int, percent: int) -> int:
    raise NotImplementedError
"""

TIP_CODE = """

def with_tip(total: int, percent: int) -> int:
    return total + total * percent // 100
"""


def append(path: Path, text: str) -> None:
    path.write_text(path.read_text() + text)


def test_change_detection_ignores_untouched_tests_and_sees_decorator_changes():
    before = "@pytest.mark.req('A')\ndef test_a():\n    assert 1\n\ndef test_b():\n    assert 2\n"
    after = "@pytest.mark.req('B')\ndef test_a():\n    assert 1\n\ndef test_b():\n    assert 2\n"
    old, new = python_tests(before), python_tests(after)
    assert old["test_a"][0] != new["test_a"][0]
    assert old["test_b"][0] == new["test_b"][0]


def test_verdicts():
    t = Selected("tests/test_x.py", "test_x")
    run = {"ran": True, "output": ""}
    ok = {"outcome": "failed", "phase": "call", "types": ["AssertionError"], "message": ""}
    assert verdict_on_base(t, {**run, "runs": [ok]}) is None
    passed = {"outcome": "passed"}
    assert "tests nothing new" in verdict_on_base(t, {**run, "runs": [passed]})
    wrong = {"outcome": "failed", "phase": "call", "types": ["TypeError"], "message": "x"}
    assert "wrong reason" in verdict_on_base(t, {**run, "runs": [wrong]})
    setup = {"outcome": "failed", "phase": "setup", "types": ["KeyError"], "message": "x"}
    assert "errored in setup" in verdict_on_base(t, {**run, "runs": [setup]})
    stub = {"outcome": "failed", "phase": "setup", "types": ["NotImplementedError"]}
    assert verdict_on_base(t, {**run, "runs": [stub]}) is None
    assert "did not run" in verdict_on_base(t, {"ran": False, "runs": [], "output": ""})
    pinned = Selected("tests/test_x.py", "test_x", characterization=True)
    assert verdict_on_base(pinned, {**run, "runs": [passed]}) is None


def test_test_first_change_with_a_stub_passes(project: Path):
    money = project / "splitter" / "money.py"
    append(money, TIP_STUB)
    git(project, "commit", "-qam", "stub")
    money.write_text(money.read_text().replace(TIP_STUB, TIP_CODE))
    append(project / "tests" / "test_split.py", TIP_TEST)
    done = prove_it(project, "red")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 tests fail before the change and pass after it" in done.stdout


def test_test_for_code_the_base_lacks_must_add_a_stub_first(project: Path):
    append(project / "splitter" / "money.py", TIP_CODE)
    append(project / "tests" / "test_split.py", TIP_TEST)
    done = prove_it(project, "red")
    assert done.returncode == 1
    assert "failed for the wrong reason on the base: ['ImportError']" in done.stderr


def test_a_test_that_already_passes_proves_nothing(project: Path):
    append(
        project / "tests" / "test_split.py",
        '\n\n@pytest.mark.req("REQ-SPL-01")\ndef test_zero():\n    assert split(0, [1]) == [0]\n',
    )
    done = prove_it(project, "red")
    assert done.returncode == 1
    assert "test_zero: passes on the code before the change" in done.stderr


def test_nothing_changed(project: Path):
    done = prove_it(project, "red")
    assert done.returncode == 0
    assert "no new or changed tests" in done.stdout


def test_project_below_the_repository_root(project: Path):
    """In a monorepo, paths and the base checkout resolve relative to the project."""
    nested = project.parent / "mono"
    nested.mkdir()
    project.rename(nested / "pkg")
    (nested / "pkg" / ".git").rename(nested / ".git")
    git(nested, "add", "-A")
    git(nested, "commit", "-qm", "move into pkg/")
    append(
        nested / "pkg" / "tests" / "test_split.py",
        '\n\n@pytest.mark.req("REQ-SPL-01")\ndef test_zero():\n    assert split(0, [1]) == [0]\n',
    )
    done = prove_it(nested / "pkg", "red")
    assert "test_zero: passes on the code before the change" in done.stderr
