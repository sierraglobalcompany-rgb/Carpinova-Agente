"""Conservative construction advisor for carpentry decisions.

Not an engineered manufacturing system. Evidence-backed practical
decision prompts; no universal adhesive temperature, fastener spacing,
wall anchoring capacity or inferred bores.
"""
from __future__ import annotations
from typing import Any

APPLICATIONS={"kitchen","bathroom","closet","shelving","general"}
EDGE_VARIANTS={"flexible","rigid","unknown"}
EDGE_WORKFLOW={"cut_shop","home","unknown"}
EDGE_ADHESIVE={"pre_glued","eva_hot_melt","pur_hot_melt","unknown"}
EDGE_EXPOSURE={"visible","concealed","wet_exposed","unknown"}
BACKS={"full","partial_service","no_back","unknown"}
SUPPORTS={"floor_legs","plinth_base","floor_direct","wall_french_cleat","wall_rail","unknown"}
JOINTS={"visible_screws","concealed_angles","cam_dowels","unknown"}
MATERIALS={"abs","pvc","melamine","wood_veneer","unknown"}
SUBSTRATES={"masonry","concrete","drywall","wood_studs","unknown"}
ALLOWED={"application","edge_variant","edge_workflow","edge_adhesive","edge_material",
         "edge_exposure","back_style","has_services","support","wall_substrate",
         "joint","water_exposure"}
SOURCES={
    "edge_egger": "https://www.egger.com/en/furniture-interior-design/range/products/pvcedging?country=US",
    "edge_rehau": "https://interior.rehau.com/en-en/products/raukantex-furniture-edgebands/standard-stock-range/hot-melt-adhesives",
    "edge_rehau_docs": "https://interior.rehau.com/en-en/products/raukantex-furniture-edgebands/tools-services",
    "wall_blum": "https://publications.blum.com/2026/catalogue/en/612/",
}
QUESTIONS={
    "application":"¿Es cocina, baño, clóset, estantería u otro mueble?",
    "edge_exposure":"¿Ese borde queda visible, oculto, expuesto a humedad o aún no se sabe?",
    "edge_workflow":"¿Colocará el canto el taller de corte o lo pegarás tú?",
    "edge_variant":"¿El canto es flexible o rígido según la ficha del proveedor?",
    "edge_material":"¿El canto es ABS, PVC, melamínico, chapa de madera o desconocido?",
    "edge_adhesive":"¿El canto viene preencolado o qué adhesivo/sistema especifica el proveedor?",
    "back_style":"¿Lleva fondo completo, fondo parcial con registro de tuberías o va sin fondo?",
    "has_services":"¿Pasan tuberías, desagües, gas, cables u otras instalaciones por el fondo?",
    "support":"¿Se apoya sobre patas, zócalo/banquero, piso o suspensión a pared?",
    "wall_substrate":"¿De qué material es la pared (ladrillo, concreto, drywall, montantes de madera)?",
    "joint":"¿Buscas tornillos visibles, escuadras ocultas o conectores desmontables?",
    "water_exposure":"¿Habrá salpicaduras o humedad frecuente?",
}

class AdviceError(ValueError):
    """Malformed or unsupported construction decisions."""


def _enum(data: dict[str,Any], key: str, choices: set[str]) -> str:
    value=data.get(key,"unknown")
    if not isinstance(value,str) or value not in choices:
        raise AdviceError(f"{key}: opción no admitida.")
    return value


