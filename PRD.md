# PRD — Taller de video con IA (la persona dentro del ciclo)

> **Qué es esto:** el **QUÉ** y el **PARA QUIÉN**. El problema, los usuarios, los objetivos y los
> recorridos por actor. Es el *norte* contra el que se evalúan las decisiones.
>
> El *por qué creemos esto* (valores) vive en [`FILOSOFIA.md`](FILOSOFIA.md); el **cómo** está
> construido en [`ARCHITECTURE.md`](ARCHITECTURE.md); el **plan** en [`ROADMAP.md`](ROADMAP.md); el
> *por qué de cada elección puntual* en [`docs/decisiones/`](docs/decisiones/).

---

## 1. El problema

Producir video corto y consistente es lento y caro: cada toma cuesta dinero, la **consistencia
entre planos** (la misma cara, el mismo look) es frágil, y delegarle todo a un modelo produce
material genérico que nadie firma. La tentación de la época es apretar un botón y publicar lo que
salga; nosotros queremos lo contrario: **velocidad y consistencia sin perder el criterio humano**.

## 2. Para quién (los actores)

Un **equipo chico de cuatro oficios** que se pasan la posta, más la audiencia final. La IA es **una
herramienta más** en la caja (junto a la oralidad, el oficio manual y el criterio humano), no la
dueña del resultado (ver [`FILOSOFIA.md`](FILOSOFIA.md)).

- **Narradora** — trae la historia (oralidad), arma y firma el plan.
- **Diseñadora** — cuida la identidad visual: la cara del personaje, el look de cada escena.
- **Ingeniero** — opera el motor, las claves, el costo, la generación.
- **Editora** — recibe el paquete y cierra el corte. (Cuando no hay editora, un agente cierra un
  corte que prioriza el mensaje sobre el pulido.)
- **Espectador** — ve el video final; nunca ve el andamiaje.

## 3. Objetivos del producto

1. **De un guion a un video posteable** sin tocar la terminal, atravesando todo el ciclo.
2. **La persona decide en cada checkpoint**: la IA propone N opciones; un humano elige y aprueba.
   Cuatro checkpoints: guion · casting + encuadre · animatic (antes de pagar video) · corte final.
3. **Iterar es barato**: re-hacer lo ya hecho cuesta $0 (caché content-addressed); el costo siempre
   visible antes del botón que gasta.
4. **Consistencia de identidad**: la cara elegida una vez viaja a todos los planos.
5. **Honestidad**: se distingue qué hizo la máquina y qué la persona; el resultado lo firma una
   persona, nunca el modelo.

## 4. No-objetivos (qué NO somos)

- **No** un botón de "hazme un video": somos un taller donde la IA es herramienta.
- **No** buscamos sacar a nadie del medio: potenciamos cada oficio.
- **No** optimizamos métricas a costa del criterio: si el modelo y la persona discrepan, gana la
  persona.
- **No** (en el MVP): edición colaborativa multi-usuario, multi-marca con herencia, self-hosting de
  modelos en el camino por defecto.

## 5. Criterios de éxito

- Una corrida de punta a punta (guion → paquete) **sin terminal**.
- En cada paso donde la IA produce algo, **hay una elección humana** persistida y reanudable.
- **Costo visible** antes de cada generación; re-correr lo cacheado = $0.
- La **misma cara/look** se mantiene entre planos de un proyecto.
- El **paquete de export** lo entiende una editora sin contexto previo.

## 6. Recorridos por actor (user journeys)

Cada recorrido es "como [actor], quiero [X] para [Y]". Los *acceptance criteria* concretos viven en
[`ROADMAP.md`](ROADMAP.md); acá va la intención, que es lo que el producto debe honrar.

### Narradora — del relato al plan firmado
> Como narradora, quiero **convertir mi guion/idea en un borrador editable** y **firmarlo**, para
> que de ahí se genere todo con mi visión, no la del modelo.

Pega o sube el texto → la IA propone un borrador (escenas, planos, personajes) → lo edita en el
**Storyboard** (el centro) → lo **firma**. El Storyboard es donde todo converge y se valida; las
demás mesas lo nutren.

### Diseñadora — la identidad visual
> Como diseñadora, quiero **fijar la cara de cada personaje y la imagen clave de cada escena**
> eligiendo entre opciones (o subiendo la mía), para que la identidad sea consistente y mía.

**Casting**: la IA propone caras; elige una (o sube/dibuja la suya); puede ajustar el prompt del
personaje y pedir variantes. **Encuadres**: elige la imagen clave por escena, con el mismo poder de
iteración. Lo elegido aparece en el Storyboard. La IA **ordena** candidatos (asistente), no decide.

### Ingeniero — el motor y el costo
> Como ingeniero, quiero **operar la generación con el costo siempre a la vista y sin pagar dos
> veces**, para iterar sin miedo y sin sorpresas de presupuesto.

Configura claves (Ajustes), elige perfil/velocidad, dispara generaciones con **costo estimado antes
del botón**, ve el **progreso en vivo** y el **libro mayor de gastos**. El caché hace gratis lo ya
hecho; un job no se duplica.

### Editora — recibir y cerrar
> Como editora, quiero **un paquete limpio que entienda sin contexto**, para cerrar el corte con mi
> criterio.

Antes de pagar video revisa el **Animatic** (la película en poses/stills, incluso "▶ reproducir el
plan" con la narrativa). Luego recibe el **export**: media sin texto/voz quemada, voces, música,
keyframes, `rough_cut.mp4` de referencia, subtítulos y guion. El `final` del run es referencia, no
el definitivo. (Sin editora, un agente cierra priorizando el mensaje.)

### Espectador — el resultado
> Como espectador, quiero **un video claro y con alma**, sin notar el andamiaje.

Ve el video final, en su formato (9:16 / 1:1 / 16:9). Nunca ve prompts, candidatos ni costos.

---

> Este PRD es liviano a propósito: captura el norte, no un backlog. Los requisitos detallados y su
> estado viven en el ROADMAP; las decisiones puntuales, en los ADRs.
