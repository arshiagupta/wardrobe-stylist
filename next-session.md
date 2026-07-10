# next-session.md - state handoff
As of: end of session 6, run inside Claude Code (desktop app, Code tab).

## Where the project stands
Phases 1 through 4 are all complete. Full detail and reasoning in context-full.md section 5, session 6 tables (there are two: Phase 3 build, then Phase 4 build further down). Nothing is blocked right now. Combined measured project spend across every phase to date: roughly $0.0101 total (about one cent), against a $10 projection and $40 hard cap.

- Phase 1: wardrobe vision extraction. 10 of 13 photos extracted, zero failures, $0.00673 total. 3 photos still unextracted (rerun extract_wardrobe.py anytime, hash-dedupe means no re-billing).
- Phase 2: profile + constraint engine. wardrobe/profile.json holds standing blockers, constraint_engine.py filters deterministically, zero AI cost, 16/16 tests passing.
- Phase 3: styling recommender. recommender.py takes --occasion/--vibe/--budget/--season as command-line flags, maps occasion to formality via a hard-coded lookup table (OCCASION_FORMALITY_MAP), filters through constraint_engine, detects structural gaps in code (detect_gaps), then makes one AI call to rank/pair/explain outfits. Outfits carry a "gaps" list (changed from a single "gap" string mid-session so each missing item is its own precise, separately-searchable description). Core logic lives in get_outfits(), reused by both recommender.py's own terminal output and by gap_fill.py. test_recommender.py: 15/15 passing.
- Phase 4: live shopping. shopping_search.py wraps Serper.dev's Google Shopping endpoint with a deterministic merchant whitelist (zara/h&m/mango) and budget filter, plus a query cache (wardrobe/shopping_cache.json). gap_fill.py turns each outfit's gap descriptions into real searches (folding in "women's" deterministically, a fix for a menswear-leakage bug found this session), then makes one small AI call per gap to pick the best real candidate and infer style attributes, with a hallucination guard (is_valid_position) that never trusts a model-picked item outside the actual filtered candidate list. MAX_SEARCHES_PER_REQUEST=3 (locked session 3) is enforced across a whole styling request; once hit, remaining gaps show "NOT FILLED" with a clear reason, never silently dropped. test_shopping_search.py: 13/13, test_gap_fill.py: 12/12.
- Real end-to-end Phase 4 run ("work dinner", £60 budget): 3 real products found and merged (H&M cigarette trousers £22.99, Zara heeled mules £35.99, Zara wide-leg trousers £25.99), all whitelisted retailers, all in budget, total AI cost $0.00140 for that whole run (ranking + all 3 picks).

## Known scope limitations to carry into the README (Phase 6), do not "fix" quietly, document honestly
- The shopping "link" field is a Google Shopping product page (google.com/search?ibp=oshop...), not a direct retailer URL. Serper does not provide a direct-merchant-link field or endpoint (confirmed live, including a 404 on a guessed second endpoint). A competing paid provider (SerpApi) does offer this via a documented `direct_link` field, but switching provider was judged too large a pivot for the remaining timebox. This directly qualifies the locked product promise in section 1 ("a clickable link redirecting to the retailer"), it is a real limitation, not a polish gap.
- MAX_SEARCHES_PER_REQUEST=3 means a heavily-gapped wardrobe can exhaust the live-search budget within the first one or two ranked outfits in a single request. Lower-ranked outfits may show gap text only, no live product. This is the cost/quota guardrail (locked session 3) working as designed, good material for the README's cost-engineering section, not a bug to hide.
- Google's 'gl' country parameter needs "gb" (ISO 3166-1 alpha-2), not "uk". Passing "uk" does not error, it silently returns US-anchored results. Already fixed in shopping_search.py, logged here so nobody "fixes" it back by accident while reading old code or notes.

## Exact resume point (for Claude Code, next session)
1. Read CLAUDE.md, context-full.md and this file fully before acting.
2. Start Phase 5: thin single page UI, deployed to Vercel. All backend logic already exists and is callable (constraint_engine.filter_wardrobe, recommender.get_outfits, gap_fill.fill_gaps_for_request). This phase is presentation layer only, no new AI call design needed.
3. Likely shape: a simple form (occasion, vibe, budget, season) that calls a backend function wrapping gap_fill.fill_gaps_for_request and renders the ranked outfits, with real product cards (title, price, merchant, link) for any filled gaps and plain text for any "NOT FILLED" ones, shown honestly rather than hidden.
4. Stretch only, do not attempt until the core UI works end to end: Web Speech API voice input for the occasion/vibe fields (browser-native, no new backend cost).
5. Before deploying anywhere, confirm with the builder: Vercel account access, and that GEMINI_API_KEY / SERPER_API_KEY will need to become Vercel environment variables (server-side only, never shipped to the browser bundle). Give exhaustive click-by-click steps for both the Vercel account step and the environment variable step, same standard as every other hands-on step this project has needed.
6. State the estimated cost before any run that calls Gemini or Serper, same as every phase so far, though Phase 5 itself is not expected to introduce new per-call costs beyond what Phases 3 and 4 already do.
7. After Phase 5, Phase 6 is README assembly from context-full.md: architecture record, cost analysis (now has 4 phases of real measured data), trade-off log (occasion mapping choice, Serper link limitation, search-cap behaviour), eval results (56 deterministic tests across 4 test files), v2 roadmap.
8. Update context-full.md and next-session.md before the session ends, same as always.

## Standing guardrails (duplicated in CLAUDE.md, which Claude Code auto-reads)
- Never print or write either API key anywhere. Ask before every run that costs money, stating estimated cost.
- Budget $40 hard cap, measured spend to date roughly $0.0101 total. Bias toward shipping given the timebox.
- Explain everything non-technically, one concept at a time. Confirm before high-stakes steps.
- Timebox: roughly 1.5 days of build time remained as of session 4. Sessions 4-6 combined have consumed real time on the deprecation saga plus Phases 1-4. Phase 5 (UI + deploy) is likely the largest remaining time risk: new tooling (Vercel) the builder has not touched before, needs exhaustive click-by-click steps throughout.
- Do not re-litigate locked decisions, point at context-full.md section 5 first.

## Starting the next session
Open Claude Code, same local session on Documents\wardrobe-stylist (files are already on disk, nothing needs to be re-uploaded). First message to send:

> Read CLAUDE.md, context-full.md and next-session.md in this folder fully before doing anything. Then confirm what you read by giving me one short table: current phase, what's next, your plan. After I confirm, follow next-session.md's "exact resume point" section in order. Repeat back the key rules (never print my API key, ask before every run that costs money with an estimate, explain non-technically) before starting.

## If resuming in the web chat instead
Attach context-full.md, next-session.md and the relevant script files, use starter-prompt.md as before. The web chat cannot run anything, so it reverts to the old model: it writes, the builder runs and pastes output.
