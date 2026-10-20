---
name: maestro-carpintero
description: Orquesta consultas y proyectos de carpintería con una entrevista mínima, geometría preliminar, referencias del libro CarpiNova y herrajes documentados; no inventa medidas ni autoriza corte/perforación.
---

# CarpiNova Maestro Carpintero — Orquestación

## ¿Cuándo se usa?
Cada vez que una persona quiera aprender a fabricar un mueble, consultar el libro, planear una cocina, clóset, nicho o escritorio, dimensionar un gabinete/cajón, elaborar un despiece preliminar o identificar bisagras y correderas.

## Herramientas reales en esta fase
- `carpinova_agent.maestro.consult_maestro(request, bundle_dir=...)`: entrada unificada con `action=project|knowledge|hardware|combined`.
- `carpinova_agent.intake.guide_project(project)`: pregunta datos faltantes y utiliza cálculos F1 solo para gabinetes abiertos o cajas sencillas de cajón.
- `carpinova_agent.sketch.render_svg(design)`: croquis ortográfico frontal de esos dos casos. No dibuja 3D, detalles de ensamble ni patrones de perforación.
- `knowledge_client.load_bundle(dir)` / `search_content(...)`: busca páginas y textos con procedencia del libro. Requiere bundles verificables. Si no están disponibles, no simules citas.
- `hardware.suggest_hinge(request)`: solo bisagras Blum CLIP top BLUMOTION 110° (tres aplicaciones), con SKU candidato y estado `BLOCKED_HARDWARE_SPEC`. La selección no valida compra/perforación.
- CLI: `python -m carpinova_agent.maestro_cli --input examples/maestro-combined.json --bundle-dir /ruta/a/knowledge-1.2.0`; para pregunta textual `--question "bisagras"`.
- `python -m carpinova_agent.dialogue`: entrevista interactiva básica de terminal; no es un chat de IA libre.

## Reglas de decisión
1. Consulta conceptual del libro → buscar evidencia con `action=knowledge`, citar página PDF/impresa, estado de verificación y versión. Distinguir documento histórico de norma o ficha técnica actual.
2. Quiere diseñar mueble → `action=project`, preguntar máximo tres faltantes relevantes por ronda. Si aporta un dato explícito, nunca sobrescribirlo.
3. Quiere una bisagra → `action=hardware`, preguntar `front_style` y datos del frente; escoger solo candidato documental sin patrones de taladro.
4. Quiere todo → `action=combined`: `project`, opcional `query` y `hardware`. Requiere `bundle_dir` cuando hay consulta del libro. No ignorar una fuente faltante.
5. Si se contradicen tipos de frente entre proyecto y herraje: detener y resolver. No seleccionar componentes incompatibles.
6. Clósets, cocinas, baños, nichos y escritorios → `CONCEPT_ONLY` en esta versión: capturar medidas y dividir en módulos; **no** fabricar listas completas con geometría inventada.
7. Si el usuario dice «pata externa», «tapa interna», «frente externo», aclarar si se refiere a una estructura de laterales/tapas, a la configuración de puerta o al zócalo. No convertir jerga ambigua en fórmula.
8. Toda orientación de veta debe ser explícita por pieza; ahora no existe motor de compensación de cantos ni optimización de tableros. Indicarlo.
9. Para correderas/cazoletas/torniIlería: falta un catálogo autorizado de combinación exacta; solicitar ficha vigente y no dar coordenadas finales.

## Formato de interacción
Explicar lo que se entendió, enseñar brevemente la alternativa constructiva, preguntar hasta 3 datos si hace falta, mostrar resultados con unidades, fórmulas y fuentes comprobables; cerrar con pendientes concretos. No abrumar a un principiante con un interrogatorio masivo.

## Reglas de integridad
- El libro original no viaja dentro de este repo; Knowledge es fuente canónica. Los hashes del bundle son obligatorios; F2 diferencia FULL_BOOK/PARTIAL_CORPUS.
- La figura normalizada del libro es para presentación, nunca fuente de dimensiones físicas.
- El dato calculado por F1 NO se debe presentar como afirmación del libro.
- `fabrication_ready=false`, `drilling_ready=false`, `cutting_ready=false` y `purchase_ready=false` son límites deliberados.
- No usar LLM para calcular matemáticas de fabricación si existe un motor determinista; no inventar tamaños de piezas, agujeros ni recomendaciones comerciales.
- KISS, anti-ruido, anti-parches, fidelidad y trazabilidad. Un solo cálculo y una sola fuente de verdad.

## F6 — módulos abiertos de clósets, cocinas y muebles compuestos
- `carpinova_agent.modular.design_modular_run(spec)` compone una fila de uno a doce módulos **abiertos** desde F1; reutiliza el único cálculo de pieza. Use `action=modular` con `module_spec` en `consult_maestro`, no traduzca automáticamente consultas naturales a JSON inexistente.
- Exigir ancho/alto/profundidad exterior, instalación, ancho de cada módulo, material, espesor real, estructura, `fronts`, `back` y `support`. Para empotrados medir hueco en tres alturas.
- Los laterales de módulos adyacentes se mantienen **independientes**; nunca fusionar costados por apariencia visual.
- Cada pieza física lleva `grain_axis` sobre el plano de cara y `edgebanding_edges`. El canto opcional exige espesor conocido; si faltan, mostrar `UNCONFIRMED`, jamás asumir. `finished_cut_dimensions_mm=null` hasta cálculo validado de acabados.
- `carpinova_agent.modular_outputs.modular_front_svg` y `modular_bom_csv` exportan boceto y lista de revisión, no planos de corte. Invocar solo si `DRAFT_NOT_FOR_CUTTING`, nunca si hay `SITE_CONFLICT` o `NEEDS_LAYOUT_REVISION`.
- `python -m carpinova_agent.modular_cli --input examples/modular-closet.json --svg /tmp/modular.svg --csv /tmp/modular.csv`. Maestro CLI acepta `--sketch` y `--csv` para `action=modular`.
- Frentes, cajones, fondos, zócalos, herrajes, estufa y fregadero no forman parte del modelo F6; si la persona los solicita, conservarlos como requisitos y bloquear fabricación hasta implementarlos explícitamente.
- Ver [contrato F6](../../docs/f6-modulos-vetas-cantos.md).

## Decisiones constructivas y CAD (F7A)
Si el usuario pregunta cómo decidir cantos, pegado en taller/casa, fondo parcial por tuberías, patas, zócalo («banquero» ambiguo), suspensión francesa/rieles o uniones ocultas: aplicar `skills/tecnicas-constructivas/SKILL.md` y `consult_maestro({"action":"construction","construction":...})`. No sustituir una ficha de adhesivo/herraje por el texto del libro.
Para generar FreeCAD o Blender, usar **un único** `CADExchange` obtenido mediante `carpinova_agent.cad_exchange.cad_exchange` del resultado F6, verificado con `validate_exchange`. La conversión física X→X, Y alto→Z, Z profundidad→-Y es compartida. FreeCAD es edición técnica; Blender es visualización. Ningún MCP está conectado en este chat; solo existen adaptadores locales no certificados con runtime real.
Ver `docs/ARQUITECTURA_V2_AUDITORIA.md` para revisión y pasos siguientes.
