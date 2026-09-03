from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = ROOT / "evals" / "cases.jsonl"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{lineno}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{lineno}")
        rows.append(value)
    return rows


def _offline_outputs(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outputs = []
    for case in cases:
        required = list(case.get("required_fields") or [])
        evidence_keys = list(case.get("expected_evidence_keys") or [])
        result: dict[str, Any] = {"evidence_keys": evidence_keys}
        for field in required:
            if field in result:
                continue
            if field == "summary":
                result[field] = "Offline fixture grounded only in supplied evidence."
            elif field == "answer":
                result[field] = "Offline fixture answer grounded only in supplied evidence."
            elif field == "priority":
                result[field] = "medium"
            elif field == "confidence":
                result[field] = 0.8
            elif field == "ranking":
                result[field] = ["creator_a", "creator_b"]
            else:
                result[field] = "fixture"
        outputs.append({"id": case["id"], "result": result})
    return outputs


def evaluate(cases_path: str | Path = DEFAULT_CASES, outputs_path: str | Path | None = None) -> dict[str, Any]:
    cases = _read_jsonl(Path(cases_path))
    outputs = _read_jsonl(Path(outputs_path)) if outputs_path else _offline_outputs(cases)
    by_id = {str(item.get("id")): item for item in outputs}
    details = []
    structured_ok = 0
    evidence_coverage_values = []
    unsupported_total = 0

    for case in cases:
        cid = str(case.get("id"))
        output = by_id.get(cid) or {}
        result = output.get("result") if isinstance(output.get("result"), dict) else {}
        required = list(case.get("required_fields") or [])
        missing_fields = [field for field in required if field not in result]
        is_structured = not missing_fields
        structured_ok += int(is_structured)

        evidence = set(str(key) for key in (case.get("evidence") or {}))
        used = set(str(key) for key in (result.get("evidence_keys") or []))
        expected = set(str(key) for key in (case.get("expected_evidence_keys") or []))
        covered = len(used & expected)
        coverage = covered / len(expected) if expected else 1.0
        evidence_coverage_values.append(coverage)
        unsupported = sorted(used - evidence)
        unsupported_total += len(unsupported)
        details.append(
            {
                "id": cid,
                "structured": is_structured,
                "missing_fields": missing_fields,
                "evidence_coverage": round(coverage, 4),
                "unsupported_evidence_keys": unsupported,
            }
        )

    n = max(1, len(cases))
    metrics = {
        "cases": len(cases),
        "structured_output_rate": round(structured_ok / n, 4),
        "mean_evidence_coverage": round(sum(evidence_coverage_values) / n, 4),
        "unsupported_evidence_key_count": unsupported_total,
    }
    passed = (
        metrics["structured_output_rate"] == 1.0
        and metrics["mean_evidence_coverage"] == 1.0
        and unsupported_total == 0
    )
    return {
        "ok": passed,
        "mode": "offline_fixture" if outputs_path is None else "provided_outputs",
        "metrics": metrics,
        "details": details,
        "warning": "Offline fixture scores validate the evaluator contract only; they are not model-quality claims.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate structured AI grounding outputs")
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--outputs", default="")
    args = parser.parse_args()
    result = evaluate(args.cases, args.outputs or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
