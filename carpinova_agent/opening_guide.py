"""Recovery of the PR #37 educational opening guide from exact visual evidence.

This is a *functional reconstruction*, not the original lost Git commit.
First four illustrations retain the reviewed OPENING_all.svg evidence.
G20 corrects only the fifth panel using the verified Knowledge book pp. 124-125.
No new tool, CAD geometry, panel BOM, machining, or fabrication authority.
"""
from __future__ import annotations

from typing import Any
from .core import DesignError

# Four preserved illustrations and one source-backed G20 inverted-T correction. Kept inline so editable-install
# packages do not need resource files or packaging/configuration changes.
_SVG_ALL = (
    "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1240\" height=\"1240\" viewBox=\"0 0 1240 1240\" role=\"img\" aria-"
    "label=\"Guía visual de manija, uñero, perfil Gola, apertura por presión y Gola de madera con T invertida. So"
    "lo revisión, no fabricar\"><title>Cómo abrir cajones y puertas sin confundir sistemas</title><desc>Comparaci"
    "ón educativa de manija externa, uñero, perfil Gola y apertura por presión. La quinta opción muestra una T i"
    "nvertida de madera fija, con montante vertical, aleta horizontal inferior, hueco para dedos y frente móvil "
    "que se abre hacia fuera. Libro de carpintería PDF 124-125; montaje, holgura y función de tope del cajón no "
    "validados.</desc><style>text{font-family:Arial,sans-serif;fill:#24354b}.title{font-size:27px;font-weight:70"
    "0}.subtitle{font-size:16px;fill:#4b6178}.card-title{font-size:19px;font-weight:700}.gesture{font-size:13px;"
    "fill:#1e6880;font-weight:700}.note{font-size:13px}.small{font-size:13px;fill:#46576a}.mini{font-size:13px;f"
    "ont-weight:700;fill:#53677d}.card{fill:#f8fafc;stroke:#becbd9;stroke-width:1.6}.selected{fill:#e8f6f8;strok"
    "e:#16718a;stroke-width:3}.wood{fill:#d4aa82;stroke:#8a674e;stroke-width:2}.concept-rail{fill:#e4e9ec;stroke"
    ":#506b76;stroke-width:2;stroke-dasharray:5 3}.grip-gap{fill:#f0f8f9;stroke:#8cb7c1;stroke-width:1;stroke-da"
    "sharray:4 3}.metal{fill:#405769;stroke:#233648;stroke-width:1}.groove{stroke:#24394c;stroke-width:8;fill:no"
    "ne;stroke-linecap:round}.recess{fill:#93b0bc;opacity:.85}.metal-line{stroke:#344c60;stroke-width:4;fill:non"
    "e}.press{fill:#e3f4f5;stroke:#1e788e;stroke-width:2}.arrow{stroke:#19738b;stroke-width:4;fill:none;stroke-l"
    "inejoin:round}.finger{stroke:#d89e76;stroke-width:13;fill:none;stroke-linecap:round}.warning{fill:#923b1e;f"
    "ont-size:14px;font-weight:700}</style><rect x=\"0\" y=\"0\" width=\"1240\" height=\"1240\" fill=\"#f6f8fb\"/><rect x="
    "\"28\" y=\"22\" width=\"1184\" height=\"1200\" rx=\"21\" fill=\"white\"/><text x=\"60\" y=\"75\" class=\"title\">¿CÓMO SE ABR"
    "E UN CAJÓN O UNA PUERTA?</text><text x=\"60\" y=\"107\" class=\"subtitle\">Mismo mueble pequeño · cuatro formas d"
    "e uso · dibujo sin escala</text><rect x=\"58\" y=\"146\" width=\"554\" height=\"290\" rx=\"13\" class=\"card\"/><text x"
    "=\"79\" y=\"179\" class=\"card-title\">1. Manija externa</text><text x=\"79\" y=\"207\" class=\"gesture\">AGARRAR Y TIR"
    "AR</text><rect x=\"83\" y=\"255\" width=\"208\" height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"349\" y=\"245\" width=\"11"
    "6\" height=\"134\" rx=\"6\" class=\"wood\"/><text x=\"99\" y=\"244\" class=\"mini\">CAJÓN</text><text x=\"367\" y=\"233\" cl"
    "ass=\"mini\">PUERTA</text><rect x=\"155\" y=\"307\" width=\"64\" height=\"10\" rx=\"5\" class=\"metal\"/><rect x=\"400\" y="
    "\"282\" width=\"9\" height=\"62\" rx=\"4\" class=\"metal\"/><text x=\"95\" y=\"398\" class=\"note\">Manija visible: sale de"
    "l frente</text><text x=\"80\" y=\"416\" class=\"small\">Se fija por fuera y sobresale del frente.</text><rect x=\""
    "633\" y=\"146\" width=\"554\" height=\"290\" rx=\"13\" class=\"card\"/><text x=\"654\" y=\"179\" class=\"card-title\">2. Uñe"
    "ro</text><text x=\"654\" y=\"207\" class=\"gesture\">METER DEDOS Y TIRAR</text><rect x=\"658\" y=\"255\" width=\"208\" "
    "height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"924\" y=\"245\" width=\"116\" height=\"134\" rx=\"6\" class=\"wood\"/><text"
    " x=\"674\" y=\"244\" class=\"mini\">CAJÓN</text><text x=\"942\" y=\"233\" class=\"mini\">PUERTA</text><path d=\"M734 257"
    " Q762 290 790 257\" class=\"groove\"/><path d=\"M926 298 Q953 310 926 322\" class=\"groove\"/><text x=\"670\" y=\"398"
    "\" class=\"note\">Rebaje en canto/frente (sin manija externa)</text><text x=\"655\" y=\"416\" class=\"small\">El ded"
    "o entra en un rebaje del frente.</text><rect x=\"58\" y=\"466\" width=\"554\" height=\"290\" rx=\"13\" class=\"card\"/>"
    "<text x=\"79\" y=\"499\" class=\"card-title\">3. Perfil / gola</text><text x=\"79\" y=\"527\" class=\"gesture\">METER D"
    "EDOS Y TIRAR</text><rect x=\"83\" y=\"575\" width=\"208\" height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"349\" y=\"565\""
    " width=\"116\" height=\"134\" rx=\"6\" class=\"wood\"/><text x=\"99\" y=\"564\" class=\"mini\">CAJÓN</text><text x=\"367\" "
    "y=\"553\" class=\"mini\">PUERTA</text><rect x=\"88\" y=\"580\" width=\"198\" height=\"13\" class=\"recess\"/><path d=\"M93"
    " 598 H281\" class=\"metal-line\"/><rect x=\"357\" y=\"570\" width=\"12\" height=\"119\" class=\"recess\"/><text x=\"95\" y"
    "=\"718\" class=\"note\">Canal continuo: sección y montaje por definir</text><text x=\"80\" y=\"736\" class=\"small\">"
    "Un canal integrado deja agarrar el borde.</text><rect x=\"633\" y=\"466\" width=\"554\" height=\"290\" rx=\"13\" clas"
    "s=\"card\"/><text x=\"654\" y=\"499\" class=\"card-title\">4. Por presión</text><text x=\"654\" y=\"527\" class=\"gestur"
    "e\">PRESIONAR Y SOLTAR</text><rect x=\"658\" y=\"575\" width=\"208\" height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"92"
    "4\" y=\"565\" width=\"116\" height=\"134\" rx=\"6\" class=\"wood\"/><text x=\"674\" y=\"564\" class=\"mini\">CAJÓN</text><te"
    "xt x=\"942\" y=\"553\" class=\"mini\">PUERTA</text><circle cx=\"762\" cy=\"630\" r=\"22\" class=\"press\"/><text x=\"743\" "
    "y=\"636\" class=\"mini\">PUSH</text><path d=\"M903 632 h-27 l9 -8 m-9 8 l9 8\" class=\"arrow\"/><circle cx=\"983\" cy"
    "=\"632\" r=\"14\" class=\"press\"/><text x=\"670\" y=\"718\" class=\"note\">Sin tirador: requiere mecanismo compatible<"
    "/text><text x=\"655\" y=\"736\" class=\"small\">El mecanismo empuja el frente al presionar.</text><rect x=\"58\" y="
    "\"795\" width=\"1127\" height=\"306\" rx=\"13\" class=\"card\"/><text x=\"80\" y=\"826\" class=\"card-title\">5. Gola de ma"
    "dera: T invertida, agarre oculto</text><text x=\"80\" y=\"851\" class=\"small\">Corte lateral conceptual · la pie"
    "za fija NO se mueve con el cajón · no es un tope certificado</text><text x=\"100\" y=\"883\" class=\"mini\">A. CÓ"
    "MO SE AGARRA EL FRENTE</text><rect x=\"114\" y=\"895\" width=\"426\" height=\"19\" class=\"wood\" data-part=\"fixed-to"
    "p-board\"/><rect x=\"291\" y=\"914\" width=\"27\" height=\"83\" class=\"wood\" data-concept=\"inverted-t-stem\"/><rect x"
    "=\"224\" y=\"978\" width=\"160\" height=\"19\" class=\"wood\" data-concept=\"inverted-t-lower-flange\"/><rect x=\"442\" y"
    "=\"933\" width=\"38\" height=\"121\" rx=\"3\" fill=\"#a8bfcd\" stroke=\"#324b62\" stroke-width=\"2\" data-part=\"moving-dr"
    "awer-front\"/><rect x=\"384\" y=\"931\" width=\"58\" height=\"45\" class=\"grip-gap\" data-concept=\"finger-clearance-n"
    "ot-dimensioned\"/><path d=\"M444 944 C424 940 407 946 396 958\" class=\"finger\" data-action=\"insert-fingers\"/><"
    "path d=\"M487 1014 H557 L546 1005 M557 1014 L546 1023\" class=\"arrow\" data-action=\"pull-front\"/><text x=\"107\""
    " y=\"1033\" class=\"small\">Pieza fija en madera: montante y ALETA INFERIOR</text><text x=\"108\" y=\"1053\" class="
    "\"small\">Los dedos entran DETRÁS del borde del frente.</text><text x=\"107\" y=\"1076\" class=\"mini\">T fija · fr"
    "ente gris móvil · abrir hacia la derecha</text><text x=\"656\" y=\"882\" class=\"mini\">B. SECCIÓN AISLADA: T INV"
    "ERTIDA</text><rect x=\"759\" y=\"913\" width=\"27\" height=\"81\" class=\"wood\" data-concept=\"inverted-t-detail-stem"
    "\"/><rect x=\"688\" y=\"994\" width=\"166\" height=\"19\" class=\"wood\" data-concept=\"inverted-t-detail-lower-flange\""
    "/><text x=\"892\" y=\"937\" class=\"small\">Montante VERTICAL</text><text x=\"892\" y=\"957\" class=\"small\">Aleta HOR"
    "IZONTAL ABAJO</text><text x=\"892\" y=\"977\" class=\"small\">Sobresale a ambos lados</text><text x=\"655\" y=\"1041"
    "\" class=\"small\">Libro: PDF 124-125 (impresas 102-103).</text><text x=\"655\" y=\"1060\" class=\"small\">Figura: a"
    "lto 6,5 cm / base 5 cm (SOLO referencia).</text><text x=\"655\" y=\"1083\" class=\"warning\">TOPE DE CAJÓN NO VER"
    "IFICADO.</text><text x=\"78\" y=\"1149\" class=\"subtitle\">COMPARA: manija sobresale · uñero y perfil requieren "
    "agarre · presión usa mecanismo.</text><text x=\"78\" y=\"1180\" class=\"warning\">SOLO EXPLICACIÓN VISUAL. No def"
    "ine espesores, perfiles, fresados, fijaciones ni compatibilidad.</text><text x=\"78\" y=\"1207\" class=\"warning"
    "\">NO CORTAR · NO TALADRAR · NO COMPRAR · NO FABRICAR.</text></svg>"
)

