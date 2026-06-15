# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock secondhand-listings dataset (loaded via `load_listings()`) for items
matching the user's keywords, and optionally filters by size and a maximum price.
It scores each listing by how well it overlaps the description and returns the best
matches first. This is a pure data-filtering tool — no LLM call.

**Input parameters:**
- `description` (str): Free-text keywords describing the wanted item, e.g. `"vintage graphic tee"`. Required. Used for keyword-overlap scoring against each listing's `title`, `description`, and `style_tags`.
- `size` (str | None): Size to filter by, e.g. `"M"`. Optional — `None` skips size filtering. Matching is case-insensitive and substring-based so `"M"` matches `"S/M"`.
- `max_price` (float | None): Inclusive price ceiling in dollars, e.g. `30.0`. Optional — `None` skips price filtering. A listing passes if `listing["price"] <= max_price`.

**What it returns:**
A `list[dict]`, sorted by relevance score (highest first), containing only listings
whose keyword score is greater than 0 and that pass the size/price filters.
Each dict is a full listing with these fields:
`id` (str), `title` (str), `description` (str), `category` (str: tops/bottoms/outerwear/shoes/accessories),
`style_tags` (list[str]), `size` (str), `condition` (str: excellent/good/fair),
`price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str: depop/thredUp/poshmark).
Returns an **empty list** (`[]`) when nothing matches — it never raises.

**What happens if it fails or returns nothing:**
The tool returns `[]` rather than raising. The planning loop detects the empty list,
writes a helpful message into `session["error"]` (naming the parsed filters that were
too narrow), and returns the session early **without** calling `suggest_outfit` or
`create_fit_card`. The user is shown the error and prompted to loosen their query.

---

### Tool 2: suggest_outfit

**What it does:**
Given one selected listing and the user's wardrobe, calls the Groq LLM to propose
1–2 complete, wearable outfits that pair the new item with named pieces the user
already owns. Produces conversational styling text, not structured data.

**Input parameters:**
- `new_item` (dict): A single listing dict (the top search result the user is considering). The tool reads its `title`, `category`, `colors`, `style_tags`, and `description` to anchor the suggestion.
- `wardrobe` (dict): A wardrobe dict with an `items` key holding a list of wardrobe-item dicts. Each item has `id`, `name`, `category`, `colors`, `style_tags`, `notes`. May be empty (`{"items": []}`) — must be handled gracefully.

**What it returns:**
A non-empty `str` containing the outfit suggestions in natural language. When the
wardrobe has items, the string names specific owned pieces (e.g. "pair it with your
baggy dark-wash jeans and white ribbed tank"). When the wardrobe is empty, the string
is general styling advice for the item (what categories/colors/vibes pair well) and
notes that suggestions will get more personal once the user adds wardrobe items.

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, the tool does not error — it switches to a
"general styling advice" prompt and still returns useful text. If the LLM call itself
raises or returns an empty/whitespace string, the tool returns a short fallback string
("Couldn't generate a styled look right now — here's the item on its own.") so the
loop can still proceed to `create_fit_card`. The loop never passes an empty string
forward.

---

### Tool 3: create_fit_card

**What it does:**
Turns the outfit suggestion and the item details into a short, shareable, social-media
style caption (an "OOTD" / fit card). Calls the Groq LLM at a higher temperature so the
output varies and sounds casual rather than like a product description.

**Input parameters:**
- `outfit` (str): The outfit-suggestion string returned by `suggest_outfit()`. Required and expected to be non-empty.
- `new_item` (dict): The same listing dict used in Tool 2. The caption mentions its `title`, `price`, and `platform` naturally (once each).

**What it returns:**
A `str` of roughly 2–4 sentences usable directly as an Instagram/TikTok caption:
casual tone, mentions the item name + price + platform once each, captures the outfit
vibe in specific terms, and reads differently for different inputs.

**What happens if it fails or returns nothing:**
The tool first guards against an empty or whitespace-only `outfit` and, if so, returns
a descriptive error string (e.g. "No outfit available to caption.") instead of raising.
If the LLM call fails or returns empty, it returns a minimal hand-built fallback caption
built from the item's `title`, `price`, and `platform` so the user always sees something
shareable. The loop stores whatever string is returned in `session["fit_card"]`.

---

### Additional Tools (if any)

None for the core build. A possible stretch tool, `parse_query(query) -> dict`, would
use the LLM to extract `{description, size, max_price}` from the raw query; for the core
build this parsing lives inline in the planning loop (regex + keyword stripping).

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop is a fixed, linear pipeline with one early-exit branch. It does not free-form
choose tools — it runs them in order, and the **only** decision point is whether
`search_listings` produced results.

1. **Initialize.** `session = _new_session(query, wardrobe)`. All output fields start `None`/`[]`, `error` starts `None`.

2. **Parse the query.** Extract three values from `query` and store them in `session["parsed"]`:
   - `max_price`: regex for a number after `$`, `under`, or `below` (e.g. `under $30` → `30.0`); else `None`.
   - `size`: regex for `size <X>` or standalone tokens like `XS/S/M/L/XL` or a shoe number; else `None`.
   - `description`: the query with the price and size phrases stripped out, used as keywords.

3. **Call `search_listings(description, size, max_price)`** and store the list in `session["search_results"]`.
   **Branch (the one real conditional):**
   - **If `search_results` is empty (`[]`):** set
     `session["error"] = "No listings matched '<description>'" + (size/price note)` and
     **`return session` immediately.** Do not call `suggest_outfit` or `create_fit_card`.
   - **Else:** continue.

4. **Select the item.** `session["selected_item"] = session["search_results"][0]` (top-ranked result).

5. **Call `suggest_outfit(selected_item, wardrobe)`** and store the string in
   `session["outfit_suggestion"]`. (This always returns usable text — empty wardrobe yields
   general advice — so there is no early exit here.)

6. **Call `create_fit_card(outfit_suggestion, selected_item)`** and store the string in
   `session["fit_card"]`.

7. **Done.** `return session`. The loop knows it is finished because all three pipeline
   stages have run (or it exited early at step 3). Success is signaled by `session["error"] is None`.

---

## State Management

**How does information from one tool get passed to the next?**

All state for a single interaction lives in one `session` dict created by
`_new_session(query, wardrobe)` (see [agent.py:26](agent.py#L26)). It is the single
source of truth and is threaded through every step — tools receive plain arguments
read from the session, and their return values are written back into the session.

Fields tracked:
- `query` (str) — the original user input.
- `parsed` (dict) — `{description, size, max_price}` produced in step 2; read by `search_listings`.
- `search_results` (list[dict]) — output of `search_listings`.
- `selected_item` (dict | None) — `search_results[0]`; input to both `suggest_outfit` and `create_fit_card`.
- `wardrobe` (dict) — passed in by the caller; input to `suggest_outfit`.
- `outfit_suggestion` (str | None) — output of `suggest_outfit`; input to `create_fit_card`.
- `fit_card` (str | None) — output of `create_fit_card`; the final shareable caption.
- `error` (str | None) — `None` on success; a user-facing message when the loop exits early.

Data flow between tools is **explicit, not global**: e.g. `suggest_outfit` does not read
`search_results` directly — the loop pulls `session["selected_item"]` and
`session["wardrobe"]` and passes them as arguments, then stores the result in
`session["outfit_suggestion"]` for the next call. `app.py`'s `handle_query` reads the
finished session: if `error` is set it shows that in panel 1 and blanks the rest;
otherwise it formats `selected_item` into panel 1, `outfit_suggestion` into panel 2,
and `fit_card` into panel 3.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Loop sets `session["error"]` to a specific message that echoes the filters back, e.g. *"I couldn't find any listings for 'vintage graphic tee' under $30 in size M. Try removing the size filter, raising your price, or using broader keywords like 'graphic tee'."* Then returns early; panels 2 and 3 stay empty. |
| suggest_outfit | Wardrobe is empty | No hard error — the tool detects `wardrobe["items"] == []` and returns general styling advice instead, e.g. *"Your closet's empty right now, so here's a starter look: this tee pairs naturally with baggy denim or wide-leg trousers and chunky sneakers. Add items to your wardrobe and I'll tailor outfits to what you own."* The loop continues to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | The tool guards empty/whitespace `outfit` and returns a built-from-item fallback caption instead of erroring, e.g. *"Thrifted gem alert 🛍️ Snagged this [title] for $[price] on [platform]. Styling ideas loading — but honestly it speaks for itself."* This still gives the user a shareable card. |

---

## Architecture

```
User query  ("vintage graphic tee under $30, size M")  +  wardrobe choice
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PLANNING LOOP  (run_agent in agent.py)                                    │
│                                                                           │
│  Step 1: session = _new_session(query, wardrobe)  ◄────────────┐         │
│                                                                 │         │
│  Step 2: parse query ──► Session: parsed = {description,        │         │
│                                  size, max_price}               │         │
│      │                                                          │         │
│      ▼                                                  ┌────────┴───────┐ │
│  ├─► search_listings(description, size, max_price) ───► │ SESSION STATE  │ │
│      │   results = []                                   │ (single dict)  │ │
│      ├──► [ERROR] session.error = "No listings          │ query          │ │
│      │            matched ..." ──► return session ──────│ parsed         │─┼─► early exit
│      │                                                  │ search_results │ │
│      │   results = [item, ...]                          │ selected_item  │ │
│      ▼                                                  │ wardrobe       │ │
│  Session: selected_item = results[0]  ─────────────────►│ outfit_sugg.   │ │
│      │                                                  │ fit_card       │ │
│  ├─► suggest_outfit(selected_item, wardrobe) ──────────►│ error          │ │
│      │   (empty wardrobe ► general advice, no exit)     └────────┬───────┘ │
│      ▼                                                           │         │
│  Session: outfit_suggestion = "..."  ◄───────────────────────────┘         │
│      │                                                                     │
│  └─► create_fit_card(outfit_suggestion, selected_item)                     │
│      │                                                                     │
│  Session: fit_card = "..."                                                 │
│      │                                                                     │
│      ▼                                                                     │
│  return session  ◄──────────────────────────────── (error path lands here)│
└─────────────────────────────────────────────────────────────────────────┘
    │
    ▼
