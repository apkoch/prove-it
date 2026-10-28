import argparse
import sys

from prove_it import config, guards, red, trace

COMMANDS = {
    "red": (red.main, "new and changed tests must fail on the code before the change"),
    "guards": (guards.main, "every guard must fire on its canary; the clean tree must pass"),
    "trace": (trace.main, "every Must/Should requirement must have a passing test"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="prove-it", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    args = parser.parse_args(argv)
    return COMMANDS[args.command][0](config.load())


if __name__ == "__main__":
    sys.exit(main())
