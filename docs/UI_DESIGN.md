# Retailer interface: design notes and known limits

## Who and what for
Small retailers on a phone, often on slow networks, in English, French, Spanish or Hindi.
Job: describe the shop, check what the system understood, get a plan they can act on and trust.

## Design decisions
- **One memorable element: the tape-measure budget bar.** Spend fills a tape; a slider below
  changes the budget and re-runs the plan live. Everything else is deliberately quiet: one
  column, ruled lists, no cards.
- **Palette:** cool grey paper `#E9EDF1`, ink `#14202E`, money teal `#00796B`, warning amber,
  error red, focus blue. Colour is never the only signal: warnings carry an "!" and words.
- **Type:** one system font stack (Noto Sans -> Noto Sans Devanagari -> system-ui). No web-font
  download, so it loads fast on weak networks and Hindi renders natively on phones.
- **Layout:** left-aligned single column, 44px minimum touch targets, no horizontal scroll at 375px.
  Numbered steps appear only for the 3-step flow, which is a real sequence.
- **Honesty in the UI:** low-confidence and missing required fields are flagged and block the plan;
  optional gaps are marked "optional" instead of nagging; hard module failures show a plain
  message and no plan; a withheld or missing explanation says so and the figures stay valid.

## Core principle in the UI
The UI never computes a forecast or a money figure. Every plan number is copied from the API
response and carries `data-path` (JSON Pointer into the plan) and `data-value` (raw value).
`tests/test_ui.py` checks, in all four languages, that the displayed text equals the optimizer
output. The tape width uses the optimizer's own `capital_utilization`. Display formatting
(separators, 2 decimals, percent for probabilities) is the only transformation.

## Explore screen (Component D)
"Find new products to try" on the plan screen calls `/opportunities`. Products are grouped
**Observed** (customers asked; a lower bound) and **Hypothesized** (from similar products; very
wide). Every card carries "Not a forecast"; hypothesized ranges are drawn with a hatched bar,
observed with a solid bar. Ranges, scores, requests and trial orders carry `data-path`, and
`tests/test_ui.py` checks they equal the API output. Trial orders come from the optimizer.
When the built-in sample catalogue is used the screen says it is invented.
The bar is a drawing of low/mid/high as fractions of high; it adds no figure.

## Known limits (be honest about these)
- Explore-screen text in fr/es/hi is also an unreviewed draft.
- **Translations are unreviewed drafts** (fr, es, hi) written by the developer; native speakers
  must review them before real retailers see them.
- **Explanation and chat text use `.` decimals and no thousands separators** (contract decision
  Q-G), so they can differ in format from the localized figures in the plan table. Same values.
- **Server text is English:** risk descriptions from the optimizer and unknown server error
  messages are shown as received (marked `lang="en"` where possible). Known codes are localized.
- **Hindi was verified by DOM text only.** The build sandbox has no Devanagari font, so Hindi was not
  checked visually; check on a real phone.
- **Not tested:** real devices, screen readers, slow-network behaviour, RTL languages (none supported).
- **State is in memory** on the server; a restart loses profiles and cached plans.