app.py handle_query maps session → 3 panels:
  error?  ► panel1 = error,           panel2 = "",  panel3 = ""
  success ► panel1 = selected_item,   panel2 = outfit_suggestion,  panel3 = fit_card
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings (Claude):** I'll paste the Tool 1 block from this planning.md
  (the three params, the scored-list return value with its exact fields, and the
  empty-list failure mode) plus the `load_listings()` docstring from
  [utils/data_loader.py](utils/data_loader.py), and ask Claude to implement the
  function. **Before trusting it I'll check that** it (a) filters by `max_price` and
  `size` *and* keyword-scores the `description`, (b) drops score-0 listings, (c) sorts
  descending, and (d) returns `[]` (never raises) on no match. Then I'll run 3 queries:
  `"vintage graphic tee under $30"` (expect tops), `"size M"` only, and
  `"designer ballgown size XXS under $5"` (expect `[]`).

- **suggest_outfit & create_fit_card (Claude):** I'll give Claude the Tool 2 and Tool 3
  blocks plus the wardrobe-item field list from
  [data/wardrobe_schema.json](data/wardrobe_schema.json) and the existing
  `_get_groq_client()` helper, and ask it to write both LLM calls. **I'll verify** that
  `suggest_outfit` branches on empty `wardrobe["items"]`, that `create_fit_card` guards
  empty `outfit` and uses a higher temperature, and that both return strings (with
  fallbacks) rather than raising. Test: run each against the example wardrobe and the
  empty wardrobe and read the output for the required elements (named pieces; item name
  + price + platform once each).

