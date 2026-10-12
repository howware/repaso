# Changelog

## 0.1.0 — first version

- Protocol for spaced review led by the agent: a topic and its study plan in units, cards from the conversation or
  from the owner's material, a daily session of a few minutes (one question at a time, answered in the owner's
  words and graded by the agent with a rubric), the answer shown only on a miss, fixing a card or a grade, progress,
  settings, and coming back after a break without guilt.
- `repaso.py`: `setup`, `config`, `topic`, `plan`, `add`, `edit`, `card-state`, `cards`, `session`, `grade`,
  `brief`, `stats`, `topics`. FSRS-6 with its default parameters, day-based, with deterministic fuzz; checked
  against reference values from py-fsrs. Each card's schedule is recomputed from its reviews. The session fits its
  minutes (30 s a review, 1 min a new card, 2 min a plan card taught first; due cards first, most at risk first; new cards only without a backlog, up to the daily limit, one plan
  unit at a time). Streak with freezes per month, milestones, mastery per unit and topic, measured retention, pace
  for a deadline. A plan card's first grade is at most good (it was taught a minute before). Errors as JSON with
  exit codes 2 and 3.
- `howware.json` lists `claude-code` in `hosts`: used in a real conversation on Claude Code.
- Requires project-memory 0.4.0. Built with `howware-builder`; the process is recorded in `docs/building.md`.
