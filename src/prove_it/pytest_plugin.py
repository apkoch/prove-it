"""Suite-wide rules, active in any project whose pyproject.toml has [tool.prove-it]:

- skip, skipif and xfail markers fail collection, and a test that skips itself at run time fails;
- every test cites the requirements it covers with @pytest.mark.req("REQ-…"), and only IDs that
  exist in the requirements table;
- with PROVE_IT_RESULTS set, each test's requirement tags, outcome and failure types are written
  there as JSON, for `prove-it trace` and `prove-it red`.
"""

import json
import os
import tomllib
from pathlib import Path

import pytest

from prove_it import requirements

BANNED_MARKERS = ("skip", "skipif", "xfail")
ACTIVE = pytest.StashKey[bool]()
RESULTS = pytest.StashKey[dict[str, dict[str, object]]]()


def _active(config: pytest.Config) -> bool:
    pyproject = Path(config.rootpath) / "pyproject.toml"
    if not pyproject.is_file():
        return False
    return "prove-it" in tomllib.loads(pyproject.read_text()).get("tool", {})


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "req(*ids): requirement IDs this test covers")
    config.addinivalue_line(
        "markers",
        "characterization(reason): pins existing behaviour for a refactor; "
        "prove-red requires it to pass on the base instead of failing",
    )
    config.stash[ACTIVE] = _active(config)
    config.stash[RESULTS] = {}


def _requirements_path(config: pytest.Config) -> Path:
    table = tomllib.loads((Path(config.rootpath) / "pyproject.toml").read_text())["tool"]
    return Path(config.rootpath) / table["prove-it"].get("requirements", "requirements.md")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Fail collection on a banned marker, a missing req tag or an unknown requirement ID."""
    if not config.stash[ACTIVE]:
        return
    known = requirements.load(_requirements_path(config))
    problems: list[str] = []
    for item in items:
        for name in BANNED_MARKERS:
            if item.get_closest_marker(name):
                problems.append(f"{item.nodeid}: @pytest.mark.{name} — skip and xfail are banned")
        ids = [str(i) for m in item.iter_markers("req") for i in m.args]
        if not ids:
            problems.append(f"{item.nodeid}: has no @pytest.mark.req(...) tag")
        problems += [f"{item.nodeid}: unknown requirement {i}" for i in ids if i not in known]
    if problems:
        raise pytest.UsageError("prove-it rules broken:\n" + "\n".join(problems))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    report = yield
    if not item.config.stash[ACTIVE]:
        return report
    if call.when == "setup":
        report.user_properties += [("req", i) for m in item.iter_markers("req") for i in m.args]
    if report.skipped:
        report.outcome = "failed"
        report.longrepr = f"{item.nodeid}: skipped at run time — skip is banned"
    row = item.config.stash[RESULTS].setdefault(
        item.nodeid,
        {"reqs": [str(i) for m in item.iter_markers("req") for i in m.args], "outcome": "not run"},
    )
    if report.failed and row["outcome"] != "failed":
        names: list[str] = []
        if call.excinfo is not None:
            value = call.excinfo.value
            group = getattr(value, "exceptions", None)
            for e in group if group else [value]:
                names += [k.__name__ for k in type(e).__mro__]
        row.update(
            outcome="failed",
            phase=call.when,
            types=names,
            message=str(call.excinfo.value)[:300] if call.excinfo else "",
        )
    elif call.when == "call" and row["outcome"] == "not run":
        row["outcome"] = "passed"
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    target = os.environ.get("PROVE_IT_RESULTS")
    if target and session.config.stash[ACTIVE]:
        Path(target).write_text(json.dumps(session.config.stash[RESULTS], indent=1))