**Milestone 4 — Planning loop and state management:**

- **run_agent (Claude):** I'll give Claude the **Planning Loop**, **State Management**,
  and **Architecture** sections above plus the `_new_session` dict from
  [agent.py:26](agent.py#L26), and ask it to implement `run_agent` exactly following the
  7 steps and the single early-exit branch. **I'll verify** the generated loop (a) writes
  every value back into `session` with the documented keys, (b) returns early with
  `session["error"]` set when `search_results == []` and does **not** call the later
  tools, and (c) otherwise selects `results[0]` and runs both LLM tools. I'll confirm by
  running the two `__main__` cases in agent.py (happy path + no-results path) and the
  `app.py` UI with both wardrobe choices.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — parse + search.**
`run_agent` builds the session, then parses the query into
`parsed = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`.
It calls `search_listings("vintage graphic tee", None, 30.0)`. The tool scores listings
on keyword overlap and price-filters at ≤ $30; the Y2K Baby Tee (`lst_002`, $18.00,
style_tags include `"graphic tee"`, `"vintage"`) scores highest. It returns a non-empty
list, stored in `session["search_results"]`.

**Step 2 — select + suggest outfit.**
The loop sets `session["selected_item"] = search_results[0]` (the Y2K Baby Tee). It calls
`suggest_outfit(selected_item, wardrobe)` with the example wardrobe (which contains baggy
dark-wash jeans, wide-leg trousers, a white ribbed tank, etc.). The LLM returns specific
outfit text naming owned pieces — e.g. tucking the baby tee into the baggy dark-wash
jeans with the chunky sneakers for a Y2K streetwear look. Stored in
`session["outfit_suggestion"]`.

**Step 3 — create fit card.**
The loop calls `create_fit_card(outfit_suggestion, selected_item)`. At higher temperature
the LLM returns a 2–4 sentence caption mentioning the Y2K Baby Tee, its $18 price, and
that it's from Depop — once each — in a casual OOTD voice. Stored in
`session["fit_card"]`. `session["error"]` is still `None`, so the loop returns the
completed session.

**Final output to user:**
`app.py` renders three panels: **Panel 1 (🛍️ Top listing)** shows the formatted Y2K Baby
Tee listing — title, $18.00, condition, size, platform (Depop). **Panel 2 (👗 Outfit
idea)** shows the styled look pairing it with their baggy jeans and chunky sneakers.
**Panel 3 (✨ Your fit card)** shows the shareable caption. (Had the search returned `[]`
— as with the `"designer ballgown size XXS under $5"` example — Panel 1 would instead
show the `session["error"]` message and Panels 2–3 would be empty.)
