"""CONTRACT.md is shared with the team: it must be current and its examples must be valid."""

import json
import re
from pathlib import Path

from marketpulse.contracts.models import CONTRACT_MODELS
from marketpulse.contracts.validate import validate_payload
from scripts.build_contract_md import OUT, render

ROOT = Path(__file__).resolve().parents[1]


def test_contract_md_is_up_to_date():
    assert OUT.read_text(encoding="utf-8") == render(), (
        "CONTRACT.md is stale: run python scripts/build_contract_md.py"
    )


def test_every_example_in_contract_md_validates():
    text = (ROOT / "CONTRACT.md").read_text(encoding="utf-8")
    # each example follows its "### 4.x Name (" heading
    blocks = re.findall(r"### 4\.\d+ (\w+) \(.*?```json\n(.*?)\n```", text, flags=re.S)
    names = {n for n, _ in blocks}
    assert names == set(CONTRACT_MODELS), "every contract needs a documented example"
    for name, body in blocks:
        validate_payload(name, json.loads(body))
