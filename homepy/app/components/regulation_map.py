import folium

ZONE_COLORS = {
    "adjusted-target": "#e67e22",
    "speculation-overheated": "#c0392b",
    "non-regulated": "#95a5a6",
}
SEOUL_CENTER = (37.5665, 126.9780)


def build_regulation_map(districts: list[dict]) -> folium.Map:
    """districts: [{name, zone, lat, lon}] -> map with circle markers colored by zone type."""
    m = folium.Map(location=SEOUL_CENTER, zoom_start=10, tiles="OpenStreetMap")
    for d in districts:
        zone = d.get("zone", "non-regulated")
        folium.CircleMarker(
            location=(d["lat"], d["lon"]), radius=14, weight=1,
            color=ZONE_COLORS.get(zone, "#95a5a6"), fill=True, fill_opacity=0.7,
            tooltip=f"{d.get('name', '')} · {zone}").add_to(m)
    return m


def regulation_map(districts: list[dict], height: int = 360) -> None:
    import streamlit as st
    html = build_regulation_map(districts)._repr_html_()  # trusted: generated locally by folium
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:  # older Streamlit
        import streamlit.components.v1 as components
        components.html(html, height=height)