def construction_advice(request: dict[str, Any], max_questions: int=3)->dict[str,Any]:
    """Return conditional recommendations and questions; never a drill-ready BOM."""
    if not isinstance(request,dict):
        raise AdviceError("La consulta debe ser un objeto JSON.")
    extra=request.keys()-ALLOWED
    if extra:
        raise AdviceError("Campos no reconocidos: "+", ".join(sorted(extra)))
    if type(max_questions) is not int or not 1<=max_questions<=6:
        raise AdviceError("max_questions: entero de 1 a 6.")
    app=_enum(request,"application",APPLICATIONS|{"unknown"})
    variant=_enum(request,"edge_variant",EDGE_VARIANTS)
    workflow=_enum(request,"edge_workflow",EDGE_WORKFLOW)
    adhesive=_enum(request,"edge_adhesive",EDGE_ADHESIVE)
    material=_enum(request,"edge_material",MATERIALS)
    exposure=_enum(request,"edge_exposure",EDGE_EXPOSURE)
    back=_enum(request,"back_style",BACKS)
    support=_enum(request,"support",SUPPORTS)
    substrate=_enum(request,"wall_substrate",SUBSTRATES)
    joint=_enum(request,"joint",JOINTS)
    for key in ("has_services","water_exposure"):
        if key in request and type(request[key]) is not bool:
            raise AdviceError(f"{key}: se requiere verdadero o falso.")
    needs=[]; recommendations=[]; blockers=[]; evidence=[]
    def ask(field:str):
        if field not in needs:needs.append(field)
    if app=="unknown":ask("application")
    if exposure=="unknown":ask("edge_exposure")
    if workflow=="unknown":ask("edge_workflow")
    if variant=="unknown":ask("edge_variant")
    if material=="unknown":ask("edge_material")
    if app in {"kitchen","bathroom"} and "water_exposure" not in request:ask("water_exposure")

    # A marketed "rigid" or "flexible" label is not a material specification.
    recommendations.append(
        "Canto: decidir por borde físico de cada panel qué lado queda visible o expuesto. "
        "El borde oculto no exige automáticamente canto decorativo, pero puede "
        "necesitar sellado por humedad/higiene y acabado de calidad."
    )
    recommendations.append(
        "Flexible o rígido NO equivalen universalmente a ABS o PVC. "
        "Pedir al proveedor material, espesor, radio mínimo, adhesivo y método de instalación."
    )
    evidence.extend(["edge_egger","edge_rehau_docs"])
    if exposure=="wet_exposed" or request.get("water_exposure") is True:
        recommendations.append(
            "Priorizar protección de cantos y juntas expuestas al agua; "
            "verificar tablero, adhesivo, continuidad del sello y mantenimiento."
        )
        blockers.append("No considerar impermeable una unión solo por tener canto decorativo.")
    if workflow=="cut_shop":
        recommendations.append(
            "Taller: pedir en la orden de corte lados exactos, espesor/material del canto, "
            "adhesivo y acabado de esquinas; solicitar una muestra y comprobar adherencia."
        )
    elif workflow=="home":
        if adhesive=="unknown":ask("edge_adhesive")
        if adhesive=="pre_glued":
            recommendations.append(
                "En casa, con canto preencolado compatible: ensayar sobre un retal, "
                "limpiar y escuadrar, activar según ficha del fabricante con herramienta "
                "apropiada, presionar uniformemente, enfriar, perfilar sobrante sin "
                "arrancar el canto y revisar adhesión. Proteger manos, ojos y ventilación."
            )
        elif adhesive in {"eva_hot_melt","pur_hot_melt"}:
            recommendations.append(
                "Adhesivo termofusible EVA/PUR requiere equipo y control según ficha "
                "de canto+adhesivo. Para colocación casera sin equipo adecuado, "
                "preferir servicio de taller o una solución preencolada compatible."
            )
            evidence.append("edge_rehau")
        else:
            blockers.append(
                "No explicar una temperatura o pegante universal; confirmar adhesivo "
                "real, equipo y compatibilidad."
            )
    if workflow=="home" and variant=="rigid":
        blockers.append(
            "Verificar radio, flexibilidad real y sistema de aplicación de este SKU; "
            "no asumir que un canto rígido se puede planchar manualmente."
        )

    if back=="unknown":ask("back_style")
    if "has_services" not in request:ask("has_services")
    if back=="full" and request.get("has_services") is True:
        blockers.append(
            "Fondo completo interfiere con servicios declarados. "
            "Definir registros y recortes con cotas reales, mantenimiento y accesibilidad."
        )
    elif back=="partial_service":
        recommendations.append(
            "Fondo parcial o registrable: ubicar instalaciones reales y dejar acceso "
            "a conexiones, válvulas, enchufes y reparaciones; proteger bordes cortados."
        )
    elif back=="no_back":
        recommendations.append(
            "Sin fondo puede facilitar tuberías y montaje, pero no asumir rigidez "
            "ni escuadra: definir arriostramiento, fijaciones o solución estructural."
        )
    elif back=="full":
        recommendations.append(
            "Fondo completo: definir espesor, ranura o aplicación, montaje y si aporta "
            "rigidez; comprobar interferencias antes de dimensionarlo."
        )

    if support=="unknown":ask("support")
    if support=="floor_legs":
        recommendations.append(
            "Patas: comprobar nivelación, carga, limpieza, humedad, zócalo de cierre "
            "y fijación pata–mueble. No determinar cantidad o posiciones sin capacidad nominal."
        )
    elif support=="plinth_base":
        recommendations.append(
            "Base/zócalo (verificar si a esto llamas 'banquero'): "
            "definir altura, material resistente a humedad, continuidad del apoyo, "
            "nivelación, retranqueo y acceso a servicios."
        )
    elif support=="floor_direct":
        recommendations.append(
            "Apoyo directo a piso: analizar humedad, nivelación, encuentro con "
            "pisos y acceso a limpieza antes de escogerlo."
        )
    elif support in {"wall_french_cleat","wall_rail"}:
        if substrate=="unknown":ask("wall_substrate")
        recommendations.append(
            "Suspensión: comparar listón francés continuo con riel y colgadores "
            "regulables según ajuste, desmontaje, soporte y estética. "
            "Seleccionar anclajes por sustrato y carga real, nunca por la forma del soporte."
        )
        evidence.append("wall_blum")
        blockers.append(
            "Mueble suspendido NO liberado: faltan masa del mueble, carga de uso, "
            "capacidad del herraje, pared y comprobación profesional de anclajes."
        )
    if joint=="unknown":ask("joint")
    if joint=="visible_screws":
        recommendations.append(
            "Tornillos visibles: confirmar espesor de panel, orientación del ensamble, "
            "atornillado a canto y tapa estética; perforación piloto depende de material/tornillo."
        )
    elif joint=="concealed_angles":
        recommendations.append(
            "Escuadras internas ocultas pueden evitar cabezas visibles, pero su "
            "resistencia, número y tornillos dependen del uso. No sustituir "
            "automáticamente una unión estructural con escuadras decorativas."
        )
    elif joint=="cam_dowels":
        recommendations.append(
            "Conectores desmontables: elegir sistema, plantilla y taladros exactos "
            "según fabricante. No usar diámetros ni distancias universales."
        )
    blockers.append(
        "No hay validación final de carga, anclajes, tornillos, taladros, sellado "
        "ni ajustes de corte: se requiere ficha y revisión de taller."
    )
    return {
        "schema_version":"0.1.0","status":"ADVISORY_ONLY",
        "fabrication_ready":False,"cutting_ready":False,"drilling_ready":False,
        "purchase_ready":False,"recommendations":recommendations,
        "questions":[{"field":k,"question":QUESTIONS[k]} for k in needs[:max_questions]],
        "all_missing_fields":needs,"blockers":blockers,
        "evidence_refs":list(dict.fromkeys(evidence)),
        "sources":{k:SOURCES[k] for k in dict.fromkeys(evidence)},
        "notes":["Las opciones son decisiones, no una lista de piezas calculadas.",
                 "Las afirmaciones del libro requieren cita de página del Knowledge canónico.",
                 "El término 'banquero' debe aclararse con el usuario antes de mapearlo a zócalo."],
    }
