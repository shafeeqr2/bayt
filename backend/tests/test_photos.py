"""The photo reader without the network: a fake backend stands in for the vision model.

Covers the prompt (room list and listing facts), the image part in the request,
the clean-up of the model's answer (room names, whitespace), and the OpenAI-style
body with an image.
"""

import json
from types import SimpleNamespace

import httpx

from app.photos import reader as m
from app.zoning import answer as llm


def listing(**over):
    base = dict(
        id="L1",
        building_type="House",
        stories="2",
        bedrooms_total=4,
        bathrooms=3,
        parking_type="Attached Garage, Garage",
        rooms=[
            {"type": "Living room", "level": "Main level", "dimension": "5 m x 4 m"},
            {"type": "Kitchen", "level": "Main level", "dimension": "4 m x 3.5 m"},
            {"type": "Primary Bedroom", "level": "Second level", "dimension": "4.5 m x 4 m"},
        ],
        photos=[{"high": "https://cdn/h1.jpg", "medium": "https://cdn/m1.jpg", "low": "https://cdn/l1.jpg"}],
    )
    base.update(over)
    return SimpleNamespace(**base)


def facts(**over):
    base = dict(
        kind="interior", title=" Kitchen. ", caption="A galley kitchen with  a window over the sink and tile floor.",
        level="main", room="kitchen", windows=1, window_wall="far", exterior_doors=0, stairs="none", open_to=["dining room"],
        storeys=None, garage="unknown",
    )
    base.update(over)
    return m.PhotoFacts(**base)


def test_prompt_lists_the_rooms_and_the_listing_facts():
    text = m.user_prompt(listing(), 0, 1)
    assert "Storeys: 2" in text and "Bedrooms: 4" in text and "Parking: Attached Garage, Garage" in text
    assert "- Kitchen (Main level, 4 m x 3.5 m)" in text
    assert "photo 1 of 1" in text


def test_clean_matches_room_names_case_insensitively_and_trims_text():
    out = m.clean(facts(), listing())
    assert out.room == "Kitchen"
    assert out.title == "Kitchen"
    assert out.caption == "A galley kitchen with a window over the sink and tile floor."


def test_clean_drops_a_room_that_is_not_listed_but_keeps_a_partial_match():
    assert m.clean(facts(room="Garage"), listing()).room is None
    assert m.clean(facts(room="Primary"), listing()).room == "Primary Bedroom"


def test_clean_keeps_exterior_facts_on_exterior_photos_only():
    out = m.clean(facts(kind="exterior_front", room="Kitchen", level="main", storeys=2, garage="left", open_to=["none"]), listing())
    assert out.room is None and out.level is None and out.storeys == 2 and out.garage == "left" and out.open_to == []
    out = m.clean(facts(kind="interior", storeys=1, garage="left", windows=1, window_wall="none"), listing())
    assert out.storeys is None and out.garage == "unknown" and out.window_wall == "unknown"


def test_openai_backend_sends_the_photo_as_an_image_part():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": facts().model_dump_json()}}]})

    backend = llm.OpenAIBackend("sk-or-v1-x", "https://openrouter.ai/api/v1", "nvidia/nemotron-3.5-super-vl", "openrouter", transport=httpx.MockTransport(handler), json_mode="object")
    out = backend.structured(system="s", user="u", schema=m.PhotoFacts, effort="low", max_tokens=300, images=["https://cdn/h1.jpg"])
    assert isinstance(out, m.PhotoFacts) and out.kind == "interior"
    user = seen["body"]["messages"][1]
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "text", "text": "u"}
    assert user["content"][1] == {"type": "image_url", "image_url": {"url": "https://cdn/h1.jpg"}}
    # Plain JSON mode: the schema travels in the system prompt, not in response_format.
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert '"PhotoFacts"' in seen["body"]["messages"][0]["content"] or "window_wall" in seen["body"]["messages"][0]["content"]


def test_object_mode_still_rejects_a_wrong_shape():
    backend = llm.OpenAIBackend("sk-or-v1-x", "https://openrouter.ai/api/v1", "x", "openrouter", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{\"kind\": \"interior\"}"}}]})
    ), json_mode="object")
    import pytest
    with pytest.raises(llm.ModelUnavailable, match="does not fit"):
        backend.structured(system="s", user="u", schema=m.PhotoFacts, effort="low", max_tokens=300)


