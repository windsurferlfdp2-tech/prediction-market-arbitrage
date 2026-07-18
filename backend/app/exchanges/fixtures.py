import json
from pathlib import Path
from typing import Any


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURE_ROOT / name).open() as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return data
