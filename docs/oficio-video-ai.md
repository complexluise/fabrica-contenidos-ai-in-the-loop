# Oficio de video con IA — las reglas que fundamentan D-070..D-074

Conocimiento operativo destilado de investigación con fuentes (2026-06), citado por los ADRs
D-070..D-074. Las versiones ejecutables viven en el código (`prompt_compile.py`, `finish.py`,
`author.py`); este documento es la referencia completa para autoría de guiones y futuras
decisiones. **Regla cero (D-070, aprendida cara):** fal ignora en silencio los parámetros
desconocidos — verificar cada parámetro contra el endpoint EXACTO (standard ≠ pro) antes de
confiar en él.

## 1. El dialecto de prompting i2v (Kling) — D-072

**La regla madre:** en image-to-video NO se describe la escena. La imagen ES la escena;
re-describirla hace que el modelo la lea como estado-objetivo (ya lo tiene → no anima casi
nada → cámara lenta flotante). Fórmula oficial de Kling para i2v: `Sujeto + Movimiento` —
nada más. 15–40 palabras.

**Estructura recomendada (orden importa; los primeros tokens pesan más):**
1. Instrucción de cámara (UNA sola; combinarlas deforma la geometría).
2. Acción del sujeto (presente, transitiva, UNA acción primaria; dos beats máximo con "then").
3. Movimiento secundario (lluvia, partículas, luz).
4. Qué queda quieto ("background remains static").

**Reglas con causa documentada:**
- **Velocidad explícita siempre** ("quickly", "at normal speed"): sin ella Kling defaultea a
  slow-mo onírico. Truco A/B-teable: "slow motion" en el negative.
- **Endpoint siempre** ("then settles into position", "comes to rest"): movimiento abierto
  ("moving around") = deriva/morphing.
- **Cámara siempre explícita** — la cámara sin especificar es causa de warping; "static shot,
  camera remains fixed" reduce morphing activamente.
- **Lenguaje de contacto explícito** ("making contact with", "touching"): lo espacial vago
  ("drinking from glass") morfea.
- La acción debe CABER en ~5s físicos; una acción de 20s prompteada en 5s sale en cámara lenta.
- Números concretos ("5 trees") fallan; el modelo no cuenta.

**Negative prompt (5–8 términos, el peor primero):** `morphing faces, identity drift, extra
limbs, slow motion, blur, distort` (+ `face swap, character merge` con 2 personajes). El
negative de imagen habla de píxeles; el de video, de TIEMPO.

**cfg_scale (default 0.5):** subir hacia 0.7 si ignora la cámara/acción; bajar a 0.3–0.4 si
el movimiento sale robótico.

**Interpolación start→end (planos `lands`):** describir la TRANSICIÓN, no el estado final
(los frames ya definen los extremos); mismas escena/luz/identidad entre ambos frames o el
modelo cae a cross-dissolve morfoso; si el camino se siente apurado → 10s en vez de 5.
En fal: `tail_image_url`, SOLO Kling 2.1 PRO ($0.45/5s). Vidu Q1 start-end ≈ $0.10/s.

Fuentes: guía oficial Kling (docs.qingque.cn), guías fal.ai (kling-2-6-pro-prompt-guide,
blog kling-3-0), VEED kling-ai-prompting-guide (pares buenos/malos verbatim), GeeLark,
Ambience AI, videoai.me (negatives testeados), Tona AI (start/end frame).

## 2. Gramática brickfilm (estilo LEGO) — D-070

**El precedente exacto:** "Trinity Help" (2009) recreó la esquiva de Matrix en LEGO: la
esquiva es UNA pose extrema sostenida (torso bisagrado, piernas plantadas) y **la CÁMARA
orbita** — la cámara actúa, el minifig posa. Para i2v esto convierte el caso más difícil
(coreografía articulada) en el más confiable (cámara sobre escena casi estática).

**Reglas de mundo (The LEGO Movie / Animal Logic):**
1. Buildability absoluta: cada frame construible con bricks reales — humo, destellos,
   estelas, balas (cilindro trans-amarillo) incluidos. La destrucción separa POR los studs.
2. Los cuerpos jamás se doblan ni deforman (7 articulaciones); un brazo lidera y el cuerpo
   lo alcanza un beat después.
3. Sin motion blur fotográfico en figuras: smears construidos de bricks translúcidos.
4. Cámara = cámara física a escala minifig: nivel de ojo (~4cm), look macro, DOF de pocos
   studs, **siempre un oclusor desenfocado en primer plano**, micro-jitter con overshoot
   (nunca un glide CG estéril).
5. Plástico vivido: huellas, micro-rayones, líneas de molde.

