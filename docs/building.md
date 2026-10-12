# How this howware was built

A record of building `repaso` with the
[`howware-builder`](https://github.com/howware/howware/blob/main/skills/howware-builder/SKILL.md) protocol. The
owner's words are kept verbatim, in Spanish.

## 1. Choosing it

The owner noticed that every howware so far was Mexican (bank statements, the SAT, Mexican rentals) and asked
which one someone in the United States would like. A US freelancer's quarterly taxes, or opening
`finanzas-personales` to US banks, fit well, but the owner knows no one there to test them with real data yet, and
each howware here has been shaped by its first real conversation. So the owner asked to think laterally:

> «hay que pensar lateralmente para ver que howware podemos hacer»

The filter was where the howware formula works best: something that builds up over time (the memory matters),
exact rules or arithmetic (the tool matters), private data (local matters) and a conversation as the natural way to
use it. Spaced review passed every test, works in any country and language, needs no new adapter, and the owner
could use it from day one. Anki is powerful but hostile; here the interface is talking.

> «el de repaso espaciado me gusta, empecemos»

## 2. Interview

| Topic | The owner's words |
|---|---|
| What to learn | «conceptos de management de ti y manejo de personal» |
| Experience | «no he usado Anki, duoingo si, aun lo uso» |
| Cards | «confio en que el agene las haga bie y corrijo despues» |
| Reviewing | «5 min, contesto con mis palabras y el agente juzga, el agente siempre califica» |
| Topics | «a decidir conforme cada usuario pone un tema, puede ser algo corto o algo que tome mucho tiempo, se tendria que hacer un tipo plan de estudio para el largo plazo» |
| Not giving up | «Hay que aplicar tecnicas como la gamificacion para evitar llegar al punto de dejarlo y que ya no interese» |
| The algorithm | «No conozco FSRS ni SM2 ni ningun otro, esto es nuevo para mi» |
| Reminders | «si me gustaria que me recordaras» |
| Language | «el idioma de acuerdo a peticion del usuario» |
| With `todo` | «solo talvez, no veo como encajaria con el todo» |
| Feedback | «solo cuando fallo o me faltó algo» (show the right answer). A preference, so it is stored in the memory and asked to every owner, not fixed in the protocol |

## 3. Design decisions

| Decision | Why |
|---|---|
| FSRS-6 with its default parameters and a 90% target | Fewer reviews than SM-2 for the same memory; published and open; the owner needn't configure anything |
| Day-based, no learning steps; a missed card comes back once at the end of the session | Sessions are a conversation of a few minutes, not a timer; the second try uses FSRS's same-day formula |
| Each card's state recomputed from its reviews, with fuzz derived from the review's key | Nothing stored can drift; changing the target reschedules every card consistently; the history can be audited |
| The agent always grades, with a four-level rubric; the owner may dispute (`--correct`) | The owner's choice; grading the idea, not the wording, is what an agent does well |
| Cards kept without approval; each records its origin and source | The owner trusts them and corrects later; a wrong card can be traced |
| A plan approved once; each unit's cards made when the unit comes up | Long topics need a plan; making all cards up front would fix a plan that should be able to change |
| New plan cards are taught before being asked | The owner hasn't seen them yet; asking cold teaches nothing |
| Streak with 2 freezes a month, days with nothing due neither count nor break it, a small daily goal, milestones, mastery per unit | Duolingo's hooks that sustain a habit, without its guilt; everything computed from the reviews |
| After a break, the usual five minutes and no new cards until the backlog clears | A wall of two hundred cards is how people quit |
| No personal data about others in cards | Learning to manage people invites real cases from the owner's team |

## 4. The first real conversation

The owner set up the memory, approved a plan of eight units for leading a software team, and did a first session
of five new cards. It worked end to end, and changed three things before publishing:

- A plan card is taught and asked in the same minute. An excellent answer was graded *easy*, which FSRS starts at
  eight days for something heard a minute before. Now a plan card's first grade is at most *good* (two days).
- The agent was asked for the next unit's cards on the first day, with eight cards still unseen. Now only when less
  than a day of new cards is left.
- `brief` failed before the memory existed; now it says that setup is needed.
- Five new cards were planned as five minutes and took about ten: teaching a card and explaining it back takes
  longer. A plan card now counts two minutes, so a five-minute session brings two or three of them.

## 5. Not included in 0.1

Images and audio, importing from Anki, fitting FSRS's parameters to the owner's own history (needs months of
reviews), notifications, and linking with `todo` (the shared memory allows it if a real case asks for it).
