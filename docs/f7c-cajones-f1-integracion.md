# F7C Task 3 — cajones integrados a la carcasa, SIN autorización de fabricación

El cálculo de cada caja se realiza **una única vez** en `carpinova_agent.core.design({"type":"drawer", ...})` (F1). `carpinova_agent.drawer_modules.module_drawers` ubica físicamente los cinco paneles derivados, sin repetir ni modificar sus dimensiones. El modelo único continúa hacia `modular_bom_csv`, `modular_front_svg` y `cad_exchange`; FreeCAD y Blender solo consumen ese contrato.

## Entrada por módulo

`module.drawers` es opcional y puede valer `"none"`, `"pending"` o una lista de 1 a 4 cajones. Cada entrada exige, sin defaults:

- `drawer_id` único dentro del módulo; `opening_bottom_offset_mm` y `opening_height_mm` de la abertura **medidos desde el hueco libre F1**.
- `opening_depth_mm`, `box_height_mm`, `panel_thickness_mm`, `bottom_thickness_mm`.
- `slide_clearance_left_mm`, `slide_clearance_right_mm`: luces suministradas expresamente, **NO recomendadas ni validadas para corredera concreta**.
- `front_setback_mm`, `rear_setback_mm` y `material_id`, `bottom_material_id`.
- `facade="pending"` o `facade` rectangular embutido explícito con `style="inset"`, material/espesor, luces izquierda/derecha/superior/inferior; veta/canto opcionales, no inferidos.

Por seguridad, este incremento no permite cajones dentro de un módulo que ya tenga puertas configuradas: primero hay que analizar apertura/colisiones. Tampoco ofrece todavía **frente de cajón sobrepuesto**: requeriría coordinación con múltiples frentes vecinos y acabado común. No añadir geometría incompleta de ese tipo.

## Modelo físico

Carcasa F1: ancho interior `clear_width_mm`, alto interior `clear_height_mm`.

Caja F1: `box_w = clear_width - slide_left - slide_right`; `box_depth = opening_depth - front_setback - rear_setback`; `wall_height = box_height - bottom_thickness`; `inner_w = box_w - 2 * drawer_panel_thickness`. Estos cálculos **se leen de F1**, no se ejecutan de nuevo dentro del integrador.

El cajón usa X a la derecha, Y arriba y Z atrás:

- Fondo inferior: plano XZ en origen `[x_left, y_bottom, z_front]`.
- Costados izquierdo/derecho: plano YZ, apoyados nominalmente sobre el fondo aplicado inferior.
- Frente y trasera **estructurales**: plano XY, entre costados, con sus Z correspondientes.
- Fachada embutida: plano XY, Z=0, definida por las cuatro holguras; se exige `front_setback_mm > facade.thickness_mm` para evitar la superposición de volúmenes con caja.
- Al apilar, las **aberturas** verticales nunca deben tocarse ni solaparse.
- Si hay fondo posterior, toda la caja queda por delante de su plano (control conservador). No se fabrican perforaciones para tuberías, correderas ni tornillos.

## Caso demostrativo reproducible

`examples/modular-two-drawers-inset.json`: base de cocina de 600 × 720 × 560 mm; 18 mm de espesor de carcasa, fondo HDF 6 mm, dos cajones `TOP` y `LOW` con aberturas de 300 mm de alto, separadas entre sí por 44 mm, ubicadas a 0 y 344 mm del inicio interior. Cada caja: luz lateral 13+13 mm, retranqueos 30/40 mm, espesor de paredes 18 mm, fondo aplicado 6 mm, altura exterior 230 mm. Dimensiones nominales F1: caja **538 mm de ancho × 460 mm de profundidad**, laterales de 224 mm de alto, frente/trasera estructurales de 502 mm de ancho. Cada frente embutido nominal mide **558 × 294 mm**. El proyecto devuelve **17 piezas físicas**: cuatro de carcasa, una de fondo, cinco por cada cajón y dos fachadas.

Los datos sirven SOLO para probar fórmulas. No prueban la compatibilidad de una corredera de 13 mm, su anclaje, recorrido, ni que la caja pueda instalarse sin tensiones.

```bash
python -m unittest discover -s tests -q
python -m carpinova_agent.modular_cli --input examples/modular-two-drawers-inset.json --csv /tmp/drawers.csv --svg /tmp/drawers.svg
python -m carpinova_agent.cad_cli --input examples/modular-two-drawers-inset.json --output /tmp/drawers-cad.json
```

## Gates y siguientes pasos

- Pruebas de cinco piezas del motor F1 contra las mismas piezas físicas del módulo; validación de aperturas, frentes, interferencia con fondo, material, seguridad de CSV y checksum CAD.
- GitHub Actions ejecuta Blender real con `.blend` y FreeCAD real con `.FCStd` sobre **17 piezas**, mide `bound_box` y `Shape.BoundBox` y compara con el mismo contrato CAD.
- Pendientes: inspección visual humana de los archivos, guías de montaje/ensayo del frente, cargas, rigidez, deslizamiento, ruedas y perfiles, SKU/longitud/placa/sistema exacto de corredera, patrones perforación y uniones.
- **Siempre `fabrication_ready=false`, `cutting_ready=false`, `drilling_ready=false`, `purchase_ready=false`**. Sin certificado de corte, taladro ni compra.

