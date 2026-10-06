# Mahlzeit: MVP product brief

Oct 6, 2026 · @Jonas

## Summary

Mahlzeit (working title) is a private web app for one couple to plan meals, shop, track food and log training. Every feature is usable by hand; AI is an optional extra. It runs as one installable PWA on Android and desktop, backed by a small self-hostable server.

The core loop is plan, shop, stock, cook, log. The home screen answers one question: what has each of us eaten and planned today, and what is left?

**How to use this brief (Claude Code).** Build milestone by milestone, M0 to M6. The principles in the next section override convenience. Where the brief is silent, choose the simplest option that satisfies the principles and record it in `docs/decisions.md`. Ask before changing the stack, a core entity of the data model or the scope of a milestone.

## Principles

Seven rules decide every trade-off; a feature that breaks one is not done.

1. **Manual first.** Every feature works completely without any AI model. AI is an option the user switches on, never a dependency and never the default.
2. **One service layer, four clients.** The UI, the Claude connector, the in-app assistant and background jobs all call the same service functions, with the same validation and permissions. No client gets a private code path.
3. **Every feature ships with its tools.** A feature is done when it has a UI path, registered tools for the same operations, tests for both, and strings in all three languages.
4. **Roughly right beats exact.** Stock is advisory. Logging is never blocked by stock, missing data or missing targets.
5. **List first for the partner.** The shopping list is the flagship. It must be the fastest thing in the app, work offline in a supermarket and sync between phones within seconds.
6. **Portable by construction.** Everything runs from one Docker Compose file with no provider-specific services, so the same stack moves from a rented server to an on-prem machine.
7. **Private where it matters.** Households are isolated from each other. Inside a household, each person controls what the other sees, and body metrics are private by default. Secrets never leave the server.

## Users

The product has two users with different habits, and the same screens must serve both.

| Aspect | Tracker | List-first partner |
| --- | --- | --- |
| Wants | Hit daily macro targets, log training, plan around what is left today | A shared shopping list that just works, and to know what is for dinner |
| Logging style | Weighs protein and added fat, eyeballs the rest; often logs by typing a list | Logs only if it takes seconds; portions by feel |
| Targets | Calories, protein, carbohydrate, fat; different on training and rest days | None at first; optional later |
| AI | Uses Claude chat daily and wants the connector | No Claude account; may use the in-app assistant on shared usage |

Both use Android phones with Chrome, plus desktop browsers. A household is a couple: the data model allows up to four members, but every screen is designed for two. Other couples can join the same instance later, each as their own household.

## Scope

The MVP covers the full loop by hand, plus the Claude connector and an optional in-app assistant. Receipt scanning and automatic planning wait in the backlog.

**In the MVP**

- Accounts, households of two (the model allows four), invite-only sign-up
- Profiles with optional targets, training and rest day types, visibility toggles
- Item catalogue: German generic foods, branded products by barcode, custom items
- Day timeline for both people, food logging, saved meals
- Recipes, planning up to 30 days ahead, joint meals, offers with push notifications
- Shared shopping list with offline use and suggestions
- Stock from purchases minus logged food, with quick corrections
- Workout log, weight and waist, a fixed analytics page
- Claude connector with read and write tools
- Optional AI layer: model-agnostic provider settings, shared usage, in-app assistant
- German, English and Dutch, switchable per user

**Not in the MVP**

- Native apps or app-store releases
- Receipt photos, eBon import and retailer account connectors (first backlog item, designed in this brief)
- Automatic meal-plan generation or macro-fitting
- Leftovers, expiry dates, spend analytics
- Open public sign-up, payments
- Health-platform sync, micronutrient views

## Domain model

The model is built around one meal entity that is either planned or logged, and one stock ledger that every purchase and every logged meal writes to.

