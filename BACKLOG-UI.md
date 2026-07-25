# EDOS — UI Backlog (Product Layer, PDF-centered)

**Reference = `EDOS_v3_Walkthrough.pdf` (25 pages).** EDOS is a **decision-intelligence workspace**, NOT a
chat app. Home screen = **Project Brain**; everything flows back to it. This backlog builds the product layer
+ UI on top of the Phase-1/2 engine (graph, persistence, retrieval, conflicts, watchdog — already built).

**Key rename (user decision): "Confidence" → "Coverage".**
Coverage = *how complete the project's engineering context is* (0–100%). It grows as the engineer adds
context/datasheets and answers the domain question-set. **Coverage is optional** — EDOS works without it —
but higher coverage = better, more-grounded results; the UI nudges "fill these to raise coverage." Never a
fabricated number: coverage = a transparent function of what's actually in the project.

**Ground rules (unchanged):** contracts = authority · one responsibility per engine · immutable+versioned
decisions · no fabrication · every ticket test-green (backend) · PDF is the visual/behavioral source of truth.

**Ticket key:** `PDF` = pages/concept · `Backend` = new API/engine work · `UI` = frontend · `AC` = acceptance
· `Resume` = where to pick up. Build top-to-bottom; each UI-CP is a resumable checkpoint (branch `ui-cp-N`).

---

## 🗺️ UI CHECKPOINT SEQUENCE (canonical)

| CP | Name | Core | PDF |
|---|---|---|---|
| **UI-CP-0** | Workspace shell | left nav + project open/create/delete + Project Brain scaffold (kill chat UI) | p2 |
| **UI-CP-1** | Project Brain (home) | coverage bar + stat tiles + decision-coverage by domain + mode entries | p2, p5, p9, p23 |
| **UI-CP-2** | Coverage engine + question-set | coverage computation, domain question-set, "raise coverage" nudges | (user spec) |
| **UI-CP-3** | Engineering Review → Findings | fast no-question scan → categorized findings | p3–6, p16–19 |
| **UI-CP-4** | Deep Dive → Decision Card | targeted Q&A ("why am I asking?") → rich Decision Card | p7–8, p10, p14 |
| **UI-CP-5** | Challenge My Decision | argue against own rec, tie to assumption + cost | p11 |
| **UI-CP-6** | Assumptions (first-class) + lifecycle | A-ids, Created→Validated→Challenged→Invalidated | p5, p11, p22 |
| **UI-CP-7** | Decision Graph + Cross-Contradiction + Diff | graph view, cross-decision conflicts, decision diff | p12–13, p20–22 |
| **UI-CP-8** | Assumption Decay Alert (background) | scheduled re-check → alerts | p21 |
| **UI-CP-9** | Execution Context | machine-readable spec export ("EDOS decides, agents execute") | p24 |
| **UI-CP-10** | Timeline + Cert Matrix + Research Workspace | replay, cert matrix, sources per decision | p8, p23, p7 |

**Reuse map (engine already built → product surface):** graph/`conflicts_with` → contradictions & graph ·
domain rules → hidden-dependency/best-practice findings · watchdog → decay alerts · retriever → context ·
decision store/versioning → decision cards & diffs · resolution → assumption lifecycle · faithfulness → evidence.

---

## Coverage model (replaces confidence) — the spec

**Overall coverage** = weighted mean of **6 domain coverages** (Architecture, Hardware, Firmware,
Manufacturing, Testing, Certification). Each domain coverage rises from three inputs:

1. **Context items** tagged to that domain (requirements/decisions/constraints ingested).
2. **Documents/datasheets** attached to that domain.
3. **Question-set answers** — each domain has a checklist of key questions; answering raises coverage.

`domain_coverage = clamp( w1·min(items/target,1) + w2·min(docs/target,1) + w3·(answered/total_questions) )`
Weights + targets are **tunable** (user), not fabricated. Nothing mandatory — an empty project = 0% coverage,
still fully usable; the bar just tells the engineer "add X to get a more grounded result."

---

