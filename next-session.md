# next-session.md - state handoff
As of: end of session 7 (strategy pivot session). Read this AFTER CLAUDE.md and context-full.md.

## The pivot in one paragraph
A strategy session on 2026-07-11 (captured in session-brief-v1.1.md) changed the plan. Phase 6 (README) is NO LONGER next. The core finding: the live app is a single-user app wearing a multi-user costume, it serves the builder's own wardrobe to every visitor. Confirmed when the builder's husband opened the live site and got styled from HER clothes. The fix (let visitors upload their own wardrobe, stored in their own browser) is now the top priority because it turns the demo from "look at her closet" into "try it with yours" and solves the photo-privacy problem by design. A revised phase plan 7A to 7E replaces "Phase 6 next". The README becomes 7E: last, but non-negotiable.

## Where the project stands
Phases 1 through 5 are complete and unchanged. The app is live: **https://wardrobe-stylist-nine.vercel.app**. Combined measured spend to date: roughly $0.0101 total (about one cent), against a $10 projection and $40 hard cap. Vercel, Serper and GitHub all free tier.

- Phase 1: wardrobe vision extraction (extract_wardrobe.py). 10 of 13-14 photos extracted, zero failures, $0.00673.
- Phase 2: profile + constraint engine (constraint_engine.py, profile.json). Deterministic, zero AI cost, 16/16 tests.
- Phase 3: styling recommender (recommender.py). Occasion mapped to formality via a lookup table, gap detection deterministic, one AI call ranks/explains. 15/15 tests.
- Phase 4: live shopping (shopping_search.py + gap_fill.py). Serper wrapper, merchant whitelist, budget filter, query cache, AI pick + attribute inference, hallucination guard. 13/13 and 12/12 tests.
- Phase 5: web UI, deployed. api/index.py (Flask, one route POST /api/style) + webapp/index.html + webapp/photos/*.svg (placeholders, real photos gitignored). GitHub repo github.com/arshiagupta/wardrobe-stylist, auto-deploys on push to main.

## Revised phase plan v4 (this is the new roadmap)
| Phase | Content | Depends on | Est effort |
|---|---|---|---|
| 7A | Multi-user upload flow: upload button (multiple files, phone camera via the same input), new API route running extraction per photo, per-session photo cap (target 20), wardrobe JSON returned to and stored in browser localStorage, app reads wardrobe from localStorage not a server file | Nothing | ~Half a day, the big one |
| 7B | User profile: form (gender/style presentation with a neutral option, age, body type or measurements, likes, avoid list), localStorage, avoid-list into the constraint engine, gender into shopping query construction AND ranking prompt, rest into the ranking prompt | 7A helps, not required | ~2-3 hours |
| 7C | UI revamp: tabs, landing/story section, wardrobe gallery, product-image click-to-expand, saved-outfits tab, search cap to 2 | 7A for the gallery | ~Half a day |
| 7D | Grouped alternates: same bottom + footwear, multiple tops, one card. Prompt + schema + rendering | 7C rendering | ~2-3 hours |
| 7E | README, non-negotiable, last but never dropped | Everything | Writing, not debugging |

## 7A and 7B are DONE (session 7). Next is 7C.
Shipped and live: 7A (multi-user upload, wardrobe in browser localStorage, /api/style reads it from the request body), a quality pass (multi-item extraction, styling rubric, budget-gated buys: budget 0 = words only, budget > 0 = shop within budget, search cap 3 -> 2), and 7B (user-profile form: avoid-list as a hard filter, gender steering new-buy searches + ranking language, age/body/likes as soft prompt context). Privacy removals done and pushed (wardrobe.json untracked, profile.json neutralised, placeholder SVGs removed). The builder confirmed 7A works in her own browser. Full detail in context-full.md's session 7 execution notes. 60/60 tests pass. Combined billed spend for session 7 to date roughly $0.008.

Remaining phases: 7C (UI revamp: tabs, landing/story section, wardrobe gallery, product-image click-to-expand, saved-outfits tab; the search-cap-to-2 part of 7C is already done), 7D (grouped alternates), 7E (README, mandatory, last).

## Exact resume point (for Claude Code, next session)
1. Read CLAUDE.md, context-full.md, this file and session-brief-v1.1.md fully before acting.
2. Build 7C next: the UI revamp (tabs, a landing/story section explaining the limited-wardrobe problem, a wardrobe gallery view, product-image click-to-expand, a saved-outfits tab backed by localStorage). The search-cap-to-2 piece listed under 7C is already done (session 7). This is builder-time only, zero API cost, but confirm the look with her as you go.
3. Any billed test run needs the builder's yes and an estimated cost first.
4. Update context-full.md and next-session.md before the session ends.

## 7A technical cautions, resolve before/while building
- The Vercel function will call Gemini once per uploaded photo. Check Vercel function request body size limits, per-photo upload requests are likely safer than one big batch [Guessing, verify].
- HEIC from iPhones may need browser-side or server-side conversion. The local extract script accepted HEIC, but the browser upload path is new and untested for it.
- Add the per-session photo cap (target 20) in code, on top of the existing per-request meters. Keep spend boring.
- Never print or commit either API key.

## The Vercel deployment saga, read before touching api/index.py or vercel.json
Full detail in context-full.md's session 6 log. Short version so it is not undone by accident:
- The Flask entrypoint MUST be `api/index.py` (not project root), with `app = Flask(...)` as a genuine top-level statement, never inside an if/else.
- Static files (the page, photos) live in `webapp/`, NOT `public/`. Vercel treats `public/` as reserved and silently excludes it from a function's bundle. Any other folder name bundles normally.
- vercel.json has ONE rewrite: `{"source": "/(.*)", "destination": "/api/index"}`. Every request goes to Flask, which serves the page, the photos and /api/style. Do not split static-serving back out to Vercel without re-reading the saga.
- GEMINI_API_KEY and SERPER_API_KEY are Vercel environment variables, never committed.

## Known scope limitations to carry into the README (7E), document honestly, do not "fix" quietly
- The shopping "link" is a Google Shopping page, not a direct retailer URL. Serper does not provide a direct-merchant link on the free route.
- MAX_SEARCHES_PER_REQUEST is now 2 (lowered from 3, session 7). A heavily-gapped wardrobe can exhaust the live-search budget in the first ranked outfit. Cost-engineering material, not a bug.
- Body type / age / measurements influence is AI-inferred (soft, in the prompt), not a deterministic guarantee like the budget or avoid-list filters. State this plainly.
- Saved outfits are localStorage only: per-device, vanish if browser data is cleared. Accounts + database are v2.
- The single-user-costume defect and the husband second-user test: log it as a real defect found in genuine second-user use.
- OCCASION_FORMALITY_MAP covers a handful of phrases only, expand as demo occasions come up.

## Standing guardrails (duplicated in CLAUDE.md)
- Never print or write either API key anywhere. Ask before every run that costs money, stating estimated cost.
- Budget $40 hard cap, measured spend to date roughly $0.0101. Bias toward shipping given the overrun timebox (~2 more build days accepted, session 7).
- Explain everything non-technically, one concept at a time. Confirm before high-stakes steps.
- Do not re-litigate locked decisions, point at context-full.md section 5 first (now including the session 7 block).

## Starting the next session
Open Claude Code, same local session on Documents\wardrobe-stylist. First message to send:

> Read CLAUDE.md, context-full.md, next-session.md and session-brief-v1.1.md fully before doing anything. Confirm the new plan back to me in one short table (phase order, what 7A involves, your build plan, technical risks), then build 7A only after I confirm. Ask before every run that costs money with an estimate. Explain non-technically as you go.