| Entity | What it holds | Rules |
| --- | --- | --- |
| User | Login, display name, language, time zone | Belongs to one household in the MVP |
| Household | Members and invites | At most 4 members; all food data is scoped to it |
| Profile | Targets, weekly training pattern, visibility and sharing toggles | Targets are optional and dated, so changes keep their history |
| Item | A food or product: names in three languages, brand, barcodes, category, base unit (g or ml), nutrition per 100, package size, serving sizes, tracking mode | Generic seed items are global and read-only; all others belong to a household |
| Recipe | Name, servings, ingredients (item and amount), optional cooked yield, notes; kind is recipe or saved meal | Nutrition is always computed from the ingredients |
| Meal entry | Date, slot, time, components (item and amount, or quick-add macros), optional recipe reference | One entry can have several participants |
| Meal participant | One person's part in a meal entry: state (planned, logged, skipped) and share | Intake is components times share; exact amounts per component can override the share |
| Offer | A proposed joint meal for a date and slot, from one member to another | States: pending, accepted, declined, countered, withdrawn, expired |
| Shopping list item | Item or free text, quantity, store, category, checked state, origin | One shared list per household |
| Purchase | Store, date, lines (item or free text, quantity, optional price) | Confirming a purchase writes stock movements |
| Stock movement | Item, signed amount, reason (purchase, consumption, correction, waste), source reference | Stock level is the sum of movements and is never shown below zero |
| Exercise, template, session, set | Training library, planned sessions, logged sets | A set records weight and reps, or time, or distance, or a combination |
| Body metric | Date, weight, waist | One per person per day |
| AI provider config | Provider type, base URL, model, encrypted key, sharing flag, monthly cap | Owned by one user; never readable by any client |
| Change record | Who changed what, through which client (ui, connector, assistant, job) | Written for every write; powers undo for AI-made changes |

Nutrition is stored per 100 g or 100 ml: energy in kcal, protein, carbohydrate, sugar, fat, saturated fat, fibre, salt, and alcohol where known. Energy is stored as given and never recomputed from the macros.

## Accounts, profile and catalogue

Sign-up is by invite only, targets are optional, and the catalogue grows from what the household scans instead of from a bulk import.

### Accounts and households

- An admin command creates the first user and issues invites for further households.
- A member invites their partner with a link or code; accepting it joins the same household.
- Login is email and password. Password reset works by email when SMTP is configured, and by admin command when it is not.

### Profile and targets

- Targets are calories, protein, carbohydrate and fat, all optional. A profile without targets shows totals only.
- A profile may hold different targets for training and rest days, with a weekly pattern that sets each day's default type. The type can be changed on any day, and a logged workout marks the day as training.
- Each target set has a start date. Past days are always compared with the targets that were valid on that day.
- Food logs and targets are always visible to the partner, because joint planning depends on them. Switches per person: show my workouts (default on), show my weight and waist (default off), share my AI usage (default off), and whether the app opens on Today or on the List.

### Catalogue

- Search is instant and local. It covers items the household has used first, then generic foods, in all three languages, and tolerates typos. Nothing calls an external service while the user types.
- Barcode scanning uses the phone camera. An unknown code is looked up in Open Food Facts and imported with one tap. An incomplete product opens the label form with the known values filled in.
- The label form mirrors a German nutrition label: values per 100 g or ml, package size, and optional serving sizes such as one egg or one slice.
- 'Search online' is an explicit action for products without a barcode at hand.
- Generic foods come from a curated subset of the German BLS database, starting with about 300 common foods including the staples in the appendix.
- Each item has a category that doubles as the shopping-list aisle, an optional default store, and a tracking mode: counted, or status only for staples such as oil and spices.
- Target: a new branded product goes from scan to logged in under 20 seconds.

## Day, logging, recipes and planning

The app opens on today: two columns, one per person, in time order, showing what was eaten and what is still planned.

### Day timeline

- Slots are breakfast, lunch, dinner and snack. The first three are anchors; a snack can sit anywhere in the day, and there can be several.
- Every entry has a time. Defaults are 08:00, 12:30 and 19:00 for the anchors and the current time for a snack. Dragging an entry up or down changes its time and its place in the order.
- A joint meal spans both columns. An empty anchor slot shows a dash.
- Planned entries are outlined and logged entries are solid.
- Each column header shows logged totals against targets and what is left. A second line shows the projection if everything planned is eaten.
- Any past day can be opened, and planning reaches 30 days ahead.

### Logging

- Add to a slot from recent and favourite items, catalogue search, a barcode, a saved meal, a recipe, or quick-add (a name plus calories, macros optional).
- A planned entry is logged with one tap on 'Eaten'; amounts can be adjusted afterwards.
- Logging a joint meal logs it for both people by default. Each person can change or remove their own part.
- Shares are set by feel: half and half by default, with presets and a slider. A person who weighs can enter exact amounts for single components instead.
- 'Copy from' repeats an entry or a whole day from the past.
- Quick-add entries and entries marked 'eaten out' do not touch stock.

