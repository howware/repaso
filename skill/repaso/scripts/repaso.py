"""repaso — the exact operations of the spaced-review howware (learn and don't forget, without an app).

The agent makes the cards, asks them and grades the owner's answers. This tool decides when each card is due
(FSRS, the scheduler Anki uses), builds the daily session, and keeps the streak, the milestones and the mastery
of each topic. Each card's state is recomputed from its reviews every time, so nothing can drift.

Commands (JSON on stdout; errors as {"ok": false, "error": {"code", "message"}}):
  setup      load the predicates into the memory
  config     show or change the settings: desired retention, session minutes, new cards per day, streak freezes
  topic      add or change a topic: name, goal, deadline, language, state
  plan       set the units of a topic's study plan, in order (JSON)
  add        add cards to a topic or unit, in bulk (JSON); the same question twice is one card
  edit       correct a card, move it to another unit, or start it over (--reset)
  card-state pause, archive or reactivate a card
  cards      the cards of a topic or unit, with when each one is due
  session    what to ask now: due cards first, then new ones, within the session's minutes
  grade      record the agent's rating of one answer and schedule the card's next review
  brief      what to show at the start of a conversation
  stats      streak, milestones, mastery per topic and unit, measured retention, the cards missed most
  topics     the topics with their progress and the pace their deadline needs

Exit codes: 0 ok · 2 invalid input · 3 memory problem.
No network, no prompts, standard library only. Days are the owner's local calendar days.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

__version__ = "0.1.0"
HERE = Path(__file__).resolve().parent
SEED = HERE / "seed.json"
MIN_MEMORY = (0, 4, 0)
OK, BAD_INPUT, MEMORY_ERROR = 0, 2, 3
SETTINGS = "settings:repaso"
DEFAULTS = {"desired_retention_bp": 9000, "session_minutes": 5, "new_per_day": 5, "freezes_per_month": 2}
RATINGS = {"again": 1, "hard": 2, "good": 3, "easy": 4}
RATING_NAMES = {v: k for k, v in RATINGS.items()}
STATES = ("active", "paused", "archived")
ORIGINS = ("conversation", "material", "plan")
# what a review, a first view and a first view taught by the agent (plan cards) take, to fit a session in its
# minutes (the first real session: five plan cards took about ten minutes)
REVIEW_SECONDS, NEW_SECONDS, TAUGHT_SECONDS = 30, 60, 120
MASTERED_DAYS = 21                       # a card is mastered when FSRS expects it to last three weeks (Anki: mature)
UNIT_MASTERED = 0.8                      # a unit is mastered when 80% of its cards are
MILESTONES = {"mastered_cards": (10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
              "streak_days": (3, 7, 14, 30, 60, 100, 180, 365, 730),
              "units_mastered": (1, 3, 5, 10, 25, 50, 100)}
MAX_QUESTION, MAX_ANSWER = 500, 1500

# -- FSRS-6 (https://github.com/open-spaced-repetition/py-fsrs, MIT): default parameters and formulas -------------
# Day-based: no learning steps, so a card is always in review; a card missed is asked again in the same session
# and that second review uses FSRS's same-day formula. Fuzz is deterministic (from the review's key), so replaying
# the history always gives the same dates.
W = (0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666, 0.796, 1.4835, 0.0614, 0.2629,
     1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542)
DECAY = -W[20]
FACTOR = 0.9 ** (1 / DECAY) - 1
S_MIN, D_MIN, D_MAX, MAX_INTERVAL = 0.001, 1.0, 10.0, 36500
FUZZ_RANGES = ((2.5, 7.0, 0.15), (7.0, 20.0, 0.1), (20.0, math.inf, 0.05))


def retrievability(stability: float, elapsed_days: int) -> float:
    return (1 + FACTOR * max(0, elapsed_days) / stability) ** DECAY


def initial_difficulty(rating: int) -> float:
    return W[4] - math.e ** (W[5] * (rating - 1)) + 1


def clamp_d(d: float) -> float:
    return min(max(d, D_MIN), D_MAX)


def next_difficulty(d: float, rating: int) -> float:
    delta = -(W[6] * (rating - 3))
    damped = d + (10.0 - d) * delta / 9.0
    return clamp_d(W[7] * initial_difficulty(4) + (1 - W[7]) * damped)


def short_term_stability(s: float, rating: int) -> float:
    increase = math.e ** (W[17] * (rating - 3 + W[18])) * s ** -W[19]
    if rating >= 2:
        increase = max(increase, 1.0)
    return max(s * increase, S_MIN)


def next_stability(d: float, s: float, r: float, rating: int) -> float:
    if rating == 1:
        long_term = W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.e ** ((1 - r) * W[14])
        return max(min(long_term, s / math.e ** (W[17] * W[18])), S_MIN)
    hard = W[15] if rating == 2 else 1
    easy = W[16] if rating == 4 else 1
    return max(s * (1 + math.e ** W[8] * (11 - d) * s ** -W[9] * (math.e ** ((1 - r) * W[10]) - 1) * hard * easy),
               S_MIN)


def interval_days(s: float, retention: float) -> int:
    return min(max(round(s / FACTOR * (retention ** (1 / DECAY) - 1)), 1), MAX_INTERVAL)


def fuzz(days: int, seed: str) -> int:
    if days < 2.5:
        return days
    delta = 1.0 + sum(f * max(min(float(days), end) - start, 0.0) for start, end, f in FUZZ_RANGES)
    lo, hi = max(2, round(days - delta)), min(round(days + delta), MAX_INTERVAL)
    lo = min(lo, hi)
    u = int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16) / 16 ** 12   # deterministic, uniform in [0, 1)
    return min(round(u * (hi - lo + 1) + lo), MAX_INTERVAL)


def schedule(reviews: list[dict], retention: float) -> dict:
    """Replay a card's reviews (oldest first; each {"day": date, "rating": int, "key": str}) into its state."""
    s = d = None
    last = due = None
    lapses = 0
    days: list[tuple[date, date]] = []   # (day reviewed, due after it), for the history of what was due when
    for rv in reviews:
        rating, day = rv["rating"], rv["day"]
        if s is None:
            s, d = max(W[rating - 1], S_MIN), clamp_d(initial_difficulty(rating))
        else:
            elapsed = (day - last).days
            if elapsed < 1:
                s = short_term_stability(s, rating)
            else:
                s = next_stability(d, s, retrievability(s, elapsed), rating)
            d = next_difficulty(d, rating)
        lapses += rating == 1
        due = day + timedelta(days=fuzz(interval_days(s, retention), rv["key"]))
        last = day
        days.append((day, due))
    return {"stability": s, "difficulty": d, "last": last, "due": due, "reps": len(reviews), "lapses": lapses,
            "days": days}


