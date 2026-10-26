"""The photo reader without the network: a fake backend stands in for the vision model.

Covers the prompt (room list and listing facts), the image part in the request,
the clean-up of the model's answer (room names, whitespace), and the OpenAI-style
body with an image.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

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
    assert m.clean(facts(room="Primary", level="second"), listing()).room == "Primary Bedroom"
    assert m.clean(facts(room="Primary", level="main"), listing()).room is None  # listed on the second floor only


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


@pytest.fixture(autouse=True)
def small_photo(monkeypatch):
    """The photo bytes come from a tiny green image, not the network; a URL ending in missing.jpg does not load."""
    monkeypatch.setattr(m.sheet, "fetch", lambda url: None if url.endswith("missing.jpg") else m.sheet.Image.new("RGB", (30, 20), (60, 140, 40)))


def test_read_retries_once_when_the_caption_names_furniture():
    first = facts(caption="A kitchen with a wood table and a window over the sink.")
    second = facts(caption="A kitchen with white cabinets and a window over the sink.")
    client = FakeVision(first, second)
    session = FakeSession()
    out = m.read_listing_photos(session, listing(), client, review=False)
    assert len(client.calls) == 2
    assert "table" in client.calls[1]["user"]
    # The photo goes as bytes, not as its URL.
    assert client.calls[0]["images"][0].startswith("data:image/jpeg;base64,")
    assert out.read == 1 and out.photos[0].facts.caption == second.caption
    assert session.committed and session.added[0].model == "fake-vl" and session.added[0].prompt_version == m.PROMPT_VERSION


def test_read_falls_back_to_the_url_when_the_photo_does_not_load():
    lst = listing(photos=[{"high": "https://cdn/missing.jpg", "medium": "https://cdn/m.jpg", "low": "x"}])
    client = FakeVision(facts(caption="A kitchen with white cabinets."))
    m.read_listing_photos(FakeSession(), lst, client, review=False)
    assert client.calls[0]["images"] == ["https://cdn/missing.jpg"]


def test_read_keeps_the_first_answer_when_the_retry_is_no_better():
    first = facts(caption="A kitchen with a wood table.")
    client = FakeVision(first, facts(caption="A kitchen with a table and chairs."))
    out = m.read_listing_photos(FakeSession(), listing(), client, review=False)
    assert out.photos[0].facts.caption == first.caption


def test_reword_level_swaps_the_floor_words_and_keeps_the_rest():
    assert m.reword_level("Main-floor kitchen with wood cabinets", "main", "basement") == "Basement kitchen with wood cabinets"
    assert m.reword_level("The basement has terrazzo flooring and a staircase up.", "basement", "main") == "The main-floor has terrazzo flooring and a staircase up."
    assert m.reword_level("A main-level bedroom with hardwood floors", "main", "second") == "A second-floor bedroom with hardwood floors"
    assert m.reword_level("Hardwood floors and a closet", "basement", "main") == "Hardwood floors and a closet"


def test_apply_fix_changes_level_room_and_the_words_and_validates_the_room():
    old = facts(kind="interior", level="main", room="Kitchen", title="Main-floor kitchen", caption="A main-floor kitchen with wood cabinets.")
    fix = m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="main", level_now="basement", room_was="Kitchen", room_now="Kitchen", why="the finishes match the basement photos")
    two_kitchens = listing(rooms=[
        {"type": "Kitchen", "level": "Main level", "dimension": "4 m x 3.5 m"},
        {"type": "Kitchen", "level": "Lower level", "dimension": "3 m x 2.5 m"},
    ])
    new = m.apply_fix(old, fix, two_kitchens)
    assert new.level == "basement" and new.room == "Kitchen"
    assert new.title == "Basement kitchen" and new.caption == "A basement kitchen with wood cabinets."
    # A room the listing does not have is dropped; exterior fixes clear the interior facts.
    assert m.apply_fix(old, m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="main", level_now="basement", room_was="Kitchen", room_now="Gym", why=""), two_kitchens).room is None
    front = m.apply_fix(facts(kind="exterior_back", level=None, room=None, storeys=1), m.Fix(photo=1, kind_was="exterior_back", kind_now="exterior_front", level_was=None, level_now=None, room_was=None, room_now=None, why="porch by the garage"), two_kitchens)
    assert front.kind == "exterior_front" and front.level is None and front.storeys == 1
    # Stairs going down: the camera is above the lowest floor, so the fix to the basement is refused.
    foyer = facts(kind="interior", level="main", room=None, stairs="down", title="Foyer", caption="A foyer with stairs down.")
    down = m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="main", level_now="basement", room_was=None, room_now=None, why="")
    assert m.apply_fix(foyer, down, two_kitchens).level == "main"


def test_fix_matches_rejects_a_misread_label():
    old = facts(kind="interior", level="main", room="Kitchen")
    ok = m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="main", level_now="basement", room_was="kitchen", room_now="Kitchen", why="")
    bad = m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="basement", level_now="main", room_was="Kitchen", room_now="Kitchen", why="")
    assert m.fix_matches(old, ok) and not m.fix_matches(old, bad)


def test_clean_drops_a_room_that_is_not_listed_on_the_photo_level():
    rooms = [{"type": "Dining room", "level": "Main level", "dimension": "3 m x 3 m"}]
    assert m.clean(facts(room="Dining room", level="basement"), listing(rooms=rooms)).room is None
    assert m.clean(facts(room="Dining room", level="main"), listing(rooms=rooms)).room == "Dining room"
    assert m.clean(facts(room="Dining room", level="unknown"), listing(rooms=rooms)).room == "Dining room"


def test_review_applies_only_real_changes_and_notes_why():
    from app.models import ListingPhoto

    lst = listing(photos=[{"high": f"https://cdn/h{i}.jpg", "medium": f"https://cdn/m{i}.jpg", "low": "x"} for i in range(3)])
    session = FakeSession()
    for i, f in enumerate([
        facts(kind="interior", level="main", room="Living room", title="Living room", caption="A main-floor room with hardwood."),
        facts(kind="interior", level="basement", room=None, title="Family room", caption="Hardwood floors and a double window."),
        facts(kind="exterior_back", level=None, room=None, title="Back yard and deck", caption="A raised deck by the driveway.", storeys=1),
    ]):
        session.add(ListingPhoto(listing_id="L1", photo_index=i, url=f"https://cdn/h{i}.jpg", model="fake-vl", prompt_version=m.PROMPT_VERSION, facts=f.model_dump(), note=None))
    review = m.Review(fixes=[
        m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="main", level_now="main", room_was="Living room", room_now="Living room", why="no change"),
        m.Fix(photo=2, kind_was="interior", kind_now="interior", level_was="basement", level_now="main", room_was=None, room_now="Living room", why="hardwood and a large window like photo 1"),
        m.Fix(photo=3, kind_was="exterior_back", kind_now="exterior_front", level_was=None, level_now=None, room_was=None, room_now=None, why="the deck is beside the driveway"),
        m.Fix(photo=9, kind_was="interior", kind_now="interior", level_was="main", level_now="main", room_was=None, room_now=None, why="no such photo"),
    ])
    client = FakeVision(*[review] * m.REVIEW_RUNS)  # every run agrees
    applied = m.review_labels(session, lst, client)
    assert [f.photo for f in applied] == [2, 3]
    assert "#2 kind=interior level=basement" in client.calls[0]["user"]
    assert "contact sheet of all 3 photos" in client.calls[0]["user"]
    assert client.calls[0]["schema"] is m.Review
    assert client.calls[0]["images"][0].startswith("data:image/jpeg;base64,")
    rows = {r.photo_index: r for r in session.added}
    assert rows[0].note is None
    assert rows[1].facts["level"] == "main" and rows[1].facts["room"] == "Living room"
    assert rows[1].note == "second pass: level: basement -> main; room: None -> Living room (hardwood and a large window like photo 1)"
    assert rows[2].facts["kind"] == "exterior_front" and rows[2].note.startswith("second pass: kind: exterior_back -> exterior_front")


def test_review_keeps_the_labels_when_the_model_fails():
    from app.models import ListingPhoto

    session = FakeSession()
    for i in range(2):
        session.add(ListingPhoto(listing_id="L1", photo_index=i, url="u", model="m", prompt_version=1, facts=facts().model_dump(), note=None))

    class Failing:
        model = "x"

        def structured(self, **kwargs):
            raise llm.ModelUnavailable("down")

    assert m.review_labels(session, listing(), Failing()) == []
    assert all(r.note is None for r in session.added)


def _fix(photo, level_was, level_now, room_was=None, room_now=None, kind="interior", why=""):
    return m.Fix(photo=photo, kind_was=kind, kind_now=kind, level_was=level_was, level_now=level_now, room_was=room_was, room_now=room_now, why=why)


def test_consensus_keeps_what_2_of_3_runs_propose():
    by = {0: facts(level="main", room=None), 1: facts(level="basement", room=None)}
    a = _fix(1, "main", "basement", room_now="Kitchen")
    a2 = _fix(1, "main", "basement", room_now="Living room")
    b = _fix(2, "basement", "main")
    out = m.consensus([[a], [a2, b], [a], [b], []], by)
    assert [(f.photo, f.level_now, f.room_now) for f in out] == [(1, "basement", "Kitchen")]  # photo 2: 1 vote; room: 2 votes for Kitchen
    # A fix that misreads the stored label does not vote.
    wrong = _fix(1, "basement", "main")
    assert m.consensus([[wrong]] * m.REVIEW_RUNS, by) == []
    # One run voting twice for the same change still counts once.
    assert m.consensus([[a, a], [a, a], [b]], by) == []


def test_neighbours_veto_a_level_change_that_looks_like_another_floor(monkeypatch):
    from app.models import ListingPhoto

    def coloured(url):
        # Main-floor photos are orange (hardwood), basement photos grey.
        return m.sheet.Image.new("RGB", (30, 20), (200, 120, 40) if "main" in url else (120, 120, 120))

    monkeypatch.setattr(m.sheet, "fetch", coloured)
    urls = ["https://cdn/main1.jpg", "https://cdn/main2.jpg", "https://cdn/main3.jpg", "https://cdn/base1.jpg", "https://cdn/base2.jpg"]
    lst = listing(photos=[{"high": u, "medium": u, "low": u} for u in urls])
    session = FakeSession()
    levels = ["main", "main", "main", "basement", "basement"]
    for i, lvl in enumerate(levels):
        f = facts(kind="interior", level=lvl, room=None, title="Room", caption="A room.")
        session.add(ListingPhoto(listing_id="L1", photo_index=i, url=urls[i], model="m", prompt_version=m.PROMPT_VERSION, facts=f.model_dump(), note=None))
    # The reviewer wants to move the orange photo 3 to the basement (vetoed: its twins are main-floor photos)
    # and the grey photo 4 to the main floor (vetoed too: its twin, photo 5, is in the basement and outweighs the rest).
    review = m.Review(fixes=[_fix(3, "main", "basement", why="x"), _fix(4, "basement", "main", why="y")])
    applied = m.review_labels(session, lst, FakeVision(*[review] * m.REVIEW_RUNS))
    assert applied == []
    # A move that the look-alikes support goes through: photo 5, mislabelled main, is grey like basement photo 4.
    session.added[4].facts = facts(kind="interior", level="main", room=None, title="Room", caption="A room.").model_dump()
    review = m.Review(fixes=[_fix(5, "main", "basement", why="grey like photo 4")])
    applied = m.review_labels(session, lst, FakeVision(*[review] * m.REVIEW_RUNS))
    assert [f.photo for f in applied] == [5]
    assert session.added[4].facts["level"] == "basement"


def test_read_runs_the_review_after_the_photos():
    first = facts(caption="A kitchen with white cabinets.")
    vision = FakeVision(first)
    text = FakeVision(m.Review(fixes=[]))
    out = m.read_listing_photos(FakeSession(), listing(), vision, review_client=text)
    assert out.read == 1 and len(text.calls) == 0  # 1 label: nothing to compare, no call


def test_read_skips_the_review_without_a_text_client(monkeypatch):
    monkeypatch.setattr(m, "make_review_client", lambda: None)
    out = m.read_listing_photos(FakeSession(), listing(), FakeVision(facts(caption="A kitchen with white cabinets.")))
    assert out.read == 1


def test_contact_sheet_numbers_the_photos_and_marks_a_missing_one(monkeypatch):
    from app.photos import sheet

    def fake_fetch(url):
        return None if url.endswith("missing.jpg") else sheet.Image.new("RGB", (300, 200), "blue")

    monkeypatch.setattr(sheet, "fetch", fake_fetch)
    img = sheet.contact_sheet(["https://cdn/a.jpg", "https://cdn/missing.jpg", "https://cdn/c.jpg"], columns=2, thumb_w=100)
    assert img.size == (200, 2 * (round(100 * 2 / 3) + sheet.LABEL_H))
    # The second tile is the grey stand-in; the first holds the blue thumbnail.
    assert img.getpixel((150, sheet.LABEL_H + 30)) == (204, 204, 204)
    assert img.getpixel((50, sheet.LABEL_H + 30)) == (0, 0, 255)
    assert sheet.data_url(img).startswith("data:image/jpeg;base64,")


def test_reword_room_follows_a_room_change_in_the_title_and_caption():
    assert m.reword_room("Dining room", "Dining room", "Kitchen") == "Kitchen"
    assert m.reword_room("The dining room has patterned tile floors.", "Dining room", "Kitchen") == "The kitchen has patterned tile floors."
    assert m.reword_room("Family room", "Family room", "Primary Bedroom") == "Primary Bedroom"
    assert m.reword_room("Hardwood floors and a closet.", "Family room", "Primary Bedroom") == "Hardwood floors and a closet."
    assert m.reword_room("A bedroom with a closet.", "Bedroom 2", "Bedroom 3") == "A bedroom 3 with a closet."


def test_apply_fix_renames_the_room_in_the_words():
    old = facts(kind="interior", level="main", room="Dining room", title="Dining room", caption="The dining room has patterned tile floors.")
    rooms = [{"type": "Dining room", "level": "Main level", "dimension": "3 m x 3 m"}, {"type": "Kitchen", "level": "Lower level", "dimension": "3 m x 3 m"}]
    fix = m.Fix(photo=1, kind_was="interior", kind_now="interior", level_was="main", level_now="basement", room_was="Dining room", room_now="Kitchen", why="")
    new = m.apply_fix(old, fix, listing(rooms=rooms))
    assert new.room == "Kitchen" and new.level == "basement"
    assert new.title == "Kitchen" and new.caption == "The kitchen has patterned tile floors."


def test_light_share_tells_a_drawing_from_a_photo():
    from app.photos import sheet

    page = sheet.Image.new("RGB", (100, 100), "white")
    d = sheet.ImageDraw.Draw(page)
    d.rectangle((10, 10, 90, 90), outline="black", width=3)
    d.line((10, 50, 90, 50), fill="black", width=2)
    assert sheet.light_share(page) > 0.8
    lawn = sheet.Image.new("RGB", (100, 100), (60, 140, 40))
    assert sheet.light_share(lawn) < 0.1


def test_a_floor_plan_label_on_a_photograph_is_asked_again():
    first = facts(kind="floor_plan", title="Floor plan", caption="A survey drawing shows the lot.", level=None, room=None)
    second = facts(kind="aerial", title="Aerial view", caption="An overhead view of the house and yard.", level=None, room=None)
    client = FakeVision(first, second)
    out = m.read_listing_photos(FakeSession(), listing(), client, review=False)
    assert len(client.calls) == 2 and "not a drawing" in client.calls[1]["user"]
    assert out.photos[0].facts.kind == "aerial"


def test_a_floor_plan_label_that_persists_on_a_photograph_becomes_other():
    plan = facts(kind="floor_plan", title="Floor plan", caption="A survey.", level=None, room=None)
    out = m.read_listing_photos(FakeSession(), listing(), FakeVision(plan, plan), review=False)
    assert out.photos[0].facts.kind == "other"


def test_a_floor_plan_label_on_a_light_page_stands(monkeypatch):
    monkeypatch.setattr(m.sheet, "fetch", lambda url: m.sheet.Image.new("RGB", (30, 20), "white"))
    plan = facts(kind="floor_plan", title="Floor plan", caption="A plan of the main floor.", level=None, room=None)
    client = FakeVision(plan)
    out = m.read_listing_photos(FakeSession(), listing(), client, review=False)
    assert len(client.calls) == 1 and out.photos[0].facts.kind == "floor_plan"


def test_read_runs_2_review_rounds():
    lst = listing(photos=[{"high": f"https://cdn/h{i}.jpg", "medium": f"https://cdn/m{i}.jpg", "low": "x"} for i in range(2)])
    vision = FakeVision(facts(caption="A kitchen."), facts(caption="A kitchen."))
    text = FakeVision(*[m.Review(fixes=[])] * (m.REVIEW_RUNS * m.REVIEW_ROUNDS))
    m.read_listing_photos(FakeSession(), lst, vision, review_client=text)
    assert len(text.calls) == m.REVIEW_RUNS * m.REVIEW_ROUNDS