### Recipes and saved meals

- A recipe has servings and ingredients from the catalogue, and its nutrition per serving is computed. With a cooked yield in grams, a portion can also be logged by cooked weight.
- A saved meal is a one-serving recipe for one-tap logging, such as a usual breakfast.
- Recipes can be marked as staples. 'Add ingredients to list' puts what is missing on the shopping list.

### Planning and offers

- People make plans: pick a staple recipe, items or free text for a date and slot. Nothing is generated automatically.
- A planned meal can be offered to the partner, who gets a push notification and an in-app badge.
- The offer card shows the meal and, if the receiver has targets, what their share does to the rest of their day.
- Accept makes the meal joint and replaces the receiver's own planned entry in that slot. Logged entries are never replaced.
- Decline leaves the sender's plan as their own.
- Counter sends a different meal back for the same slot. If it is accepted, it replaces the sender's plan.
- Either person can send a new offer for a slot at any time, also after one was accepted. Pending offers can be withdrawn, and they expire when the day ends.

## Shopping list and stock

The shopping list is the feature the partner will judge the app by, so its speed and offline behaviour are part of its definition of done.

### Shopping list

- One shared list per household. A change appears on the other phone within 3 seconds when both are online.
- Adding takes one field. Suggestions come from the household's own history first, then the catalogue. Anything else is added as free text, non-food included.
- Quantity and store are optional. Stores: ALDI, Lidl, EDEKA, REWE, Netto, Penny, dm, other, plus custom ones.
- Items are grouped by aisle category. A free-text item remembers the category it was last moved to.
- Checking off works offline. Offline changes queue on the phone and sync without duplicates when the connection returns.
- Shopping mode: large rows, checked items sink to the bottom, undo, screen stays awake.
- A 'Suggested' section sits under the list and never adds anything by itself:
  - missing ingredients for meals planned in the next 3 days (configurable)
  - staples marked low or out
  - usual purchases that are not in stock, once there is enough history
- 'Bought' turns all checked items into one purchase: pick the store, adjust quantities, confirm. Food items go into stock and the checked items leave the list.
- Budgets: the list is usable within 1 second on a repeat visit, and adding ten items takes under a minute.

### Stock

- Stock goes up with purchases: from the list through 'Bought', by barcode, or by hand. A price per line is optional.
- Stock goes down when meals are logged. A joint meal deducts the whole dish once.
- Counted items track an amount. Status-only items show ok, low or out and are flipped with a tap.
- Stock never blocks logging and is never shown below zero. A shortfall is recorded quietly as a correction.
- Pantry check: go through a category, fix amounts with a stepper, or mark the category as checked. Thirty items should take under 2 minutes.
- Every change is a movement in a ledger, so a report can compare purchased, logged, wasted and corrected amounts per item.

## Training, body metrics, analytics, notifications, languages

Training and body data live in the same app but stay personal: each person decides what the other sees.

### Workouts

- An exercise has a measurement type: weight and reps, bodyweight reps with optional added or assisting weight, time, distance, or weight with time or distance. Per-side exercises are flagged.
- Templates hold an ordered list of exercises with target sets. The five training days in the appendix are seeded as the tracker's templates.
- A session starts from a template or empty. While logging, each exercise shows the sets from the previous session, with a 'same as last' shortcut.
- History per exercise shows the top set of each session and flags personal records.
- Visible to the partner by default, with a switch to hide.

### Body metrics

- Weight daily and waist weekly, one tap from the day view. The 7-day average is the number shown first.
- Private by default, with a switch to share.

### Analytics

One page with a period selector of 7, 30 or 90 days:

- Nutrition: calories and protein against target per day, and days on target
- Body: 7-day average weight, and waist
- Food: most eaten items and recipes
- Shopping: most purchased items overall and by store, spend where prices exist, purchased versus logged per item
- Training: sessions per week, how often each exercise is done, top-set trend for chosen lifts

Each report is also a connector tool, so questions beyond this page can be asked in chat.

### Notifications

- Web push for a new offer and for a counter-offer, with a switch per user. Everything else is an in-app badge.

### Languages

- German, English and Dutch on every screen, set per user. No hard-coded strings.
- Item names fall back from the user's language to German, then English. Numbers and dates follow the language.
- Draft translations are acceptable at each milestone; Jonas reviews German and Dutch.