**NEXT_SAFE_ACTION**: revisión owner de esta rama DRAFT; consolidar/aprobar PRs anteriores en orden, recertificar QA exact-head; luego incorporar correderas de fabricante por referencia, frentes decorativos sobrepuestos y secuencia de montaje bajo nuevos casos medibles. No crear «solución» que duplique F1 o aparezca solo en Blender.

## Entrevista Maestro: decisiones antes de acabados

Para `action=modular` con estado `DRAFT_NOT_FOR_CUTTING`, `consult_maestro` pregunta **primero** por los campos pendientes de frente/puerta (`fronts`), fondo (`back`), cajones (`drawers`) y soporte (`support`); después por cada `drawers[].facade="pending"` con material, grosor y holguras explícitas; **al final** por la veta y el canto de la carcasa (`finish`). Esto evita que el límite de tres preguntas oculte una distribución de cajones sin resolver. En un empotrado sin medidas reales, los anchos superior/medio/inferior continúan teniendo prioridad absoluta.

Estas preguntas **no rellenan automáticamente campos** ni seleccionan una guía, bisagra, tornillo o patrón de taladro. La respuesta sigue siendo preliminar y bloqueada para fabricación. El texto genérico del borrador ya no afirma incorrectamente que «no hay cajones» cuando F7C sí los modela.

## Consulta del libro integrada en el diseño modular

`consult_maestro({"action":"modular","module_spec":{...},"query":"bisagras"}, bundle_dir="...")` mantiene **un único resultado** con el modelo modular, preguntas constructivas y búsqueda del libro verificado. `query` es **opcional**: sin él no se carga ni consulta Knowledge; con él, la ruta de lectura es **idéntica** a `action=knowledge`/`action=combined`. No hay indexador, motor de búsqueda ni copia paralela del PDF.

La respuesta devuelve `knowledge.coverage`, los fragmentos encontrados, `source_provenance` con `book`, `content_id`, `pdf_page`, `printed_page` y `review_status`. Si no se entrega `bundle_dir`, **falla explícitamente**; si el corpus es parcial o no hay coincidencias, deja constancia en `blockers`. No considera una coincidencia léxica como una norma técnica comprobada y **no inventa una recomendación de herraje, perforación o anclaje**.

Para probarlo con fuente real, el job `source-backed-full-book` de `.github/workflows/maestro-ci.yml` reconstruye la distribución canónica Knowledge v1.2.0 desde el commit fijado, consulta `bisagras` junto al ejemplo de cocina de **13 piezas** y archiva `maestro-modular-cited-knowledge.json`. Esta función es pedagógica, no habilita `fabrication_ready`, `cutting_ready`, `drilling_ready` o `purchase_ready`.

## Filtro de contexto léxico por cinco temas — auditoría conservadora

Para `action=modular`, además de `query` opcional se admite `evidence_topic` opcional **solo si hay `query`**. Categorías controladas: `edge_banding` (cantos), `backs_and_services` (fondos **y** instalaciones en el mismo registro), `screws_and_connectors` (tornillos/esquineros), `wall_support` (pared **y** apoyo/anclaje en el mismo registro) y `floor_support` (patas, banquero, zócalo). No son normas constructivas.

El flujo reaprovecha **exactamente** el lector canónico `load_bundle`/`search_content`: examina hasta **20 registros de búsqueda** y comprueba términos **completos**, con tildes normalizadas, dentro del mismo registro; no une la palabra «fondo» de una página con «tuberías» de otra ni trata «encanto» como «canto». Registros que satisfacen las familias del tema se devuelven como **candidatos léxicos**, priorizando coincidencias en texto frente a etiquetas editoriales. Si no los hay en esa muestra, devuelve lista vacía y advertencia. **No afirma que el concepto esté ausente del libro completo**; otro vocabulario o los dibujos pueden contenerlo.

La respuesta trae `knowledge.relevance_review` con muestras revisadas, `matched_terms`, `relation_status`, `candidate_count_in_sample`, `original_lexical_total_matches` y advertencias; `source_provenance` solo referencia los candidatos devueltos con página PDF e impresa original. Los flags `reviewed_against_original_pdf`, `technical_suitability_verified`, `manufacturer_spec_verified` están siempre en **false**, aun si el estado de extracción dice `VISUALLY_VERIFIED`: verificar un texto extraído **no certifica** que su consejo aplique al mueble diseñado. Ningún criterio de este filtro determina herrajes, espesor de canto, fijación ni capacidad estructural.

Ejemplo de solicitud con `--bundle-dir` validado:

```json
{
  "action": "modular",
  "module_spec": {"...": "usar una especificación modular válida existente"},
  "query": "fondo y tuberías",
  "evidence_topic": "backs_and_services"
}
```

### Revisión humana pendiente por candidato

Para pasar de coincidencia a recomendación individualizada, inspeccionar la **página PDF original y dibujo** (no solo el texto normalizado), corroborar contexto, compatibilidad real con material, humedad, lugar de instalación y herraje; registrar qué se aceptó/rechazó y por qué; exigir ficha **actual** del fabricante cuando aplique. Esta etapa de aprobación semántica **no está automatizada**. No convertir una etiqueta editorial o una coincidencia de texto en autoridad de fabricación.

El workflow `source-backed-full-book` ejecuta una matriz con los cinco temas, publica `maestro-topic-context-audit.json` y no exige coincidencias inventadas donde el libro no las tenga. Las pruebas incluyen falsos positivos por subcadenas, contextos repartidos entre páginas y falsos permisos de fabricación.
