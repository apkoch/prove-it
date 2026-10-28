# `just check` is what CI runs.

set shell := ["bash", "-euo", "pipefail", "-c"]

# The example project has no environment of its own; it runs in this repository's.
example := "uv run --locked --project " + justfile_directory() + " --directory example"

check: lint test example

lint:
    uv run --locked ruff check .
    uv run --locked ruff format --check .

# prove-it's own tests: unit tests, plus end-to-end runs against copies of the example project.
test:
    uv run --locked pytest

# Run all three checks on the example project.
example:
    {{example}} prove-it trace
    {{example}} prove-it guards
    {{example}} prove-it red