## AI layer

AI reaches the app through three optional surfaces that share one set of tools, so anything AI can do a person can do by hand, and the reverse.

| Surface | Runs where | Paid by | Needs |
| --- | --- | --- | --- |
| Claude connector | In a Claude chat on web, desktop or phone | The person's own Claude plan | A Claude account per person |
| In-app assistant | Inside the app, in an 'Ask' panel | The configured provider key | A provider config the person owns or shares in |
| Background jobs | On the server, on a schedule | The configured provider key | The same, plus the job switched on |

### One tool registry

- Each tool is defined once: name, description, input schema, the service function it calls, and whether it reads or writes.
- The registry is exported to the connector as MCP tools and handed to the in-app assistant for tool calling. Jobs call the same service functions.
- Tools act as the signed-in user, with that user's permissions and visibility.
- Every write records which client made it and can be undone for 24 hours. In the UI, AI-made changes are labelled and offer undo.
- When no provider is available to a user, no AI entry point is shown.

### Providers and sharing

- One provider interface with two adapters: Anthropic, and OpenAI-compatible with a custom base URL. The second covers other hosted providers and local runtimes on an on-prem server.
- Settings: provider, base URL, model, API key, and a 'test connection' button. The MVP default is Claude Haiku 4.5. Switching model or provider is a settings change, never a code change.
- The key is encrypted at rest, write-only in the UI and never sent to any client.
- 'Share my AI usage' lets the partner use the in-app assistant and the jobs on the owner's key. It shares usage only: the partner never sees the key or the account behind it. The owner sees usage per person and can set a monthly cap.
- A Claude chat account cannot be shared through the app. A partner who wants the chat connector needs their own Claude account.

### Connector tools

The connector is served under `/mcp`. Its tools grow with the milestones:

| Area | Read | Write |
| --- | --- | --- |
| Day | get\_day, get\_household\_snapshot | log\_food, log\_planned\_meal, update\_entry, delete\_entry |
| Catalogue | search\_items, get\_item | create\_item, update\_item |
| Recipes | list\_recipes, get\_recipe | create\_recipe, update\_recipe |
| Plan | get\_meal\_plan, list\_offers | plan\_meal, send\_offer, respond\_to\_offer |
| List | get\_shopping\_list | add\_list\_items, check\_list\_items, remove\_list\_items |
| Stock | get\_stock | record\_purchase, adjust\_stock |
| Training and body | get\_workouts, get\_body\_metrics | log\_workout, log\_body\_metric |
| Analytics | get\_report |  |
| Safety | list\_changes | undo\_change |

`get_household_snapshot` returns in one call both people's remaining macros for today, tonight's plan, pending offers, the shopping list and a stock summary. It is the tool behind 'what should we cook tonight'.

### Receipts (first backlog item, designed now)

- A receipt inbox holds documents from any source: photo, PDF upload, Android share-to-app, later e-mail forwarding and per-person retailer account connectors that can be shared with the household.
- Each document passes through optional steps: a rule-based parser for known PDF formats, a lookup of remembered line-to-item matches per store, and an AI step that reads and matches the rest.
- The AI step runs as a batch job every few hours or on demand, through the same provider interface. Without a provider, the document waits for manual entry beside its image.
- Parsed receipts always land in a review screen. Stock changes only when a person confirms.
- Retailer account connectors would rely on unofficial interfaces. Treat them as optional adapters that can break, store their credentials encrypted, and prefer share-to-app and e-mail forwarding.

## Architecture

One backend service with one database serves the PWA, the connector, the assistant and the jobs, packaged so the same Compose file runs on a rented server today and on-prem later.

&#91;embedded content: architecture · four clients, one service layer\]

People, Claude, the in-app assistant and the jobs all go through the same service layer. The dashed parts can be switched off without losing a feature.

### Stack

| Part | Choice |
| --- | --- |
| Backend | Python 3.12 or newer, FastAPI, SQLAlchemy 2 with Alembic, Pydantic 2 |
| Database | PostgreSQL 16 or newer, with trigram search |
| Frontend | TypeScript, React, Vite, installable PWA with a service worker, TanStack Query, i18next, a drag-and-drop library |
| API | REST with OpenAPI; the TypeScript client is generated from the schema |
| Connector | An MCP server library for Python (the official SDK or FastMCP), mounted in the same service at `/mcp` |
| Jobs | A worker process from the same codebase; queue and schedule live in Postgres |
| Proxy and TLS | Caddy |
| Containers | caddy, app, worker, db; one `docker compose up` |

