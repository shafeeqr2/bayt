# Devpost submission draft

Everything below is ready to paste into the Devpost form for the Nebius x NVIDIA
Global AI Hackathon. Fields are in the form's order. Track: **Best Apps and Agents**.

## Project name

Bayt

## Tagline (short)

House search that knows why you like a house. Every Toronto listing is read by
Nemotron, scored for 4 kinds of buyer, and matched to homes "like this, but..."

## Links

- Demo: https://bayt.andalsolutions.com
- Repository: https://github.com/kkamilahmed/bayt
- Video: (YouTube link)

## Inspiration

Real estate search is still a filter form: price, beds, baths. But buyers do not
shop that way. They open a house they like and ask "what else is like this?". And
"like this" means different things to different people. A first-time buyer loves a
bungalow because it is move-in ready and has parking. An investor loves the same
bungalow because the basement has a second kitchen and a separate entrance. A
flipper sees a dated kitchen and a price under the area median. A builder sees a
33 ft lot in a multiplex zone. One house, 4 reasons.

Netflix recently moved from a click-based recommender to one where a language
model reads what a title is about. We wanted to do the same for houses, with the
reasons written down, and with the buyer able to steer.

## What it does

Bayt is a real estate search for Toronto with 2,261 live listings. For every listing:

1. **A house profile.** NVIDIA Nemotron 3.5 Super VL reads the listing text, the
   room list, up to 8 photos, the City of Toronto zoning and lot data, and a rent
   estimate. It writes a fact layer (era, style, finish, condition, basement,
   suites, outdoor space) and 4 persona views: a score from 1 to 10 for a
   first-time buyer, an investor, a flipper and a builder, with a pitch in that
   buyer's words, the signals behind the score, and the concerns.
2. **Similar homes, per buyer.** The pitches are embedded and stored in pgvector.
   When a buyer opens a listing and picks who they are, Bayt filters to the same
   price band and 5 km, takes the 30 nearest pitches, and asks Nemotron to rank
   the best 8 with 1 reason line each and 1 line on what sets this house apart.
3. **Steering.** A "like this, but..." box. Type "bigger backyard and a garage".
   Nemotron rewrites the source pitch with the change applied, the search runs
   from that text, and the reasons say how each match meets the ask. 5 facet
   chips (layout, finish, lot, location, money) say what counts.
4. **Search by fit.** The search page has an "I am a" selector and a "Best fit"
   sort, so an investor sees investor-scored homes first, with the score on each
   card.
5. **Session taste.** No login. Tap the heart on homes you like. After every 5
   actions Nemotron sums up what you seem to like, guesses the buyer type you are,
   and above 70% confidence the site sets that buyer for you.
6. **The rest of the app** gives buyers clarity before they purchase: a lot and
   zoning analysis from City of Toronto open data (coverage, height, as-of-right
   units, garden suite potential, nearby Committee of Adjustment decisions), a
   zoning question box answered by Nemotron with citations to the by-law and the
   analysis, photo labels and a Nemotron-completed room list that feed a possible floor
   plan, and an investment estimate per listing.

## How we built it

- FastAPI + SQLAlchemy + Alembic backend, Postgres 17 with PostGIS and pgvector,
  Next.js 16 frontend. Docker Compose on 1 DigitalOcean droplet behind Caddy.
- **Every model call goes through Nebius Token Factory**, using the OpenAI-style
  API with structured JSON output and the pydantic schema checked on our side.

| Job | Model on Token Factory | Calls |
|---|---|---|
| House profile from text, data and up to 8 photos | `nvidia/Nemotron-3.5-Super-VL` | 1 per listing, about 6 s |
| Rerank of 30 nearest houses with reasons | `nvidia/Nemotron-3.5-Super-VL` | 1 per listing page and persona, cached 24 h |
| "Like this, but..." rewrite | `nvidia/Nemotron-3.5-Super-VL` | 1 per typed ask, cached 24 h |
| Photo labels | `nvidia/Nemotron-3.5-Super-VL` | 1 per listing |
| Zoning answer with citations | `nvidia/nemotron-3-super-120b-a12b` | 2 per new question, cached |
| Room completion for the floor plan (rooms the description and photos name) | `nvidia/nemotron-3-super-120b-a12b` | 1 per listing, cached |
| Session taste: a summary of what you keep opening and saving, with a buyer-type guess | `nvidia/nemotron-3-super-120b-a12b` | 1 per 5 actions, no login |
| Pitch embeddings, 2,048 dims | `Qwen/Qwen3-Embedding-8B` | 200 pitches per request |

