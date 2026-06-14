# Filosofía: Tecnologías mixtas

> **La IA propone; la persona decide.**
> Y la IA es solo *una* de las herramientas — no la más importante.

Este documento explica el *por qué* del proyecto. Si solo vas a leer una cosa antes
de contribuir, que sea esta. El *qué/para-quién* vive en [`PRD.md`](./PRD.md), lo técnico en
[`ARCHITECTURE.md`](./ARCHITECTURE.md), y el *cómo trabajamos en equipo* en
[`docs/flujo-de-trabajo.md`](./docs/flujo-de-trabajo.md).

---

## 1. Por qué existe esto

Queremos producir video **rápido y consistente sin perder lo humano**. La tentación
de la época es delegarle todo a un modelo y publicar lo que escupa. Nosotros hacemos
lo contrario: usamos la IA donde de verdad ayuda, y dejamos en manos de personas lo
que solo las personas hacen bien — contar una historia, cuidar una cara, elegir el
momento, sentir el ritmo de un corte.

## 2. El principio: tecnologías mixtas

No creemos en "automatizarlo todo". Creemos en **usar la herramienta pertinente para
cada paso**. La IA es una más en una caja que también contiene:

- **La oralidad** — contar, conversar, narrar. El guion nace de una historia, no de un prompt.
- **El trabajo en equipo** — cuatro oficios que se pasan la posta (narración, diseño,
  ingeniería, edición). Ver los roles en [`docs/flujo-de-trabajo.md`](./docs/flujo-de-trabajo.md).
- **El oficio manual** — un keyframe se puede dibujar a mano; a veces eso es lo correcto.
- **El criterio humano** — la decisión de qué sirve y qué no.

La IA entra **cuando es pertinente**: generar N opciones para que una persona elija más
rápido, animar un keyframe ya aprobado, transcribir, abaratar la iteración. No entra a
firmar el resultado. Esa es la diferencia entre *usar* una herramienta y *obedecerla*.

## 3. La regla de oro

> La IA **genera opciones**; las **personas deciden**. En cada paso donde la IA produce
> algo, **un humano elige y aprueba**. Si una pieza sale al mundo, es porque una persona
> la aprobó. La IA nunca firma — nosotros sí.

Esto es lo que en la industria llaman *"AI-in-the-Loop"*: la persona está **siempre
dentro del ciclo**. En este proyecto lo decidimos primero, antes que la arquitectura
(ver decisión [D-021]), y se nota en todo el diseño: el Quality Gate es un **asistente
que ordena candidatos**, no un juez que aprueba solo; es **suave por defecto** ([D-018]);
y hay **cuatro checkpoints humanos** explícitos (guion · casting + keyframe · video · corte final).

## 4. Los valores que nos guían

- **Amor a la vida.** La tecnología es un medio para hacer cosas que valgan la pena,
  no un fin. Si una decisión técnica deshumaniza el trabajo, está mal aunque sea eficiente.
- **Respeto.** A las personas del equipo, a quien contribuye, a quien mira el video.
  Respeto también al oficio: la IA no reemplaza a la narradora, la diseñadora, el
  ingeniero o la editora — los **potencia**.
- **Honestidad.** Decimos qué hizo una máquina y qué hizo una persona. No vendemos
  como mágico lo que es asistido, ni escondemos el trabajo humano detrás del modelo.
- **Pertinencia sobre automatización.** Preguntamos "¿esto necesita IA?" antes que
  "¿cómo lo automatizo?". A veces la mejor herramienta es una conversación.

## 5. Cómo se ve esto en el código

La filosofía no es un cartel; está en las decisiones de ingeniería:

| Principio | Cómo se materializa | Decisión |
|---|---|---|
| La persona dentro del ciclo | Checkpoints `cast` / `pick-cast` / `keyframes` / `pick` | [D-021], [D-022] |
| La IA asiste, no juzga sola | Gate como *ranker*, suave por defecto (`enforce: false`) | [D-016], [D-018] |
| Pertinencia sobre peso | Preferir APIs antes que librerías pesadas locales | [D-017] |
| Iterar sin miedo | Caché content-addressed: re-correr lo ya hecho cuesta $0 | [D-013], [D-015] |
| Trazabilidad humana | Cada decisión técnica queda escrita y numerada (ADRs) | [`docs/decisiones/`](./docs/decisiones/) |
| Entregar a una persona | El `export` arma un paquete que un humano entiende sin contexto | [D-029], [D-030] |

## 6. Lo que **no** somos

- No somos un botón de "hazme un video". Somos un taller donde la IA es una herramienta.
- No buscamos quitar a nadie del medio. Buscamos que cada persona haga su mejor trabajo
  más rápido.
- No optimizamos métricas a costa del criterio. Si el modelo y la persona discrepan,
  gana la persona.

## 7. Si vas a contribuir

Trae este espíritu. Un buen aporte aquí no es solo código que pasa los tests: es código
que **mantiene a la persona en el centro**. Antes de proponer "que la IA decida X
sola", preguntá si eso respeta la regla de oro. Los detalles prácticos de cómo aportar
están en [`CONTRIBUTING.md`](./CONTRIBUTING.md) y las normas de convivencia en
[`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md).

Gracias por sumar tu oficio al de la máquina. 🤝

---

[D-016]: ./docs/decisiones/0011-0020.md
[D-017]: ./docs/decisiones/0011-0020.md
[D-018]: ./docs/decisiones/0011-0020.md
[D-013]: ./docs/decisiones/0011-0020.md
[D-015]: ./docs/decisiones/0011-0020.md
[D-021]: ./docs/decisiones/0021-0030.md
[D-022]: ./docs/decisiones/0021-0030.md
[D-029]: ./docs/decisiones/0021-0030.md
[D-030]: ./docs/decisiones/0021-0030.md