No Redis, no object storage, no hosted auth service, no vendor SDKs beyond the AI adapters. Files are stored on a mounted volume behind a small storage interface.

### Layers

- `domain`: pure logic for nutrition maths, shares, the stock ledger, offer states and suggestions.
- `services`: transactions, permissions and change records. This is the only layer that writes.
- Adapters on top: `api` (REST for the UI), `tools` (the registry, exported to MCP and to the assistant), `assistant` (provider calls and the tool loop), `jobs`.
- Adapters contain no business rules.

### Sign-in and connector auth

- App sessions: email and password hashed with Argon2id, server-side sessions in HttpOnly cookies, CSRF protection, rate-limited login.
- Connector, step 1 (M1): each user gets a personal connector URL containing a long random token and adds it in Claude as a custom connector with no sign-in. The token is stored hashed, shown once, can be revoked and rotated in settings, and is never logged.
- Connector, step 2 (before a second household joins): OAuth 2.1 with PKCE, so people sign in instead of pasting a URL. Use a vetted, self-hostable component or the MCP library's own support, not hand-written protocol code. Claude can identify itself with a pre-registered client ID, dynamic registration or its published client metadata; choose what the component supports. Run a short spike first and record the choice.

### Sync and offline

- The server is the source of truth. The client caches queries and updates optimistically.
- A server-sent event stream per household tells clients what changed, and they refetch. Polling every 15 seconds is the fallback.
- The shopping list works offline: changes queue in the browser with client-made ids and idempotency keys. Conflicts resolve per field, last write wins, and a removed item stays removed.
- Other screens show cached data offline and need a connection to write.

### Data sources

- Generic foods: BLS 4.0 from the Max Rubner-Institut, open data under CC BY 4.0 with the institute named as publisher. The main Excel file holds the BLS code, the German name and the English name, then values per 100 g of edible portion. An import script builds the curated seed; Dutch names are added in a reviewed seed file.
- Branded products: Open Food Facts, under the Open Database License. Use API v3 product reads for barcodes, and text search only on the explicit 'search online' action.
- Open Food Facts allows 15 product reads and 10 searches per minute per IP address and rules out search-as-you-type. Route both calls through a server-side rate limiter, cache the results, and send a User-Agent of the form `AppName/Version (ContactEmail)`. Fill in their API usage form before going live.
- Show attribution for both sources on an About screen, and keep the source and source id on every imported item.
- No scraping of retailer websites.

### Deployment

- Now: any EU server that runs Docker; 2 vCPU and 4 GB RAM is comfortable. The budget is 20 euros a month in total, domain and backups included.
- Later: the same Compose file on an on-prem machine with a static IP. It needs a public DNS name, ports 80 and 443 and outbound HTTPS. The PWA and push require HTTPS, and the server must be reachable from the internet for the Claude connector.
- Everything is configured through environment variables. One `BASE_URL` drives the connector metadata, the PWA manifest and push.
- Moving is backup, copy, restore, switch DNS. The backup and restore scripts are written and tested in M0.
- Local models: point the provider config at a local OpenAI-compatible endpoint. An optional Compose profile can add a local runtime and is off by default.

### Security and privacy

- Every query is scoped to the caller's household in the service layer. Tests attempt cross-household access on every endpoint and every tool.
- Visibility toggles are enforced on the server, including in tools and reports.
- API keys, push keys and any future retailer credentials are encrypted with a key from the environment and never logged.
- Nothing is sent to an AI provider unless a provider is configured and the person uses an AI feature or has switched on an AI job.
- Backups stored off the machine are encrypted.

### Quality

- Unit tests for domain logic, API tests for every endpoint, and a test for every tool through the registry.
- An end-to-end smoke test on a mobile viewport covers: join by invite, log food, plan a meal and accept an offer, use the list offline and sync, 'Bought', stock.
- The full test suite passes with AI switched off. CI runs lint, type checks, tests and image builds on every push.

## Milestones

Seven milestones, each usable by itself; the first three put the tracker's log and the partner's list on both phones.

