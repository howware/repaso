<h1 align="center">repaso · Learn and don't forget, without an app</h1>

<p align="center">
  <b>Tell your AI agent what you want to learn, or what you just learned. It makes the cards, quizzes you five
  minutes a day, grades your answers in your own words, and brings each card back right before you would forget
  it.</b>
</p>

<p align="center">
  <a href="https://github.com/howware/repaso/actions/workflows/ci.yml"><img src="https://github.com/howware/repaso/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="Version 0.1.0">
  <a href="https://howware.org"><img src="https://img.shields.io/badge/howware-0.2-5a45d6" alt="howware 0.2"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="Apache 2.0">
</p>

<p align="center"><a href="README.es.md">Español</a> · <a href="docs/building.md">How it was built</a></p>

> **A [howware](https://howware.org):** your know-how, put to work by AI. Here the know-how is how people learn
> for good: small questions, answered in your own words, at growing intervals. The agent does what it does well
> (making cards, asking, judging an imperfect answer, explaining) and an exact tool does what it does badly (keeping
> count of thousands of reviews and their dates, with [FSRS](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm),
> the scheduler Anki uses). It needs only the [memory](https://github.com/howware/long-term-memory-for-AI), and
> works for any subject, in any language.

```text
› Repásame.
  Tienes 6 tarjetas hoy (unos 3 min). Racha: 12 días.
  1/6 · ¿Por qué no se delega la responsabilidad final?

› Porque aunque otro haga el trabajo, el que responde por el resultado sigue siendo uno.
  ✓ Bien.
  2/6 · ¿Qué tres partes tiene el feedback SBI?

› Situación, comportamiento… y no me acuerdo de la otra.
  Casi: te faltó Impacto (situación, comportamiento, impacto).
  …
  ✓ Listo: 6 repasadas. Racha: 13 días. 🎉 25 tarjetas dominadas.
```

## What it does

| You say | It does |
|---|---|
| «I want to learn to manage people» | Asks what for, how deep and by when; proposes a **study plan** in units; you approve it once. Makes the cards of the first unit, and of each next one when it comes up |
| «Today I read that…» | Turns it into one or two cards, right away, without questions |
| «Quiz me» | A session of five minutes: what is due first (most at risk of being forgotten), then a few new cards. New cards from the plan are **taught first**, then asked. One question at a time; you answer in your words |
| (you answer) | The agent grades it: again, hard, good or easy. On a miss it gives the right answer; on a good answer, as you prefer. What you missed comes back at the end of the session |
| «How am I doing?» | Streak, mastery per topic and unit, how much you actually remember against your target, the next milestone, the cards you miss most |
| «For the exam on December 15» | Says if you are on pace, and how many new cards a day the date needs |

**Habit without guilt.** A streak with two freezes a month (a cold shouldn't erase forty days), a small daily goal,
mastery you can see per unit, milestones, and after a break a normal five-minute session instead of two hundred
cards. Everything shown is computed from your reviews; nothing is invented to keep you hooked.

## How it works

| Part | Here |
|---|---|
| Protocol | [`skill/repaso/SKILL.md`](skill/repaso/SKILL.md): making good cards, the grading rubric, the session, plans, coming back after a break, in plain words |
| Tool | [`repaso.py`](skill/repaso/scripts/repaso.py): FSRS (checked against its reference implementation), the session within its minutes, one unit of the plan at a time, the streak and its freezes, milestones, mastery, measured retention |
| Adapter | The [memory](https://github.com/howware/long-term-memory-for-AI) keeps topics, plans, cards and every review. Each card's schedule is **recomputed from its reviews**, so it never drifts and can be audited |

## Install

```bash
git clone https://github.com/howware/long-term-memory-for-AI && python long-term-memory-for-AI/tools/install_skill.py
git clone https://github.com/howware/repaso && python repaso/tools/install_skill.py
```

Requires Python 3.9+ and project-memory 0.4.0+. For Codex: `python repaso/tools/install_skill.py --target
~/.codex/skills/repaso`. Then open your agent in a folder of your choice and say: *"I want to learn …"*.

## Privacy and limits

| Designed to stay on your computer | What the AI agent sees |
|---|---|
| The memory file: topics, plans, cards, every review, your settings | The cards, your answers and your progress, when it queries them |
| Material you keep in the folder and don't share | What you type or share in the conversation |

**What it can't do or guarantee:**
- What the agent sees leaves your computer for your AI provider, under its terms. The memory is not encrypted.
- **Cards made by the agent can be wrong**, above all those from its own knowledge. Each card records where it came
  from; say "that card is wrong" and it is corrected (and started over if needed).
- A grade is the agent's judgment of your answer, not a measurement. You can dispute it.
- **No notifications:** the reminder appears when you open a conversation in that folder.
- Text only in this version: no images or audio, no import from Anki.
- **Tested in a real conversation on Claude Code only**; Codex will be added to `howware.json` once tested.

Everything is open source: the protocol, the tool and the memory can be read and checked.

## Development

```bash
git clone https://github.com/howware/long-term-memory-for-AI ../long-term-memory-for-AI
python -m unittest discover -s tests -v
git ls-files -z | xargs -0 python tools/check_private_data.py
```

The tests run against a temporary memory with synthetic cards, and check FSRS against reference values from
[py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) (MIT). See [AGENTS.md](AGENTS.md), and how it was
built with `howware-builder`: [docs/building.md](docs/building.md).

## License

[Apache 2.0](LICENSE). The FSRS formulas and default parameters come from
[open-spaced-repetition](https://github.com/open-spaced-repetition) (MIT).
