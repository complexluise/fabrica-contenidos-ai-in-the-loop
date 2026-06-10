"""One-off (D-047 F5): enriquece el proyecto fracking con el artefacto audiovisual.

Carga el spec, conserva prompt/dialogo/ambience/audio existentes, y aplica por
plano la gramatica de camara + estructura visual + intencion + transicion, y la
curva de intensidad por escena. Reescribe via write_spec (valida el schema).

Correr: uv run python scripts/_enrich_fracking.py
"""

from __future__ import annotations

from pipeline.contracts import Camera, Visual
from pipeline.project import Project, load_project_spec, write_spec

SLUG = "desmintiendo_fracking_sostenible"

# Intensidad visual (1-5): arco que construye hacia los picos de "castigo" (s5) y
# la falla mas violenta (s8 cizallamiento); respiros en el dato y el cierre.
INTENSITY = {"s1": 4, "s2": 3, "s3": 4, "s4": 3, "s5": 5,
             "s6": 4, "s7": 4, "s8": 5, "s9": 3, "s10": 2, "s11": 1}

# Artefacto por (scene_id, shot_idx): intention, action(EN, alimenta generacion),
# camera, visual, transition. graphics = texto en pantalla real.
SHOTS = {
    ("s1", 0): dict(
        intention="Gancho: plantar el mito y desmentirlo de entrada con el sello FALSO",
        action="amigurumi crochet presenter holds a crochet oil-well cross-section prop (three "
               "concentric silver-gray tubes nested like a telescope, cream cement in the gaps) in "
               "both raised stubby yarn arms at chest level, prop sharp in foreground, knitted face "
               "in soft focus behind",
        camera=dict(size="CU", angle="eye", move="push_in", focus="shallow"),
        visual=dict(tone="neutral", palette=["cream", "mustard", "silver-gray", "red"],
                    foreground="el prop telescopico del pozo", background="fondo crema-mostaza liso",
                    focal_point="el prop en las manos del presentador",
                    graphics='"El fracking es seguro si se construye bien" + sello FALSO rojo'),
        transition="smash_cut"),
    ("s2", 0): dict(
        intention="Promesa: el problema no es la obra, es la fisica; preparar al espectador",
        action="amigurumi crochet presenter facing camera with a calm focused head tilt, two "
               "kinetic text cards floating at different heights",
        camera=dict(size="MCU", angle="eye", move="static", focus="shallow"),
        visual=dict(tone="high_key", palette=["cream", "white"],
                    background="fondo crema liso con bokeh suave",
                    focal_point="la cara del presentador", graphics='"fisica de materiales" / "geofisica"'),
        transition="cut"),
    ("s3", 0): dict(
        intention="Revelar que un pozo NO es un tubo simple: sorpresa estructural",
        action="hands slide three concentric silver-gray yarn tubes into position one inside the "
               "other like a telescope, cream cement filling the annular gaps, full prop on mustard fabric",
        camera=dict(size="LS", angle="overhead", move="push_in", focus="deep"),
        visual=dict(tone="neutral", palette=["silver-gray", "cream", "mustard"],
                    focal_point="el centro del telescopio de tubos", graphics='"ACERO + CEMENTO = el sello"'),
        transition="match_cut"),
    ("s3", 1): dict(
        intention="Aislar el sello: el cemento es la unica barrera entre gas y agua",
        action="extreme macro of the annular gap between the outer and middle silver-gray tubes, "
               "filled with thick cream-beige cement yarn, fiber texture filling the frame",
        camera=dict(size="ECU", angle="eye", move="static", focus="shallow"),
        visual=dict(tone="neutral", palette=["cream", "silver-gray"],
                    focal_point="la fibra del cemento en el hueco anular"),
        transition="cut"),
    ("s3", 2): dict(
        intention="Establecer la geografia del riesgo: gas abajo, agua arriba",
        action="overhead of the top edge of the prop where a wavy blue yarn aquifer band lays; a thin "
               "red yarn strand sits deep below between the tubes; camera pulls up revealing the vertical distance",
        camera=dict(size="MCU", angle="overhead", move="pull_out", focus="deep"),
        visual=dict(tone="neutral", palette=["blue", "silver-gray", "red"],
                    foreground="banda azul del acuifero", background="profundidad oscura del pozo",
                    focal_point="la distancia vertical entre gas y agua"),
        transition="cut"),
    ("s4", 0): dict(
        intention="Mostrar que SI se inspecciona: conceder el punto antes de matizarlo",
        action="looking down into the silver-gray tube from above, a small gray cylindrical crochet "
               "USI probe lowered slowly by a hand, white thread concentric wave circles radiating from the tip",
        camera=dict(size="LS", angle="overhead", move="push_in", focus="deep"),
        visual=dict(tone="low_key", palette=["silver-gray", "white", "charcoal"],
                    background="oscuridad atmosferica del pozo",
                    focal_point="la sonda y las ondas de ultrasonido"),
        transition="cut"),
    ("s4", 1): dict(
        intention="El limite clave: revisar hoy no garantiza el sello en 30 anos",
        action="extreme macro of the inner tube wall: a small green checkmark in green yarn on the left "
               "(intact bond), a small orange hourglass icon on the right (unknown future), rim-lit yarn fibers",
        camera=dict(size="ECU", angle="eye", move="static", focus="shallow"),
        visual=dict(tone="low_key", palette=["green", "orange", "silver-gray"],
                    focal_point="el contraste check verde vs reloj naranja",
                    graphics='"Revisar ≠ Garantizar"'),
        transition="cut"),
    ("s5", 0): dict(
        intention="Climax del castigo: el pozo se infla y desinfla a presiones enormes, en ciclos",
        action="side-angle of a cream-beige crochet sphere inside a rigid gray yarn mold, hands "
               "squeezing rhythmically from both sides, sphere compressing and bouncing back in cycles, "
               "red yarn arrows pointing inward",
        camera=dict(size="MLS", angle="eye", move="static", focus="deep"),
        visual=dict(tone="neutral", palette=["cream", "gray", "red"],
                    focal_point="la esfera comprimiendose", graphics='"Presion ciclica"'),
        transition="match_cut"),
    ("s5", 1): dict(
        intention="La consecuencia fisica: la fatiga abre micro-grietas en el material",
        action="extreme macro of the cream-beige yarn fibers at the compression point: stitches "
               "visibly pulling apart, yarn loops distorting under stress, micro-gaps forming",
        camera=dict(size="ECU", angle="eye", move="push_in", focus="shallow"),
        visual=dict(tone="neutral", palette=["cream"],
                    focal_point="las fibras separandose por fatiga"),
        transition="cut"),
    ("s6", 0): dict(
        intention="Falla 1, debonding: el acero se despega del cemento y queda un anillo",
        action="side shot of a silver-gray yarn tube gently pulled upward by fingers, the cream-beige "
               "cement annulus staying behind, a dark ring channel opening between them",
        camera=dict(size="MLS", angle="eye", move="pull_out", focus="deep"),
        visual=dict(tone="low_key", palette=["silver-gray", "cream", "black"],
                    background="fondo negro mate para contraste",
                    focal_point="el anillo oscuro que se abre", graphics='"1 · DESPEGUE (debonding)"'),
        transition="cut"),
    ("s6", 1): dict(
        intention="El atajo: el gas empieza a subir por el microanillo",
        action="extreme macro of the dark microannular gap between gray tube and cream cement ring, "
               "three thin red yarn strands curling upward through the narrow dark channel",
        camera=dict(size="ECU", angle="low", move="push_in", focus="shallow"),
        visual=dict(tone="low_key", palette=["red", "silver-gray", "black"],
                    background="canal oscuro y estrecho",
                    focal_point="las hebras rojas de gas ascendiendo"),
        transition="cut"),
    ("s7", 0): dict(
        intention="Falla 2, fisura radial: al dilatarse el acero agrieta el cemento",
        action="top-down of the cream-beige cement cylinder with a radial crack propagating outward "
               "from the center like a cracked windshield, the swollen silver-gray tube at the center",
        camera=dict(size="MS", angle="overhead", move="static", focus="deep"),
        visual=dict(tone="low_key", palette=["cream", "silver-gray"],
                    focal_point="la grieta radial desde el centro", graphics='"2 · FISURA RADIAL"'),
        transition="cut"),
    ("s7", 1): dict(
        intention="El camino del gas: si encuentra la grieta, llega al agua",
        action="tracking the red yarn strand as it travels along the radial crack from the inner "
               "annulus outward and upward toward a wavy blue yarn aquifer band at the top",
        camera=dict(size="CU", angle="low", move="track", focus="shallow"),
        visual=dict(tone="low_key", palette=["red", "cream", "blue"],
                    focal_point="la hebra roja acercandose al agua azul"),
        transition="dissolve"),
    ("s8", 0): dict(
        intention="Falla 3, cizallamiento: la fatiga dobla o corta el acero (la mas violenta)",
        action="silver-gray yarn tube bent at a sharp 35-degree kink, yarn fibers visibly stretched "
               "and stitches distorting at the bend, stress concentration at the deformation point",
        camera=dict(size="MCU", angle="dutch", move="push_in", focus="shallow"),
        visual=dict(tone="low_key", palette=["silver-gray", "charcoal"],
                    background="fondo carbon oscuro con rim-light",
                    focal_point="el quiebre del tubo", graphics='"3 · CIZALLAMIENTO"'),
        transition="cut"),
    ("s8", 1): dict(
        intention="El resultado oculto: el pozo roto, donde nadie lo ve",
        action="overhead top-down of the kinked area, the cream cement block with radial stress "
               "fractures around the bend, the broken casing cross-section seen from above",
        camera=dict(size="CU", angle="overhead", move="static", focus="deep"),
        visual=dict(tone="low_key", palette=["cream", "silver-gray", "charcoal"],
                    focal_point="la seccion rota del casing"),
        transition="cut"),
    ("s9", 0): dict(
        intention="Cierre: y esto en el MEJOR caso; faltan geologia, quimicos y sismos",
        action="amigurumi crochet presenter in tight close-up with a concerned expression; below the "
               "frame edge a crochet geological diorama with an amber fault line through earthy rock strata, "
               "blue droplet and orange seismic-wave knitted icons",
        camera=dict(size="CU", angle="eye", move="static", focus="shallow"),
        visual=dict(tone="neutral", palette=["caramel", "brown", "ochre", "amber"],
                    foreground="diorama geologico de crochet", focal_point="la cara preocupada del presentador",
                    graphics='"fallas geologicas · quimicos · sismicidad inducida"'),
        transition="cut"),
    ("s10", 0): dict(
        intention="El dato cientifico duro: 6x mas fallas en shale (Ingraffea, PNAS 2014)",
        action="a large bold 6x numeral enters frame center with a subtle zoom-in, cream yarn texture "
               "filling the numbers on a dark warm charcoal background",
        camera=dict(size="MS", angle="eye", move="push_in", focus="deep"),
        visual=dict(tone="low_key", palette=["charcoal", "cream", "white"],
                    focal_point="el numeral 6x",
                    graphics='"6x — pozos de shale vs convencionales"'),
        transition="cut"),
    ("s10", 1): dict(
        intention="Aterrizar el dato: lo enterrado a kilometros no se repara",
        action="side-by-side of two minimalist crochet well silhouettes, left intact silver-gray and "
               "cream (conventional), right with red yarn damage marks and gaps (shale, degraded)",
        camera=dict(size="MS", angle="eye", move="static", focus="deep"),
        visual=dict(tone="low_key", palette=["silver-gray", "cream", "red", "charcoal"],
                    focal_point="el contraste convencional vs shale",
                    graphics='"CONVENCIONAL / SHALE — Ingraffea et al., PNAS 2014, 41.000 pozos"'),
        transition="cut"),
    ("s11", 0): dict(
        intention="CTA: el riesgo no se elimina, solo se aplaza; compartir",
        action="amigurumi crochet presenter in medium shot, relaxed warm smile, stubby yarn arms open "
               "in a welcoming gesture, plain warm cream background with soft bokeh",
        camera=dict(size="MS", angle="eye", move="static", focus="shallow"),
        visual=dict(tone="high_key", palette=["cream", "caramel", "navy"],
                    background="fondo crema calido con bokeh", focal_point="el presentador en gesto abierto",
                    graphics='"@handle · Comparte · Fuentes: ver descripcion"'),
        transition="cut"),
}


def main() -> None:
    project = Project(SLUG)
    spec = load_project_spec(project.spec_path)
    touched = 0
    for scene in spec.scenes:
        scene.visual_intensity = INTENSITY.get(scene.id, scene.visual_intensity)
        for j, shot in enumerate(scene.shots):
            art = SHOTS.get((scene.id, j))
            if not art:
                continue
            shot.intention = art["intention"]
            shot.action = art["action"]
            shot.framing = ""  # el artefacto reemplaza al framing legacy
            shot.camera = Camera(**art["camera"])
            shot.visual = Visual(**art["visual"])
            shot.transition = art.get("transition")
            touched += 1
    write_spec(spec, project.spec_path)
    print(f"Enriquecidos {touched} planos en {len(spec.scenes)} escenas -> {project.spec_path}")


if __name__ == "__main__":
    main()