| # | Name | Delivers | Done when |
| --- | --- | --- | --- |
| M0 | Foundation | Repo, Compose stack, CI, migrations, invite-only sign-in, households, PWA shell in three languages, push plumbing, deployment with TLS, backup and restore | Both people install the PWA from the live URL, log in and switch language; a restore from backup has been run once |
| M1 | Track | Catalogue (seed, search, barcode, custom items), targets and day types, day timeline, logging, saved meals, connector with personal URLs and the day and catalogue tools | One full day is logged through the UI and another through Claude chat; totals match a hand calculation; scan-to-logged takes under 20 seconds |
| M2 | List | Shared shopping list with history-based adding, stores, categories, live sync, offline queue, shopping mode, list tools | A change shows on the other phone within 3 seconds; a shop done in airplane mode syncs cleanly afterwards |
| M3 | Plan together | Recipes, planning to 30 days, joint meals with shares, offers with push, one-tap 'Eaten', drag to reorder, plan and recipe tools | A week of dinners is planned from staple recipes; offer, counter and accept work across two phones with push |
| M4 | Stock | Purchases, 'Bought' from the list, stock ledger, deduction from logs, tracking modes, pantry check, list suggestions, stock tools | After one shop and three days of logging, the purchased-versus-logged report is plausible; a 30-item pantry check takes under 2 minutes |
| M5 | Train and measure | Exercise library, templates, sessions with last-session display, weight and waist, visibility toggles, analytics page, matching tools | The five seeded training days can be logged one-handed in the gym; a weekly review comes from one report call |
| M6 | Optional AI | Provider settings, encrypted keys, shared usage with a cap, usage log, in-app assistant on the tool registry, undo, job hooks | With no provider, no AI entry point is visible and all tests pass; with Haiku configured, a dinner question in the app ends, after confirmation, in a planned joint meal and list items; switching provider needs settings only |

## Backlog

Nothing here is built in the MVP; the order is the current priority.

1. Receipt inbox: photo, PDF and share-to-app capture, rule-based eBon parsing, AI batch matching, review screen.
2. Automatic receipt intake: e-mail forwarding first, then per-person retailer account connectors with household sharing and scheduled checks.
3. Suggestions without AI: restock predictions from purchase rhythm, aisle order per store.
4. Macro-fitting planner: fill the rest of a day or a week so both people hit their targets.
5. Leftovers and batch cooking; expiry dates.
6. Spend analytics and price history.
7. Target wizard for people who start without targets.
8. Screens for three and four members.
9. Sending new products back to Open Food Facts.

Required before a second household joins, whatever its place in this list: connector sign-in through OAuth, and a data export per household.

## Decisions to confirm

Seven choices in this brief were made on Jonas's behalf and are cheap to change before M0 starts.

| # | Decision | Why | Alternative |
| --- | --- | --- | --- |
| 1 | The backend is a portable container stack (FastAPI and Postgres) instead of Supabase | On-prem later, background jobs and one service layer; the same four containers run anywhere | Supabase cloud now and self-hosted Supabase later: free at first with sign-in ready-made, but about ten services to run on-prem and logic split across SQL policies and TypeScript functions |
| 2 | 'Share usage' means sharing AI usage of the in-app assistant and jobs, with the key hidden | A Claude chat account is personal; an API key used on the server can serve the household | Each person brings their own key |
| 3 | The connector starts with a personal URL per user; OAuth sign-in comes before a second household joins | The connector works in M1 without security-critical protocol code | OAuth from day one |
| 4 | A joint meal is logged for both people when either taps 'Eaten', with shares by feel | It makes the partner's logging effortless | Each person confirms their own part |
| 5 | The shopping list (M2) is built before planning (M3) | It is the partner's reason to open the app | Planning first |
| 6 | AI-parsed receipts always need a person's confirmation before stock changes | A wrong match would silently corrupt stock | Auto-book lines that match a remembered item |
| 7 | 'Mahlzeit' is a working title | The repo needs a name | Any other name |

## Kickoff prompt for Claude Code

Paste this as the first prompt, with this brief saved in the repository as `docs/brief.md`.