class ToolError(Exception):
    def __init__(self, message: str, code: int = BAD_INPUT):
        super().__init__(message)
        self.code = code


# -- memory adapter -----------------------------------------------------------------------
def find_helper(explicit: str | None) -> Path:
    for c in (explicit, os.environ.get("HOWWARE_MEMORY_HELPER"),
              Path.home() / ".claude/skills/project-memory/scripts/memory.py",
              Path.home() / ".codex/skills/project-memory/scripts/memory.py"):
        if c and Path(c).is_file():
            return Path(c)
    raise ToolError("project-memory is not installed (or pass --mem / HOWWARE_MEMORY_HELPER).", MEMORY_ERROR)


class Memory:
    PAGE = 5000

    def __init__(self, helper: Path, db: str | None):
        self.helper, self.db = helper, db

    def command(self, args: tuple[str, ...]) -> list[str]:
        return [sys.executable, str(self.helper)] + (["--db", self.db] if self.db else []) + list(args)

    def run(self, *args: str, stdin: dict | None = None) -> Any:
        for attempt in (1, 2):
            cmd = self.command(args)
            proc = subprocess.run(cmd, input=json.dumps(stdin, ensure_ascii=False) if stdin is not None else None,
                                  capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 0:
                return json.loads(proc.stdout) if proc.stdout.strip() else None
            message = (proc.stderr or proc.stdout).strip()
            if attempt == 1 and "at least one second" in message:
                time.sleep(1.1)
                continue
            raise ToolError(f"memory {args[0]} failed: {message[-600:]}", MEMORY_ERROR)

    def check_version(self) -> None:
        out = subprocess.run([sys.executable, str(self.helper), "--version"], capture_output=True, text=True).stdout
        found = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
        if not found or tuple(int(x) for x in found.groups()) < MIN_MEMORY:
            raise ToolError(f"project-memory >= {'.'.join(map(str, MIN_MEMORY))} is required (found: {out.strip()}).",
                            MEMORY_ERROR)

    def rows(self, *args: str) -> list[dict]:
        return self.rows_many([args])[0]

    def rows_many(self, queries: list[tuple[str, ...]]) -> list[list[dict]]:
        """Several `list` queries at once, in parallel processes (each one costs a Python start); later pages,
        rarely needed, one by one."""
        procs = [subprocess.Popen(self.command(("list", *q, "--limit", str(self.PAGE))), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, encoding="utf-8") for q in queries]
        out = []
        for q, proc in zip(queries, procs):
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                raise ToolError(f"memory list failed: {(stderr or stdout).strip()[-600:]}", MEMORY_ERROR)
            page = json.loads(stdout)
            rows, offset = page["rows"], self.PAGE
            while page.get("truncated"):
                page = self.run("list", *q, "--limit", str(self.PAGE), "--offset", str(offset))
                rows += page["rows"]
                offset += self.PAGE
            out.append(rows)
        return out

    def write(self, by: str, content: str, kind: str = "user_statement", **sections) -> dict:
        return self.run("write", stdin={"source": {"type": kind, "content": content, "provided_by": by,
                                                   "captured_at": "now"},
                                        "performed_by": by, **sections})


# -- exact helpers ------------------------------------------------------------------------
def parse_offset(text: str) -> timezone:
    m = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", text.strip())
    if not m:
        raise ToolError(f"Time zone offset must look like -06:00, not {text!r}")
    minutes = int(m.group(2)) * 60 + int(m.group(3))
    return timezone(timedelta(minutes=minutes if m.group(1) == "+" else -minutes))


def local_offset() -> str:
    z = datetime.now().astimezone().strftime("%z")
    return f"{z[:3]}:{z[3:]}"


def parse_day(text: str, what: str = "date") -> date:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        raise ToolError(f"{what} must be YYYY-MM-DD, not {text!r}") from None


def noon(day: date, tz: timezone) -> str:
    return datetime(day.year, day.month, day.day, 12, tzinfo=tz).isoformat(timespec="seconds")


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "x"


def entity_key(kind: str, ref: str) -> str:
    return ref if ref.startswith(f"{kind}:") else f"{kind}:{slug(ref)}"


def card_key(topic: str, question: str) -> str:
    """The same question in the same topic is the same card, however it is spaced or capitalized."""
    norm = " ".join(unicodedata.normalize("NFKC", question).casefold().split())
    return f"card:{topic.split(':', 1)[1]}-{hashlib.sha256(norm.encode()).hexdigest()[:10]}"


def rating_of(text: str) -> int:
    value = RATINGS.get((text or "").strip().lower())
    if not value:
        raise ToolError(f"--rating is again, hard, good or easy, not {text!r}")
    return value


def percent(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def read_json(path: str) -> Any:
    try:
        # bytes, so stdin is UTF-8 whatever the console's code page (Windows would read it as cp1252)
        text = (sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()).decode("utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise ToolError(f"Cannot read {path} as UTF-8 text: {getattr(error, 'strerror', None) or error}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ToolError(f"{path} is not JSON (line {error.lineno}: {error.msg}).") from error


def text_field(value: Any, what: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"Every card needs a non-empty {what}.")
    value = value.strip()
    if len(value) > limit:
        raise ToolError(f"A card's {what} is {len(value)} characters; keep it under {limit} (split the card).")
    return value


# -- the library: settings, topics, units, cards and reviews, read once per command ---------------------------
TOPIC_FACTS = ("topic_goal", "topic_deadline", "topic_language", "topic_state")
UNIT_FACTS = ("in_topic/key", "unit_order", "unit_summary")
CARD_FACTS = ("card_question", "card_answer", "in_topic/key", "in_unit/key", "card_origin", "card_source_text",
              "card_seq", "card_state")


def columns(facts: tuple[str, ...]) -> list[str]:
    return [x for f in ("key", "name", *(f"fact:{f}" for f in facts)) for x in ("--column", f)]


class Library:
    def __init__(self, mem: Memory, tz: timezone, today: date):
        self.mem, self.tz, self.today = mem, tz, today
        event = lambda kind, *cols: ("--event-type", kind, *[x for c in ("key", "occurred_at", "link:about_card/key",
                                                                         *cols) for x in ("--column", c)])
        rows, topics, units, cards, resets, reviews = mem.rows_many([
            ("--entity-type", "settings", "--where", f"key = {SETTINGS}", *columns(tuple(DEFAULTS))),
            ("--entity-type", "topic", *columns(TOPIC_FACTS)), ("--entity-type", "unit", *columns(UNIT_FACTS)),
            ("--entity-type", "card", *columns(CARD_FACTS)), event("card_reset"),
            event("card_reviewed", "attr:rating", "attr:attempt")])
        self.reset_events = resets
        if not rows:
            raise ToolError("This memory has no repaso settings yet: run TOOL setup first.", MEMORY_ERROR)
        self.settings = {k: rows[0][f"fact:{k}"] if rows[0][f"fact:{k}"] is not None else v
                         for k, v in DEFAULTS.items()}
        self.retention = self.settings["desired_retention_bp"] / 10000
        self.topics = {r["key"]: {"key": r["key"], "name": r["name"], "goal": r["fact:topic_goal"],
                                  "deadline": day_of(r["fact:topic_deadline"]), "language": r["fact:topic_language"],
                                  "state": r["fact:topic_state"] or "active"}
                       for r in topics}
        self.units = {r["key"]: {"key": r["key"], "name": r["name"], "topic": r["fact:in_topic/key"],
                                 "order": r["fact:unit_order"], "summary": r["fact:unit_summary"]}
                      for r in units}
        self.cards = {}
        for r in cards:
            self.cards[r["key"]] = {"key": r["key"], "question": r["fact:card_question"],
                                    "answer": r["fact:card_answer"], "topic": r["fact:in_topic/key"],
                                    "unit": r["fact:in_unit/key"], "origin": r["fact:card_origin"],
                                    "source": r["fact:card_source_text"], "seq": r["fact:card_seq"] or 0,
                                    "state": r["fact:card_state"] or "active"}
        self.reviews: dict[str, list[dict]] = {}
        self.resets: dict[str, datetime] = {}
        for r in resets:
            at = datetime.fromisoformat(r["occurred_at"])
            self.resets[r["link:about_card/key"]] = max(at, self.resets.get(r["link:about_card/key"], at))
        for r in reviews:
            self.add_review(r["link:about_card/key"], r["key"], datetime.fromisoformat(r["occurred_at"]),
                            r["attr:rating"], r["attr:attempt"] or 1)
        self.rescore()

    def add_review(self, card: str, key: str, at: datetime, rating: int, attempt: int) -> None:
        if card in self.resets and at <= self.resets[card]:
            return
        self.reviews.setdefault(card, []).append({"key": key, "at": at, "day": at.astimezone(self.tz).date(),
                                                  "rating": rating, "attempt": attempt})

    def drop_review(self, card: str, key: str) -> None:
        self.reviews[card] = [r for r in self.reviews.get(card, []) if r["key"] != key]

    def rescore(self) -> None:
        for rvs in self.reviews.values():
            rvs.sort(key=lambda x: (x["at"], x["key"]))
        self.state = {k: schedule(self.reviews.get(k, []), self.retention) for k in self.cards}

    # -- what is live --------------------------------------------------------------------
    def live(self, card: dict) -> bool:
        return card["state"] == "active" and self.topics.get(card["topic"], {}).get("state", "active") == "active"

    def seen(self, key: str) -> bool:
        return bool(self.state[key]["reps"])

    def mastered(self, key: str, before: date | None = None) -> bool:
        st = self.state[key] if before is None else self.state_before(key, before)
        return bool(st["reps"]) and st["stability"] >= MASTERED_DAYS

    def state_before(self, key: str, day: date) -> dict:
        return schedule([r for r in self.reviews.get(key, []) if r["day"] < day], self.retention)

    def due_cards(self) -> list[str]:
        return [k for k, c in self.cards.items() if self.live(c) and self.seen(k) and self.state[k]["due"] <= self.today]

    def topic_cards(self, topic: str, unit: str | None = None) -> list[str]:
        return [k for k, c in self.cards.items() if c["topic"] == topic and c["state"] != "archived"
                and (unit is None or c["unit"] == unit)]

    def plan(self, topic: str) -> list[dict]:
        return sorted((u for u in self.units.values() if u["topic"] == topic), key=lambda u: (u["order"] or 0, u["key"]))

    def new_queue(self, topic: str) -> tuple[list[str], dict | None]:
        """Unseen cards of a topic in the order to introduce them, and the unit that needs cards next, if any.
        Cards from the conversation come first; then the plan, one unit at a time: a unit's cards open once
        every card of the units before it has been seen."""
        fresh = lambda keys: sorted((k for k in keys if self.cards[k]["state"] == "active" and not self.seen(k)),
                                    key=lambda k: (self.cards[k]["seq"], k))
        loose = [k for k in self.topic_cards(topic) if not self.cards[k]["unit"] or self.cards[k]["unit"] not in self.units]
        queue = fresh(loose)
        plan = self.plan(topic)
        for i, unit in enumerate(plan):
            keys = self.topic_cards(topic, unit["key"])
            if not keys:
                return queue, unit
            pending = fresh(keys)
            queue += pending
            if pending:      # the unit being introduced; the next one may need its cards soon
                following = plan[i + 1] if i + 1 < len(plan) else None
                return queue, following if following and not self.topic_cards(topic, following["key"]) else None
        return queue, None

    def new_today(self) -> int:
        return sum(1 for k in self.cards if self.reviews.get(k) and self.reviews[k][0]["day"] == self.today)

    # -- the streak ----------------------------------------------------------------------
    def days(self) -> dict[date, dict]:
        """Per day with something to do or done: reviews (first attempts) and cards that were due at its start."""
        out: dict[date, dict] = {}
        for k, rvs in self.reviews.items():
            for r in rvs:
                if r["attempt"] == 1:
                    out.setdefault(r["day"], {"reviews": 0, "due": 0})["reviews"] += 1
        for k, st in self.state.items():
            if not self.live(self.cards[k]):
                continue
            for (reviewed, due), nxt in zip(st["days"], [*st["days"][1:], None]):
                until = nxt[0] if nxt else self.today        # due from `due` until it is reviewed again
                d = due
                while d <= until and d <= self.today:
                    out.setdefault(d, {"reviews": 0, "due": 0})["due"] += 1
                    d += timedelta(days=1)
        return out

    def goal_met(self, info: dict) -> bool:
        per_session = self.settings["session_minutes"] * 60 // REVIEW_SECONDS
        return info["reviews"] > 0 and info["reviews"] >= min(per_session, info["due"])

    def streak(self, until: date | None = None) -> dict:
        until = until or self.today
        days = self.days()
        freezes = self.settings["freezes_per_month"]
        used: dict[tuple[int, int], int] = {}
        current = best = 0
        frozen: list[str] = []
        if days:
            d = min(days)
            while d <= until:
                info = days.get(d, {"reviews": 0, "due": 0})
                if self.goal_met(info):
                    current += 1
                elif info["due"] == 0 and info["reviews"] == 0:
                    pass                                          # nothing to do that day: neither counts nor breaks
                elif d == until:
                    pass                                          # today is not over
                elif used.get((d.year, d.month), 0) < freezes:
                    used[(d.year, d.month)] = used.get((d.year, d.month), 0) + 1
                    frozen.append(d.isoformat())
                else:
                    current = 0
                    frozen = []
                best = max(best, current)
                d += timedelta(days=1)
        today = days.get(until, {"reviews": 0, "due": 0})
        return {"days": current, "best": best, "today_done": self.goal_met(today),
                "today_reviews": today["reviews"], "freezes_left_this_month": freezes - used.get((until.year, until.month), 0),
                "freezes_used": frozen[-5:]}

    # -- progress and milestones -----------------------------------------------------------
    def unit_progress(self, unit: dict) -> dict:
        keys = [k for k in self.topic_cards(unit["topic"], unit["key"]) if self.cards[k]["state"] == "active"]
        m = sum(self.mastered(k) for k in keys)
        return {"unit": unit["key"], "name": unit["name"], "order": unit["order"], "cards": len(keys),
                "seen": sum(self.seen(k) for k in keys), "mastered": m, "mastery_percent": percent(m, len(keys)),
                "is_mastered": bool(keys) and m / len(keys) >= UNIT_MASTERED}

    def topic_progress(self, topic: dict) -> dict:
        keys = [k for k in self.topic_cards(topic["key"]) if self.cards[k]["state"] == "active"]
        seen, m = sum(self.seen(k) for k in keys), sum(self.mastered(k) for k in keys)
        units = [self.unit_progress(u) for u in self.plan(topic["key"])]
        out = {"topic": topic["key"], "name": topic["name"], "state": topic["state"], "language": topic["language"],
               "goal": topic["goal"], "cards": len(keys), "seen": seen, "mastered": m,
               "mastery_percent": percent(m, len(keys)), "due_today": sum(1 for k in self.due_cards()
                                                                          if self.cards[k]["topic"] == topic["key"]),
               "units": units, "units_without_cards": sum(1 for u in units if not u["cards"])}
        if topic["deadline"]:
            left = (topic["deadline"] - self.today).days
            unseen = len(keys) - seen
            need = math.ceil(unseen / left) if left > 0 else None
            out["deadline"] = {"date": topic["deadline"].isoformat(), "days_left": left, "unseen_cards": unseen,
                               "new_per_day_needed": need,
                               "on_pace": left > 0 and (need or 0) <= self.settings["new_per_day"],
                               **({"note": "units without cards yet are not counted"} if out["units_without_cards"]
                                  else {})}
        return out

    def counts(self, before: date | None = None) -> dict:
        keys = [k for k, c in self.cards.items() if c["state"] == "active"]
        units = 0
        for u in self.units.values():
            ks = [k for k in self.topic_cards(u["topic"], u["key"]) if self.cards[k]["state"] == "active"]
            units += bool(ks) and sum(self.mastered(k, before) for k in ks) / len(ks) >= UNIT_MASTERED
        return {"mastered_cards": sum(self.mastered(k, before) for k in keys), "units_mastered": units,
                "streak_days": self.streak(before - timedelta(days=1) if before else None)["days"]}

    def milestones(self) -> dict:
        now, before = self.counts(), self.counts(self.today)
        reached = {k: max([m for m in MILESTONES[k] if now[k] >= m], default=None) for k in MILESTONES}
        new = [{"kind": k, "value": m} for k in MILESTONES for m in MILESTONES[k] if before[k] < m <= now[k]]
        nxt = {k: next((m for m in MILESTONES[k] if m > now[k]), None) for k in MILESTONES}
        return {"counts": now, "reached": reached, "new_today": new, "next": nxt}

    def card_view(self, key: str, with_answer: bool = True) -> dict:
        c, st = self.cards[key], self.state[key]
        out = {"card": key, "question": c["question"], "topic": c["topic"],
               "unit": c["unit"], "state": c["state"], "origin": c["origin"], "source": c["source"]}
        if with_answer:
            out["answer"] = c["answer"]
        if st["reps"]:
            elapsed = (self.today - st["last"]).days
            out.update({"due": st["due"].isoformat(), "due_in_days": (st["due"] - self.today).days,
                        "last_review": st["last"].isoformat(), "reviews": st["reps"], "lapses": st["lapses"],
                        "stability_days": round(st["stability"], 1), "difficulty": round(st["difficulty"], 2),
                        "recall_percent_now": round(100 * retrievability(st["stability"], elapsed)),
                        "mastered": st["stability"] >= MASTERED_DAYS})
        else:
            out["new"] = True
        return out


def day_of(value: Any) -> date | None:
    return date.fromisoformat(str(value)[:10]) if value else None


# -- commands -------------------------------------------------------------------------------
def cmd_setup(mem: Memory, args, now: datetime) -> dict:
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    result = mem.write(args.by, f"repaso seed v{seed['seed_version']}", "helper_command",
                       predicates=[{**p, "distinct_from_similar": True} for p in seed["predicates"]],
                       entities=seed["entities"])
    for event_type in seed["high_volume_event_types"]:
        mem.run("define-event-type", "--type", event_type, "--high-volume", "--by", args.by,
                "--reason", "One per answer: thousands per year")
    return {"ok": True, "seed_version": seed["seed_version"], "settings": Library(mem, now.tzinfo, now.date()).settings,
            "warnings": result.get("warnings", [])}


def cmd_config(mem: Memory, args, now: datetime) -> dict:
    facts = []
    if args.retention is not None:
        if not 70 <= args.retention <= 97:
            raise ToolError("--retention is a percent from 70 to 97 (90 is the usual; higher means many more reviews).")
        facts.append(("desired_retention_bp", int(round(args.retention * 100))))
    for name, value, lo, hi in (("session_minutes", args.minutes, 1, 60), ("new_per_day", args.new_per_day, 0, 50),
                                ("freezes_per_month", args.freezes, 0, 10)):
        if value is not None:
            if not lo <= value <= hi:
                raise ToolError(f"--{name.replace('_', '-')} goes from {lo} to {hi}.")
            facts.append((name, value))
    if facts:
        if not args.by:
            raise ToolError("Changing a setting needs --by.")
        mem.write(args.by, args.source or "Settings changed",
                  facts=[{"subject": SETTINGS, "predicate": p, "value": v, "valid_from": "now"} for p, v in facts])
    lib = Library(mem, now.tzinfo, now.date())
    return {"ok": True, "settings": lib.settings, "changed": [p for p, _ in facts],
            "reviews_per_session": lib.settings["session_minutes"] * 60 // REVIEW_SECONDS}


def cmd_topic(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    key = entity_key("topic", args.key)
    current = lib.topics.get(key)
    if not current and not args.name:
        raise ToolError(f"New topic {key}: give it a --name.")
    entity = {"key": key, "type": "topic", "name": args.name or current["name"]}
    if current and args.name and args.name != current["name"]:
        entity["rename"] = True
    facts = []
    if args.goal:
        facts.append(("topic_goal", args.goal))
    if args.deadline:
        if args.deadline == "none":
            facts.append(("topic_deadline", None))
        else:
            day = parse_day(args.deadline, "--deadline")
            if day <= now.date():
                raise ToolError("--deadline must be after today.")
            facts.append(("topic_deadline", noon(day, now.tzinfo)))
    if args.language:
        facts.append(("topic_language", args.language))
    if args.state:
        if args.state not in STATES:
            raise ToolError(f"--state is {', '.join(STATES)}.")
        facts.append(("topic_state", args.state))
    elif not current:
        facts.append(("topic_state", "active"))
    result = mem.write(args.by, args.source or f"Topic {entity['name']}", entities=[entity],
                       facts=[{"subject": key, "predicate": p, "value": v, "valid_from": "now"}
                              for p, v in facts if v is not None],
                       **({"close": [{"subject": key, "predicate": p, "at": "now", "if_present": True}
                                     for p, v in facts if v is None]} if any(v is None for _, v in facts) else {}))
    return {"ok": True, "topic": key, "name": entity["name"], "created": not current,
            "warnings": result.get("warnings", [])}


def find_topic(lib: Library, ref: str) -> dict:
    key = entity_key("topic", ref)
    found = lib.topics.get(key) or next((t for t in lib.topics.values() if t["name"].lower() == ref.lower()), None)
    if not found:
        raise ToolError(f"No topic {ref!r} (topics: {', '.join(lib.topics) or 'none yet'}).")
    return found


def unit_key(topic: str, ref: str) -> str:
    return ref if ref.startswith("unit:") else f"unit:{topic.split(':', 1)[1]}-{slug(ref)}"


def cmd_plan(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    topic = find_topic(lib, args.topic)
    units = read_json(args.file)
    if not isinstance(units, list) or not units:
        raise ToolError('The plan is a JSON list: [{"name": "...", "summary": "..."}, ...], in study order.')
    entities, facts, keys = [], [], []
    for i, u in enumerate(units, 1):
        if not isinstance(u, dict) or not str(u.get("name", "")).strip():
            raise ToolError(f"Unit {i} of the plan needs a name.")
        key = unit_key(topic["key"], u.get("key") or u["name"])
        if key in keys:
            raise ToolError(f"Two units of the plan are the same: {key}.")
        keys.append(key)
        entities.append({"key": key, "type": "unit", "name": u["name"].strip(),
                         **({"rename": True} if key in lib.units and lib.units[key]["name"] != u["name"].strip() else {})})
        facts += [{"subject": key, "predicate": "in_topic", "value": topic["key"]},
                  {"subject": key, "predicate": "unit_order", "value": i}]
        if u.get("summary"):
            facts.append({"subject": key, "predicate": "unit_summary", "value": str(u["summary"]).strip()})
    missing = [u["key"] for u in lib.plan(topic["key"]) if u["key"] not in keys]
    if missing:
        raise ToolError("The plan must list every unit the topic already has, in the new order. Missing: "
                        + ", ".join(missing))
    mem.write(args.by, args.source or f"Study plan of {topic['name']}", entities=entities,
              facts=[{**f, "valid_from": "now"} for f in facts])
    lib = Library(mem, now.tzinfo, now.date())
    return {"ok": True, "topic": topic["key"], "units": [lib.unit_progress(u) for u in lib.plan(topic["key"])]}


def cmd_add(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    topic = find_topic(lib, args.topic)
    unit = None
    if args.unit:
        unit = unit_key(topic["key"], args.unit)
        if unit not in lib.units or lib.units[unit]["topic"] != topic["key"]:
            raise ToolError(f"No unit {args.unit!r} in {topic['key']} (TOOL plan first).")
    if args.origin not in ORIGINS:
        raise ToolError(f"--origin is {', '.join(ORIGINS)}.")
    cards = read_json(args.file)
    if isinstance(cards, dict):
        cards = [cards]
    if not isinstance(cards, list) or not cards:
        raise ToolError('Cards are a JSON list: [{"question": "...", "answer": "..."}, ...].')
    seq = max((c["seq"] for c in lib.cards.values()), default=0)
    entities, facts, created, existing, seen_now = [], [], [], [], set()
    for c in cards:
        if not isinstance(c, dict):
            raise ToolError("Each card is an object with question and answer.")
        q, a = text_field(c.get("question"), "question", MAX_QUESTION), text_field(c.get("answer"), "answer", MAX_ANSWER)
        key = card_key(topic["key"], q)
        if key in lib.cards or key in seen_now:
            existing.append({"card": key, "question": q})
            continue
        seen_now.add(key)
        seq += 1
        entities.append({"key": key, "type": "card", "name": q[:80]})
        values = {"card_question": q, "card_answer": a, "in_topic": topic["key"], "card_origin": args.origin,
                  "card_source_text": str(c.get("source") or args.source_text or "").strip() or None,
                  "card_seq": seq, "card_state": "active", "in_unit": unit}
        facts += [{"subject": key, "predicate": p, "value": v, "valid_from": "now"} for p, v in values.items()
                  if v is not None]
        created.append({"card": key, "question": q})
    if entities:
        mem.write(args.by, args.source or f"{len(entities)} cards for {topic['name']}", entities=entities, facts=facts)
    return {"ok": True, "topic": topic["key"], "unit": unit, "created": created, "existing": existing}


def find_card(lib: Library, ref: str) -> dict:
    found = lib.cards.get(ref if ref.startswith("card:") else f"card:{ref}")
    if not found:
        raise ToolError(f"No card {ref!r}.")
    return found


def cmd_edit(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    card = find_card(lib, args.card)
    facts = []
    if args.question:
        facts.append(("card_question", text_field(args.question, "question", MAX_QUESTION)))
    if args.answer:
        facts.append(("card_answer", text_field(args.answer, "answer", MAX_ANSWER)))
    if args.unit:
        unit = unit_key(card["topic"], args.unit)
        if unit not in lib.units or lib.units[unit]["topic"] != card["topic"]:
            raise ToolError(f"No unit {args.unit!r} in {card['topic']}.")
        facts.append(("in_unit", unit))
    if not facts and not args.reset:
        raise ToolError("Nothing to change: give --question, --answer, --unit or --reset.")
    reason = args.reason or args.source or "Card corrected"
    events = []
    if args.reset:
        n = sum(1 for r in lib.reset_events if r["link:about_card/key"] == card["key"])
        events.append({"key": f"RESET_{card['key'].split(':', 1)[1]}_{n + 1}", "type": "card_reset",
                       "occurred_at": now.isoformat(timespec="seconds"), "summary": f"Card started over: {reason[:100]}",
                       "attributes": {"reason_text": reason},
                       "links": [{"predicate": "about_card", "entity": card["key"]}]})
    mem.write(args.by, reason, facts=[{"subject": card["key"], "predicate": p, "value": v, "valid_from": "now"}
                                      for p, v in facts], **({"events": events} if events else {}))
    lib = Library(mem, now.tzinfo, now.date())
    return {"ok": True, **lib.card_view(card["key"]), "reset": bool(args.reset)}


def cmd_card_state(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    if args.state not in STATES:
        raise ToolError(f"--state is {', '.join(STATES)}.")
    keys = [find_card(lib, c)["key"] for c in args.card]
    mem.write(args.by, args.source or f"Cards {args.state}",
              facts=[{"subject": k, "predicate": "card_state", "value": args.state, "valid_from": "now"} for k in keys])
    return {"ok": True, "cards": keys, "state": args.state}


def cmd_cards(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    keys = list(lib.cards)
    if args.topic:
        topic = find_topic(lib, args.topic)
        keys = [k for k in keys if lib.cards[k]["topic"] == topic["key"]]
    if args.unit:
        unit = args.unit if args.unit.startswith("unit:") else None
        keys = [k for k in keys if lib.cards[k]["unit"] == unit or (unit is None and lib.cards[k]["unit"]
                and lib.cards[k]["unit"].endswith("-" + slug(args.unit)))]
    if args.state:
        keys = [k for k in keys if lib.cards[k]["state"] == args.state]
    if args.search:
        needle = args.search.casefold()
        keys = [k for k in keys if needle in (lib.cards[k]["question"] + " " + lib.cards[k]["answer"]).casefold()]
    keys.sort(key=lambda k: (lib.cards[k]["topic"], lib.cards[k]["seq"], k))
    return {"ok": True, "count": len(keys), "cards": [lib.card_view(k) for k in keys[:args.limit]]}


def build_session(lib: Library, minutes: int | None) -> dict:
    budget = (minutes or lib.settings["session_minutes"]) * 60
    due = lib.due_cards()
    # most at risk of being forgotten first: lowest recall now, then the most overdue
    due.sort(key=lambda k: (retrievability(lib.state[k]["stability"], (lib.today - lib.state[k]["last"]).days),
                            lib.state[k]["due"], k))
    capacity = budget // REVIEW_SECONDS
    review = due[:capacity]
    backlog = len(due) - len(review)
    left = budget - len(review) * REVIEW_SECONDS
    new, needs_cards = [], []
    allowance = max(0, lib.settings["new_per_day"] - lib.new_today())
    topics = sorted((t for t in lib.topics.values() if t["state"] == "active"),
                    key=lambda t: (t["deadline"] or date.max, t["key"]))
    queues = []
    for t in topics:
        queue, unit = lib.new_queue(t["key"])
        queues.append(queue)
        if unit and len(queue) < lib.settings["new_per_day"]:
            needs_cards.append({"topic": t["key"], "unit": unit["key"], "name": unit["name"], "summary": unit["summary"],
                                "unseen_left_in_topic": len(queue)})
    cost = lambda k: TAUGHT_SECONDS if lib.cards[k]["origin"] == "plan" else NEW_SECONDS
    if not backlog:
        added = True
        while allowance and added:                          # one topic at a time, in turns, while they fit
            added = False
            for q in queues:
                if q and allowance and cost(q[0]) <= left:
                    left -= cost(q[0])
                    new.append(q.pop(0))
                    allowance -= 1
                    added = True
    seconds = len(review) * REVIEW_SECONDS + sum(cost(k) for k in new)
    out = {"ok": True, "today": lib.today.isoformat(),
           "review": [lib.card_view(k) for k in review], "new": [lib.card_view(k) for k in new],
           "minutes": math.ceil(seconds / 60), "due_total": len(due), "backlog_after": backlog,
           "new_left_today": allowance, "needs_cards": needs_cards, "streak": lib.streak()}
    if backlog:
        out["catch_up_days"] = math.ceil(len(due) / max(capacity, 1))
    return out


def cmd_session(mem: Memory, args, now: datetime) -> dict:
    return build_session(Library(mem, now.tzinfo, now.date()), args.minutes)


def cmd_grade(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    card = find_card(lib, args.card)
    rating = rating_of(args.rating)
    # A plan card is taught and asked in the same minute: recalling it then says little about tomorrow, so its
    # first grade is at most good (easy would start it at eight days).
    capped = rating == 4 and card["origin"] == "plan" and not lib.reviews.get(card["key"])
    if capped:
        rating = 3
    if args.attempt not in (1, 2):
        raise ToolError("--attempt is 1 (first time today) or 2 (asked again after a miss).")
    before = lib.milestones()["counts"]
    stem = f"REV_{card['key'].split(':', 1)[1]}_{lib.today.strftime('%Y%m%d')}_{args.attempt}"
    today = [r for r in lib.reviews.get(card["key"], []) if r["day"] == lib.today and r["attempt"] == args.attempt]
    if today and not args.correct:
        prev = today[-1]
        return {"ok": True, "unchanged": True, "card": card["key"], "rating": RATING_NAMES[prev["rating"]],
                "message": "This card already has a grade for this attempt today. If it is a new answer after a miss, "
                           "use --attempt 2; to change the grade, --correct."}
    if args.correct:
        if not today:
            raise ToolError("--correct changes today's grade of this attempt, and there is none yet.")
        mem.run("void", "--event", today[-1]["key"], "--reason", args.source or "Grade corrected", "--by", args.by)
        stem += f"_c{now.strftime('%H%M%S')}"
    attrs = {"rating": rating, "attempt": args.attempt}
    if args.answer:
        attrs["answer_text"] = args.answer[:MAX_ANSWER]
    if args.correct:
        lib.drop_review(card["key"], today[-1]["key"])
    lib.add_review(card["key"], stem, now, rating, args.attempt)
    lib.rescore()      # the state after this review, computed here instead of reading everything again
    mem.write(args.by, args.answer or f"Review of {card['key']}", "user_statement", events=[{
        "key": stem, "type": "card_reviewed", "occurred_at": now.isoformat(timespec="seconds"),
        "summary": f"{RATING_NAMES[rating]}: {card['question'][:100]}", "attributes": attrs,
        "links": [{"predicate": "about_card", "entity": card["key"]}]}])
    after = lib.milestones()
    view = lib.card_view(card["key"], with_answer=False)
    reached = [{"kind": k, "value": m} for k in MILESTONES for m in MILESTONES[k] if before[k] < m <= after["counts"][k]]
    return {"ok": True, "card": card["key"], "rating": RATING_NAMES[rating], "attempt": args.attempt,
            "next_review": view["due"], "next_in_days": view["due_in_days"], "mastered": view["mastered"],
            "ask_again_this_session": rating == 1 and args.attempt == 1,
            **({"note": "First view of a card just taught: recorded as good, not easy."} if capped else {}),
            "streak": lib.streak(), "milestones_reached": reached}


def cmd_brief(mem: Memory, args, now: datetime) -> dict:
    try:
        lib = Library(mem, now.tzinfo, now.date())
    except ToolError as error:
        if error.code != MEMORY_ERROR:
            raise
        return {"ok": True, "today": now.date().isoformat(), "setup_needed": True,
                "message": "No memory or no repaso settings here yet: start the memory, then TOOL setup."}
    if not lib.topics:
        return {"ok": True, "today": lib.today.isoformat(), "empty": True}
    session = build_session(lib, None)
    last = max((r["day"] for rvs in lib.reviews.values() for r in rvs), default=None)
    deadlines = [p["deadline"] | {"topic": p["topic"], "name": p["name"]}
                 for p in (lib.topic_progress(t) for t in lib.topics.values() if t["state"] == "active")
                 if p.get("deadline")]
    return {"ok": True, "today": lib.today.isoformat(), "weekday": lib.today.strftime("%a").lower(),
            "to_review": len(session["review"]), "new": len(session["new"]), "minutes": session["minutes"],
            "due_total": session["due_total"], "backlog_after": session["backlog_after"],
            "days_since_last_review": (lib.today - last).days if last else None,
            "streak": session["streak"], "needs_cards": session["needs_cards"], "deadlines": deadlines,
            "milestones_next": lib.milestones()["next"]}


def cmd_stats(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    since = lib.today - timedelta(days=args.days)
    first = [r for k, rvs in lib.reviews.items() for i, r in enumerate(rvs)
             if i > 0 and r["attempt"] == 1 and r["day"] > since]     # reviews of cards seen before, first try of the day
    recalled = sum(1 for r in first if r["rating"] > 1)
    topics = [lib.topic_progress(t) for t in lib.topics.values() if t["state"] != "archived"
              and (not args.topic or t["key"] == find_topic(lib, args.topic)["key"])]
    hardest = sorted((k for k in lib.cards if lib.state[k]["lapses"] and lib.cards[k]["state"] == "active"),
                     key=lambda k: (-lib.state[k]["lapses"], -lib.state[k]["difficulty"], k))[:args.hardest]
    return {"ok": True, "today": lib.today.isoformat(), "streak": lib.streak(), "milestones": lib.milestones(),
            "retention": {"days": args.days, "reviews": len(first), "recalled": recalled,
                          "measured_percent": percent(recalled, len(first)),
                          "target_percent": lib.settings["desired_retention_bp"] // 100},
            "reviews_total": sum(len(v) for v in lib.reviews.values()), "topics": topics,
            "missed_most": [lib.card_view(k) for k in hardest]}


def cmd_topics(mem: Memory, args, now: datetime) -> dict:
    lib = Library(mem, now.tzinfo, now.date())
    return {"ok": True, "topics": [lib.topic_progress(t) for t in sorted(lib.topics.values(), key=lambda t: t["key"])
                                   if args.all or t["state"] != "archived"]}


# -- CLI ------------------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(prog="repaso.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"repaso.py {__version__}")
    p.add_argument("--mem", help="Path to project-memory's memory.py")
    p.add_argument("--db", help="Path to the memory (default: the current project's)")
    p.add_argument("--tz", default=os.environ.get("HOWWARE_TZ") or local_offset(), help="UTC offset, e.g. --tz=-07:00")
    p.add_argument("--now", default=os.environ.get("REPASO_NOW"), help=argparse.SUPPRESS)  # fixed clock for tests
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name: str, by: bool = True, source: bool = True):
        s = sub.add_parser(name)
        if by:
            s.add_argument("--by", required=True, help="person:<id> of the owner")
        if source:
            s.add_argument("--source", help="The owner's literal words")
        return s

    cmd("setup", source=False)
    s = cmd("config", by=False)
    s.add_argument("--by", help="person:<id> of the owner (needed to change a setting)")
    s.add_argument("--retention", type=float, help="desired retention in percent, 70-97 (default 90)")
    s.add_argument("--minutes", type=int, help="minutes of the daily session (default 5)")
    s.add_argument("--new-per-day", type=int, help="new cards per day (default 5)")
    s.add_argument("--freezes", type=int, help="streak freezes per month (default 2)")
    s = cmd("topic")
    s.add_argument("--key", required=True)
    s.add_argument("--name")
    s.add_argument("--goal", help="what for, in the owner's words")
    s.add_argument("--deadline", help="YYYY-MM-DD, or none")
    s.add_argument("--language", help="language of the cards, e.g. es")
    s.add_argument("--state", help=" | ".join(STATES))
    s = cmd("plan")
    s.add_argument("--topic", required=True)
    s.add_argument("--file", required=True, help='JSON list [{"name", "summary"}] in order, or - for stdin')
    s = cmd("add")
    s.add_argument("--topic", required=True)
    s.add_argument("--unit")
    s.add_argument("--origin", default="conversation", help=" | ".join(ORIGINS))
    s.add_argument("--source-text", help="where the cards came from, for every card without its own")
    s.add_argument("--file", required=True, help='JSON list [{"question", "answer", "source"}], or - for stdin')
    s = cmd("edit")
    s.add_argument("--card", required=True)
    s.add_argument("--question")
    s.add_argument("--answer")
    s.add_argument("--unit")
    s.add_argument("--reset", action="store_true", help="start the card over: its past reviews stop counting")
    s.add_argument("--reason", help="why, in the owner's words")
    s = cmd("card-state")
    s.add_argument("--card", required=True, action="append", help="repeatable")
    s.add_argument("--state", required=True, help=" | ".join(STATES))
    s = cmd("cards", by=False, source=False)
    s.add_argument("--topic")
    s.add_argument("--unit")
    s.add_argument("--state", help=" | ".join(STATES))
    s.add_argument("--search", help="text in the question or the answer")
    s.add_argument("--limit", type=int, default=200)
    s = cmd("session", by=False, source=False)
    s.add_argument("--minutes", type=int, help="this session only (default: the setting)")
    s = cmd("grade", source=True)
    s.add_argument("--card", required=True)
    s.add_argument("--rating", required=True, help="again | hard | good | easy")
    s.add_argument("--answer", help="what the owner answered, in their words")
    s.add_argument("--attempt", type=int, default=1, help="2 when asked again after a miss")
    s.add_argument("--correct", action="store_true", help="replace today's grade of this attempt")
    cmd("brief", by=False, source=False)
    s = cmd("stats", by=False, source=False)
    s.add_argument("--topic")
    s.add_argument("--days", type=int, default=30, help="window for the measured retention")
    s.add_argument("--hardest", type=int, default=5)
    s = cmd("topics", by=False, source=False)
    s.add_argument("--all", action="store_true", help="include archived topics")
    args = p.parse_args()

    commands = {"setup": cmd_setup, "config": cmd_config, "topic": cmd_topic, "plan": cmd_plan, "add": cmd_add,
                "edit": cmd_edit, "card-state": cmd_card_state, "cards": cmd_cards, "session": cmd_session,
                "grade": cmd_grade, "brief": cmd_brief, "stats": cmd_stats, "topics": cmd_topics}
    try:
        tz = parse_offset(args.tz)
        if args.now:
            try:
                now = datetime.fromisoformat(args.now).replace(tzinfo=tz)
            except ValueError:
                raise ToolError(f"--now must be YYYY-MM-DDTHH:MM, not {args.now!r}") from None
        else:
            now = datetime.now(tz).replace(microsecond=0)
        mem = Memory(find_helper(args.mem), args.db)
        mem.check_version()
        result, code = commands[args.command](mem, args, now), OK
    except ToolError as error:
        result, code = {"ok": False, "error": {"code": error.code, "message": str(error)}}, error.code
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(code)


if __name__ == "__main__":
    main()
