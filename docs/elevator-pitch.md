# Bayt: the elevator pitch

Four spoken versions, shortest first. Say them, do not read them. Every number
below is from the README, the Devpost draft or the live site on 30 October 2026.

Team: Shareq Rabbani, Shafeeq Rabbani, Khaja Kamil.
Live: https://bayt.andalsolutions.com · Code: https://github.com/shafeeqr2/bayt

---

## 1. Fifteen seconds, about 40 words

*Use it in a hallway, in a lift, or when a judge says "so what is it?"*

> Ask any realtor what buyers say most. "I want a home similar to this one."
> Filters cannot answer that. Bayt can. NVIDIA Nemotron reads every Toronto
> listing like a buyer would, then finds the homes you would love and says why.
> Search by taste, not by filters.

---

## 2. Thirty seconds, about 80 words

*Use it at a booth, or as the first answer in a Q&A.*

> Every search site gives you price, beds and baths. Nobody shops that way.
> Buyers open a house they like and ask for more like it. That is taste, and
> taste is not a filter.
>
> Bayt does what Netflix did. A model reads what each house is about. Nemotron
> reads the text, 8 photos and the lot data for 2,261 Toronto homes, writes a
> pitch for 4 kinds of buyer, and ranks 8 matches with 1 reason each.
>
> It is live today. Search by taste, not by filters.

---

## 3. Sixty seconds, about 160 words

*Use it when you have the judge's full attention and a laptop nearby.*

> Here is the most common sentence in real estate: "I want a home similar to
> this one." No search site can answer it. Bayt can.
>
> Nemotron 3.5 Super VL, running on Nebius Token Factory, reads every listing
> the way a buyer would: the text, 8 photos, the City's lot and zoning data. It
> writes a pitch and a score for 4 buyers: first-time buyer, investor, flipper,
> builder. We call it Taste Match. Press "More like this" and you get 8 homes
> ranked for the buyer you are, each with 1 reason. Type "a bigger backyard and
> a garage" and the list moves with you.
>
> Builders and investors get more. Build Check answers a plan in plain words with
> citations to the zoning by-law. Precedent Check shows every Committee of
> Adjustment decision within 500 metres since 2001.
>
> 2,261 live listings, profiled in 78 minutes for about 8 dollars. Open source.
> Try it on your phone right now: bayt dot andalsolutions dot com.

---

## 4. Two minutes, about 300 words

*The stand-up pitch. Hook, problem, demo moment, models, numbers, team, close.*

> Picture a Saturday open house. A couple walks through a bungalow and loves it.
> On the way out they tell the agent the one thing every agent hears most:
> "I want a home similar to this one."
>
> The agent goes home and types price, beds and baths into a search box. That is
> not what the couple asked for. They asked for their taste. Taste is not a
> filter.
>
> Netflix hit the same wall years ago. Click counts could not say why you liked a
> show, so they switched to a language model that reads what each title is
> about. We did that for houses.
>
> Here is 39 Rhydwen Avenue. One house, 4 scores: 8 for a first-time buyer, 8
> for an investor, 5 for a flipper, 6 for a builder. Press "More like this".
> Eight homes in the same price band within 5 kilometres, ranked for an
> investor, each with a reason in plain words. "Two rentable doors, 8 percent
> yield." Now type "a bigger backyard and a garage". The list changes, and every
> reason answers the ask.
>
> Builders and investors get Build Check and Precedent Check. Describe a plan,
> and Nemotron answers with citations to By-law 569-2013. Around this house,
> 222 Committee of Adjustment files since 2001: 188 approved, 9 refused.
> Precedent, not a promise, and we say so.
>
> Why these models? Nemotron 3.5 Super VL reads 8 photos and writes strict JSON
> in about 6 seconds. Nemotron 3 Super reasons over long by-law text cheaply.
> Both run on Nebius Token Factory. The whole catalogue was profiled in 78
> minutes for about 8 dollars.
>
> It is live with 2,261 Toronto listings, no login, 319 tests, MIT licence. We
> are Shareq, Shafeeq and Khaja, and we built this in the hackathon window.
>
> Bayt. Search by taste, not by filters.

---

## If the judge asks

**Why Nemotron?**
Nemotron 3.5 Super VL was the first vision-language model we tried that read 8
photos plus the listing text and returned a 1,200-token, schema-valid JSON in
about 6 seconds. Nemotron 3 Super gave correct by-law citations in every Build
Check answer we spot-checked, at a fraction of the cost of the closed models we
had used before.

**Why not fine-tune?**
The hard part was not the model, it was the rubric: what a 9 out of 10 means for
a flipper versus a first-time buyer. Versioned prompts, strict schemas and a
scrubber that keeps street names and prices out of the pitch got us there, and
every prompt change re-runs the catalogue for about 8 dollars.

**How is this different from Zillow's similar homes?**
Zillow matches on structured fields and clicks: price, size, location. Taste
Match matches on a written pitch per buyer type, explains each match in 1 line,
and lets you steer it in words, so the same house gets 4 different lists.

**What about other cities?**
Listings, photos and the model pipeline are city-agnostic; Toronto is first
because its open data gives us parcels, building outlines, zoning layers and
Committee of Adjustment files. Another city needs its zoning rules encoded and
its open data mapped, and everything else runs as is.

**How do you know the matches are good?**
Every match carries a reason you can check against the listing, and location and
price are hard filters, so a bad match is visible, not hidden. The plan has three
hand-check gates: 50 profiles read, 100 pair judgments with 70 percent agreement,
10 steering trials; we ran spot checks during the build and the full counts are
the next step.

**What did Token Factory change for you?**
One API key replaced a GPU setup and a free tier that hit its daily quota. The
OpenAI-style API meant the switch was 1 provider entry and 3 model names, rate
limits grew with our use, and the full catalogue ran in 78 minutes.
