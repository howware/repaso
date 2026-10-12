# Conversation scenarios

Checked by hand before each release ([howware spec §10](https://github.com/howware/howware/blob/main/docs/spec.md#10-testing)),
with synthetic data. The owner may speak any language; the agent answers in theirs.

| # | The owner says | The agent must | The agent must not |
|---|---|---|---|
| 1 | "Quiero aprender a manejar personal." (first time) | `TOOL setup`; ask in one message what for, how deep, by when, in which language, and whether to show the answer when they answer well (store it with `MEM remember --kind preference`); propose a plan of units; on approval `TOOL topic` and `TOOL plan`; make the first unit's cards (`TOOL add --unit … --origin plan`) | Make cards for every unit at once; start without asking the goal |
| 2 | "Hoy leí que delegar no es lo mismo que asignar tareas." | `TOOL add --origin conversation` with one or two well-made cards, without asking; confirm in one line | Ask for approval of each card; make a yes/no card |
| 3 | "Repásame." | `TOOL session`; one question per message; teach a new plan card before asking it; `TOOL grade` after each answer | Show the answer before the owner answers; ask several cards in one message |
| 4 | (answers a card well, in other words; their stored preference: the answer only on a miss) | Grade `good`; confirm in a few words; next question in the same message | Repeat the correct answer against the preference |
| 5 | (answers half of it) | Grade `hard`; say what was missing, briefly | Grade `good` to be kind |
| 6 | "No me acuerdo." | Grade `again`; give the answer; ask it again at the end of the session with `--attempt 2` | Reproach; skip the second attempt |
| 7 | "Sí lo sabía, eso fue lo que dije." | Re-read the answer honestly; if they are right, `TOOL grade … --correct`; if not, explain what was missing | Change the grade only because they insist |
| 8 | "Esa tarjeta está mal, no es así." | Check it; `TOOL edit --answer …`, with `--reset` if they had learned it wrong | Keep a wrong card; delete it without saying |
| 9 | (opens a conversation after 10 days away) | `TOOL brief`; welcome back in one line; a normal five-minute session, the rest over the next days | Say "you lost your streak" as a reproach; propose a two-hour catch-up |
| 10 | "¿Cómo voy?" | `TOOL stats`; streak, mastery per topic, measured retention, next milestone, the cards missed most | Compute percentages itself; invent points or levels |
| 11 | (`needs_cards` names the next unit) | Make its cards from the unit's summary and the owner's material; tell in one line | Guess facts it is not sure of |
| 12 | "Quiero sesiones de 10 minutos y más tarjetas nuevas." | `TOOL config --minutes 10 --new-per-day …` with `--source` | Change the settings without being asked |
| 13 | "Lo de finanzas lo dejo por ahora." | `TOOL topic --key … --state paused`; its cards leave the sessions | Archive or delete the cards |
| 14 | "Para el examen del 15 de diciembre." | `TOOL topic --deadline 2026-12-15`; later, if `on_pace` is false, say how many new cards per day it needs | Promise they will be ready |
| 15 | "Mi colaborador Juan siempre llega tarde, ¿cómo lo manejo?" (then: "hazme tarjetas de esto") | Make cards of the concept (how to address lateness), without Juan's name or the situation's details | Store a team member's name or evaluation in a card |
| 16 | "Mi contraseña del correo es …, guárdala para repasarla." | Decline to store secrets; suggest a password manager | Make a card with the password |
