"""Tests of repaso.py against a real, temporary memory. Synthetic data only.

The memory helper is found in HOWWARE_MEMORY_HELPER, in ../long-term-memory-for-AI or in the installed skill.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skill" / "repaso" / "scripts" / "repaso.py"
sys.path.insert(0, str(TOOL.parent))
import repaso as rp  # noqa: E402

BY = "person:test"

# FSRS-6 reference values from py-fsrs 6 (Scheduler(learning_steps=(), relearning_steps=(), enable_fuzzing=False,
# desired_retention=0.9)), reviews at noon UTC: [day, rating, stability, difficulty, interval in days].
REFERENCE = {
    "good_chain": [[0, 3, 2.3065, 2.118103970459016, 2], [3, 3, 13.826903694354568, 2.111214235785395, 14],
                   [14, 3, 49.97448567068601, 2.1043313908464483, 50], [60, 3, 167.55784884500244, 2.0974554287524403, 168]],
    "miss_then": [[0, 3, 2.3065, 2.118103970459016, 2], [4, 1, 0.6614165256503188, 7.394502741279718, 1],
                  [4, 3, 0.7141261520890895, 7.382336607835277, 1], [6, 3, 3.520709470933534, 7.37018264052428, 4],
                  [20, 2, 11.172665590445867, 8.239433056587904, 11], [50, 4, 49.9657517513224, 7.6363619958159825, 50]],
    "first_again": [[0, 1, 0.212, 6.4133, 1], [1, 1, 0.10088578982099844, 8.806304468856837, 1],
                    [2, 3, 0.6832068408085884, 8.792726533684817, 1], [5, 3, 2.7511442725663953, 8.77916217644797, 3]],
    "easy": [[0, 4, 8.2956, 1.0, 8], [15, 4, 95.50778429167745, 1.0, 96]],
    "late": [[0, 3, 2.3065, 2.118103970459016, 2], [30, 3, 37.42063838925624, 2.111214235785395, 37],
             [31, 2, 39.67790818362485, 4.748284761594571, 40]],
}


def find_helper() -> Path | None:
    for c in (os.environ.get("HOWWARE_MEMORY_HELPER"), ROOT.parent / "long-term-memory-for-AI" / "db" / "memory.py",
              Path.home() / ".claude/skills/project-memory/scripts/memory.py"):
        if c and Path(c).is_file():
            return Path(c)
    return None


HELPER = find_helper()


class FsrsTest(unittest.TestCase):
    def test_matches_the_reference_implementation(self):
        for name, rows in REFERENCE.items():
            reviews = []
            for day, rating, stability, difficulty, interval in rows:
                reviews.append({"day": date(2026, 1, 1) + timedelta(days=day), "rating": rating, "key": name})
                st = rp.schedule(reviews, 0.9)
                with self.subTest(case=name, day=day):
                    self.assertAlmostEqual(st["stability"], stability, places=9)
                    self.assertAlmostEqual(st["difficulty"], difficulty, places=9)
                    self.assertEqual(rp.interval_days(st["stability"], 0.9), interval)

    def test_fuzz_is_deterministic_and_bounded(self):
        self.assertEqual(rp.fuzz(2, "a"), 2)
        values = {rp.fuzz(50, f"k{i}") for i in range(200)}
        self.assertTrue(values <= set(range(46, 56)), values)   # as py-fsrs: 50 ± 4.475, rounded
        self.assertGreater(len(values), 3)
        self.assertEqual(rp.fuzz(50, "same"), rp.fuzz(50, "same"))

    def test_higher_retention_means_shorter_intervals(self):
        self.assertLess(rp.interval_days(30, 0.95), rp.interval_days(30, 0.9))
        self.assertGreater(rp.interval_days(30, 0.8), rp.interval_days(30, 0.9))
        self.assertEqual(rp.interval_days(0.01, 0.9), 1)

    def test_card_keys(self):
        self.assertEqual(rp.card_key("topic:x", "¿Qué  es delegar?"), rp.card_key("topic:x", "¿qué es DELEGAR? "))
        self.assertNotEqual(rp.card_key("topic:x", "a"), rp.card_key("topic:y", "a"))
        self.assertEqual(rp.slug("Delegación eficaz"), "delegacion-eficaz")


@unittest.skipUnless(HELPER, "project-memory is not installed")
class ToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "memory.sqlite")
        subprocess.run([sys.executable, str(HELPER), "--db", self.db, "init", "--owner-name", "Test",
                        "--owner-key", BY], check=True, capture_output=True)
        self.assertTrue(self.tool("setup", "--by", BY)["ok"])

    def tearDown(self):
        self.tmp.cleanup()

    def tool(self, *args: str, code: int = 0, now: str = "2026-10-12T09:00", stdin: object = None) -> dict:
        proc = subprocess.run([sys.executable, str(TOOL), "--mem", str(HELPER), "--db", self.db, "--tz=-06:00",
                               "--now", now, *args], capture_output=True,
                              input=None if stdin is None else json.dumps(stdin, ensure_ascii=False).encode("utf-8"))
        out = proc.stdout.decode("utf-8")
        self.assertEqual(proc.returncode, code, out + proc.stderr.decode("utf-8", "replace"))
        return json.loads(out)

    def topic(self, key="lid", name="Liderazgo", **extra):
        flags = [x for k, v in extra.items() for x in (f"--{k}", v)]
        return self.tool("topic", "--key", key, "--name", name, *flags, "--by", BY)

    def add(self, cards, topic="lid", unit=None, now="2026-10-12T09:00"):
        return self.tool("add", "--topic", topic, *(["--unit", unit] if unit else []), "--file", "-", "--by", BY,
                         stdin=[{"question": q, "answer": f"answer {q}"} for q in cards], now=now)

    def grade(self, card, rating, now, *extra, code=0):
        return self.tool("grade", "--card", card, "--rating", rating, *extra, "--by", BY, now=now, code=code)

    def test_cards_are_idempotent_and_the_plan_opens_one_unit_at_a_time(self):
        self.topic()
        plan = self.tool("plan", "--topic", "lid", "--file", "-", "--by", BY,
                         stdin=[{"name": "Delegación", "summary": "cuándo delegar"}, {"name": "Feedback"},
                                {"name": "Conflictos"}])
        self.assertEqual([u["unit"] for u in plan["units"]],
                         ["unit:lid-delegacion", "unit:lid-feedback", "unit:lid-conflictos"])
        first = self.add(["¿Qué es delegar?", "¿Qué no se delega?"], unit="Delegación")
        self.assertEqual(len(first["created"]), 2)
        again = self.add(["¿qué es delegar? "], unit="Delegación")
        self.assertEqual((len(again["created"]), len(again["existing"])), (0, 1))
        self.add(["¿Qué es el feedback SBI?"], unit="Feedback")
        loose = self.add(["Una idea de la conversación"])
        session = self.tool("session")
        # conversation cards first, then the first unit; the second unit waits until the first is seen
        self.assertEqual([c["card"] for c in session["new"]],
                         [loose["created"][0]["card"], first["created"][0]["card"], first["created"][1]["card"]])
        self.assertEqual(session["needs_cards"], [])
        for c in session["new"]:
            self.grade(c["card"], "good", "2026-10-12T09:05")
        session = self.tool("session", now="2026-10-12T09:10")
        self.assertEqual([c["question"] for c in session["new"]], ["¿Qué es el feedback SBI?"])
        self.assertEqual(session["needs_cards"][0]["unit"], "unit:lid-conflictos")
        self.assertEqual(session["new_left_today"], 1)
        # reordering must keep every unit
        missing = self.tool("plan", "--topic", "lid", "--file", "-", "--by", BY, stdin=[{"name": "Feedback"}], code=2)
        self.assertIn("unit:lid-delegacion", missing["error"]["message"])

    def test_grading_schedules_and_never_counts_an_answer_twice(self):
        self.topic()
        card = self.add(["¿Qué es delegar?"])["created"][0]["card"]
        miss = self.grade(card, "again", "2026-10-12T09:01", "--answer", "no me acuerdo")
        self.assertTrue(miss["ask_again_this_session"])
        self.assertEqual(miss["next_review"], "2026-10-13")
        repeat = self.grade(card, "good", "2026-10-12T09:02")
        self.assertTrue(repeat["unchanged"])
        self.assertEqual(repeat["rating"], "again")
        second = self.grade(card, "good", "2026-10-12T09:03", "--attempt", "2")
        self.assertFalse(second["ask_again_this_session"])
        fixed = self.grade(card, "hard", "2026-10-12T09:04", "--attempt", "2", "--correct")
        self.assertEqual(fixed["rating"], "hard")
        view = self.tool("cards", "--topic", "lid")["cards"][0]
        self.assertEqual((view["reviews"], view["lapses"]), (2, 1))
        expected = rp.schedule([{"day": date(2026, 10, 12), "rating": 1, "key": "a"},
                                {"day": date(2026, 10, 12), "rating": 2, "key": "b"}], 0.9)
        self.assertAlmostEqual(view["stability_days"], round(expected["stability"], 1))
        self.assertEqual(self.tool("session", now="2026-10-13T08:00")["review"][0]["card"], card)
        nothing = self.grade(card, "good", "2026-10-13T08:01", "--correct", code=2)
        self.assertIn("none yet", nothing["error"]["message"])

    def test_session_fits_its_minutes_and_a_backlog_brings_no_new_cards(self):
        self.topic()
        self.tool("config", "--minutes", "2", "--new-per-day", "3", "--by", BY)
        cards = [c["card"] for c in self.add([f"q{i}" for i in range(8)])["created"]]
        session = self.tool("session")
        self.assertEqual(len(session["new"]), 2)          # 2 minutes = two first views
        self.assertEqual(session["minutes"], 2)
        for c in cards:                                    # all seen (more than the daily limit, on purpose)
            self.grade(c, "again", "2026-10-12T09:05")
        late = self.tool("session", now="2026-10-20T09:00")
        self.assertEqual(len(late["review"]), 4)           # 2 minutes = four reviews
        self.assertEqual((late["due_total"], late["backlog_after"], late["catch_up_days"]), (8, 4, 2))
        self.assertEqual(late["new"], [])
        brief = self.tool("brief", now="2026-10-20T09:00")
        self.assertEqual((brief["to_review"], brief["days_since_last_review"]), (4, 8))

    def test_streak_with_freezes(self):
        self.topic()
        card = self.add(["q"])["created"][0]["card"]
        day = lambda n: f"2026-10-{n:02d}T09:00"
        for n in (1, 2, 4, 5):                             # Oct 3 missed: a freeze keeps the streak
            self.grade(card, "again", day(n))
        streak = self.tool("brief", now=day(5))["streak"]
        self.assertEqual((streak["days"], streak["freezes_left_this_month"], streak["today_done"]), (4, 1, True))
        self.assertEqual(streak["freezes_used"], ["2026-10-03"])
        streak = self.tool("brief", now=day(6))["streak"]   # today not done yet: the streak is not lost
        self.assertEqual((streak["days"], streak["today_done"]), (4, False))
        streak = self.tool("brief", now=day(9))["streak"]   # 6 and 7 missed: one freeze left, then it breaks
        self.assertEqual((streak["days"], streak["best"], streak["freezes_left_this_month"]), (0, 4, 0))

    def test_milestones_and_mastery(self):
        self.topic(deadline="2026-12-31")
        self.tool("plan", "--topic", "lid", "--file", "-", "--by", BY, stdin=[{"name": "Delegación"}])
        card = self.add(["q"], unit="Delegación")["created"][0]["card"]
        self.add(["otra"])
        self.grade(card, "easy", "2026-10-12T09:00")
        reached = self.grade(card, "easy", "2026-10-20T09:00")["milestones_reached"]
        self.assertIn({"kind": "units_mastered", "value": 1}, reached)
        topic = self.tool("topics", now="2026-10-20T09:10")["topics"][0]
        self.assertEqual((topic["cards"], topic["seen"], topic["mastered"], topic["mastery_percent"]), (2, 1, 1, 50))
        self.assertTrue(topic["units"][0]["is_mastered"])
        self.assertEqual(topic["deadline"]["unseen_cards"], 1)
        self.assertEqual(topic["deadline"]["days_left"], 72)
        stats = self.tool("stats", now="2026-10-20T09:10")
        self.assertEqual(stats["retention"]["reviews"], 1)
        self.assertEqual(stats["retention"]["measured_percent"], 100)

    def test_a_plan_card_just_taught_starts_at_most_good(self):
        self.topic()
        self.tool("plan", "--topic", "lid", "--file", "-", "--by", BY, stdin=[{"name": "Delegación"}])
        card = self.tool("add", "--topic", "lid", "--unit", "Delegación", "--origin", "plan", "--file", "-", "--by", BY,
                         stdin=[{"question": "q", "answer": "a"}])["created"][0]["card"]
        first = self.grade(card, "easy", "2026-10-12T09:00")
        self.assertEqual((first["rating"], first["next_review"]), ("good", "2026-10-14"))
        self.assertIn("note", first)
        more = self.tool("add", "--topic", "lid", "--unit", "Delegación", "--origin", "plan", "--file", "-", "--by", BY,
                         stdin=[{"question": f"p{i}", "answer": "a"} for i in range(4)], now="2026-10-15T09:00")
        session = self.tool("session", now="2026-10-15T09:01")      # one review (30 s) and two cards taught (2 min each)
        self.assertEqual((len(session["review"]), len(session["new"]), session["minutes"]), (1, 2, 5))
        self.assertEqual(len(more["created"]), 4)
        self.assertEqual(self.grade(card, "easy", "2026-10-14T09:00")["rating"], "easy")
        loose = self.add(["from the conversation"])["created"][0]["card"]
        self.assertEqual(self.grade(loose, "easy", "2026-10-14T09:01")["rating"], "easy")

    def test_brief_before_setup(self):
        empty = str(Path(self.tmp.name) / "none.sqlite")
        proc = subprocess.run([sys.executable, str(TOOL), "--mem", str(HELPER), "--db", empty, "brief"],
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(json.loads(proc.stdout)["setup_needed"])

    def test_edit_reset_and_pause(self):
        self.topic()
        a, b = (c["card"] for c in self.add(["q1", "q2"])["created"])
        self.grade(a, "again", "2026-10-12T09:00")
        edited = self.tool("edit", "--card", a, "--answer", "corrected", "--reset", "--reason", "estaba mal",
                           "--by", BY, now="2026-10-12T10:00")
        self.assertTrue(edited["new"])
        self.assertEqual(edited["answer"], "corrected")
        self.tool("card-state", "--card", b, "--state", "paused", "--by", BY)
        session = self.tool("session", now="2026-10-12T10:05")
        self.assertEqual([c["card"] for c in session["new"]], [a])
        self.topic(state="paused")
        self.assertEqual(self.tool("session", now="2026-10-12T10:06")["new"], [])

    def test_refusals(self):
        self.topic()
        card = self.add(["q"])["created"][0]["card"]
        self.assertIn("again, hard", self.grade(card, "perfect", "2026-10-12T09:00", code=2)["error"]["message"])
        self.assertIn("No topic", self.tool("add", "--topic", "nada", "--file", "-", "--by", BY, stdin=[],
                                            code=2)["error"]["message"])
        long = self.tool("add", "--topic", "lid", "--file", "-", "--by", BY, code=2,
                         stdin=[{"question": "x" * 600, "answer": "y"}])
        self.assertIn("split the card", long["error"]["message"])
        self.assertIn("70 to 97", self.tool("config", "--retention", "99", "--by", BY, code=2)["error"]["message"])
        self.assertIn("after today", self.tool("topic", "--key", "lid", "--deadline", "2026-01-01", "--by", BY,
                                               code=2)["error"]["message"])
        self.assertIn("No card", self.grade("card:nope", "good", "2026-10-12T09:00", code=2)["error"]["message"])

    def test_config_and_deadline_removal(self):
        out = self.tool("config", "--retention", "85", "--by", BY)
        self.assertEqual(out["settings"]["desired_retention_bp"], 8500)
        self.assertEqual(self.tool("config")["settings"]["desired_retention_bp"], 8500)
        self.topic(deadline="2026-12-31")
        self.tool("topic", "--key", "lid", "--deadline", "none", "--by", BY, now="2026-10-12T09:05")
        self.assertNotIn("deadline", self.tool("topics", now="2026-10-12T09:06")["topics"][0])


class ContractTest(unittest.TestCase):
    def test_version(self):
        out = subprocess.run([sys.executable, str(TOOL), "--version"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.split()[-1], rp.__version__)


if __name__ == "__main__":
    unittest.main()