**Reglas de actuación (cara fija):** emoción = ángulo de cámara (low=poder, high=derrota,
dutch=caos) + postura (cabeza/torso/brazos) + plano de reacción. La expresión impresa es un
PROP que se cambia entre planos, jamás morfea dentro de uno.

**Reglas de acción:** los impactos no se suavizan (parada instantánea / rebote / follow-
through); el corte ocurre EN el contacto y el sonido vende el golpe — la reacción ES el
puñetazo; planos de acción 0.5–1.5s, cortados en acción.

Fuentes: fxguide + Expanded Cinematography + MPA (The LEGO Movie / Animal Logic), IndieWire
(Chris McKay), Bricks in Motion, Stop Motion Tutorials, Brickfilms Wiki (Trinity Help),
Four Bricks Tall (k.c.legos).

## 3. La capa de finishing — D-073

**Orden canónico (load-bearing, como un node tree):**
`normalizar por clip → look compartido (curva S + saturación 0.9) → vignette → halation →
sharpen → GRANO (último op visual) → loudnorm (audio al final)`.

- **Grano temporal** fino 35mm al 10–15% (≈ `noise=alls=5-10:allf=t+u`): "reduce la
  detección de AI hasta 40%" (Green Frog Labs). Sobre el film CONCATENADO (unifica tomas de
  generaciones distintas) y SIEMPRE con encode `-tune grain`.
- **Halation casi invisible** (alpha ~0.12, solo highlights altos, tinte cálido, screen):
  los coloristas avisan que si se nota, está mal.
- "Los colores de cine pueden ser saturados o luminosos, nunca ambos" → bajar saturación +
  roll-off de highlights = el golpe directo al "plástico digital" (el colorista de 20 años
  del ad de Porsche con Veo gradea exactamente para eso).
- **Velocidad 1.10–1.30x por clip** + conformar todo a 24fps: el fix documentado de la
  flotación AI. `tblend=average` añade el motion blur que al AI le falta.
- **Audio = ~50% de la experiencia percibida** (la cifra más repetida del oficio): room tone
  continuo bajo TODO + música ducked + impactos en cortes de beat (no en todos). Mastering
  **two-pass loudnorm linear a −14 LUFS / −1.0 dBTP** (IG/TikTok; pasarse activa el
  limitador de la plataforma).
- IG 1080×1920: zona segura inferior 320px, derecha 120px; mixed case > ALL-CAPS; un solo
  color de acento; bold geométrico (Montserrat/Inter/Poppins).

Fuentes: Noam Kroll (orden de grading), CROMO/Blackmagic forum (node order), Lift Gamma Gain
(halation), int10h + logiclrd gist (ffmpeg grain/halation), Green Frog Labs (checklist
anti-slop), 344 Audio / FilmLocal (el 50%), ClickyApps + 32blog (LUFS), Zeely/Outfy (safe
zones), Reelwords/OpusClip (captions).

## 4. La economía de tomas — D-074

Los números reales de los creadores top (con el MISMO stack que este pipeline):
- **PJ Accetturo** (Nano Banana + Kling): ad de Kalshi (NBA Finals) = **300–400 generaciones
  → 15 clips**, $2,000, 2 días, solo. Su ratio de video tras curaduría dura de stills: 3:1–5:1.
  Regla: 5–10 variaciones por escena, "cherry-pick the most realistic physics".
- **shy kids** ("Air Head", Sora): ratio **300:1**; de cada generación de 20s conservaban
  **2–3 segundos**.
- **Pipeline universal stills-first** (PJ, Curious Refuge, Daubrez, Gabe Michael): el frame
  exacto se fija (y se retoca a nivel píxel) ANTES de gastar video; en el workflow de 10
  pasos de Curious Refuge el video aparece en el paso 8.
- **Planos finales de 2–5s**: la atención en contenido AI cae a los 6–8s (vs 10–12 real);
  nadie publica un clip crudo de 5s.
- Prompts por plano AUTOSUFICIENTES: re-describir personaje/setting/tono en cada generación
  de still (nunca asumir que el modelo recuerda contexto) — para VIDEO i2v aplica lo
  contrario (§1: la imagen ya lo trae).

Traducción a este pipeline: menos planos-video × más `takes` × descarte humano
(`pipeline takes` / `pick-take`); contemplativos como `media: still` (Ken Burns, $0);
el costo por corrida es una decisión del guion, no una constante.

Fuentes: The Creator Report + DesignRush + villager1598 (PJ Accetturo), No Film School + MIT
Technology Review (shy kids), New Atlas + Creative Bloq (Gaál/Porsche), Curious Refuge
(workflow 10 pasos), Runway customer stories (Gen:48).
