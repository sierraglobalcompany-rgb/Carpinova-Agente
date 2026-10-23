"""Recovery of the PR #37 educational opening guide from exact visual evidence.

This is a *functional reconstruction*, not the original lost Git commit.
Source graphic = reviewed OPENING_all.svg from CI artifact for SHA fdecd59.
No new tool, CAD geometry, panel BOM, machining, or fabrication authority.
"""
from __future__ import annotations

from typing import Any
from .core import DesignError

# Exact reviewed 1240x1240 SVG from CI artifact. Kept inline so editable-install
# packages do not need resource files or packaging/configuration changes.
_SVG_ALL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="1240" viewBox="0 0 1240 1240" role="img" aria'
    '-label="Guía visual de manija, uñero, perfil, apertura por presión y travesaño interior tipo T pendiente d'
    'e definir"><title>Cómo abrir cajones y puertas sin confundir sistemas</title><desc>Comparación con el mism'
    'o cajón pequeño y la misma puerta: manija externa, uñero rebajado, canal tipo gola y apertura por presión.'
    ' Un corte conceptual indica frentes arriba y abajo, hueco de agarre, dedos entrando hacia el interior y fr'
    'ente tirado hacia el exterior; el travesaño en T se dibuja discontinuo porque su forma, material y anclaje'
    ' no han sido definidos. No es una pieza para fabricar.</desc><style>text{font-family:Arial,sans-serif;fill'
    ':#24354b}.title{font-size:27px;font-weight:700}.subtitle{font-size:16px;fill:#4b6178}.card-title{font-size'
    ':19px;font-weight:700}.gesture{font-size:13px;fill:#1e6880;font-weight:700}.note{font-size:13px}.small{fon'
    't-size:13px;fill:#46576a}.mini{font-size:13px;font-weight:700;fill:#53677d}.card{fill:#f8fafc;stroke:#becb'
    'd9;stroke-width:1.6}.selected{fill:#e8f6f8;stroke:#16718a;stroke-width:3}.wood{fill:#d4aa82;stroke:#8a674e'
    ';stroke-width:2}.concept-rail{fill:#e4e9ec;stroke:#506b76;stroke-width:2;stroke-dasharray:5 3}.grip-gap{fi'
    'll:#f0f8f9;stroke:#8cb7c1;stroke-width:1;stroke-dasharray:4 3}.metal{fill:#405769;stroke:#233648;stroke-wi'
    'dth:1}.groove{stroke:#24394c;stroke-width:8;fill:none;stroke-linecap:round}.recess{fill:#93b0bc;opacity:.8'
    '5}.metal-line{stroke:#344c60;stroke-width:4;fill:none}.press{fill:#e3f4f5;stroke:#1e788e;stroke-width:2}.a'
    'rrow{stroke:#19738b;stroke-width:4;fill:none;stroke-linejoin:round}.finger{stroke:#d89e76;stroke-width:13;'
    'fill:none;stroke-linecap:round}.warning{fill:#923b1e;font-size:14px;font-weight:700}</style><rect x="0" y='
    '"0" width="1240" height="1240" fill="#f6f8fb"/><rect x="28" y="22" width="1184" height="1200" rx="21" fill'
    '="white"/><text x="60" y="75" class="title">¿CÓMO SE ABRE UN CAJÓN O UNA PUERTA?</text><text x="60" y="107'
    '" class="subtitle">Mismo mueble pequeño · cuatro formas de uso · dibujo sin escala</text><rect x="58" y="1'
    '46" width="554" height="290" rx="13" class="card"/><text x="79" y="179" class="card-title">1. Manija exter'
    'na</text><text x="79" y="207" class="gesture">AGARRAR Y TIRAR</text><rect x="83" y="255" width="208" heigh'
    't="112" rx="7" class="wood"/><rect x="349" y="245" width="116" height="134" rx="6" class="wood"/><text x="'
    '99" y="244" class="mini">CAJÓN</text><text x="367" y="233" class="mini">PUERTA</text><rect x="155" y="307"'
    ' width="64" height="10" rx="5" class="metal"/><rect x="400" y="282" width="9" height="62" rx="4" class="me'
    'tal"/><text x="95" y="398" class="note">Manija visible: sale del frente</text><text x="80" y="416" class="'
    'small">Se fija por fuera y sobresale del frente.</text><rect x="633" y="146" width="554" height="290" rx="'
    '13" class="card"/><text x="654" y="179" class="card-title">2. Uñero</text><text x="654" y="207" class="ges'
    'ture">METER DEDOS Y TIRAR</text><rect x="658" y="255" width="208" height="112" rx="7" class="wood"/><rect '
    'x="924" y="245" width="116" height="134" rx="6" class="wood"/><text x="674" y="244" class="mini">CAJÓN</te'
    'xt><text x="942" y="233" class="mini">PUERTA</text><path d="M734 257 Q762 290 790 257" class="groove"/><pa'
    'th d="M926 298 Q953 310 926 322" class="groove"/><text x="670" y="398" class="note">Rebaje en canto/frente'
    ' (sin manija externa)</text><text x="655" y="416" class="small">El dedo entra en un rebaje del frente.</te'
    'xt><rect x="58" y="466" width="554" height="290" rx="13" class="card"/><text x="79" y="499" class="card-ti'
    'tle">3. Perfil / gola</text><text x="79" y="527" class="gesture">METER DEDOS Y TIRAR</text><rect x="83" y='
    '"575" width="208" height="112" rx="7" class="wood"/><rect x="349" y="565" width="116" height="134" rx="6" '
    'class="wood"/><text x="99" y="564" class="mini">CAJÓN</text><text x="367" y="553" class="mini">PUERTA</tex'
    't><rect x="88" y="580" width="198" height="13" class="recess"/><path d="M93 598 H281" class="metal-line"/>'
    '<rect x="357" y="570" width="12" height="119" class="recess"/><text x="95" y="718" class="note">Canal cont'
    'inuo: sección y montaje por definir</text><text x="80" y="736" class="small">Un canal integrado deja agarr'
    'ar el borde.</text><rect x="633" y="466" width="554" height="290" rx="13" class="card"/><text x="654" y="4'
    '99" class="card-title">4. Por presión</text><text x="654" y="527" class="gesture">PRESIONAR Y SOLTAR</text'
    '><rect x="658" y="575" width="208" height="112" rx="7" class="wood"/><rect x="924" y="565" width="116" hei'
    'ght="134" rx="6" class="wood"/><text x="674" y="564" class="mini">CAJÓN</text><text x="942" y="553" class='
    '"mini">PUERTA</text><circle cx="762" cy="630" r="22" class="press"/><text x="743" y="636" class="mini">PUS'
    'H</text><path d="M903 632 h-27 l9 -8 m-9 8 l9 8" class="arrow"/><circle cx="983" cy="632" r="14" class="pr'
    'ess"/><text x="670" y="718" class="note">Sin tirador: requiere mecanismo compatible</text><text x="655" y='
    '"736" class="small">El mecanismo empuja el frente al presionar.</text><rect x="58" y="795" width="1127" he'
    'ight="306" rx="13" class="card"/><text x="80" y="826" class="card-title">5. Travesaño interior tipo T: ide'
    'a por confirmar</text><text x="80" y="852" class="small">NO es la tapa T (superior) del mueble; tampoco eq'
    'uivale automáticamente a un perfil Gola.</text><text x="85" y="891" class="mini">VISTA FRONTAL · DOS FRENT'
    'ES</text><rect x="98" y="904" width="330" height="71" rx="5" class="wood"/><rect x="98" y="1003" width="33'
    '0" height="71" rx="5" class="wood"/><rect x="98" y="980" width="330" height="16" class="recess"/><rect x="'
    '98" y="986" width="330" height="5" class="metal"/><text x="451" y="966" class="small">Espacio para meter l'
    'os dedos</text><path d="M440 982 L575 982" class="arrow"/><text x="690" y="891" class="mini">CORTE CONCEPT'
    'UAL · SIN MEDIDAS</text><text x="697" y="906" class="mini">EXTERIOR</text><text x="999" y="906" class="min'
    'i">INTERIOR DEL MUEBLE</text><rect x="704" y="918" width="105" height="52" class="wood" data-part="upper-f'
    'ront"/><rect x="704" y="1005" width="105" height="59" class="wood" data-part="lower-front"/><rect x="810" '
    'y="974" width="222" height="26" class="grip-gap" data-concept="finger-clearance-not-dimensioned"/><rect x='
    '"835" y="963" width="243" height="14" class="concept-rail" data-concept="unvalidated-t-crosspiece"/><rect '
    'x="978" y="963" width="16" height="93" class="concept-rail" data-concept="unvalidated-t-crosspiece"/><text'
    ' x="870" y="950" class="mini">Pieza T: ubicación por confirmar</text><path d="M810 987 C835 986 854 998 87'
    '6 989" class="finger"/><circle cx="806" cy="987" r="8" fill="#d89e76"/><path d="M854 1016 H913 L901 1008 M'
    '913 1016 L901 1024" class="arrow" data-action="insert-fingers"/><text x="819" y="1043" class="mini">1. ENT'
    'RAR</text><path d="M707 1042 H662 L674 1034 M662 1042 L674 1050" class="arrow" data-action="pull-front"/><'
    'text x="650" y="1079" class="mini">2. TIRAR</text><text x="833" y="1083" class="small">No hay sección, mat'
    'erial, apoyo ni holgura aprobados.</text><text x="78" y="1149" class="subtitle">COMPARA: manija sobresale '
    '· uñero y perfil requieren agarre · presión usa mecanismo.</text><text x="78" y="1180" class="warning">SOL'
    'O EXPLICACIÓN VISUAL. No define espesores, perfiles, fresados, fijaciones ni compatibilidad.</text><text x'
    '="78" y="1207" class="warning">NO CORTAR · NO TALADRAR · NO COMPRAR · NO FABRICAR.</text></svg>'
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
        "Travesaño interior tipo T: idea por confirmar; introducir los dedos "
        "en el hueco y tirar del frente. No es la tapa T de F1 ni equivale "
        "automáticamente a un perfil Gola. Forma, material, anclaje y "
        "holgura todavía sin validar.",
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
              "name": "Travesaño interior tipo T",
              "description": "Concepto ilustrativo sin sección constructiva.",
              "selectable_for_drawer": False}],
        "sketch_svg": svg,
        "sketch_text": "\n".join(lines),
        "human_summary": (
            "El mismo cajón y una puerta muestran manija, uñero, "
            "perfil y apertura por presión. El travesaño T se explica "
            "como idea, no como herraje ni diseño autorizado."
        ),
        "blockers": [
            "El travesaño T puede ser una idea de madera, perfil gola "
            "u otra construcción: pedir sección y ejemplo antes de modelar.",
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
