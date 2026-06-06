# Cómo contribuir

¡Gracias por querer aportar! Este proyecto es un taller de **tecnologías mixtas**: la
IA es una herramienta más y la persona siempre decide. Antes de tocar código, lee la
[**FILOSOFIA.md**](./FILOSOFIA.md) — un buen aporte aquí mantiene a la persona en el centro,
no solo pasa los tests.

Al participar aceptás el [Código de Conducta](./CODE_OF_CONDUCT.md).

## Antes de empezar

Lee, en este orden, lo que sea relevante a tu cambio:

1. [`FILOSOFIA.md`](./FILOSOFIA.md) — el *por qué*.
2. [`SPEC.md`](./SPEC.md) — arquitectura y contratos (las 10 capas).
3. [`ROADMAP.md`](./ROADMAP.md) — sprints y criterios de aceptación.
4. [`decisions/`](./decisions/) — los ADR: el *por qué* de cada elección técnica.

## Preparar el entorno

Este proyecto usa **[uv](https://docs.astral.sh/uv/) exclusivamente** — nunca `pip`,
`venv` ni un `python` pelado. Python está fijado a **3.12**. Necesitás **ffmpeg** en el `PATH`.

```bash
uv sync --extra apis --extra dev      # core + APIs (anthropic, fal-client) + pytest
# añade --extra vision                # opcional: señales CLIP/aesthetic (pesado: torch)

cp .env.example .env                  # y rellená tus claves (FAL_KEY es obligatoria)
```

Las claves se leen desde `.env` (gitignored) en `src/pipeline/settings.py`.
**Nunca** subas un `.env` ni pegues claves reales en código, issues o PRs.

## Correr el proyecto

```bash
uv run pytest                          # toda la suite (asyncio_mode=auto; los async no llevan decorador)
uv run pytest tests/test_strategies.py # un archivo
uv run pipeline run <slug>             # ejecutar el CLI
```

No hay linter ni formateador configurado: **los tests son el único gate**.

## Las reglas del código (importan)

- **TDD test-first, pero solo el core crítico.** Escribimos test antes que código para
  contratos, routing/estrategias, fusión del gate, telemetría, proyecto/caché y studio.
  Las **APIs externas, ffmpeg y prompts** se validan con *smoke runs reales*, **no** con
  unit tests. No agregues cobertura amplia más allá de ese core (ver [D-012]).
- **Contratos primero.** Todo depende de `contracts.py` (Pydantic v2) y de los `Protocol`
  (`Provider`, `QualityGate`, `Strategy`), no de clases concretas.
- **Preferir APIs sobre librerías pesadas locales.** Es una decisión de diseño ([D-017]),
  no un descuido: nada de whisper/torch/insightface en el camino por defecto.
- **Tolerancia a fallos.** Una escena o un proveedor caído **no** debe abortar la corrida
  (`asyncio.gather(..., return_exceptions=True)`; fallos al `run_report.json`).
- **Consola en ASCII.** El host es Windows/PowerShell (cp1252). Usá `->` en vez de `→` en
  prints; los caracteres no-ASCII en consola pueden crashear. En archivos `.md` los acentos
  están bien.
- **El CLI es la superficie pública.** Skills y agentes externos apuntan al *contrato del
  CLI*, no a clases internas ([D-023]). Si cambiás el nombre de un subcomando, un flag o un
  formato de salida, **actualizá `skills/*/SKILL.md`** — `tests/test_skills_contract.py`
  detecta la deriva. Lo interno de `src/pipeline/` se refactoriza libremente.

## Decisiones de arquitectura (ADR)

Si tu cambio es una **decisión** (no un bugfix obvio), documentala en [`decisions/`](./decisions/):
numeración continua, máximo 10 por archivo, con **Contexto · Decisión · Consecuencias**.
Hacelo *como parte* del PR, no después.

## El flujo para proponer cambios

1. **Abrí un issue** primero para cambios no triviales — así discutimos el enfoque antes
   de que escribas código (respeta tu tiempo y el de quien revisa).
2. **Ramá** desde `main` (`git switch -c mi-cambio`). Trabajá el cambio completo.
3. **Corré `uv run pytest`** y dejalo en verde.
4. **Commit.** Git no tiene identidad global configurada aquí; commiteá con:
   ```bash
   git -c user.name="Tu Nombre" -c user.email="tu@correo.com" commit
   ```
   Mensajes claros, en español, en imperativo ("agrega ducking de música", no "agregado").
5. **Abrí el PR** y llená la plantilla (checklist de tests, ADR y skills).

## Checklist antes de abrir el PR

- [ ] `uv run pytest` pasa en verde.
- [ ] Si cambié el CLI, actualicé `skills/*/SKILL.md`.
- [ ] Si tomé una decisión de diseño, la registré en `decisions/`.
- [ ] No hay secretos, `.env` ni claves en el diff.
- [ ] La consola no imprime caracteres no-ASCII.
- [ ] El cambio respeta la regla de oro: **la persona sigue decidiendo**.

¿Dudas? Abrí un issue con la etiqueta `pregunta`. Acá se aprende preguntando.

[D-012]: ./decisions/0011-0020.md
[D-017]: ./decisions/0011-0020.md
[D-023]: ./decisions/0021-0030.md