## UI-CP-0 — Workspace shell
**PDF:** overall layout (dark, purple accent, card-based). **Depends:** — (projects API exists).
**UI:** replace the chat SPA. Left rail = projects (create/open/**delete**). Main = router with a **Project
Brain** home + mode views. EDOS wordmark. No chat bubbles anywhere.
**Backend:** none (projects CRUD done).
- [x] 0.1 App shell + left rail + routing (Brain / Review / Deep Dive / Graph / Execution Context tabs).
- [x] 0.2 Project create / open / delete wired.
- [x] 0.3 Design tokens matching PDF (colors, category chips, severity pills).
**AC:** open app → pick/create project → land on Project Brain (not chat). Delete works. **Resume:** shell in place.

---

## UI-CP-1 — Project Brain (home dashboard)
**PDF:** p2 (Day-0 brain), p5/p9/p23 (updated brains). **Depends:** UI-CP-0, UI-CP-2 (coverage) — build the
static shell first, wire live numbers after CP-2.
**Backend:** `GET /v1/projects/{id}/brain` → `{ coverage, coverage_by_domain[6], counts:{decisions,
assumptions, contradictions, open_risks} }`. Counts from decision store + graph + watchdog.
**UI:** big **Coverage** bar (gradient, %), 4 stat tiles, **Decision Coverage** grid (6 domains, % bars),
"Start Engineering Review" + "Deep Dive" buttons.
- [x] 1.1 `GET /brain` endpoint (counts + coverage). 1.2 Coverage bar + tiles. 1.3 Domain coverage grid.
  1.4 Mode-entry buttons.
**AC:** empty project = 0% coverage, 0 counts; after review/decisions the numbers rise. **Resume:** brain renders live.

---

## UI-CP-2 — Coverage engine + question-set
**PDF:** user spec (coverage grows with context/datasheets/answers; optional).
**Backend:** `engines/coverage.py` (formula above); domain question-set (`GET /v1/projects/{id}/coverage` →
per-domain breakdown + unanswered questions); `POST /v1/projects/{id}/coverage/answer {domain, question_id,
answer}` (answer → ingested as context + raises coverage). Document attach endpoint (reuse items,
`item_type=document`, domain tag). Add optional `domain` tag to ProjectItem.
**UI:** coverage detail panel — per-domain %, "answer these to raise coverage" checklist, attach-datasheet.
- [x] 2.1 ProjectItem `domain` tag (+ migration). 2.2 coverage.py + `GET /coverage`. 2.3 question-set +
  `POST /coverage/answer`. 2.4 UI coverage panel + nudges.
**AC:** answering a question / adding a datasheet raises that domain's coverage; nothing is mandatory. **Resume:** coverage live-computed.

---

## UI-CP-3 — Engineering Review → Findings
**PDF:** p3–6, p16–19 (fast scan, categorized findings, "IF YOU IGNORE THIS", evidence).
**Backend:** `engines/findings.py` + `POST /v1/projects/{id}/review {text}` → `findings[]` each
`{category: contradiction|hidden_dependency|assumption|optimization|best_practice, severity, title, detail,
if_ignored:[...], evidence:[...]}`. Sources: **graph** (contradictions vs past decisions), **domain rules**
(hidden-dep/best-practice), **LLM** (the rest, stub→heuristic fallback). No questions asked (fast).
**UI:** review input → findings list, color-coded cards per category, severity pill, "IF YOU IGNORE THIS"
box, evidence chips, "Save to Project Brain" (findings feed counts + coverage).
- [x] 3.1 findings.py (rules+graph+LLM merge). 3.2 `POST /review`. 3.3 UI findings cards. 3.4 save-to-brain.
**AC:** a BMS-style input surfaces contradictions/hidden-deps/assumptions with consequences + evidence, no questions. **Resume:** review returns findings.

---

## UI-CP-4 — Deep Dive → Decision Card
**PDF:** p7–8, p10, p14 (5–8 "why am I asking?" questions → rich Decision Card).
**Backend:** (a) `POST /v1/projects/{id}/deepdive {topic}` → `questions[]` each `{q, why}` (planner LLM,
stub→heuristic). (b) `POST /v1/projects/{id}/deepdive/decide {topic, answers[]}` → rich **Decision Card**:
extend the decision envelope with `comparison_matrix` (criteria×options, recommended flag), `decision_impact`
(if-changes→affected areas), `impacted_components`, `review_conditions`. (Keep locked decision contract pure;
richer fields live in the persistence envelope / a `decision_detail` block — same stance as CP-11.)
**UI:** Deep Dive Q&A (each question shows "why am I asking?"), then Decision Card: comparison matrix (★),
recommendation + why-others-eliminated, Decision Impact grid, Risks & Blind Spots, **Decision Explorer**
(deps/related/assumptions/impacted/review-conditions), Accept, Share link.
- [x] 4.1 deepdive questions. 4.2 decide → rich card (envelope fields). 4.3 UI Q&A flow. 4.4 UI Decision Card. 4.5 Accept+writeback.
**AC:** topic → targeted questions with rationale → a Decision Card matching the PDF layout. **Resume:** decision card renders.

---

## UI-CP-5 — Challenge My Decision (the iconic interaction)
**PDF:** p11. **Depends:** UI-CP-4, UI-CP-6.
**Backend:** `POST /v1/decisions/{id}/challenge` → picks the load-bearing assumption, argues the counter-case
(what that assumption costs vs the alternative), with a cost estimate; returns `{assumption, this_costs[],
alternative_offers[], cost_callout}`. LLM-driven (stub→structured heuristic). Marking the assumption
`challenged` reuses CP-15 resolution → assumption becomes a *monitored* risk.
**UI:** ⚡ "Challenge This Decision" → side-by-side "what A-x is costing you" vs "what the alternative offers",
red cost callout, "Mark assumption as Challenged".
- [x] 5.1 challenge engine (`engines/challenge.py`: load-bearing pick + stub→heuristic counter-case, no
  fabricated $ offline). 5.2 `POST /v1/decisions/{id}/challenge` + `/challenge/accept`. 5.3 UI challenge
  panel (two-column costing-you/alternative-offers + red cost callout). 5.4 mark-challenged →
  `resolution.challenge_assumption` (assumption → monitored risk).
**AC:** challenging DR surfaces the assumption + $ cost; marking it flips it to a tracked risk. **Resume:** challenge flow works.

---

## UI-CP-6 — Assumptions first-class + lifecycle
**PDF:** p5, p11, p22 (A1–A22, Created→Validated→Challenged→Invalidated).
**Backend:** promote assumptions to first-class rows (`Assumption` table: id `A{n}`, project_id, statement,
status, source_decision, risk_if_wrong, created_at) so they persist, get IDs, cross-decision, and feed decay
alerts. Endpoints: list, set-status (validate/challenge/invalidate). Extraction (CP smart-ask) also creates them.
**UI:** assumptions panel (chips with status color), per-decision assumption chips, status transitions.
- [x] 6.1 Assumption table + migration. 6.2 CRUD/status endpoints. 6.3 wire decisions→assumptions. 6.4 UI panel.
  Assumption table (`A{n}` per project, lifecycle status) + alembic `0010_assumptions`; `engines/assumptions.py`;
  `GET /projects/{id}/assumptions` + `POST /assumptions/{aid}/status`; decisions (persist + deep-dive) mirror
  inline assumptions into first-class rows; resolution challenge/resolve flips matching row status;
  `/brain` assumptions count now live (open/resolved split); UI Assumptions panel + status chips on Decision Card.
**AC:** assumptions have stable IDs + lifecycle; challenging/validating updates status + coverage. **Resume:** assumptions first-class.

---

## UI-CP-7 — Decision Graph + Cross-Contradiction + Diff
**PDF:** p12–13, p20–22 (graph, cross-decision contradiction, decision diff).
**Backend:** `GET /v1/projects/{id}/graph` → nodes (decisions+assumptions) + edges (deps/conflicts/supersedes)
for viz; `GET /v1/decisions/{id}/diff` → `{from, to, why_changed[], affected[]}` between versions;
cross-contradiction already via `conflicts_with` + watchdog.
**UI:** graph canvas (nodes color by type/validity, dashed = challenged/invalidated), cross-decision
contradiction cards, Decision Diff card (struck-through old → new, why changed, affected).
- [x] 7.1 `GET /graph`. 7.2 decision diff. 7.3 UI graph. 7.4 UI diff + cross-contradiction cards.
  `engines/graph_view.py` (build_graph / decision_diff / contradictions — deterministic, no LLM);
  `GET /projects/{id}/graph` (decision+assumption nodes, deps/conflicts/supersedes edges + assumption→decision
  links, stable ids, `conflict:true` marks contradictions, decision validity derived from touching edges);
  `GET /projects/{id}/contradictions` (conflicts_with pairs → labels + explanation);
  `GET /decisions/{id}/diff?from&to` (defaults to=latest/from=parent; single-version → empty diff; why_changed
  from summary/status/confidence/assumption + decision_impact deltas, affected from impacted_components/
  decision_impact/affected_decisions); UI Decision Graph tab = inline SVG (purple decision nodes, dashed
  challenged/invalidated assumptions, red conflicts_with edges) + cross-contradiction cards + diff viewer
  (struck-through old→new, why-changed / affected). `tests/test_graph_diff.py` (7 tests).
**AC:** changing a decision shows a diff + surfaces impacts; graph renders the decision web. **Resume:** graph+diff live.

---

## UI-CP-8 — Assumption Decay Alert (background)
**PDF:** p21 ("the moment a prompt could never reach").
**Backend:** scheduled watchdog pass over active assumptions/decisions (age + cross-decision conflict check)
→ alerts (reuse watchdog + conflicts). Optional notify hook (ntfy/email).
**UI:** alerts feed on Project Brain (decay alerts, cross-decision contradictions caught in background).
- [x] 8.1 scheduled scan. 8.2 alert surfacing. 8.3 UI alerts feed.
  `engines/decay.py` (`decay_scan(session, project_id, now=None, age_days=30)` — composes the first-class
  assumption ledger + `graph_view.contradictions`, no LLM): (a) aged still-`created` assumptions older than
  `age_days` → `assumption_decay` (medium, "needs re-validation (age N days)"); (b) `conflicts_with` pairs →
  `cross_decision_contradiction` (high, or **critical** when an assumption is an endpoint or is sourced from a
  conflicting decision — the "A12 forced-air vs IP67" moment, naming both sides + the participating
  assumption). `now` is injectable so the 30-day trigger is deterministic (tests back-date `created_at` + pass
  `now`). `GET /projects/{id}/decay-alerts?age_days&as_of` (`as_of` = injectable now); `/alerts` unchanged.
  Best-effort ntfy notify hook (`notify_critical_contradiction`, opt-in `EDOS_DECAY_NOTIFY=1`, never in tests,
  failure non-fatal). Project Brain renders a distinct "⚠ Background review" feed. `tests/test_decay.py`
  (9 tests).
**AC:** an aged assumption that now conflicts (e.g., IP67 vs forced-air) raises a background alert. **Resume:** decay alerts fire.

---

## UI-CP-9 — Execution Context (the handoff)
**PDF:** p24 ("EDOS decides. Agents execute."). **This is the day-1 goal.**
**Backend:** `GET /v1/projects/{id}/execution-context` → structured, machine-readable spec: Accepted Decisions,
Constraints, Interfaces, Acceptance Criteria, Standards, Open Risks — assembled from accepted decisions +
assumptions + findings. JSON + copyable text.
**UI:** Execution Context view (the dark spec card from the PDF) + copy/export for any coding agent.
- [x] 9.1 execution-context assembler. 9.2 endpoint (json+text). 9.3 UI view + copy.
  `engines/execution_context.py` (`build(session, project_id, now=None)` + `to_text` — deterministic, no LLM):
  ACCEPTED DECISIONS (latest `accepted` decisions, or latest `recommended` marked **provisional** when none
  accepted; each with summary/recommendation + `key_params` from the decision_detail comparison_matrix
  recommended option + impacted_components); CONSTRAINTS (requirement/constraint items + decision_detail
  review_conditions + high/critical risk mitigations); INTERFACES (decision_detail impacted_components +
  whole-token protocol scan SPI/isoSPI/CAN/I2C/UART/BLE/ADC/GPIO/…); ACCEPTANCE CRITERIA (accepted decisions'
  next_actions + measurable requirement items); STANDARDS (regex scan ISO 26262/AEC-Q100/UN 38.3/AIS 156/ECE
  R100/IEC 62619/IP67/ASIL/…); OPEN RISKS (open=created/challenged first-class assumptions + active
  `conflicts_with` contradictions + accepted-decision freeze_blockers). `meta`: project_id / injected
  `generated_at` (None offline → deterministic) / coverage (`coverage_report`). `GET
  /projects/{id}/execution-context` (JSON, `?format=text`) + `GET …/execution-context.txt` (plain-text spec).
  UI Execution Context tab = the dark spec card (PDF p24 sections + "EDOS decides. Agents execute.") with a
  **Copy spec** button that copies the .txt form. `tests/test_execution_context.py` (12 tests).
**AC:** a project with accepted decisions emits a coherent spec a coding agent can consume. **Resume:** exec-context exports.

---

## UI-CP-10 — Timeline + Certification Matrix + Research Workspace
**PDF:** p23 (timeline/replay), p8 (cert matrix), p7 (research workspace).
**Backend:** timeline from decision/finding/assumption events (+ coverage at each step); cert-matrix
generator (standards×regions×cost×timeline) as a finding/tool; research workspace = documents/sources linked
to a decision (reuse items `item_type=document` + decision link).
**UI:** timeline rail (day-by-day + coverage badge), cert matrix table, research workspace panel per decision.
- [ ] 10.1 timeline events. 10.2 cert matrix. 10.3 research workspace links. 10.4 UI for each.
**AC:** replay shows the project's decision history with coverage growth; sources visible per decision. **Resume:** timeline+matrix+sources.

---

## Backend additions summary (new work beyond Phase-2)
`engines/coverage.py` · `engines/findings.py` · `engines/challenge.py` · `engines/execution_context.py` ·
`Assumption` table (first-class) · ProjectItem `domain` tag · decision envelope extras (comparison_matrix,
decision_impact, impacted_components, review_conditions) · endpoints: `/brain`, `/coverage(+answer)`,
`/review`, `/deepdive(+decide)`, `/decisions/{id}/challenge`, `/graph`, `/decisions/{id}/diff`,
`/execution-context`, `/timeline`. All LLM parts stub→heuristic fallback (tests green offline), real LLM live.

## Sequence
```
UI-CP-0 shell → 1 Brain → 2 Coverage → 3 Review/Findings → 4 Deep Dive/Decision Card
→ 5 Challenge → 6 Assumptions → 7 Graph/Diff → 8 Decay Alert → 9 Execution Context → 10 Timeline/Matrix
```
Each is a resumable branch `ui-cp-N`; backend tickets ship with their UI-CP so the surface always has data.
