from homepy.app.components.knowledge_graph import build_graph_html


def test_build_graph_html_contains_nodes_and_relations():
    html = build_graph_html({
        "nodes": [{"id": "C001", "type": "complex", "label": "단지A", "attributes": {}},
                  {"id": "D1", "type": "district", "label": "강남구", "attributes": {}}],
        "edges": [{"source": "C001", "target": "D1", "relation": "located_in"}]})
    assert "located_in" in html and "C001" in html and "D1" in html
