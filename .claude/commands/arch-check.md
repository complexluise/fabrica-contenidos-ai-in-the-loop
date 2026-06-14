---
description: El architect audita la coherencia docs<->código y propone fixes (solo docs + recomendaciones).
---

Despachá al subagente `architect` para una auditoría de coherencia
**documentación ↔ código**.

Alcance: $ARGUMENTS
(si no se especificó alcance arriba, auditá todo el repo: PRD/ARCHITECTURE/ROADMAP/ADRs vs src, app, tests).

Pedile que devuelva, en orden:
1. Veredicto de coherencia (¿el código refleja ARCHITECTURE? ¿el ROADMAP refleja lo
   hecho? ¿falta o sobra algún ADR?).
2. Drift concreto con `archivo:línea` (doc dice A, código hace B).
3. Recomendaciones de código para el `coder` (sin tocar código).
4. Las ediciones de docs que el architect SÍ hace para restaurar la sincronía
   (AC del ROADMAP, ADRs, punteros), diciendo qué archivos tocó.

Recordale: edita SOLO documentación, nunca código. Al terminar, reportame el resumen
y, si dejó recomendaciones de código, preguntame si querés que las mande al `coder`.