- Where Token Factory accelerated the work: the whole catalogue, 2,261 houses and
  9,044 persona pitches, was profiled and embedded in 78 minutes for about $8. A
  listing page answers in 1 to 6 seconds. We turn Nemotron's thinking off with
  `chat_template_kwargs: {enable_thinking: false}` for these "write JSON from the
  given material" calls, which brings the profile call from a timeout to 6 s.
- Location and price are hard filters, never part of the vector, so "similar"
  means similar for the buyer's reasons, not "same street".

## Challenges we ran into

- Nemotron on Token Factory reasons by default. With the default settings our
  structured calls returned an empty answer after spending the whole token budget
  on hidden reasoning. The fix was 1 request field, but it took a while to find.
- About 1 listing in 100 came back with a list field written as 1 comma-separated
  string. We now accept both shapes.
- Photos must go up as JPEG bytes, resized to 800 px, 8 per listing. That is
  about 1 MB per call and 674 tokens per image.
- Pitches must never mention the address, the street, the neighbourhood or the
  dollar price, or the vector learns location instead of the house. The prompt
  forbids it and a scrubber enforces it.

## Accomplishments that we're proud of

- The same house gets 4 different similar-home lists, and the reasons read like a
  buyer wrote them: "Legal basement apartment with separate entrance and second
  kitchen, two rentable doors, 7.0% yield, 5.6% cap."
- Steering works on what the profiles know. "Bigger backyard and a garage" moves
  the list and the reasons say "Bigger 36.1 x 124.8 lot, detached garage".
- 291 backend tests, no network calls in the test suite.

## What we learned

- A language model that writes down *why* makes a recommender you can argue with.
  Click data cannot do that at our scale.
- Persona rubrics matter more than the model. Most of our time went into what a
  9/10 means for a flipper.
- A typed ask can only reach what the profiles describe. "Closer to the subway"
  does nothing until a transit data source exists.

## What's next for Bayt

- Taste across devices: the session is a cookie today.
- Transit, schools and walk data in the profile, so location asks work.
- Hand-judged gates: 50 profiles read, 100 pair judgments, 10 steering trials.

## Built with

python, fastapi, sqlalchemy, postgresql, postgis, pgvector, next.js, react,
typescript, tailwind, docker, caddy, nebius-token-factory, nvidia-nemotron,
qwen3-embedding, digitalocean, cloudflare

## Testing instructions (for the judges)

Live site, no login: https://bayt.andalsolutions.com

1. On the search page set "I am a" to **Investor** and sort by **Best fit**. Every
   card shows that buyer's score.
2. Open a house. "Who this home suits" shows the score per buyer. Click
   **More like this**: a page with 8 houses ranked for that buyer, 1 reason each.
   The sparkle button on any tile opens the same page for that house.
3. In the "Like this, but…" box type **bigger backyard and a garage** and click
   **Find homes like this**. The list and the reasons change. Turn the **Money**
   chip off to search every price.
4. Scroll to "What could you build here?", type **keep the house and add a second
   storey**, and click "Check the zoning" for the cited answer.
5. Tap the heart on 5 homes, then open **Saved** in the header: Nemotron sums up
   what you like and names the buyer you are. The search page now defaults to it.

Run it yourself: `git clone`, `./start.sh`, open http://localhost:3000. The first
run seeds the database. Put a Token Factory key in `.env` as `LLM_API_KEY` for the
model parts. See README.md.

## How we used NVIDIA Nemotron and Nebius Token Factory (form question)

All model calls in Bayt run on Nebius Token Factory. NVIDIA Nemotron 3.5 Super VL
writes the house profiles from text and photos, ranks and explains the similar
homes, rewrites the pitch for a typed ask, and labels the photos. Nemotron 3
Super answers the zoning question with citations. Token Factory's embedding
endpoint (Qwen3-Embedding-8B, asked for 2,048 dims) powers the pgvector search.
The whole catalogue was processed on Token Factory in 78 minutes for about $8.
Details and numbers: README.md, section "AI models".

