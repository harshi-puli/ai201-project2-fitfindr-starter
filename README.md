# FitFindr 🛍️

FitFindr is a tool-using agent that helps you shop secondhand. You describe what
you're looking for in plain language ("vintage graphic tee under $30, size M");
the agent finds a matching listing, styles it against your existing wardrobe, and
writes a shareable "fit card" caption for it.

It runs as a Gradio web app and orchestrates three tools through a planning loop
that **decides what to do next based on what each tool returns** — not a fixed
script that always does the same thing.

---

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

The two LLM tools use Groq's `llama-3.3-70b-versatile`.

## Run it

```bash
python app.py
```

Open the URL printed in your terminal (usually http://localhost:7860 — check the
output, the port can differ). Type a query, pick a wardrobe, and hit **Find it**.

You can also run the agent headless:

```bash
python agent.py          # runs a happy-path query and the no-results path
pytest tests/            # unit tests for all three tools + their failure modes
python tests/trigger_failures.py   # deliberately triggers every failure mode
```

---

## How the agent works

### Tool inventory

All three tools live in [tools.py](tools.py) and are callable / testable on their own.

**1. `search_listings(description, size, max_price) -> list[dict]`**
- **Purpose:** Find secondhand listings matching the user's request. Pure data
  filtering over the 40-item mock dataset — no LLM call.
- **Inputs:**
  - `description` (`str`) — keywords describing the wanted item (e.g. `"vintage graphic tee"`). Scored by keyword overlap against each listing's title, description, style tags, and category.
  - `size` (`str | None`) — size to filter by; `None` skips it. Case-insensitive substring match, so `"m"` matches `"S/M"`.
  - `max_price` (`float | None`) — inclusive price ceiling; `None` skips it.
- **Output:** a `list[dict]` of matching listings, **sorted best-match-first**, each
  containing `id`, `title`, `description`, `category`, `style_tags`, `size`,
  `condition`, `price`, `colors`, `brand`, `platform`. Returns `[]` when nothing
  matches — it never raises.

**2. `suggest_outfit(new_item, wardrobe) -> str`**
- **Purpose:** Style the found item against the user's closet. Calls the LLM.
- **Inputs:**
  - `new_item` (`dict`) — a single listing dict (the selected search result).
  - `wardrobe` (`dict`) — `{"items": [...]}`, each item having `name`, `category`, `colors`, `style_tags`, `notes`. May be empty.
- **Output:** a non-empty `str`. With a populated wardrobe it names specific owned
  pieces ("pair it with your baggy straight-leg jeans and chunky white sneakers");
  with an empty wardrobe it gives general styling advice instead.

**3. `create_fit_card(outfit, new_item) -> str`**
- **Purpose:** Turn the styled look into a casual, shareable social-media caption.
  Calls the LLM at high temperature so repeated runs vary.
- **Inputs:**
  - `outfit` (`str`) — the suggestion string from `suggest_outfit`.
  - `new_item` (`dict`) — the same listing dict, so the caption can mention the item name, price, and platform.
- **Output:** a 2–4 sentence `str` usable as an Instagram/TikTok caption.

### The planning loop — what the agent decides

The loop lives in `run_agent(query, wardrobe)` in [agent.py](agent.py). It is a
linear pipeline with **one real decision point**, and that decision is what makes it
an agent rather than a script: the agent only continues if the search actually found
something.

1. **Initialize** a `session` dict (the single source of truth for the run).
2. **Parse the query** with `_parse_query()` (regex, no LLM): pull a `max_price`
   (number after `$`/`under`/`below`), a `size` (`size X` or a standalone size token),
   and a `description` (the query with those phrases stripped, used as keywords).
   Stored in `session["parsed"]`.
3. **Search.** Call `search_listings(description, size, max_price)`; store the list in
   `session["search_results"]`.
   - **Decision:** *if the result list is empty*, the agent **stops here**. It writes a
     specific error into `session["error"]` (echoing back the filters it used) and
     returns immediately. It does **not** call `suggest_outfit` or `create_fit_card`,
     because styling and captioning a nonexistent item would be meaningless. This is
     the branch that makes the agent behave differently for different inputs.
   - *Otherwise*, it proceeds.
4. **Select** the top-ranked listing: `session["selected_item"] = search_results[0]`.
5. **Suggest an outfit** from the selected item + wardrobe; store in
   `session["outfit_suggestion"]`. (No early exit here — an empty wardrobe still yields
   useful general advice, so the loop always has something to caption.)
6. **Create the fit card** from the outfit + selected item; store in `session["fit_card"]`.
7. **Return** the session. Success is signaled by `session["error"] is None`.

So the agent makes two kinds of judgment: *what to search for* (parsed from free text)
and, critically, *whether the result is good enough to keep going* — short-circuiting
the expensive LLM steps when there's nothing to style.

### State management

Everything for one interaction lives in a single `session` dict created by
`_new_session()`. It is the only thing passed around, and each step reads from it and
writes its result back into it:

