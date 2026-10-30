"""Session taste: pure parts and the summary flow. No network, no database."""

from types import SimpleNamespace

from app.taste import service as taste


def test_sid_validation():
    assert taste.valid_sid("a" * 8) and taste.valid_sid("Ab-_9" * 4)
    assert not taste.valid_sid("short") and not taste.valid_sid("x" * 65) and not taste.valid_sid("bad sid!")


def test_summary_is_due_every_fifth_action():
    assert [n for n in range(1, 16) if taste.due(n)] == [5, 10, 15]
    assert not taste.due(0)


def test_saves_replay_save_and_unsave_in_order():
    rows = [("a", "save"), ("b", "save"), ("a", "unsave"), ("c", "save"), ("a", "save")]
    assert taste.saved_ids(rows) == ["a", "c", "b"]
    assert taste.saved_ids([("a", "unsave")]) == []


def test_default_persona_needs_the_threshold():
    strong = SimpleNamespace(persona="investor", confidence=0.7)
    weak = SimpleNamespace(persona="investor", confidence=0.69)
    odd = SimpleNamespace(persona="landlord", confidence=0.9)
    assert taste.default_persona(strong) == "investor"
    assert taste.default_persona(weak) is None
    assert taste.default_persona(odd) is None
    assert taste.default_persona(None) is None


def listing(**over):
    base = dict(building_type="House", bedrooms_text="3 + 1", bathrooms=2, sqft_min=1100, sqft_max=1500, lot_size="33 x 100 FT", ownership_type="Freehold")
    base.update(over)
    return SimpleNamespace(**base)


def test_event_lines_carry_facts_scores_and_the_best_pitch():
    lines = taste.event_lines([
        ("save", "similar", listing(), {"investor": 8, "flipper": 5, "first_time_buyer": 7, "builder": 6}, "Legal basement apartment."),
        ("open", None, listing(building_type="Apartment", lot_size=None), {}, None),
    ])
    assert lines[0].startswith("- SAVE (from similar): House, 3 + 1 bd, 2 ba, 1100-1500 sqft, 33 x 100 FT, Freehold.")
    assert "First-time buyer 7, Investor 8, Flipper 5, Builder 6" in lines[0] and lines[0].endswith("Pitch: Legal basement apartment.")
    assert lines[1] == "- OPEN: Apartment, 3 + 1 bd, 2 ba, 1100-1500 sqft, Freehold. Scores: no scores yet."
    assert taste.user_prompt(lines).startswith("Actions, oldest first:\n- SAVE")


def test_clean_clamps_confidence_and_trims_likes():
    t = taste.clean(taste.Taste(summary="  You like bungalows.  ", persona="investor", confidence=1.4, likes=[" suites ", "", "a", "b", "c", "d", "e"]))
    assert t.summary == "You like bungalows." and t.confidence == 1.0 and t.likes == ["suites", "a", "b", "c", "d"]


def test_metric_counts_sessions_whose_saved_house_came_from_similar():
    rows = [
        ("s1", "a", "open", "search"), ("s1", "a", "save", None),
        ("s2", "b", "open", "similar"), ("s2", "b", "save", None),
        ("s3", "c", "open", "similar"), ("s3", "d", "save", None),
        ("s4", "e", "open", "similar"),
    ]
    assert taste.metric_from_rows(rows) == {"sessions_with_save": 3, "sessions_saved_via_similar": 1, "share": 0.333}
    assert taste.metric_from_rows([])["share"] is None


class FakeSession:
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


class FakeClient:
    model = "fake/model"

    def __init__(self, result, session):
        self.result, self.session = result, session

    def structured(self, *, system, user, schema, effort, max_tokens, images=None):
        self.session.events.append("model")
        assert schema is taste.Taste and effort == "low" and "SAVE" in user
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_summarize_releases_the_connection_and_stores_the_taste(monkeypatch):
    session = FakeSession()
    client = FakeClient(taste.Taste(summary="You keep saving houses with a suite.", persona="investor", confidence=0.9, likes=["suites"]), session)
    monkeypatch.setattr(taste, "_window", lambda s, sid: [("save", "similar", listing(), {"investor": 9}, "Two doors.")])
    row = taste.summarize(session, "session-1", 5, client)
    assert session.events == ["close", "model", "add", "commit"]
    assert row is session.stored and row.persona == "investor" and row.confidence == 0.9 and row.actions == 5
    assert taste.default_persona(row) == "investor"


def test_summarize_stores_the_failure_and_returns_none(monkeypatch):
    session = FakeSession()
    client = FakeClient(taste.llm.ModelUnavailable("rate limited"), session)
    monkeypatch.setattr(taste, "_window", lambda s, sid: [("save", None, listing(), {}, None)])
    assert taste.summarize(session, "session-1", 5, client) is None
    assert session.stored.summary is None and "rate limited" in session.stored.note


def test_summarize_without_a_client_or_events_is_none(monkeypatch):
    assert taste.summarize(FakeSession(), "session-1", 5, None) is None
    monkeypatch.setattr(taste, "_window", lambda s, sid: [])
    assert taste.summarize(FakeSession(), "session-1", 5, FakeClient(None, FakeSession())) is None
