"""버전이 붙은 탐지 설정 (config/anomaly.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    version: str
    window_months: int = 6
    min_count: int = 3
    mad_k: float = 3.0
    flat_pct: float = 0.15
    exclude_direct: bool = True
    unsettled_months: int = 2
    cancelled_codes: tuple[str, ...] = ("O",)
    direct_codes: tuple[str, ...] = ("직거래",)
    corporate_codes: tuple[str, ...] = ("법인",)
    success_codes: tuple[str, ...] = ("00", "000")
    page_size: int = 1000

    def as_dict(self) -> dict:
        return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(self).items()}


# TOML 섹션 → {TOML 키: Settings 필드}
_SECTIONS: dict[str, dict[str, str]] = {
    "thresholds": {
        "window_months": "window_months",
        "min_count": "min_count",
        "mad_k": "mad_k",
        "flat_pct": "flat_pct",
        "exclude_direct": "exclude_direct",
        "unsettled_months": "unsettled_months",
    },
    "codes": {
        "cancelled": "cancelled_codes",
        "direct": "direct_codes",
        "corporate": "corporate_codes",
    },
    "api": {
        "success_codes": "success_codes",
        "page_size": "page_size",
    },
}


def load_settings(path: Path) -> Settings:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    unknown_top = set(data) - set(_SECTIONS) - {"version"}
    if unknown_top:
        raise ValueError(f"알 수 없는 설정 항목: {sorted(unknown_top)}")
    if "version" not in data:
        raise ValueError("설정에 version이 없다")

    fields: dict[str, object] = {"version": str(data["version"])}
    for section, mapping in _SECTIONS.items():
        values = data.get(section, {})
        unknown = set(values) - set(mapping)
        if unknown:
            raise ValueError(f"[{section}]의 알 수 없는 키: {sorted(unknown)}")
        for key, value in values.items():
            fields[mapping[key]] = tuple(value) if isinstance(value, list) else value
    return Settings(**fields)
