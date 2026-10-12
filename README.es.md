<h1 align="center">repaso · Aprender y no olvidar, sin app</h1>

<p align="center">
  <b>Dile a tu agente de IA qué quieres aprender, o qué acabas de aprender. Él hace las tarjetas, te pregunta cinco
  minutos al día, califica tus respuestas dichas con tus palabras y te trae cada tarjeta justo antes de que la
  olvides.</b>
</p>

<p align="center">
  <a href="https://github.com/howware/repaso/actions/workflows/ci.yml"><img src="https://github.com/howware/repaso/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/versión-0.1.0-blue" alt="Versión 0.1.0">
  <a href="https://howware.org/es/"><img src="https://img.shields.io/badge/howware-0.2-5a45d6" alt="howware 0.2"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/licencia-Apache%202.0-green" alt="Apache 2.0">
</p>

<p align="center"><a href="README.md">English</a> · <a href="docs/building.md">Cómo se construyó</a></p>

> **Un [howware](https://howware.org/es/):** tu saber hacer, puesto a trabajar con IA. Aquí el saber hacer es cómo
> se aprende para siempre: preguntas pequeñas, contestadas con tus palabras, a intervalos que crecen. El agente hace
> lo que hace bien (hacer tarjetas, preguntar, juzgar una respuesta imperfecta, explicar) y una herramienta exacta
> lo que hace mal (llevar la cuenta de miles de repasos y sus fechas, con
> [FSRS](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm), el algoritmo que usa Anki). Solo
> necesita la [memoria](https://github.com/howware/long-term-memory-for-AI) y sirve para cualquier tema, en
> cualquier idioma.

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

## Qué hace

| Dices | Hace |
|---|---|
| «Quiero aprender a manejar personal» | Pregunta para qué, qué tan a fondo y para cuándo; propone un **plan de estudio** por unidades y lo apruebas una vez. Hace las tarjetas de la primera unidad, y las de cada siguiente cuando le toca |
| «Hoy leí que…» | Lo convierte en una o dos tarjetas, en el momento, sin preguntas |
| «Repásame» | Una sesión de cinco minutos: primero lo que toca (lo que más riesgo tiene de olvidarse), luego unas pocas tarjetas nuevas. Las nuevas del plan **primero te las enseña** y luego te las pregunta. Una pregunta a la vez; contestas con tus palabras |
| (contestas) | El agente califica: otra vez, difícil, bien o fácil. Si fallas, te da la respuesta correcta; si contestas bien, como prefieras. Lo que fallaste vuelve al final de la sesión |
| «¿Cómo voy?» | Racha, dominio por tema y unidad, cuánto recuerdas de verdad contra tu meta, el siguiente hito, las tarjetas que más fallas |
| «Para el examen del 15 de diciembre» | Dice si vas al paso y cuántas tarjetas nuevas al día necesita esa fecha |

**Hábito sin culpa.** Una racha con dos comodines al mes (una gripe no debería borrar cuarenta días), una meta
diaria pequeña, dominio visible por unidad, hitos y, después de un descanso, una sesión normal de cinco minutos en
vez de doscientas tarjetas. Todo lo que ves sale de tus repasos; nada se inventa para engancharte.

## Cómo funciona

| Parte | Aquí |
|---|---|
| Protocolo | [`skill/repaso/SKILL.md`](skill/repaso/SKILL.md): cómo hacer buenas tarjetas, cómo calificar, la sesión, los planes, volver después de un descanso, en palabras claras |
| Herramienta | [`repaso.py`](skill/repaso/scripts/repaso.py): FSRS (comprobado contra su implementación de referencia), la sesión dentro de sus minutos, una unidad del plan a la vez, la racha y sus comodines, hitos, dominio, retención medida |
| Adaptador | La [memoria](https://github.com/howware/long-term-memory-for-AI) guarda temas, planes, tarjetas y cada repaso. El calendario de cada tarjeta se **recalcula a partir de sus repasos**, así que nunca se desvía y se puede auditar |

## Instalación

```bash
git clone https://github.com/howware/long-term-memory-for-AI && python long-term-memory-for-AI/tools/install_skill.py
git clone https://github.com/howware/repaso && python repaso/tools/install_skill.py
```

Requiere Python 3.9+ y project-memory 0.4.0+. Para Codex: `python repaso/tools/install_skill.py --target
~/.codex/skills/repaso`. Luego abre tu agente en la carpeta que quieras y di: *«Quiero aprender …»*.

## Privacidad y límites

| Diseñado para quedarse en tu computadora | Lo que ve el agente de IA |
|---|---|
| El archivo de la memoria: temas, planes, tarjetas, cada repaso, tus ajustes | Las tarjetas, tus respuestas y tu avance, cuando los consulta |
| El material que guardes en la carpeta y no compartas | Lo que escribes o compartes en la conversación |

**Lo que no puede hacer ni garantizar:**
- Lo que ve el agente sale de tu computadora hacia tu proveedor de IA, bajo sus términos. La memoria no está cifrada.
- **Las tarjetas que hace el agente pueden tener errores**, sobre todo las que salen de su propio conocimiento.
  Cada tarjeta guarda de dónde salió; di «esa tarjeta está mal» y se corrige (y vuelve a empezar si hace falta).
- Una calificación es el juicio del agente sobre tu respuesta, no una medición. Puedes discutirla.
- **Sin notificaciones:** el recordatorio aparece cuando abres una conversación en esa carpeta.
- Solo texto en esta versión: sin imágenes ni audio, sin importar mazos de Anki.
- **Probado en una conversación real solo en Claude Code**; Codex se agregará a `howware.json` cuando se pruebe.

Todo es código abierto: el protocolo, la herramienta y la memoria se pueden leer y revisar.

## Desarrollo

```bash
git clone https://github.com/howware/long-term-memory-for-AI ../long-term-memory-for-AI
python -m unittest discover -s tests -v
git ls-files -z | xargs -0 python tools/check_private_data.py
```

Las pruebas corren contra una memoria temporal con tarjetas sintéticas, y comparan FSRS con valores de referencia
de [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) (MIT). Ver [AGENTS.md](AGENTS.md), y cómo se
construyó con `howware-builder`: [docs/building.md](docs/building.md).

## Licencia

[Apache 2.0](LICENSE). Las fórmulas y los parámetros por omisión de FSRS vienen de
[open-spaced-repetition](https://github.com/open-spaced-repetition) (MIT).
