"""Append-only JSONL lineage catalog."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path("data/catalog/lineage.jsonl")


class LineageTracker:
    def __init__(self, path: Path | str = DEFAULT_PATH) -> None:
        self.path = Path(path)

    def record(self, source: str, stage: str, output: str | Path, quality_report=None,
               input_path: str | Path | None = None, row_count: int | None = None) -> None:
        """Append one record. ``quality_report`` may be a dict, an object with
        ``passed``/``row_count`` attributes, a bool, or None."""
        passed, rows = None, row_count
        if isinstance(quality_report, dict):
            passed = quality_report.get("passed")
            rows = rows if rows is not None else quality_report.get("row_count")
        elif isinstance(quality_report, bool):
            passed = quality_report
        elif quality_report is not None:
            passed = getattr(quality_report, "passed", None)
            rows = rows if rows is not None else getattr(quality_report, "row_count", None)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "stage": stage,
            "input_path": str(input_path) if input_path is not None else None,
            "output_path": str(output),
            "row_count": rows,
            "quality_passed": passed,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
