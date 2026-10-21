# F3 — Entrevista de requisitos y boceto ortográfico (MVP)

## Alcance presente
- `guide_project()` admite **JSON estructurado** y responde qué datos faltan o produce geometría preliminar delegada a `carpinova_agent.core.design()` (el mismo motor F1).
- Cuestionario de máximo tres preguntas por paso (configurable de 1 a 6). Acepta nombres comunes en español, incluidos cajón/clóset.
- Gabinetes y cajas de cajón con datos completos se calculan en estado permanente `DRAFT_NOT_FOR_CUTTING`. No se añaden medidas ocultas.
- Clósets, cocinas, nichos, bibliotecas, escritorios y baños pasan a `CONCEPT_ONLY`; requieren subdividir en módulos y NO generan piezas fabricables de modo automático.
- `render_svg()` produce un **croquis frontal ortográfico proporcional** con cotas nominales, para gabinete abierto/caja de cajón; no dibuja bisagras, tornillos ni patrones de mecanizado. El SVG se deriva exclusivamente de la salida de F1, sin segunda geometría.
- La conversación en lenguaje natural, el render 3D y la búsqueda del libro aún requieren integración posterior; **no son funcionalidades de este MVP**.

## Ejecución
\nLa entrevista por terminal funciona con preguntas y respuestas manuales; no necesita escribir JSON:\n\n\x60\x60\x60bash\npython -m carpinova_agent.dialogue\n\x60\x60\x60\n\n```bash
python -m unittest discover -s tests -v
python -m carpinova_agent.guide_cli --input examples/intake-cabinet-partial.json
python -m carpinova_agent.guide_cli --input examples/intake-cabinet-draft.json --output /tmp/proyecto.json --sketch /tmp/croquis.svg
python -m carpinova_agent.guide_cli --input examples/intake-drawer-partial.json
python -m carpinova_agent.guide_cli --input examples/intake-closet.json
```

## Preguntas comunes
- Gabinete: ancho/alto/profundidad, espesor, estructura (costados completos o tapas/base completas).
- Cajón: luz disponible, alto exterior deseado, espesores, holguras izquierda/derecha de corredera, retiros delantero/trasero.
- Mueble multicomponente: medidas generales, división en módulos, obstáculos, anclajes y servicios (requieren diseño posterior).
- Tras geometría: ubicación, tipo de frente, fondo, veta, herrajes exactos, cantos y control de sitio.

## Verificación del lugar\n- Si la instalación es `built_in`, se solicitan tres anchos reales de hueco (arriba, medio, abajo).\n- Si el ancho nominal del mueble iguala o supera la menor luz medida, la respuesta indica `SITE_CONFLICT` y bloquea la recomendación de fabricar; no inventa una holgura para hacerlo encajar.\n- Si la persona aporta cotas antes de indicar tipo de mueble, quedan preservadas para la siguiente pregunta.\n\n## Advertencias obligatorias
- Un *frente aplicado* o *embutido* indica intención; el motor **no** añade una puerta ni calcula luces/bisagras por esa elección.
- Introducir holguras de corredera NO demuestra que cumplan su ficha técnica; no existe perforación automática.
- Un dibujo SVG es solo la proyección 2D de un cuerpo geométrico simple. No equivale a plano aprobado para cortar.
- Ninguna cota deriva de figuras normalizadas del libro.
- No se interpreta una foto como medida ni se hace dimensionado a partir de una imagen.
- Los tres registros de ancho del espacio (arriba, medio y abajo) no fijan por sí solos el tamaño del mueble.

## Dependencias de integración
PR F3 depende de la rama F1, a la que apunta. F2 es independiente: búsquedas con referencias del libro se integrarán cuando se aprueben ambos contratos y se valide con los bundles reales completos. Sin fusionar PRs de manera automática.

## Próximo incremento
Convertir preguntas/respuestas en un flujo conversacional real con registro de decisiones, reconocimiento controlado de medidas y un ProjectSpec unificado; consumo de fuentes F2; módulos agregados; estudio de fichas de fabricantes. Mantener los bloqueos de fabricación hasta que haya geometría/ferretería verificadas.
