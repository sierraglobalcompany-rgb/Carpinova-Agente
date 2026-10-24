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



# G30 · Additional deterministic orientation sketch; DOES NOT replace G23 golden SVG.
# Source context: Knowledge p0124/p0125; mount and drawer use NOT certified.
_T_BETWEEN_SIDES_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="745" viewBox="0 0 1180 745" role="img" aria-label="G30. Frente de una T invertida entre los dos laterales LI y LD y sección perpendicular con el ala horizontal abajo, sin unión fabricable">
<title>G30 · T invertida interior entre los dos laterales · dos vistas</title>
<desc>Frente: pieza transversal horizontal entre las caras interiores de LI y LD, sin soportes externos. Sección perpendicular: montante vertical arriba y ala horizontal inferior, con forma de T invertida. Frente móvil separado. No hay fijaciones ni holguras aprobadas.</desc>
<style>
text{font-family:Arial,sans-serif;fill:#25374b}.head{font-size:29px;font-weight:700}.sub{font-size:17px;fill:#52677c}.panel{fill:#f8fafc;stroke:#b8cad8;stroke-width:2}.label{font-size:21px;font-weight:700}.note{font-size:16px}.part{fill:#d5ad84;stroke:#8c6748;stroke-width:2}.side{fill:#b4c9d6;stroke:#5b7890;stroke-width:2}.rail{fill:#d5ad84;stroke:#8c6748;stroke-width:2}.front{fill:#9fbdca;stroke:#38576f;stroke-width:2}.warn{font-size:17px;font-weight:700;fill:#9b421f}.dash{stroke:#a47742;stroke-width:2;stroke-dasharray:6 5;fill:none}
</style>
<rect x="0" y="0" width="1180" height="745" fill="#fff"/>
<text x="40" y="53" class="head">G30 · T INVERTIDA INTERIOR — REFERENCIA GEOMÉTRICA</text>
<text x="40" y="84" class="sub">Referencia geométrica genérica: ancho W, tablero t; dimensiones reales a cargo de F1</text>
<rect x="36" y="114" width="550" height="432" rx="14" class="panel"/>
<text x="56" y="155" class="label">1. FRENTE: ENTRE LI Y LD</text>
<text x="56" y="183" class="note">La pieza transversal está DENTRO de los laterales.</text>
<rect x="80" y="225" width="35" height="205" class="side" data-part="LI"/>
<rect x="545" y="225" width="35" height="205" class="side" data-part="LD"/>
<rect x="115" y="301" width="430" height="30" class="rail" data-part="rail-spanning-between-sides" data-join="unverified"/>
<rect x="115" y="331" width="430" height="18" fill="#bd9267" stroke="#8c6748" stroke-width="2" data-part="lower-flange-front-projection"/>
<path d="M115 291 V354 M545 291 V354" class="dash" data-concept="unvalidated-side-joins"/>
<text x="97" y="453" text-anchor="middle" class="label">LI</text><text x="563" y="453" text-anchor="middle" class="label">LD</text>
<path d="M115 476 V486 M545 476 V486 M115 482 H545" stroke="#4b6479" stroke-width="2" fill="none"/>
<text x="330" y="509" text-anchor="middle" class="note">Luz conceptual entre laterales = W − 2·t (F1 calcula)</text>
<text x="56" y="529" class="note">Extremos y uniones: SIN DEFINIR · ninguna escuadra exterior</text>
<rect x="602" y="114" width="543" height="432" rx="14" class="panel"/>
<text x="622" y="155" class="label">2. CORTE PERPENDICULAR: SECCIÓN ┴</text>
<text x="622" y="183" class="note">Montante vertical ARRIBA · ala horizontal ABAJO.</text>
<rect x="819" y="218" width="24" height="122" class="part" data-part="inverted-t-vertical-stem"/>
<rect x="769" y="340" width="124" height="24" class="part" data-part="inverted-t-bottom-flange"/>
<path d="M843 246 H944" stroke="#536a7b" stroke-width="2"/>
<text x="947" y="240" class="note">Montante fijo</text>
<path d="M769 354 L725 383 H715" stroke="#536a7b" stroke-width="2"/>
<text x="622" y="397" class="note">Ala inferior</text>
<rect x="997" y="278" width="29" height="159" class="front" data-part="moving-drawer-front"/>
<path d="M1106 301 H1045 L1027 300" fill="none" stroke="#157d98" stroke-width="4" data-action="finger-access-to-moving-front"/>
<path d="M1043 292 L1027 300 L1043 309" fill="none" stroke="#157d98" stroke-width="4"/>
<text x="1065" y="457" text-anchor="middle" class="note">Frente móvil</text>
<path d="M769 404 H893" class="dash"/>
<text x="646" y="485" class="note">Acceso, altura H y vuelo V: SIN VALIDAR</text>
<text x="646" y="513" class="note">El dibujo NO muestra tornillos ni unión a los laterales.</text>
<rect x="36" y="565" width="1109" height="140" rx="12" fill="#fff7ef" stroke="#e5b38f" stroke-width="2"/>
<text x="58" y="599" class="warn">CONCEPTO, NO CONSTRUCCIÓN APROBADA</text>
<text x="58" y="632" class="note">Libro PDF 124–125: T de madera para PUERTAS; 6,5 cm alto y 5 cm base solo en su figura.</text>
<text x="58" y="661" class="note">No se ha validado cómo sujetarla entre LI/LD ni su repetición en cajones A/B/C/D.</text>
<text x="58" y="689" class="warn">0 piezas · NO CORTAR · NO TALADRAR · NO COMPRAR · NO FABRICAR</text>
</svg>"""


_G39_SHARED_GRIP_AB_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="1480" height="950" viewBox="0 0 1480 950" role="img" aria-label="G39 educativo: agarres A inferior y B superior no verificados; T invertida fija en muestra separada, sin posición ni unión aprobadas" data-review="G39" data-verified="false" data-join="unverified" data-fabrication-ready="false" data-piece-count="0">
<title>G39 · Revisión educativa del agarre compartido A–B</title>
<desc>C01 nominal: 500 por 800 mm, tablero de 15 mm, aberturas A/B/C/D de 137/137/137/275 mm y tres franjas ilustrativas de 28 mm. Dos trayectorias hipotéticas apuntan al borde inferior de A y al borde superior de B; ambas están sin verificar. G_AB es separación frontal proyectada, no espacio libre validado. La T se mantiene fija entre LI y LD según G30; aquí se muestra aislada, sección invertida, sin ubicación ni fijación. Cero piezas y sin autorización de fabricación.</desc>
<style>
text{font-family:Arial,sans-serif;fill:#243b53}.title{font-size:25px;font-weight:700}.subtitle{font-size:15px;fill:#52677c}.panel{fill:#f8fafc;stroke:#b8cad8;stroke-width:2}.head{font-size:19px;font-weight:700}.note{font-size:14px;fill:#4c6174}.small{font-size:12px;fill:#52677c}.front{fill:#d9e8ef;stroke:#496c83;stroke-width:2}.board{fill:#d7b28f;stroke:#89684c;stroke-width:2}.gap{fill:#fff0d8;stroke:#bd8741;stroke-width:1.5;stroke-dasharray:5 4}.route{fill:none;stroke:#14768b;stroke-width:4;stroke-dasharray:9 5}.edge{stroke:#a34d2e;stroke-width:3}.warn{fill:#963e23;font-size:14px;font-weight:700}.route-label{fill:#126d82;font-size:13px;font-weight:700}
</style>
<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto"><path d="M0 0 L9 4.5 L0 9 Z" fill="#14768b"/></marker></defs>
<rect width="1480" height="950" fill="#ffffff"/>
<text x="36" y="42" class="title">G39 · ESTUDIO EDUCATIVO DE AGARRE COMPARTIDO A–B</text>
<text x="36" y="70" class="subtitle">C01 nominal · hipótesis visuales sin validar · esta lámina no es un plano de fabricación</text>
<rect x="30" y="100" width="420" height="720" rx="14" class="panel"/>
<rect x="465" y="100" width="575" height="720" rx="14" class="panel"/>
<rect x="1055" y="100" width="395" height="720" rx="14" class="panel"/>
<text x="50" y="139" class="head">1. C01 · ALZADO NOMINAL</text>
<text x="50" y="165" class="note">500 mm ancho × 800 mm alto · tablero 15 mm</text>
<text x="50" y="186" class="small">Escala vertical nominal; franjas ilustrativas, no piezas</text>
<rect x="82" y="196" width="316" height="512" fill="#ffffff" stroke="#536b7d" stroke-width="2" data-kind="nominal-outline" data-physical-part="false"/>
<rect x="82" y="196" width="316" height="9.6" class="board" data-kind="nominal-board" data-nominal-mm="15" data-physical-part="false"/>
<rect x="95" y="205.6" width="290" height="87.68" class="front" data-part="A" data-nominal-mm="137" data-verified="false"/>
<text x="240" y="255" text-anchor="middle" font-size="16" font-weight="700">A · 137 mm</text>
<rect x="95" y="293.28" width="290" height="17.92" class="gap" data-kind="illustrative-band" data-nominal-mm="28" data-physical-part="false"/>
<rect x="95" y="311.2" width="290" height="87.68" class="front" data-part="B" data-nominal-mm="137" data-verified="false"/>
<text x="240" y="361" text-anchor="middle" font-size="16" font-weight="700">B · 137 mm</text>
<rect x="95" y="398.88" width="290" height="17.92" class="gap" data-kind="illustrative-band" data-nominal-mm="28" data-physical-part="false"/>
<rect x="95" y="416.8" width="290" height="87.68" class="front" data-part="C" data-nominal-mm="137" data-verified="false"/>
<text x="240" y="466" text-anchor="middle" font-size="16" font-weight="700">C · 137 mm</text>
<rect x="95" y="504.48" width="290" height="17.92" class="gap" data-kind="illustrative-band" data-nominal-mm="28" data-physical-part="false"/>
<rect x="95" y="522.4" width="290" height="176" class="front" data-part="D" data-nominal-mm="275" data-verified="false"/>
<text x="240" y="615" text-anchor="middle" font-size="16" font-weight="700">D · 275 mm</text>
<rect x="82" y="698.4" width="316" height="9.6" class="board" data-kind="nominal-board" data-nominal-mm="15" data-physical-part="false"/>
<text x="50" y="744" class="note">3 franjas ilustrativas de 28 mm</text>
<text x="50" y="769" class="warn">No son divisores ni acceso para dedos</text>
<text x="50" y="793" class="small">3 × 137 + 275 + 3 × 28 + 2 × 15 = 800 mm</text>
<text x="485" y="139" class="head">2. A–B · DOS VÍAS HIPOTÉTICAS</text>
<text x="485" y="165" class="note">Esquema conceptual, sin escala; A y B son frentes móviles</text>
<rect x="650" y="218" width="250" height="158" rx="4" class="front" data-part="A" data-role="moving-front" data-verified="false"/>
<text x="775" y="281" text-anchor="middle" font-size="20" font-weight="700">FACHADA A · MÓVIL</text>
<text x="775" y="316" text-anchor="middle" class="note">borde inferior de A</text>
<line id="edge-A-lower" x1="650" y1="376" x2="900" y2="376" class="edge" data-part="A" data-edge="lower" data-verified="false"/>
<rect x="630" y="396" width="290" height="92" rx="8" class="gap" data-kind="conceptual-overlap-band" data-verified="false" data-physical-part="false"/>
<text x="775" y="421" text-anchor="middle" font-size="14" font-weight="700">BANDA NOMINAL 28 mm</text>
<text x="775" y="444" text-anchor="middle" class="small">no es luz libre ni holgura aprobada</text>
<text x="775" y="468" text-anchor="middle" class="small">G_AB = 28 − S_A,inferior − S_B,superior</text>
<line id="edge-B-upper" x1="650" y1="500" x2="900" y2="500" class="edge" data-part="B" data-edge="upper" data-verified="false"/>
<rect x="650" y="500" width="250" height="158" rx="4" class="front" data-part="B" data-role="moving-front" data-verified="false"/>
<text x="775" y="564" text-anchor="middle" font-size="20" font-weight="700">FACHADA B · MÓVIL</text>
<text x="775" y="600" text-anchor="middle" class="note">borde superior de B</text>
<path d="M505 381 C552 381 593 376 642 376" class="route" marker-end="url(#arrow)" data-route="A-lower" data-target="edge-A-lower" data-verified="false"/>
<path d="M505 496 C552 496 593 500 642 500" class="route" marker-end="url(#arrow)" data-route="B-upper" data-target="edge-B-upper" data-verified="false"/>
<text x="485" y="329" class="route-label">A · borde inferior</text>
<text x="485" y="351" class="small">A · ruta NO VERIFICADA</text>
<text x="485" y="548" class="route-label">B · borde superior</text>
<text x="485" y="570" class="small">B · ruta NO VERIFICADA</text>
<text x="485" y="704" class="warn">Separación frontal proyectada, no espacio útil</text>
<text x="485" y="730" class="note">Solapes sin definir; G_AB &gt; 0 no demuestra acceso</text>
<text x="485" y="759" class="small">No se dibujan manos; acceso, ergonomía y colisiones pendientes</text>
<text x="1076" y="139" class="head">3. T FIJA · SECCIÓN ┴</text>
<text x="1076" y="165" class="note">Muestra aislada; sin ubicación ni fijación</text>
<text x="1076" y="191" class="small">T permanece interna entre LI/LD según G30;</text>
<text x="1076" y="211" class="small">esta lámina no la instala en la franja A–B.</text>
<rect x="1225" y="258" width="32" height="148" class="board" data-part="T" data-role="t-stem" data-verified="false"/>
<rect x="1172" y="406" width="138" height="27" class="board" data-part="T" data-role="t-lower-flange" data-verified="false"/>
<text x="1241" y="477" text-anchor="middle" class="note">MONTANTE ↑</text>
<text x="1241" y="503" text-anchor="middle" class="note">ALA INFERIOR ↓</text>
<text x="1076" y="552" class="warn">Unión y anclaje: SIN VALIDAR</text>
<text x="1076" y="582" class="note">Sin tornillos, ranuras ni cotas H/V</text>
<text x="1076" y="620" class="small">Libro: figura para puertas, 65 × 50 mm;</text>
<text x="1076" y="641" class="small">no valida su uso en cajones ni esta franja.</text>
<text x="1076" y="687" class="small">La T no es una manija móvil.</text>
<rect x="30" y="835" width="1420" height="78" rx="10" fill="#fff5ed" stroke="#e2b18c" stroke-width="2"/>
<text x="365" y="866" class="warn">T FIJA · A Y B MÓVILES · DOS RUTAS CONCEPTUALES NO VERIFICADAS</text>
<text x="380" y="893" class="warn">NEEDS_USER_CONFIRMATION · 0 PIEZAS · NO CORTAR · NO TALADRAR · NO COMPRAR · NO FABRICAR</text>
</svg>
"""

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
                                   and focus not in ("all", "t_rail_concept",
                                                     "t_rail_ab_review")):
        raise DesignError("focus desconocido para la guía de aperturas.")
    if focus == "all":
        return _SVG_ALL
    if focus in ("t_rail_concept", "t_rail_ab_review"):
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
        **({"between_sides_concept_svg": _T_BETWEEN_SIDES_SVG}
           if focus in ("all", "t_rail_concept", "t_rail_ab_review") else {}),
        **({"shared_grip_ab_concept_svg": _G39_SHARED_GRIP_AB_SVG}
           if focus == "t_rail_ab_review" else {}),
        "sketch_text": "\n".join(lines + ([
            "G39 ilustrativo: A por el borde inferior y B por el borde superior;"
            " ambas trayectorias están NO VERIFICADAS.",
            "G_AB = 28 − S_A,inferior − S_B,superior es separación frontal proyectada;"
            " solapes indeterminados y G_AB > 0 no prueban acceso.",
            "La T permanece fija entre LI/LD según G30; ubicación y unión en A–B"
            " sin definir. La figura de 65 × 50 mm corresponde a puertas y no valida cajones.",
        ] if focus == "t_rail_ab_review" else [])),
        "human_summary": (
            "Las cuatro aperturas habituales se conservan. La quinta compara "
            "un acceso bloqueado por la tapa con una ranura donde sí se puede "
            "tomar el canto del frente móvil. La T permanece fija y no prueba "
            "su uso como tope o su montaje real en cajones."
            + (" G39 añade una revisión hipotética de los bordes de A y B; las rutas, "
               "solapes, acceso real y montaje de la T siguen sin validar."
               if focus == "t_rail_ab_review" else "")
        ),
        "blockers": [
            "El libro describe una T invertida de madera para puertas; "
            "usarla en cajones o como tope requiere validación independiente.",
            "Verificar H (luz vertical), V (vuelo), acceso real, "
            "correderas, fijaciones e interferencias antes de fabricar.",
            "Los 20 mm sugeridos no son mínimo documentado en el libro.",
            "G30 muestra T entre LI/LD en planta frontal y sección ┴, pero NO modela unión ni instala cajones."
        ] + ([
            "G39: el acceso por el borde inferior de A y el superior de B es hipotético; rutas, ergonomía e interferencias no verificadas.",
            "G_AB = 28 − S_A,inferior − S_B,superior es separación frontal proyectada; los solapes no están definidos y G_AB > 0 no prueba agarre.",
            "La ubicación física y unión de la T respecto a A–B no están definidas; la T se muestra aislada y no fabricable.",
            "La figura bibliográfica de T 65 × 50 mm describe puertas; no certifica repetición ni montaje en cajones."
        ] if focus == "t_rail_ab_review" else []),
        "piece_count": 0,
        "can_generate_f7c": False,
        "fabrication_ready": False,
        "cutting_ready": False,
        "drilling_ready": False,
        "purchase_ready": False,
    }
