"""The GIS client's host fallback: a layer whose primary host is down is served by its alternate."""

import httpx
import pytest

from app.lot import toronto
from app.lot.toronto import FALLBACK_LAYERS, LAYERS, GISError, TorontoGIS

ENVELOPE = "-79.4008,43.6612,-79.3992,43.6628"
STREET = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[-79.399, 43.6608], [-79.3993, 43.6617]]},
            "properties": {"CENTRELINE_ID": 1, "LINEAR_NAME_FULL": "Huron St", "FEATURE_CODE_DESC": "Local"},
        }
    ],
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(toronto.time, "sleep", lambda s: None)


def gis_with(handler) -> TorontoGIS:
    return TorontoGIS(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_centreline_uses_mirror_first():
    hosts = []

    def handler(request):
        hosts.append(str(request.url))
        return httpx.Response(200, json=STREET)

    feats = gis_with(handler)._query("centreline", geometry=ENVELOPE, geometry_type="esriGeometryEnvelope")
    assert [f.properties["LINEAR_NAME_FULL"] for f in feats] == ["Huron St"]
    assert hosts == [f"{LAYERS['centreline']}/query"]


def test_centreline_falls_back_when_mirror_times_out():
    hosts = []

    def handler(request):
        hosts.append(str(request.url))
        if request.url.host == "services3.arcgis.com":
            raise httpx.ReadTimeout("The read operation timed out", request=request)
        return httpx.Response(200, json=STREET)

    feats = gis_with(handler)._query("centreline", geometry=ENVELOPE, geometry_type="esriGeometryEnvelope")
    assert len(feats) == 1
    primary, fallback = f"{LAYERS['centreline']}/query", f"{FALLBACK_LAYERS['centreline'][0]}/query"
    assert hosts == [primary] * toronto.RETRIES + [fallback]


def test_error_when_every_host_fails():
    def handler(request):
        return httpx.Response(200, json={"error": {"code": 503, "message": "Wait timeout for the request exceeded."}})

    with pytest.raises(GISError, match="centreline"):
        gis_with(handler)._query("centreline", geometry=ENVELOPE, geometry_type="esriGeometryEnvelope")


def test_layers_without_fallback_fail_after_retries():
    calls = []

    def handler(request):
        calls.append(request.url.host)
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(GISError, match="parcels"):
        gis_with(handler)._query("parcels", geometry="-79.4,43.66", geometry_type="esriGeometryPoint")
    assert calls == ["gis.toronto.ca"] * toronto.RETRIES