## Feedback on Nebius Token Factory and the NVIDIA models (form question)

What worked well:

- The OpenAI-style API meant the switch from another provider was 1 provider
  entry and 3 model names. `response_format` JSON and the `dimensions` parameter
  on embeddings both just worked.
- Speed. Nemotron 3.5 Super VL reads 8 photos and writes a 1,200-token profile in
  6 seconds. The rate limit grew with our use without asking.
- The `x-ratelimit-*` headers and `Retry-After` made the backfill easy to pace.

What cost us time, with suggestions:

1. **Thinking is on by default and eats the output budget.** A structured call
   with `max_tokens: 2000` came back with empty `content`, `finish_reason:
   length`, and 2,000 reasoning tokens. Nothing in the quickstart or the JSON
   docs says this. Suggest: document `chat_template_kwargs.enable_thinking` on
   the model cards and the structured-output page, or expose a top-level
   `reasoning` field like other gateways do.
2. **No NVIDIA embedding model.** We would have liked to stay all-NVIDIA.
   NV-EmbedQA or Nemotron Embed on Token Factory would close that gap.
3. **Schema drift in JSON mode.** About 1 call in 100 wrote a list field as 1
   comma-separated string under `response_format: json_object`. Strict
   `json_schema` would avoid it. A note on which models honour `strict: true`
   with thinking off would help.
4. **Billing surprises.** A card account can go negative and be charged later,
   and there is no spending cap, budget alert, or balance endpoint in the API.
   A hard monthly cap and a `GET /v1/balance` would let a hackathon team sleep.
5. **Builder Program credits** take days to arrive. A same-day small credit on
   sign-up for hackathon participants would remove the card step entirely.
6. Small things: the model list page in the docs is truncated with "...", so
   the exact Nemotron ids had to be read from the catalogue UI; the vision
   example names only one Qwen model, though Nemotron 3.5 Super VL accepts
   `image_url` data URLs fine.

## Video script (under 3 minutes)

Record the screen at 1920x1080 in a browser with no bookmarks bar. Voice over
the recording, no music. Do not show the REALTOR.ca logo or links. Cut each shot
on the action.

| Time | On screen | Say |
|---|---|---|
| 0:00 | Search page, Toronto homes | "This is Bayt, a house search for Toronto. Two thousand two hundred listings. Every one of them has been read by NVIDIA Nemotron on Nebius Token Factory." |
| 0:15 | Set "I am a: Investor", sort "Best fit", click Search | "Say who you are. An investor. Sort by best fit. Each card now shows how well the house fits an investor, one to ten." |
| 0:35 | Open 39 Rhydwen Avenue | "Open one. Under the price, four scores, one to ten, for a first-time buyer, an investor, a flipper and a builder. The same house, four reasons." |
| 0:55 | Click "More like this", Investor active | "More like this, for an investor. Eight houses in the same price band within five kilometres, ranked by Nemotron, with one reason each. Two rentable doors, seven percent yield, multiplex zone." |
| 1:20 | Click First-time buyer chip | "Switch to first-time buyer. Different houses, different reasons: move-in ready, parking, updated kitchen." |
| 1:35 | Type "bigger backyard and a garage", click Find homes like this | "Now steer it. Like this, but a bigger backyard and a garage. Nemotron rewrites what we are looking for, the search runs again, and every reason says how the house meets the ask." |
| 2:00 | Turn the Money chip off | "Turn money off to search every price. Location off to search the whole city." |
| 2:12 | Scroll to "What could you build here?", type a plan, click Check | "And because buyers want clarity, Bayt reads the zoning. Keep the house, add a second storey. The answer cites the by-law and the lot analysis." |
| 2:35 | README "AI models" section | "All of it runs on Nebius Token Factory with NVIDIA Nemotron. The whole catalogue was profiled in seventy-eight minutes for about eight dollars. The code is open source." |
| 2:50 | Search page again | "Bayt. House search that knows why you like a house." |
