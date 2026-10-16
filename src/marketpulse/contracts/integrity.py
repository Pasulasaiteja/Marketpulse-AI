"""Number-integrity check: every figure an explanation shows must come from the plan.

Rules (see CONTRACT.md): ASCII digits, '.' as decimal separator, no thousands
separators inside ``Explanation.text``. Identifiers must contain a letter
(e.g. P002). The UI localizes display separately.
"""

from __future__ import annotations

import re

from marketpulse.contracts.models import Explanation, OptimizerPlan

# Standalone numbers only: digits glued to letters (ids like "P002") are identifiers, not figures.
_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")


def resolve_pointer(doc: object, pointer: str) -> object:
    """Resolve an RFC 6901 JSON Pointer against a JSON-like document."""
    cur = doc
    for raw in pointer.lstrip("/").split("/") if pointer else []:
        key = raw.replace("~1", "/").replace("~0", "~")
        cur = cur[int(key)] if isinstance(cur, list) else cur[key]
    return cur


def check_explanation_numbers(exp: Explanation, plan: OptimizerPlan) -> list[str]:
    """Return a list of problems; empty means the explanation is grounded."""
    doc = plan.model_dump(mode="json")
    problems: list[str] = []
    cited: list[float] = []
    for fig in exp.cited_figures:
        try:
            actual = resolve_pointer(doc, fig.path)
        except (KeyError, IndexError, ValueError):
            problems.append(f"cited path {fig.path} not found in plan")
            continue
        if actual != fig.value:
            problems.append(f"{fig.path}: cited {fig.value!r} but plan has {actual!r}")
        if isinstance(actual, (int, float)):
            cited.append(float(actual))
    for tok in _NUM.findall(exp.text):
        if not any(abs(float(tok) - c) < 0.005 for c in cited):
            problems.append(f"number {tok} in text is not a cited plan figure")
    return problems
