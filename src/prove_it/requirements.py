"""Requirements as a markdown table: | ID | Requirement | Priority |.

Priority is M (must), S (should) or C (could). Must and Should requirements need a passing test.
A requirement whose text contains *Retired* is kept for its ID but needs nothing.
"""

import re
from dataclasses import dataclass
from pathlib import Path

ROW = re.compile(r"^\|\s*(REQ-[A-Z]+-\d+)\s*\|\s*(.*?)\s*\|\s*([MSC])\s*\|", re.M)


@dataclass(frozen=True)
class Requirement:
    id: str
    text: str
    priority: str

    @property
    def retired(self) -> bool:
        return "*Retired*" in self.text

    @property
    def due(self) -> bool:
        return self.priority in "MS" and not self.retired


def parse(text: str) -> dict[str, Requirement]:
    return {m[1]: Requirement(m[1], m[2], m[3]) for m in ROW.finditer(text)}


def load(path: Path) -> dict[str, Requirement]:
    return parse(path.read_text()) if path.is_file() else {}
