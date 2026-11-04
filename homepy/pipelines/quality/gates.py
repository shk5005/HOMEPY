"""Quality gate for Raw -> Cleaned (spec Section 4.6)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

_KIND_CHECKS = {
    "datetime": pd.api.types.is_datetime64_any_dtype,
    "float": pd.api.types.is_numeric_dtype,
    "int": pd.api.types.is_numeric_dtype,
    "str": lambda s: pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s),
}


@dataclass
class QualityReport:
    passed: bool
    null_ratio: float = 0.0
    duplicate_ratio: float = 0.0
    schema_ok: bool = True
    failures: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


class QualityGate:
    """Enforces null ratio, duplicate ratio and schema match thresholds."""

    def __init__(
        self,
        null_ratio_max: float = 0.05,
        duplicate_ratio_max: float = 0.01,
        schema_match: bool = True,
    ):
        self.null_ratio_max = null_ratio_max
        self.duplicate_ratio_max = duplicate_ratio_max
        self.schema_match = schema_match

    def check(
        self,
        df: pd.DataFrame,
        expected_schema: dict,
        duplicate_subset: list[str] | None = None,
    ) -> QualityReport:
        """``expected_schema`` maps column -> kind (datetime/float/int/str)."""
        failures: list[str] = []
        details: dict = {}
        n = len(df)

        null_by_col = {c: float(df[c].isna().mean()) for c in df.columns} if n else {}
        # Overall ratio (null cells / all cells): optional columns must not block the pipeline.
        total_cells = n * len(df.columns)
        null_ratio = float(df.isna().sum().sum() / total_cells) if total_cells else 0.0
        details["null_ratio_by_column"] = null_by_col
        if null_ratio > self.null_ratio_max:
            bad = sorted(c for c, r in null_by_col.items() if r > 0)
            failures.append(f"null ratio {null_ratio:.3f} > {self.null_ratio_max} (columns with nulls: {bad})")

        subset = [c for c in (duplicate_subset or []) if c in df.columns] or None
        dup_ratio = float(df.duplicated(subset=subset).mean()) if n else 0.0
        if dup_ratio > self.duplicate_ratio_max:
            failures.append(f"duplicate ratio {dup_ratio:.3f} > {self.duplicate_ratio_max}")

        schema_ok = True
        if self.schema_match:
            missing = [c for c in expected_schema if c not in df.columns]
            wrong = [
                c for c, kind in expected_schema.items()
                if c in df.columns and c not in missing
                and not _KIND_CHECKS.get(kind, lambda s: True)(df[c])
                and not df[c].isna().all()
            ]
            details["missing_columns"] = missing
            details["wrong_type_columns"] = wrong
            if missing or wrong:
                schema_ok = False
                failures.append(f"schema mismatch: missing={missing} wrong_type={wrong}")

        return QualityReport(
            passed=not failures,
            null_ratio=null_ratio,
            duplicate_ratio=dup_ratio,
            schema_ok=schema_ok,
            failures=failures,
            details=details,
        )
