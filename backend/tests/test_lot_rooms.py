"""Room completion: the prompt, the clean-up and the cache. No network calls."""

from types import SimpleNamespace

from pydantic import BaseModel

from app.lot import rooms
from app.photos.reader import ListingPhotos, PhotoFacts, PhotoLabel


def listing(**over):
    base = dict(
        id="1",
        rooms=[
            {"type": "Living room", "level": "Main level", "dimension": "3.5 m x 4.0 m"},
            {"type": "Office", "level": "Main level", "dimension": None},
        ],
        bedrooms_text="3 + 1",
        bedrooms_total=4,
        bathrooms=3,
        stories="2",
        building_type="House",
        sqft_min=1500,
        sqft_max=2000,
        description="Finished basement with a 4th bedroom and a 3-piece bath. 1.5 storey with dormers.",
        raw={"_details": {"Building": {"HalfBathTotal": "1"}}},
    )
    base.update(over)
    return SimpleNamespace(**base)


def photos():
    facts = PhotoFacts(
        kind="interior", title="Second-floor office", caption="A small room.", level="second", room=None, windows=1,
        window_wall="far", exterior_doors=0, stairs="none", open_to=[], storeys=None, garage="unknown",
    )
    return ListingPhotos(listing_id="1", model="m", read=1, total=2, photos=[
        PhotoLabel(index=0, url="u0", facts=facts),
        PhotoLabel(index=1, url="u1", facts=None, note="not read"),
    ])


def test_prompt_lists_rooms_counts_description_and_photos():
    text = rooms.user_prompt(listing(), photos())
    assert "- Living room | Main level | 3.5 m x 4.0 m" in text
    assert "- Office | Main level | no size" in text
    assert "Bedrooms: 3 + 1" in text and "Bathrooms: 3 (half: 1)" in text
    assert "4th bedroom" in text
    assert "- Second-floor office; level: second" in text


def test_clean_maps_levels_drops_echoes_and_odd_sizes_and_caps_the_count():
    raw = rooms.Completion(
        rooms=[rooms.RoomHint(name="Bedroom 4", level="Lower level", width_m=3.3, depth_m=3.6, source="description", why="4th bedroom")]
        + [rooms.RoomHint(name="Living room", level="Ground level", width_m=3.5, depth_m=4.0, source="room list", why="listed with size")]
        + [rooms.RoomHint(name="Closet", level="Main level", width_m=0.5, depth_m=0.5, source="photos", why="tiny")]
        + [rooms.RoomHint(name="Attic", level="Attic", width_m=3, depth_m=3, source="photos", why="odd level")]
        + [rooms.RoomHint(name=f"Room {i}", level="Second level", width_m=30, depth_m=3, source="photos", why="x") for i in range(10)],
        upper_floor_share=1.4,
        notes=["Open plan", " ", "Second note", "Third note"],
    )
    out = rooms.clean(raw, rooms.sized_rooms(listing()))
    assert out.rooms[0].name == "Bedroom 4" and out.rooms[0].level == "Basement"
    assert all(r.name not in ("Closet", "Attic", "Living room") for r in out.rooms)
    assert len(out.rooms) == rooms.MAX_ROOMS
    assert out.rooms[1].width_m == 8.0  # clamped
    assert out.upper_floor_share is None
    assert out.notes == ["Open plan", "Second note"]


def test_sized_rooms_reads_the_room_table_with_the_drawn_level_names():
    assert rooms.sized_rooms(listing()) == {("living room", "Main level")}


class FakeClient:
    model = "fake/model"

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def structured(self, *, system, user, schema, effort, max_tokens, images=None):
        self.calls += 1
        assert schema is rooms.Completion and effort == "low"
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_complete_runs_one_structured_call_and_cleans_the_answer():
    client = FakeClient(rooms.Completion(
        rooms=[rooms.RoomHint(name="Bedroom 4", level="Basement", width_m=3.3, depth_m=3.6, source="description", why="4th bedroom")],
        upper_floor_share=0.6, notes=[],
    ))
    out = rooms.complete(client, listing(), None)
    assert client.calls == 1 and out.upper_floor_share == 0.6 and out.rooms[0].level == "Basement"


def test_hints_for_without_a_client_is_none():
    assert rooms.hints_for(None, listing(), None) is None


class FakeSession:
    """Enough of a Session to see the connection go back before the model call."""

    def __init__(self):
        self.events: list[str] = []
        self.stored = None

    def get(self, model, key):
        return None

    def close(self):
        self.events.append("close")

    def add(self, row):
        self.events.append("add")
        self.stored = row

    def commit(self):
        self.events.append("commit")


class RecordingClient(FakeClient):
    def __init__(self, result, session):
        super().__init__(result)
        self.session = session

    def structured(self, **kw):
        self.session.events.append("model")
        return super().structured(**kw)


def test_hints_for_releases_the_connection_during_the_model_call(monkeypatch):
    session = FakeSession()
    client = RecordingClient(rooms.Completion(rooms=[], upper_floor_share=None, notes=[]), session)
    monkeypatch.setattr(rooms.photo_reader, "labels_for", lambda s, l: None)
    row = rooms.hints_for(session, listing(), client)
    assert session.events == ["close", "model", "add", "commit"]
    assert row is session.stored and row.hints == {"rooms": [], "upper_floor_share": None, "notes": []}
    assert row.model == "fake/model" and row.prompt_version == rooms.PROMPT_VERSION


def test_hints_for_stores_the_failure_and_returns_none(monkeypatch):
    session = FakeSession()
    client = FakeClient(rooms.llm.ModelUnavailable("the model is rate limited"))
    monkeypatch.setattr(rooms.photo_reader, "labels_for", lambda s, l: None)
    assert rooms.hints_for(session, listing(), client) is None
    assert session.stored.hints is None and "rate limited" in session.stored.note
