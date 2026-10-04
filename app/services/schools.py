"""School scope for the Beijing campus support assistant."""

from functools import lru_cache
from pathlib import Path

SCHOOLS_PATH = Path(__file__).resolve().parents[2] / "data" / "beijing_schools.txt"


@lru_cache(maxsize=1)
def beijing_schools() -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in SCHOOLS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
