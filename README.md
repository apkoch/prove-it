# prove-it

**Tests that have to prove they can fail. Guards that have to prove they fire. Requirements that
have to prove they're tested.**

A small toolkit for pytest projects, built for codebases where AI coding agents write much of the
code *and* the tests.

[![ci](https://github.com/apkoch/prove-it/actions/workflows/ci.yml/badge.svg)](https://github.com/apkoch/prove-it/actions/workflows/ci.yml)

---

## Why

A green CI run tells you the checks passed. It doesn't tell you the checks *could have failed*.
When an agent writes both the code and its tests, these are the failures you actually see:

| Failure | What it looks like | Caught by |
|---|---|---|
| A test that can't fail | Tautology, wrong assertion, mocked-out subject | `prove-it red` |
| A test "fixed" by weakening it | The expected value changed to match the bug | `prove-it red` + protected oracles |
| A guard that quietly stopped working | A lint rule or CI check disabled by a config change | `prove-it guards` |
| Coverage that shrinks | Tests skipped, xfailed, or deleted | the pytest plugin + `prove-it trace` |
| Work nobody asked for, or that went missing | Tests that cite no requirement; requirements with no test | `prove-it trace` |

Line coverage catches none of these. Each check below fails the build when one of them happens.

## The three checks

### `prove-it red`: every new test must fail on the old code

It finds every test function added or changed since the base commit (comparing ASTs, decorators
included) and checks out the base in a temporary git worktree. It overlays your *new* tests onto
the *old* code and runs them there. Each one must fail **for the right reason**: an assertion,
`pytest.fail`, or a stub's `NotImplementedError`. An import or fixture error doesn't count; it
means "add a stub first". The tests must then pass on your change.

```text
$ prove-it red
prove-red: 1 new or changed tests since 87ed362d88.
| Test | Base (must be red) | Change (must be green) |
|---|---|---|
| `tests/test_split.py::test_one_payer_pays_everything` | ❌ passes on the code before the change: it tests nothing new | ✅ |

prove-red FAILED:
- tests/test_split.py::test_one_payer_pays_everything: passes on the code before the change: it tests nothing new
```

Tests marked `@pytest.mark.characterization(reason=...)` are the exception: they pin existing
behaviour before a refactor, so they must *pass* on the base.

### `prove-it guards`: every guard must fire on a deliberate violation

Every rule you enforce (a lint ban, an invariant test, a CI policy) gets a **canary**: a patch
that breaks exactly that rule. For each guard, `prove-it guards` copies the tree to a sandbox,
applies the canary, runs the guard's command, and requires it to fail *with the expected
message*. It also checks:

- every guard's command passes on the clean tree;
- every guard has a canary, and every canary belongs to a guard;
- a canary that no longer applies fails the run, so canaries can't drift out of date unnoticed.

```text
$ prove-it guards
clean tree · prove-it red: passes
clean tree · prove-it trace: passes
clean tree · python -m pytest: passes
float-ban (REQ-NFR-01): fires
shares-sum-to-total (REQ-SPL-01): fires
skip-marker-ban: fires
runtime-skip-ban: fires
every-test-cites-a-requirement: fires
requirements-must-exist: fires
prove-red: fires
trace-coverage: fires

prove-guards passed: all 8 guards fire, and the clean tree passes.
```

The checks also guard each other. `prove-red` and `trace` are themselves guards with canaries,
so if one of them breaks, `prove-guards` fails.

### `prove-it trace`: every requirement must have a passing test

Requirements live in a markdown table, and tests cite them:

```python
@pytest.mark.req("REQ-SPL-01")
def test_shares_sum_to_total(): ...
```

The bundled **pytest plugin** fails collection when a test cites no requirement or an ID that
doesn't exist, bans `skip`/`skipif`/`xfail` markers, and turns a runtime `pytest.skip()` into a
failure. `prove-it trace` runs the suite and fails if any **M**ust or **S**hould requirement has
no passing test. It writes a traceability matrix to `.prove-it/traceability.md`.

## Quick start

```bash
uv add --dev "prove-it @ git+https://github.com/apkoch/prove-it"
```

Add a `[tool.prove-it]` table to your `pyproject.toml`. Its presence is also what turns the
pytest plugin on:

```toml
[tool.prove-it]
requirements = "requirements.md"           # | REQ-XXX-01 | text | M/S/C |
test_command = ["python", "-m", "pytest"]
tests = ["tests"]                          # where prove-red looks for changed tests
from_change = ["pyproject.toml", "requirements.md"]  # taken from the change in the base checkout
guards = "guards/guards.toml"
canaries = "guards/canaries"
```

Add a guard and its canary:

```toml
# guards/guards.toml
[[guard]]
name = "float-ban"
command = "python -m pytest"          # must pass on the clean tree
paths = ["tests/test_rules.py"]       # appended for the canary run only
canary = "float-in-allocator.patch"   # git diff that introduces a float
expect = ["float is banned in money code"]
```

The quickest way to write a canary is to break the rule by hand, then save the diff with
`git diff > guards/canaries/<name>.patch` and revert.

Then add all three to CI:

```bash
prove-it trace && prove-it guards && prove-it red
```

## The example

[`example/`](example/) is a tiny bill-splitting library: integer cents, the largest-remainder
method, and Hypothesis property tests. It's there to show every check working on a real codebase
and as a template to copy. Its eight guards cover money rules (no floats, shares always sum to
the total), test-suite rules (no skips, every test cites a known requirement), and the process
checks themselves.

```bash
just example   # trace, guards and red on the example project
just check     # lint + prove-it's own tests + the example
```

## Design notes and limits

- **Sandboxes, not mocks.** Every guard runs in its own copy of the working tree, in parallel. If
  your commands share external state (a database or a port), give each sandbox its own. The
  original project gave every test worker its own database.
- **Import from the checkout.** `prove-red` puts the base checkout first on `PYTHONPATH`. If your
  package is installed in editable mode from the working tree, use pytest's `pythonpath` setting
  instead, or the "base" run will import the new code.
- **Monorepos work.** Paths resolve relative to the directory holding `[tool.prove-it]`, wherever
  it sits in the repository.
- **Expected messages are precise on purpose.** A guard that fails for some *other* reason hasn't
  proven anything. If a dependency changes its error text, update `expect`.
- **pytest only.** The project this came from also ran `prove-red` over Playwright end-to-end
  tests, comparing titles and requiring an `expect()` failure on a loaded page. That part
  isn't included here.

## Where this came from

I built these checks for a fintech MVP that I developed mostly by directing AI coding agents in
parallel, one per module. There they enforced 34 guards across a FastAPI/PostgreSQL backend and
a Next.js client. This repo is a generalized version of that tooling, configurable for any pytest
project and with a new example. It contains none of that product's business logic.

## License

MIT