_OPTIONS = (
    ("handle", "Manija externa", "Agarre sobresaliente: se tira."),
    ("finger_pull", "Uñero", "Rebaje donde entran los dedos para tirar."),
    ("profile", "Perfil / gola", "Canal continuo para agarrar y tirar."),
    ("push_to_open", "Por presión", "Se presiona el frente: requiere mecanismo."),
)
_FOCUS_COORDS = {
    "handle": (58, 146), "finger_pull": (633, 146),
    "profile": (58, 466), "push_to_open": (633, 466),
}


def opening_guide_svg(focus: str = "all") -> str:
    """Keep the artifact byte-identical for 'all'; accent only selected card."""
    if type(focus) is not str or (focus not in _FOCUS_COORDS
                                   and focus not in ("all", "t_rail_concept")):
        raise DesignError("focus desconocido para la guía de aperturas.")
    if focus == "all":
        return _SVG_ALL
    if focus == "t_rail_concept":
        old = '<rect x="58" y="795" width="1127" height="306" rx="13" class="card"/>'
    else:
        x, y = _FOCUS_COORDS[focus]
        old = (f'<rect x="{x}" y="{y}" width="554" height="290" '
               'rx="13" class="card"/>')
    assert _SVG_ALL.count(old) == 1, "PR37 reviewed SVG source changed unexpectedly"
    return _SVG_ALL.replace(old, old.replace('class="card"', 'class="selected"'), 1)