| Field | Written by | Read by |
|---|---|---|
| `query` | caller | parsing |
| `parsed` | step 2 | `search_listings` |
| `search_results` | `search_listings` | the empty-check + item selection |
| `selected_item` | step 4 (`search_results[0]`) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | caller | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | the UI |
| `error` | step 3 (only on no-results) | the UI |

Data is passed **explicitly as arguments**, not through globals — e.g. `suggest_outfit`
doesn't reach into `search_results`; the loop pulls `session["selected_item"]` and
hands it in. This is verifiable: the same dict object flows through unchanged —
`session["selected_item"] is session["search_results"][0]` is `True`, and that exact
object is what gets passed to both LLM tools (no re-prompting, no hardcoded values in
between). [app.py](app.py)'s `handle_query()` reads the finished session: on error it
shows the message in panel 1 and blanks the rest; on success it formats `selected_item`
→ panel 1, `outfit_suggestion` → panel 2, `fit_card` → panel 3.

### Error handling (per tool, with a real triggered example)

Each tool was deliberately broken and observed recovering — see
[tests/trigger_failures.py](tests/trigger_failures.py).

| Tool | Failure mode | What the agent does |
|---|---|---|
| `search_listings` | No listing matches the query | Returns `[]` (never raises). The loop turns that into a specific, actionable message and stops. |
| `suggest_outfit` | Wardrobe is empty | Detects `wardrobe["items"] == []` and returns general styling advice instead of crashing. Also has a try/except LLM fallback so it never returns an empty string. |
| `create_fit_card` | `outfit` is empty/whitespace | Guards before any LLM call and returns a descriptive message. Also has a hand-built fallback caption if the LLM call fails. |

**Concrete example (triggered).** Running the impossible query
`designer ballgown size XXS under $5`:

```
$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]

# full agent:
error    -> I couldn't find any listings for 'designer ballgown', size XXS, under $5.
            Try removing the size filter, raising your price, or using broader keywords.
fit_card -> None
```

The empty list propagates into the loop, the loop short-circuits, and `fit_card`
stays `None` — proving the two LLM tools were never invoked. The user gets told *what*
failed and *what to try*, not a bare "no results."

### Spec reflection

The implementation matches [planning.md](planning.md) closely: three tools with the
documented signatures, the linear-pipeline-with-one-branch loop, and the `session`
dict as the single state object. Two things I learned by building it:

- **The branch is the whole point.** My first instinct was to run all three tools
  every time; the empty-results short-circuit is what makes behavior input-dependent
  and saves two LLM calls when there's nothing to style.
- **Keyword search is noisier than the spec assumed.** My planning walkthrough used the
  full conversational query ("...I mostly wear baggy jeans and chunky sneakers...").
  In practice those extra words dilute the keyword score and can outrank the real
  target (the word `vintage` matches many items), so a short query like
  `vintage graphic tee under $30` reliably returns the Y2K Baby Tee while the long one
  may not. A future improvement is stripping styling-preference clauses before scoring,
  or using the LLM to extract clean keywords.

---

## AI usage

I used Claude (in Claude Code) as a pair-programmer, driven by the specs in planning.md.

**1. Implementing `search_listings`.** I gave Claude the Tool 1 block from planning.md
(the three parameters with types, the scored-list return value with its exact fields,
and the "return `[]`, never raise" failure mode) plus the `load_listings()` docstring.
It produced a function that filtered and scored listings. **What I checked/changed:** I
verified it filtered by *all three* parameters and dropped score-0 items, and I
confirmed the size match was case-insensitive substring (`"m"` in `"S/M"`) rather than
exact equality, which would have missed valid listings. I then tested it against three
queries (a normal query, a size-only query, and the impossible one) before trusting it.

**2. Implementing the planning loop (`run_agent`).** I gave Claude the **Planning
Loop**, **State Management**, and **Architecture** (the ASCII diagram) sections from
planning.md, plus the `_new_session` dict. It generated a loop that ran the steps in
order. **What I overrode:** I made sure the no-results case set `session["error"]` and
`return`ed *before* the LLM tools — the first pass was structured so it could still
fall through, which would have defeated the whole branch. I also confirmed every value
was written back into `session` under the documented keys (so the UI and tests can read
them), and verified the same `selected_item` object flows into both LLM tools rather
than being re-derived.

---

## Project layout

```
ai201-project2-fitfindr-starter/
├── tools.py                  # the three tools
├── agent.py                  # run_agent() planning loop + query parsing
├── app.py                    # Gradio UI + handle_query()
├── data/
│   ├── listings.json         # 40 mock secondhand listings
│   └── wardrobe_schema.json  # wardrobe format + example/empty wardrobes
├── utils/data_loader.py      # data-loading helpers
├── tests/
│   ├── test_tools.py         # pytest unit tests (incl. failure modes)
│   └── trigger_failures.py   # deliberately triggers every failure mode
└── planning.md               # design spec + agent diagram
```
