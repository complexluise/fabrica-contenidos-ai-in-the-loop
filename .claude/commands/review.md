---
description: El verifier revisa el diff actual (adversarial, read-only) y devuelve veredicto + hallazgos.
---

Despachá al subagente `verifier` para revisar el trabajo actual.

Alcance: $ARGUMENTS
(si no se especificó alcance arriba, revisá el diff del árbol de trabajo: `git diff` + lo staged).

Pedile que:
1. Lea el diff y juzgue correctitud, casos borde, regresiones.
2. Corra los tests relevantes (`uv run pytest <archivos>`, o la suite si el cambio es
   transversal) y, si toca frontend, el build (`npx vite build`).
3. Devuelva un **veredicto claro** (PASA / NO PASA / PASA CON RESERVAS) y **hallazgos**
   con `archivo:línea` y severidad, separando bugs de mejoras opcionales, con la
   evidencia real de los tests.

Es read-only: no arregla nada. Al terminar, reportame el veredicto y, si hay bugs
crítico/alto, preguntame si querés que mande los hallazgos al `coder` para corregir.
