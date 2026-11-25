"""ReportGenerator: renders an InvestmentVerdict (+ optional debate) to HTML/PDF."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATE_NAME = "verdict_report.html"


def radar_svg(factors: list[Any], size: int = 360) -> Markup:
    """Build an inline SVG radar chart from factor scores (normalized 0-100)."""
    n = len(factors)
    if n < 3:
        return Markup("")
    c, r = size / 2, size / 2 - 50

    def pt(i: int, frac: float) -> tuple[float, float]:
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return c + r * frac * math.cos(ang), c + r * frac * math.sin(ang)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
             f'viewBox="0 0 {size} {size}">']
    for level in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, level) for i in range(n)))
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#cbd5e1" stroke-width="1"/>')
    for i in range(n):
        x, y = pt(i, 1.0)
        parts.append(f'<line x1="{c}" y1="{c}" x2="{x:.1f}" y2="{y:.1f}" stroke="#e2e8f0"/>')
    data = " ".join(
        f"{x:.1f},{y:.1f}"
        for x, y in (pt(i, max(0.0, min(100.0, f.normalized)) / 100) for i, f in enumerate(factors))
    )
    parts.append(f'<polygon points="{data}" fill="rgba(37,99,235,0.3)" stroke="#2563eb" stroke-width="2"/>')
    for i, f in enumerate(factors):
        x, y = pt(i, 1.12)
        name = str(f.name).replace("&", "&amp;").replace("<", "&lt;")
        parts.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="8" text-anchor="middle">{name}</text>')
    parts.append("</svg>")
    return Markup("".join(parts))


class ReportGenerator:
    def __init__(self, template_dir: str | Path = DEFAULT_TEMPLATE_DIR) -> None:
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(["html"]),
        )

    def generate_html(
        self,
        verdict: Any,
        debate: Any | None = None,
        score: Any | None = None,
        scenarios: Any | None = None,
        complex_id: str | None = None,
    ) -> str:
        """Render the report. ``score`` (InvestmentScore) and ``scenarios``
        (ScenarioResult) are optional enrichments for sections 1-3."""
        factors = list(score.factors) if score is not None else []
        ctx = {
            "verdict": verdict,
            "debate": debate,
            "score": score,
            "factors": sorted(factors, key=lambda f: f.weight, reverse=True),
            "radar": radar_svg(factors),
            "scenarios": list(scenarios.scenarios) if scenarios is not None else [],
            "sensitivity": list(scenarios.sensitivity) if scenarios is not None else [],
            "complex_id": complex_id or getattr(score, "complex_id", None)
            or getattr(scenarios, "complex_id", None) or "-",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "computed_at": getattr(score, "computed_at", None),
        }
        return self.env.get_template(TEMPLATE_NAME).render(**ctx)

    def generate_pdf(self, verdict: Any, debate: Any | None = None, **kwargs: Any) -> bytes:
        from weasyprint import HTML

        return HTML(string=self.generate_html(verdict, debate, **kwargs)).write_pdf()