```text
You are building Mahlzeit, a private web app for couples to plan meals, shop, track food and log training. The full product brief is in docs/brief.md. Read all of it before doing anything else.

Work in this order:

1. Reply with (a) the questions and risks you see in the brief, (b) a proposed repository layout, (c) the data model as a Mermaid ER diagram, and (d) a task list for milestone M0 only. Then stop and wait for my go.
2. After my go, implement M0 and nothing beyond it. Keep commits small and the main branch green.
3. At the end of the milestone, show me how to run it locally and how to deploy it, and list what you verified against the milestone's "Done when" column.

Rules for the whole project:

- The principles in the brief override convenience. Every feature must work fully without any AI model.
- All business rules live in the service layer. The REST API, the tool registry, the assistant and the jobs are thin adapters over it.
- A feature is done only when it has its UI path, its registered tools, tests for both, and German, English and Dutch strings.
- Everything runs from one Docker Compose file and is configured by environment variables. Do not add managed or provider-specific services.
- Write tests first for domain logic: nutrition maths, shares, the stock ledger, offer states, permissions. Include tests that attempt cross-household access.
- Record every decision the brief leaves open in docs/decisions.md, one line each. Ask me before changing the stack, a core entity or a milestone's scope.
- Maintain CLAUDE.md with the commands to run, test, lint and migrate, and the conventions you set.
- Check current documentation before using a library's API, in particular the MCP server library and the Open Food Facts API.
- Never commit secrets. Provide .env.example.
```

For each later milestone, the prompt is one line: implement the next milestone from the brief, starting with its task list.

## Appendix: seed data

These lists make the app useful on day one: the tracker's staple foods as favourites and his five training days as templates.

### Staple foods

Seed these as generic items from the BLS, raw unless noted, and mark them as favourites for the first household:

- Protein: chicken breast, pork loin, beef sirloin, ribeye, salmon, canned tuna in water, skyr, eggs, whey protein, skim milk, whole milk
- Carbohydrates: rice (dry), pasta (dry), potatoes, oats, bread rolls, kidney beans (canned), bananas, blueberries, raspberries, watermelon, honey, jam
- Fat and vegetables: olive oil, avocado, Gouda or Edam, broccoli, green beans, peppers, tomatoes, cucumber

Skyr and whey protein are brand-specific in practice. Seed generic entries and let barcode scans replace them.

### Serving sizes

| Item | One serving |
| --- | --- |
| Egg | 55 g |
| Bread roll | 70 g |
| Cheese, one portion | 30 g |
| Whey, one scoop | 30 g |
| Honey, one portion | 20 g |
| Olive oil, one portion | 10 g |

### Workout templates

| Day | Exercises (sets x reps unless noted) |
| --- | --- |
| 1 Hinge | Deadlift 4x6; Romanian deadlift 3x8; hip thrust 3x10; lying leg curl 3x12; farmer's walk 3 x 40 m; pull-ups 4x2 |
| 2 Pull | Pull-ups 3 x max minus 1; pull-up negatives 3 x 5 s; assisted pull-ups 3x8; barbell row 4x6; lat pulldown 3x10; chest-supported row 3x12; face pull 3x15; EZ curl 3x10 |
| 3 Carry and core | Zercher carry 4 x 45 s; front-rack carry 3 x 45 s; suitcase carry 3 x 40 m per side; hanging leg raise 3x12; ab wheel or cable crunch 3x12; back extension 3x15 |
| 4 Squat | Back squat 4x6; front squat 3x6; Bulgarian split squat 3x10 per leg; leg press 3x12; calf raise 3x15; pull-ups 4x2 |
| 5 Push | Bench press 4x6; overhead press 4x6; incline dumbbell press 3x10; dips 3x8; lateral raise 3x15; triceps pushdown 3x12 |

Together these use every measurement type the workout log must support: weight and reps, bodyweight and assisted reps, time, distance and per-side work.

## Sources

Facts about external services were checked on 6 October 2026 against these pages:

- [BLS 4.0 FAQ](https://blsdb.de/faq): file structure, values per 100 g
- [BLS download page](https://blsdb.de/download): CC BY 4.0 licence and citation
- [Open Food Facts API documentation](https://openfoodfacts.github.io/openfoodfacts-server/api/): licence, rate limits, User-Agent, API versions
- [Claude custom connectors with remote MCP](https://claude.com/docs/connectors/custom/remote-mcp): adding a connector, sign-in options
- [FastMCP authentication guide](https://gofastmcp.com/servers/auth/authentication.md): auth patterns and the caution against a hand-built OAuth server
- [Supabase self-hosting with Docker](https://supabase.com/docs/guides/self-hosting/docker): services in the self-hosted stack
- [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing): Haiku 4.5 and batch rates