def test_openai_backend_without_images_keeps_the_plain_string():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": facts().model_dump_json()}}]})

    backend = llm.OpenAIBackend("sk-or-v1-x", "https://openrouter.ai/api/v1", "x", "openrouter", transport=httpx.MockTransport(handler))
    backend.structured(system="s", user="u", schema=m.PhotoFacts, effort="low", max_tokens=300)
    assert seen["body"]["messages"][1] == {"role": "user", "content": "u"}


def test_default_vision_model_follows_the_provider(monkeypatch):
    monkeypatch.setattr(m.settings, "photo_model", "")
    monkeypatch.setattr(m.settings, "llm_api_key", "sk-or-v1-x")
    assert m.model_name() == "nvidia/nemotron-3.5-super-vl"
    monkeypatch.setattr(m.settings, "llm_api_key", "sk-ant-x")
    assert m.model_name() == "claude-opus-5-5"
    monkeypatch.setattr(m.settings, "photo_model", "some/other-vl")
    assert m.model_name() == "some/other-vl"
    monkeypatch.setattr(m.settings, "llm_api_key", None)
    monkeypatch.setattr(m.settings, "photo_model", "")
    assert m.model_name() == ""


def test_photo_url_prefers_the_asked_size_then_falls_back():
    p = {"high": "h", "medium": "m", "low": "l"}
    assert m.photo_url(p) == "h" and m.photo_url(p, "medium") == "m"
    assert m.photo_url({"low": "l"}) == "l"


def test_furniture_words_finds_what_leaves_with_the_seller():
    # Appliances come with the house and are not furniture.
    assert m.furniture_words("A kitchen with white cabinets, a stainless refrigerator, a stove, and a dishwasher.") == []
    assert m.furniture_words("Hardwood floors, a double window, and a closet.") == []
    assert m.furniture_words("A table and chairs under a pendant light.") == ["table", "chairs", "pendant light"]


def test_clean_uses_the_level_when_two_listed_rooms_share_a_name():
    two_kitchens = listing(rooms=[
        {"type": "Kitchen", "level": "Main level", "dimension": "4 m x 3.5 m"},
        {"type": "Kitchen", "level": "Lower level", "dimension": "3 m x 2.5 m"},
    ])
    assert m.clean(facts(room="Kitchen", level="basement"), two_kitchens).room == "Kitchen"
    assert m.clean(facts(room="Kitchen", level="main"), two_kitchens).room == "Kitchen"
    assert m.clean(facts(room="Basement kitchen", level="basement"), two_kitchens).room == "Kitchen"
    assert m.clean(facts(room="Basement gym", level="basement"), two_kitchens).room is None


class FakeVision:
    """A Backend that answers from a queue and records each prompt."""

    model = "fake-vl"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


class FakeSession:
    """Holds the added rows and hands them back on the next query, like a committed table."""

    def __init__(self):
        self.added = []
        self.committed = False

    def scalars(self, stmt):
        return SimpleNamespace(all=lambda: list(self.added))

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.committed = True


def test_read_retries_once_when_the_caption_names_furniture():
    first = facts(caption="A kitchen with a wood table and a window over the sink.")
    second = facts(caption="A kitchen with white cabinets and a window over the sink.")
    client = FakeVision(first, second)
    session = FakeSession()
    out = m.read_listing_photos(session, listing(), client)
    assert len(client.calls) == 2
    assert "table" in client.calls[1]["user"]
    assert client.calls[0]["images"] == ["https://cdn/h1.jpg"]
    assert out.read == 1 and out.photos[0].facts.caption == second.caption
    assert session.committed and session.added[0].model == "fake-vl" and session.added[0].prompt_version == m.PROMPT_VERSION


def test_read_keeps_the_first_answer_when_the_retry_is_no_better():
    first = facts(caption="A kitchen with a wood table.")
    client = FakeVision(first, facts(caption="A kitchen with a table and chairs."))
    out = m.read_listing_photos(FakeSession(), listing(), client)
    assert out.photos[0].facts.caption == first.caption
