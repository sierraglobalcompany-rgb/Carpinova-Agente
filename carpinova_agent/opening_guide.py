"""Recovery of the PR #37 educational opening guide from exact visual evidence.

This is a *functional reconstruction*, not the original lost Git commit.
First four illustrations retain the reviewed OPENING_all.svg evidence.
G23 replaces the fifth panel with the G22 blocked-vs-accessible concept, using Knowledge book pp. 124-125.
No new tool, CAD geometry, panel BOM, machining, or fabrication authority.
"""
from __future__ import annotations

from typing import Any
from .core import DesignError

# Four preserved illustrations and one source-backed G20 inverted-T correction. Kept inline so editable-install
# packages do not need resource files or packaging/configuration changes.
_SVG_ALL = (
    "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1240\" height=\"1510\" viewBox=\"0 0 1240 1510\" role=\"img\" aria-"
    "label=\"Guía de cinco aperturas: contraste entre tapa que bloquea la entrada y ranura para agarrar el frente"
    " móvil. T invertida fija, sin fabricación\"><title>Cómo abrir cajones y puertas sin confundir sistemas</titl"
    "e><desc>Las cuatro primeras opciones permanecen. La quinta compara A, tapa que bloquea el acceso, y B, ranu"
    "ra desde el exterior para alcanzar el borde del frente móvil y tirar de él. La T de madera permanece fija, "
    "sin manos. H y V no se han validado; 20 mm es una propuesta del usuario, no un mínimo del libro.</desc><sty"
    "le>text{font-family:Arial,sans-serif;fill:#24354b}.title{font-size:27px;font-weight:700}.subtitle{font-size"
    ":16px;fill:#4b6178}.card-title{font-size:19px;font-weight:700}.gesture{font-size:13px;fill:#1e6880;font-wei"
    "ght:700}.note{font-size:13px}.small{font-size:13px;fill:#46576a}.mini{font-size:13px;font-weight:700;fill:#"
    "53677d}.card{fill:#f8fafc;stroke:#becbd9;stroke-width:1.6}.selected{fill:#e8f6f8;stroke:#16718a;stroke-widt"
    "h:3}.wood{fill:#d4aa82;stroke:#8a674e;stroke-width:2}.concept-rail{fill:#e4e9ec;stroke:#506b76;stroke-width"
    ":2;stroke-dasharray:5 3}.grip-gap{fill:#f0f8f9;stroke:#8cb7c1;stroke-width:1;stroke-dasharray:4 3}.metal{fi"
    "ll:#405769;stroke:#233648;stroke-width:1}.groove{stroke:#24394c;stroke-width:8;fill:none;stroke-linecap:rou"
    "nd}.recess{fill:#93b0bc;opacity:.85}.metal-line{stroke:#344c60;stroke-width:4;fill:none}.press{fill:#e3f4f5"
    ";stroke:#1e788e;stroke-width:2}.arrow{stroke:#19738b;stroke-width:4;fill:none;stroke-linejoin:round}.finger"
    "{stroke:#d89e76;stroke-width:13;fill:none;stroke-linecap:round}.warning{fill:#923b1e;font-size:14px;font-we"
    "ight:700}</style><rect x=\"0\" y=\"0\" width=\"1240\" height=\"1240\" fill=\"#f6f8fb\"/><rect x=\"28\" y=\"22\" width=\"11"
    "84\" height=\"1200\" rx=\"21\" fill=\"white\"/><text x=\"60\" y=\"75\" class=\"title\">¿CÓMO SE ABRE UN CAJÓN O UNA PUER"
    "TA?</text><text x=\"60\" y=\"107\" class=\"subtitle\">Mismo mueble pequeño · cuatro formas de uso · dibujo sin es"
    "cala</text><rect x=\"58\" y=\"146\" width=\"554\" height=\"290\" rx=\"13\" class=\"card\"/><text x=\"79\" y=\"179\" class=\""
    "card-title\">1. Manija externa</text><text x=\"79\" y=\"207\" class=\"gesture\">AGARRAR Y TIRAR</text><rect x=\"83\""
    " y=\"255\" width=\"208\" height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"349\" y=\"245\" width=\"116\" height=\"134\" rx=\"6"
    "\" class=\"wood\"/><text x=\"99\" y=\"244\" class=\"mini\">CAJÓN</text><text x=\"367\" y=\"233\" class=\"mini\">PUERTA</te"
    "xt><rect x=\"155\" y=\"307\" width=\"64\" height=\"10\" rx=\"5\" class=\"metal\"/><rect x=\"400\" y=\"282\" width=\"9\" heigh"
    "t=\"62\" rx=\"4\" class=\"metal\"/><text x=\"95\" y=\"398\" class=\"note\">Manija visible: sale del frente</text><text "
    "x=\"80\" y=\"416\" class=\"small\">Se fija por fuera y sobresale del frente.</text><rect x=\"633\" y=\"146\" width=\"5"
    "54\" height=\"290\" rx=\"13\" class=\"card\"/><text x=\"654\" y=\"179\" class=\"card-title\">2. Uñero</text><text x=\"654"
    "\" y=\"207\" class=\"gesture\">METER DEDOS Y TIRAR</text><rect x=\"658\" y=\"255\" width=\"208\" height=\"112\" rx=\"7\" c"
    "lass=\"wood\"/><rect x=\"924\" y=\"245\" width=\"116\" height=\"134\" rx=\"6\" class=\"wood\"/><text x=\"674\" y=\"244\" clas"
    "s=\"mini\">CAJÓN</text><text x=\"942\" y=\"233\" class=\"mini\">PUERTA</text><path d=\"M734 257 Q762 290 790 257\" cl"
    "ass=\"groove\"/><path d=\"M926 298 Q953 310 926 322\" class=\"groove\"/><text x=\"670\" y=\"398\" class=\"note\">Rebaje"
    " en canto/frente (sin manija externa)</text><text x=\"655\" y=\"416\" class=\"small\">El dedo entra en un rebaje "
    "del frente.</text><rect x=\"58\" y=\"466\" width=\"554\" height=\"290\" rx=\"13\" class=\"card\"/><text x=\"79\" y=\"499\" "
    "class=\"card-title\">3. Perfil / gola</text><text x=\"79\" y=\"527\" class=\"gesture\">METER DEDOS Y TIRAR</text><r"
    "ect x=\"83\" y=\"575\" width=\"208\" height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"349\" y=\"565\" width=\"116\" height=\""
    "134\" rx=\"6\" class=\"wood\"/><text x=\"99\" y=\"564\" class=\"mini\">CAJÓN</text><text x=\"367\" y=\"553\" class=\"mini\">"
    "PUERTA</text><rect x=\"88\" y=\"580\" width=\"198\" height=\"13\" class=\"recess\"/><path d=\"M93 598 H281\" class=\"met"
    "al-line\"/><rect x=\"357\" y=\"570\" width=\"12\" height=\"119\" class=\"recess\"/><text x=\"95\" y=\"718\" class=\"note\">C"
    "anal continuo: sección y montaje por definir</text><text x=\"80\" y=\"736\" class=\"small\">Un canal integrado de"
    "ja agarrar el borde.</text><rect x=\"633\" y=\"466\" width=\"554\" height=\"290\" rx=\"13\" class=\"card\"/><text x=\"65"
    "4\" y=\"499\" class=\"card-title\">4. Por presión</text><text x=\"654\" y=\"527\" class=\"gesture\">PRESIONAR Y SOLTAR"
    "</text><rect x=\"658\" y=\"575\" width=\"208\" height=\"112\" rx=\"7\" class=\"wood\"/><rect x=\"924\" y=\"565\" width=\"116"
    "\" height=\"134\" rx=\"6\" class=\"wood\"/><text x=\"674\" y=\"564\" class=\"mini\">CAJÓN</text><text x=\"942\" y=\"553\" cl"
    "ass=\"mini\">PUERTA</text><circle cx=\"762\" cy=\"630\" r=\"22\" class=\"press\"/><text x=\"743\" y=\"636\" class=\"mini\">"
    "PUSH</text><path d=\"M903 632 h-27 l9 -8 m-9 8 l9 8\" class=\"arrow\"/><circle cx=\"983\" cy=\"632\" r=\"14\" class=\""
    "press\"/><text x=\"670\" y=\"718\" class=\"note\">Sin tirador: requiere mecanismo compatible</text><text x=\"655\" y"
    "=\"736\" class=\"small\">El mecanismo empuja el frente al presionar.</text><rect x=\"58\" y=\"795\" width=\"1127\" he"
    "ight=\"573\" rx=\"13\" class=\"card\"/><text x=\"80\" y=\"831\" class=\"card-title\" style=\"font-size:23px\">5. Gola de "
    "madera: T invertida · ¿por dónde entran los dedos?</text><text x=\"80\" y=\"858\" class=\"small\" style=\"font-siz"
    "e:16px\">La T es FIJA. Se abre tomando el canto del FRENTE MÓVIL, nunca tirando de la T.</text><rect x=\"83\" "
    "y=\"883\" width=\"500\" height=\"327\" rx=\"11\" fill=\"#fff\" stroke=\"#d1dce7\" stroke-width=\"2\"/><rect x=\"83\" y=\"883"
    "\" width=\"500\" height=\"57\" rx=\"11\" fill=\"#fff1f0\"/><text x=\"105\" y=\"918\" style=\"font-size:20px;font-weight:b"
    "old;fill:#983f3e\">A · ENTRADA BLOQUEADA</text><rect x=\"125\" y=\"973\" width=\"370\" height=\"26\" class=\"wood\" da"
    "ta-part=\"blocked-fixed-top-board\"/><rect x=\"269\" y=\"999\" width=\"28\" height=\"107\" class=\"wood\"/><rect x=\"226"
    "\" y=\"1090\" width=\"115\" height=\"17\" class=\"wood\"/><rect x=\"450\" y=\"999\" width=\"43\" height=\"152\" rx=\"3\" fill="
    "\"#a8bfcd\" stroke=\"#324b62\" stroke-width=\"2\" data-part=\"blocked-drawer-front\"/><circle cx=\"530\" cy=\"1063\" r="
    "\"19\" fill=\"#bc4946\"/><path d=\"M520 1053 L540 1073 M540 1053 L520 1073\" fill=\"none\" stroke=\"#fff\" stroke-wid"
    "th=\"5\" stroke-linecap=\"round\"/><text x=\"106\" y=\"1175\" style=\"font-size:16px;fill:#933e3b\">SIN HUECO: la tap"
    "a tapa el acceso.</text><text x=\"106\" y=\"1197\" class=\"small\">Aunque la T esté invertida, no sirve así.</tex"
    "t><rect x=\"598\" y=\"883\" width=\"560\" height=\"327\" rx=\"11\" fill=\"#fff\" stroke=\"#c1ddda\" stroke-width=\"2\"/><re"
    "ct x=\"598\" y=\"883\" width=\"560\" height=\"57\" rx=\"11\" fill=\"#e7f5f1\"/><text x=\"618\" y=\"918\" style=\"font-size:2"
    "0px;font-weight:bold;fill:#20665c\">B · ACCESO POSIBLE (CONCEPTO)</text><text x=\"620\" y=\"959\" class=\"mini\">I"
    "NTERIOR DEL MUEBLE</text><text x=\"1086\" y=\"959\" class=\"mini\">AFUERA →</text><rect x=\"633\" y=\"981\" width=\"43"
    "9\" height=\"28\" class=\"wood\" data-part=\"accessible-fixed-top-board\"/><rect x=\"809\" y=\"1009\" width=\"29\" heigh"
    "t=\"98\" class=\"wood\" data-concept=\"inverted-t-stem\"/><rect x=\"755\" y=\"1092\" width=\"136\" height=\"16\" class=\"w"
    "ood\" data-concept=\"inverted-t-lower-flange\"/><rect x=\"1004\" y=\"1044\" width=\"43\" height=\"121\" rx=\"3\" fill=\"#"
    "a8bfcd\" stroke=\"#324b62\" stroke-width=\"2\" data-part=\"moving-drawer-front\"/><rect x=\"1004\" y=\"1009\" width=\"6"
    "8\" height=\"35\" fill=\"#e8f8fb\" fill-opacity=\".48\" stroke=\"#378ea5\" stroke-width=\"1.5\" stroke-dasharray=\"4 3\""
    " data-concept=\"access-height-h-unverified\"/><path d=\"M1133 1022 H1095 Q1056 1022 1033 1034 L1006 1045\" stro"
    "ke=\"#147991\" stroke-width=\"5\" stroke-linecap=\"round\" fill=\"none\" data-action=\"insert-fingers\"/><path d=\"M10"
    "12 1035 L1006 1045 L1019 1041\" fill=\"none\" stroke=\"#147991\" stroke-width=\"4\" stroke-linejoin=\"round\"/><circ"
    "le cx=\"1007\" cy=\"1045\" r=\"5\" fill=\"#147991\" stroke=\"#fff\" stroke-width=\"1.5\" data-action=\"grip-drawer-front"
    "\"/><path d=\"M1057 1110 H1136 L1125 1101 M1136 1110 L1125 1119\" class=\"arrow\" data-action=\"pull-front\"/><pat"
    "h d=\"M1084 1009 V1044 M1077 1009 H1091 M1077 1044 H1091\" stroke=\"#b36f2a\" stroke-width=\"2\" fill=\"none\" data"
    "-concept=\"H-vertical-clearance\"/><text x=\"1097\" y=\"1060\" class=\"mini\" style=\"fill:#9f6124\">H</text><path d="
    "\"M1047 968 H1072 M1047 962 V974 M1072 962 V974\" stroke=\"#b36f2a\" stroke-width=\"2\" fill=\"none\" data-concept="
    "\"V-top-overhang\"/><text x=\"1055\" y=\"957\" class=\"mini\" style=\"fill:#9f6124\">V</text><text x=\"620\" y=\"1181\" s"
    "tyle=\"font-size:16px;fill:#155f71\">1. ENTRAR por la ranura libre.</text><text x=\"620\" y=\"1202\" style=\"font-"
    "size:16px;fill:#155f71\">2. AGARRAR el borde gris.  3. TIRAR →</text><path d=\"M84 1230 H1156\" stroke=\"#cbd9d"
    "f\" stroke-width=\"2\"/><text x=\"86\" y=\"1260\" class=\"mini\" style=\"font-size:18px\">H = ranura vertical libre · "
    "V = vuelo horizontal de la tapa</text><text x=\"86\" y=\"1291\" class=\"small\" style=\"font-size:16px\">H ≈ 20 mm "
    "es propuesta del usuario; NO es mínimo recomendado ni aprobado por el libro.</text><text x=\"86\" y=\"1320\" cl"
    "ass=\"small\" style=\"font-size:16px\">Fuente: libro PDF 124–125 (impresas 102–103). T de madera: 6,5 cm alto /"
    " base 5 cm (figura).</text><text x=\"86\" y=\"1350\" class=\"warning\">Montaje en cajones, holguras ergonómicas y"
    " función como tope: SIN VALIDAR.</text><text x=\"78\" y=\"1415\" class=\"subtitle\">COMPARA: manija sobresale · u"
    "ñero y perfil requieren agarre · presión usa mecanismo.</text><text x=\"78\" y=\"1445\" class=\"warning\">SOLO EX"
    "PLICACIÓN VISUAL. No define espesores, perfiles, fresados, fijaciones ni compatibilidad.</text><text x=\"78\""
    " y=\"1481\" class=\"warning\">NO CORTAR · NO TALADRAR · NO COMPRAR · NO FABRICAR.</text></svg>"
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
        old = '<rect x="58" y="795" width="1127" height="573" rx="13" class="card"/>'
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
        "Gola de madera: la T invertida queda FIJA. Si la tapa superior bloquea "
        "la entrada no puede abrirse así. Solo con una ranura accesible se "
        "alcanza el canto del frente móvil y se tira de él. H es la altura "
        "libre y V el vuelo de la tapa. 20 mm es una propuesta del usuario, "
        "NO un mínimo documentado. Tope y montaje aún no validados.",
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
            "Las cuatro aperturas habituales se conservan. La quinta compara "
            "un acceso bloqueado por la tapa con una ranura donde sí se puede "
            "tomar el canto del frente móvil. La T permanece fija y no prueba "
            "su uso como tope o su montaje real en cajones."
        ),
        "blockers": [
            "El libro describe una T invertida de madera para puertas; "
            "usarla en cajones o como tope requiere validación independiente.",
            "Verificar H (luz vertical), V (vuelo), acceso real, "
            "correderas, fijaciones e interferencias antes de fabricar.",
            "Los 20 mm sugeridos no son mínimo documentado en el libro."
        ],
        "piece_count": 0,
        "can_generate_f7c": False,
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
    }