def guide_opening_systems(spec: Any) -> dict[str, Any]:
    """Serve a human educational slide through the existing Maestro route."""
    if (type(spec) is not dict or spec.get("type") != "opening_system_guide"
            or set(spec) - {"type", "focus"}):
        raise DesignError("Guía de aperturas: type y focus opcional solamente.")
    focus = spec.get("focus", "all")
    # Validate before rendering even when text explanation is selected.
    svg = opening_guide_svg(focus)
    lines = [
        "SISTEMAS DE APERTURA · GUÍA ILUSTRATIVA, NO PARA FABRICAR",
        "Manija: visible fuera del frente; agarrar y tirar.",
        "Uñero: rebaje que permite meter los dedos y tirar.",
        "Perfil/gola: canal continuo de agarre; sección real por confirmar.",
        "Por presión: el frente se libera mediante mecanismo compatible.",
        "Gola de madera con T invertida: aleta horizontal inferior y montante fijo. "
        "Los dedos entran detrás del frente para tirar de él. "
        "El libro lo ilustra para puertas; su aplicación a cajones, anclaje, "
        "holgura y función de tope aún no están validados.",
        "NO CORTAR, NO TALADRAR, NO COMPRAR, NO FABRICAR.",
    ]
    return {
        "type": "opening_system_guide",
        "status": "NEEDS_USER_CONFIRMATION",
        "guided": True,
        "focus": focus,
        "review_only": True,
        "opening_options": [
            {"intent": key, "name": name, "description": detail,
             "selectable_for_drawer": True}
            for key, name, detail in _OPTIONS
        ] + [{"intent": None, "concept_id": "t_rail_concept",
              "name": "Gola de madera: T invertida",
              "description": "Gola de madera con T invertida del libro; montaje y tope de cajón no verificados.",
              "selectable_for_drawer": False}],
        "sketch_svg": svg,
        "sketch_text": "\n".join(lines),
        "human_summary": (
            "Las cuatro aperturas habituales se conservan. La quinta muestra "
            "una T invertida de madera fija con aleta inferior para explicar "
            "el agarre oculto; no acredita un tope ni montaje en cajones."
        ),
        "blockers": [
            "El libro describe una T invertida de madera para puertas; "
            "usarla en cajones o como tope requiere validación independiente.",
            "Faltan material, agarre útil, sección, fijaciones y "
            "compatibilidad; no aprobar mecanizado ni fabricación."
        ],
        "piece_count": 0,
        "can_generate_f7c": False,
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
    }
