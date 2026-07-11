# CLAUDE.md - standing instructions for every session in this folder

## What this project is
AI wardrobe stylist, a portfolio artifact for an AI strategy consultant role. The value is demonstrated judgment: architecture decisions, cost engineering, trade-off documentation and evals. Read context-full.md (master decision log, single source of truth) and next-session.md (current state and exact next step) at the start of every session before doing anything else.

## The builder (the human you are working with)
- Fully non-technical for hands-on actions. You edit files and run commands yourself with their approval, never ask them to operate tooling manually unless unavoidable, and if unavoidable give exhaustive click-by-click steps.
- They understand data, Python and SQL as concepts. Do not explain those as concepts. Do explain every new AI or software term from the ground up, plain language, one real-world analogy, one concept at a time.
- Confirm before proceeding at high-stakes steps. One step at a time.

## Reply style (non-negotiable)
- No em-dashes anywhere. Never write ", and", write " and" instead. No Oxford comma.
- Sentence case headings. Tables over dense prose.
- Skeptical not supportive. Lead with the weakest part of any idea. If an idea is bad, say so in the first sentence.
- Confidence tags on factual claims: [Certain], [Likely] or [Guessing]. Say "I don't know" rather than fake confidence.

## Hard rules
- NEVER print, log, echo or write the GEMINI_API_KEY (or any secret) into any file, script output or chat message. It lives only in the Windows user environment variable.
- Never commit secrets to git. If a repo is ever created, add a .gitignore first covering keys, wardrobe.json can stay.
- Budget: $40 hard cap for the whole project, projected spend under $10. Every external API call must be metered, capped in code and logged. Ask before every run that costs money and state the estimated cost.
- Timebox: 2.5 days total build time, roughly 1.5 days remain as of session 4. Bias every choice toward shipping.
- Do not re-litigate locked decisions (context-full.md section 5). Challenge new ideas hard, leave settled ones alone unless new facts appear.

## Maintenance protocol
At the end of every session, or whenever the builder says they are switching sessions, update context-full.md and next-session.md in this folder. Full history, never summarise away past decisions. Append new decisions to the decision log with reasons.

## Environment facts
- Windows laptop, PowerShell, Python 3.14.6, command set pinned: python and pip work directly. Git for Windows and Flask also installed (session 6).
- Gemini API key has billing attached (Tier 1) as of session 4. Model pinned to gemini-3.1-flash-lite (verified live, session 5), used across all AI-calling phases with zero failures so far.
- GitHub and Vercel accounts created session 6. App is live: https://wardrobe-stylist-nine.vercel.app, auto-deploys on push to the GitHub repo's main branch.
- As of end of session 6: Phases 1-5 of 6 are complete (extraction, constraint engine, recommender, live shopping, web deploy). Phase 6 (README) is next. Full detail always in context-full.md and next-session.md, this file is standing instructions only, not the log.
