"""Pyvis knowledge-graph builder (pure; returns HTML string)."""
from __future__ import annotations

from pyvis.network import Network

TYPE_COLORS = {
    "region": "#8e44ad", "district": "#2980b9", "dong": "#16a085",
    "complex": "#e67e22", "indicator": "#c0392b", "policy": "#7f8c8d",
}
DEFAULT_COLOR = "#95a5a6"


def build_graph_html(graph: dict, height: str = "600px") -> str:
    net = Network(height=height, width="100%", directed=True, cdn_resources="in_line")
    ids = set()
    for n in graph.get("nodes", []):
        ids.add(n["id"])
        net.add_node(n["id"], label=n.get("label") or n["id"],
                     color=TYPE_COLORS.get(n.get("type"), DEFAULT_COLOR),
                     title=f"{n.get('type', '')}: {n.get('attributes', {})}")
    for e in graph.get("edges", []):
        if e["source"] in ids and e["target"] in ids:
            net.add_edge(e["source"], e["target"], label=e.get("relation", ""))
    return net.generate_html()
