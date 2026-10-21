"""Turn a strategy written in plain language into search parameters.

"Looking for a condo under 800k with a 6-8% return, I make 140k and have 150k
saved" becomes `building_type=Apartment`, `max_price=800000`, `min_cap_rate=6`,
`income=140000`, `down_payment=150000`. Every parameter is one the search API
accepts, and every interpretation is returned in words so the buyer can check
and correct it in the form.

The rules are deliberately plain pattern matching: deterministic, instant and
testable. Anything the rules miss is listed under `unmatched` rather than
guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

Params = dict[str, str | list[str]]


@dataclass
class ParsedStrategy:
    params: Params = field(default_factory=dict)
    understood: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)


BUILDING_TYPES = [
    (re.compile(r"\b(condo|condominium|apartment|apt)s?\b", re.I), "Apartment", "condos"),
    (re.compile(r"\b(town\s?house|townhome|row\s?house)s?\b", re.I), "Row / Townhouse", "townhouses"),
    (re.compile(r"\bduplex(es)?\b", re.I), "Duplex", "duplexes"),
    (re.compile(r"\btriplex(es)?\b", re.I), "Triplex", "triplexes"),
    (re.compile(r"\bfourplex(es)?\b", re.I), "Fourplex", "fourplexes"),
    (re.compile(r"\b(detached|semi(-detached)?|bungalow|house)s?\b", re.I), "House", "houses"),
]

POTENTIAL_LABELS = {
    "suite": "an existing rental suite",
    "suite_potential": "room to add a basement suite",
    "separate_entrance": "a separate entrance to the basement",
    "garden_suite": "space for a garden suite",
    "severance": "a lot that could be severed",
    "multiplex": "zoning that allows a multiplex",
    "extra_bedroom": "a room that could become another bedroom",
}
POTENTIAL_RULES = [
    (re.compile(r"garden\s+suite|laneway\s+(?:house|suite|home)", re.I), "garden_suite"),
    (re.compile(r"\bsever|split\s+the\s+lot|two\s+lots|subdivide|severance", re.I), "severance"),
    (re.compile(r"multiplex|sixplex|\bplex\s+potential|add(?:ing)?\s+(?:more\s+)?units|more\s+units|convert(?:ed|ing)?\s+(?:in)?to\s+(?:a\s+)?(?:duplex|triplex|fourplex|multiplex|\d+\s+units)", re.I), "multiplex"),
    (
        re.compile(
            r"(?:add|build|create|potential\s+for|room\s+for|could\s+(?:be|add|have))[^.]{0,30}?"
            r"(?:basement|in-?law|rental|income|second(?:ary)?)\s+(?:suite|apartment|apt|unit)|house\s*hack",
            re.I,
        ),
        "suite_potential",
    ),
    (re.compile(r"sep[ae]rate\s+(?:side\s+|basement\s+|private\s+)?entr(?:ance|y)", re.I), "separate_entrance"),
    (
        re.compile(
            r"(?:basement|in-?law|rental|income|second(?:ary)?|nanny)\s+(?:suite|apartment|apt|unit)|tenant|rented\s+basement",
            re.I,
        ),
        "suite",
    ),
    (
        re.compile(
            r"(?:add|extra|another|additional|one\s+more|more)\s+bedrooms?|(\d)\s*-?\s*(?:bed|bedroom|br)\s+(?:in)?to\s+(?:a\s+)?(\d)\s*-?\s*(?:bed|bedroom|br)",
            re.I,
        ),
        "extra_bedroom",
    ),
]

# Money: "$800k", "800,000", "1.2M", "1.2 million", "$140 000".
_MONEY = re.compile(r"\$?\s?(\d{1,3}(?:[, ]\d{3})+|\d+(?:\.\d+)?)\s*(k|m|million|thousand|grand)?\b", re.I)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|to|–)?\s*(\d+(?:\.\d+)?)?\s*%")
_BEDS = re.compile(r"\b(\d)\s*\+?\s*(?:-|\s)?\s*(?:bed(?:room)?s?|br|bd)\b", re.I)
_BATHS = re.compile(r"\b(\d)\s*\+?\s*(?:-|\s)?\s*(?:bath(?:room)?s?|ba|wr)\b", re.I)
_AMORTIZATION = re.compile(r"\b(25|30)\s*(?:-|\s)?\s*(?:year|yr)s?\s*(?:amortization|amort|mortgage)?", re.I)
_LIVE_IN = re.compile(r"live\s+in|move\s+in|owner[- ]occup|primary\s+residence|house\s*hack|for\s+(?:myself|us|my\s+family)", re.I)
_CASH_FLOW_POSITIVE = re.compile(
    r"cash\s*-?\s*flow\s*(?:positive|neutral)|positive\s+cash\s*-?\s*flow|pays?\s+for\s+itself|carr(?:y|ies)\s+itself"
    r"|break\s*-?\s*even|cover(?:s|ing)?\s+(?:the|its|my)\s+(?:mortgage|costs|carrying)",
    re.I,
)
_CASH_FLOW_AMOUNT = re.compile(
    r"cash\s*-?\s*flow(?:s|ing)?\s+(?:of|at\s+least|above|over|positive\s+by)?\s*\+?\s*\$?\s?(\d[\d,]*)(?:\s*(?:/|per|a)\s*(?:month|mo\b|mth))?",
    re.I,
)

MAX_PRICE_CUES = re.compile(r"\b(under|below|less\s+than|up\s+to|max(?:imum)?|budget(?:\s+of|\s+is)?|at\s+most|no\s+more\s+than|afford(?:ing)?|around|about|spend)\b", re.I)
MIN_PRICE_CUES = re.compile(r"\b(over|above|more\s+than|at\s+least|starting\s+(?:at|from)|from)\b", re.I)
INCOME_CUES = re.compile(r"\b(income|salary|make|making|earn(?:ing|s)?|take\s+home|per\s+year|a\s+year|annually|household)\b", re.I)
DOWN_CUES = re.compile(r"\b(down(?:\s*payment)?|saved|savings|cash|deposit|equity|to\s+put\s+down|in\s+the\s+bank)\b", re.I)
DEBT_CUES = re.compile(r"\b(debts?|car\s+payment|student\s+loan|loan\s+payments?|owe|credit\s+card)\b", re.I)
RETURN_CUES = re.compile(r"\b(return|cap\s*rate|cap|roi|yield|cash\s*on\s*cash|coc)\b", re.I)
RATE_CUES = re.compile(r"\b(interest|rate|mortgage\s+at|fixed|variable)\b", re.I)
RENT_OUT_CUES = re.compile(r"rent(?:al|ed)?\s+(?:it\s+)?out|rental\s+property|investment\s+property|investor|tenants?", re.I)

CITIES = ["Toronto", "Vaughan", "Markham", "Mississauga", "Richmond Hill", "Pickering"]


def _amount(value: str, unit: str | None) -> int:
    number = float(value.replace(",", "").replace(" ", ""))
    unit = (unit or "").lower()
    if unit in {"k", "thousand", "grand"}:
        number *= 1_000
    elif unit in {"m", "million"}:
        number *= 1_000_000
    elif number < 10_000:  # "800" on its own means $800k in this market
        number *= 1_000
    return round(number)


def _context(text: str, start: int, end: int, before: int = 40, after: int = 25) -> tuple[str, str]:
    return text[max(0, start - before) : start], text[end : end + after]


def _money(value: int) -> str:
    return f"${value:,.0f}"


def parse_strategy(text: str, communities: list[str] = ()) -> ParsedStrategy:
    """Interpret free text. `communities` lets neighbourhood names ("Leslieville") become the keyword filter."""
    result = ParsedStrategy()
    params = result.params
    says = result.understood.append
    text = text.strip()
    if not text:
        return result
    consumed: list[tuple[int, int]] = []

    def take(span: tuple[int, int]) -> None:
        consumed.append(span)

    # Percentages: returns, down payment, interest rate.
    for m in _PERCENT.finditer(text):
        low, high = float(m.group(1)), float(m.group(2)) if m.group(2) else None
        before, after = _context(text, m.start(), m.end())
        if RETURN_CUES.search(after) or RETURN_CUES.search(before):
            cue = (RETURN_CUES.search(after) or RETURN_CUES.search(before)).group(1).lower()
            quoted = m.group(0) + (" " + after.strip().split(" ")[0] if RETURN_CUES.search(after) else "")
            if "yield" in cue:
                params["min_gross_yield"] = f"{low:g}"
                says(f"Gross rental yield of at least {low:g}% (from “{quoted.strip()}”)")
            else:
                params["min_cap_rate"] = f"{low:g}"
                says(
                    f"Cap rate of at least {low:g}% (from “{quoted.strip()}”)"
                    + (f"; the upper end, {high:g}%, is not a filter" if high else "")
                )
            take(m.span())
        elif DOWN_CUES.search(after) or re.search(r"down\s*$", before, re.I):
            params["down_payment_pct"] = f"{low:g}"
            says(f"{low:g}% down payment")
            take(m.span())
        elif RATE_CUES.search(after) or RATE_CUES.search(before):
            params["interest_rate"] = f"{low:g}"
            says(f"Mortgage rate of {low:g}%")
            take(m.span())

    # Beds and baths, including "2-bed into a 3-bed".
    conversion = re.search(r"(\d)\s*-?\s*(?:bed|bedroom|br)\s+(?:in)?to\s+(?:a\s+)?(\d)\s*-?\s*(?:bed|bedroom|br)", text, re.I)
    if conversion:
        params["min_beds"] = conversion.group(1)
        says(f"At least {conversion.group(1)} bedrooms today, with a room that could become bedroom {conversion.group(2)}")
        take(conversion.span())
    else:
        m = _BEDS.search(text)
        if m:
            params["min_beds"] = m.group(1)
            says(f"At least {m.group(1)} bedrooms")
            take(m.span())
    m = _BATHS.search(text)
    if m:
        params["min_baths"] = m.group(1)
        says(f"At least {m.group(1)} bathrooms")
        take(m.span())

    m = _AMORTIZATION.search(text)
    if m:
        params["amortization"] = m.group(1)
        says(f"{m.group(1)}-year amortization")
        take(m.span())

    # Cash flow.
    m = _CASH_FLOW_AMOUNT.search(text)
    if m:
        amount = int(m.group(1).replace(",", ""))
        params["min_cash_flow"] = str(amount)
        says(f"Cash flow of at least {_money(amount)}/month after the mortgage")
        take(m.span())
    else:
        m = _CASH_FLOW_POSITIVE.search(text)
        if m:
            params["min_cash_flow"] = "0"
            says("Cash flow at or above zero after the mortgage")
            take(m.span())

    # Money amounts: price, income, down payment, debts.
    previous_end = 0
    for m in _MONEY.finditer(text):
        if any(s <= m.start() < e for s, e in consumed):
            continue
        if not m.group(0).strip().startswith("$") and m.group(2) is None and float(m.group(1).replace(",", "").replace(" ", "")) < 100:
            continue  # a bare small number is a count, not money
        amount = _amount(m.group(1), m.group(2))
        # The words just before an amount say what it is ("make $140k"); the few
        # words after are a fallback ("$150k saved"). Both windows stop at the
        # neighbouring amounts so one amount's cue is not read as another's.
        before, after = _context(text, m.start(), m.end(), after=14)
        before = before[max(0, previous_end - (m.start() - len(before))) :]
        previous_end = m.end()
        kind = next(
            (
                name
                for window in (before, after)
                for name, cues in (
                    ("debts", DEBT_CUES),
                    ("down", DOWN_CUES),
                    ("income", INCOME_CUES),
                    ("min_price", MIN_PRICE_CUES),
                    ("max_price", MAX_PRICE_CUES),
                )
                if (cues.search(window) if window is before or name != "min_price" else None)
            ),
            None,
        )
        if kind is None and m.group(0).strip().startswith("$"):
            kind = "max_price"
        if kind == "debts":
            monthly = amount if amount < 10_000 else round(amount / 12)
            params["monthly_debts"] = str(monthly)
            says(f"{_money(monthly)}/month in other debt payments")
        elif kind == "down":
            params["down_payment"] = str(amount)
            says(f"{_money(amount)} down payment")
        elif kind == "income":
            params["income"] = str(amount)
            says(f"Household income of {_money(amount)}/year")
        elif kind == "min_price":
            params["min_price"] = str(amount)
            says(f"Price of at least {_money(amount)}")
        elif kind == "max_price":
            params["max_price"] = str(amount)
            says(f"Price up to {_money(amount)}")
        else:
            continue
        take(m.span())

    # Home type, cities and neighbourhoods.
    for pattern, value, label in BUILDING_TYPES:
        m = pattern.search(text)
        if m and "building_type" not in params:
            params["building_type"] = value
            says(f"Only {label}")
            take(m.span())
    for city in CITIES:
        m = re.search(rf"\b{re.escape(city)}\b", text, re.I)
        if m:
            params["city"] = city
            says(f"In {city}")
            take(m.span())
            break
    for community in sorted(communities, key=len, reverse=True):
        if len(community) < 4:
            continue
        m = re.search(rf"\b{re.escape(community)}\b", text, re.I)
        if m:
            params["q"] = community
            says(f"In {community}")
            take(m.span())
            break

    # Value-add potential.
    potential: list[str] = []
    for pattern, key in POTENTIAL_RULES:
        m = pattern.search(text)
        if m and key not in potential:
            if key == "suite" and "suite_potential" in potential:
                continue
            potential.append(key)
            take(m.span())
    if potential:
        params["potential"] = potential
        says("Must have " + ", ".join(POTENTIAL_LABELS[k] for k in potential))

    # Who will live there.
    if _LIVE_IN.search(text):
        params["occupancy"] = "live_in"
        says("You will live in it, so the insured down payment rules apply and rent does not count toward qualifying")
    elif RENT_OUT_CUES.search(text):
        params["occupancy"] = "rent_out"

    # A sensible sort for the goal.
    if "min_cash_flow" in params:
        params["sort"] = "cash_flow_desc"
    elif "min_cap_rate" in params or "min_gross_yield" in params:
        params["sort"] = "cap_rate_desc"

    # What was left over, so the buyer can see what the rules did not catch.
    for m in re.finditer(r"[^.,;!?\n]+", text):
        if not m.group(0).strip():
            continue
        if not any(s < m.end() and e > m.start() for s, e in consumed):
            result.unmatched.append(m.group(0).strip())
    return result
