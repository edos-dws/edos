# Pending Queries — to resolve in one shot

Running list of issues the user is reporting during testing. **Do NOT resolve these individually** — record
only. The user will say when to "sort it in one shot" and then all open items get fixed together.

Status legend: 🔴 open · 🟡 in progress · ✅ done

---

## Q1 — Deep Dive re-asks questions the user already answered ✅ done
_Reported: 2026-07-26 · Fixed: 2026-07-26_

**Fix:** `_persist_answers` now stores the **question + answer** (`Q: … — A: …`) as project context, and the
frontend/decide-request carry the question text (`q`). Skip-known matches a new question's wording against the
stored Q&A, so an already-answered question is recognised and skipped. Verified in the e2e trace: Round-2 on
the same topic skipped the previously-answered questions.

**Symptom:** When generating clarification questions / passing context to the LLM, the **same question is
asked to the user multiple times**, even though the user already answered it in a prior round/session.

**Expected:**
- Once the user answers a question, that answer must be **stored** (project context / answered-questions
  store) so it is never re-asked.
- Question generation must **skip anything already answered or already known** from the project's
  graph/knowledge before showing questions to the user.
- Also improve question **quality** ("ask the better question and work as per that").

**Where to look when resolving (pointers, not action):**
- `src/edos/engines/deepdive.py` → `plan_questions()` (skip-known via `_covered_by` / embedder semantic match),
  `_persist_answers()` (answers → project context), `_candidate_questions()`.
- Verify the answered-questions actually persist across rounds/sessions and that the skip-known check fires
  against them (the semantic-match skip may not be catching prior answers).
- Coverage answered-questions store (`coverage/answer`) vs deep-dive answers — check both feed the skip logic.

---

## Q2 — Questions must be necessity-driven; 5 is a MAX not a default; add a zero-question confirmation path ✅ done
_Reported: 2026-07-26 · Fixed: 2026-07-26 · related to [Q1]_

**Fix:** prompt now asks for **0–5, only if necessary** (empty when context suffices); `_candidate_questions`
no longer forces ≥5 (honours the model's count, cap 5); `_heuristic_questions` returns only triggered probes
(≤5, a few essentials when nothing matches); `plan_questions` caps at 5 and returns an `understanding`. When
zero questions remain, the frontend shows a **confirmation card** ("My understanding … Agree & generate") that
goes straight to the decision. Verified in the e2e trace (Round-1 asked 4, not a forced 5).

**Symptom:** Deep Dive asks a fixed batch (~5 questions) **every time**, regardless of whether they're
needed. That's too much work for the user.

**Expected flow (by priority):**
- Ask questions **only if necessary** — not for everything.
- **5 = hard maximum**, never a default. Ask **fewer** when fewer matter; ask the highest-priority ones only.
- **Zero-question path:** if nothing needs asking, **don't ask anything** — instead show a **confirmation
  message** stating EDOS's understanding of the user's decision ("This is my understanding of what you're
  deciding — do you agree?") and **continue on agree**.
- Follow this flow end-to-end (question count scales to actual need).

**Where to look when resolving (pointers, not action):**
- `src/edos/engines/deepdive.py` → `plan_questions()` currently targets/asserts a 5–8 range; make count
  need-driven (0…5). `_candidate_questions()` for prioritisation.
- Zero-question `note` path already exists (`DD.note` / "project already has enough context") — extend it
  into the **understanding-confirmation** UX in `frontend/index.html` (`renderDeepDive` / `ddFollowup` /
  `ddDecide`), so 0 questions → show understanding summary → agree → decide.
- Tests assume `5 <= len(questions) <= 8` (`tests/test_deepdive.py`) — will need updating when resolved.

---

# Future features (not now — record only)

## F1 — "Enhance prompt" 🔵 future
_Reported: 2026-07-26_

Add an **Enhance prompt** feature (like the ✨ enhance/expand button in AI chat inputs) — lets the user take
their rough decision/topic text and have EDOS rewrite/expand it into a sharper, more complete problem
statement before running the Deep Dive / review.

**Notes:** user has "multiple things to check on this" and will flesh it out later. Placeholder for now.
Likely lives on the Deep Dive composer (and possibly the Engineering Review input). To scope when picked up:
which model tier, whether it edits in place vs shows a diff, and how it uses existing project context.
