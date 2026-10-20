# F5 — CarpiNova Maestro: prueba de integración controlada

## Qué ya funciona
Una solicitud JSON puede pedir una de estas operaciones:
- `project`: clasificar mueble, solicitar hasta tres medidas/decisiones faltantes y, solo para gabinete/caja de cajón, devolver geometría preliminar y piezas desde F1.
- `knowledge`: recuperar fragmentos del libro con `content_id`, página física, página impresa y estado editorial, previa verificación de los tres bundles F2.
- `hardware`: clasificar aplicación y comprobar referencia candidata de bisagra Blum F4, sin falsos taladros ni autorización de compra.
- `combined`: todas las anteriores juntas, con validación de coherencia entre `front_style` de proyecto y herraje.

Cualquier objeto no reconocido, incompatible o sin bundle cuando se solicita libro produce un error explícito. La salida nunca es un plano de taller certificado.

## Ejecución sin consultas al libro
```bash
python -m carpinova_agent.maestro_cli --input examples/maestro-questions.json
python -m carpinova_agent.dialogue
python -m unittest discover -s tests -v
```

## Ejecución con el libro completo
En un checkout de `sierraglobalcompany-rgb/CarpiNova-Knowledge` fijado en `4df02ef54562fac5a820cbad92b0edee547c310b` (no usar `main` móvil):
```bash
uv sync --all-groups
uv run python -m carpinova_knowledge validate --root .
uv run python -m carpinova_knowledge build-book-dist --root . --book-id cpnc-2025 --out work/knowledge-1.2.0
```
Copiar la carpeta `work/knowledge-1.2.0` sin modificar bytes, o montarla en ruta local, y ejecutar en Carpinova-Agente:
```bash
python -m carpinova_agent.maestro_cli --question "bisagras" --bundle-dir /ruta/knowledge-1.2.0
python -m carpinova_agent.maestro_cli --input examples/maestro-combined.json --bundle-dir /ruta/knowledge-1.2.0 --sketch /tmp/gabinete.svg
```

En GitHub Actions el workflow `maestro-ci.yml` verifica automáticamente los archivos fuente de Knowledge en ese SHA, genera los tres bundles **completos** de Knowledge v1.2.0, valida sus contadores y realiza una petición combinada real. La extracción visual contra PDF y la certificación de fabricación son procesos independientes; pasar el CI no demuestra esos extremos.

## Dependencias / limpieza del PR
Rama de integración `feat/f5-integrated-tool-orchestrator` creada desde F3 (PR #4). Para QA sin tocar los PR abiertos, reutiliza **los mismos blobs Git, idénticos byte a byte**, de F2 (PR #2) y F4 (PR #6), solo en la rama de prueba. Sus fuentes de verdad siguen en las ramas de origen. Tras aprobación de F1→F4, reorganizar el historial para que el PR F5 incluya únicamente el orquestador/skill/docs/pruebas; no fusionar prematuramente una copia temporal de los cuatro PR.

## Limitaciones técnicas actuales
- No existe LLM integrado ni una interfaz conversacional web/móvil; la consulta libre `--question` es búsqueda léxica del libro, no comprensión generativa.
- No existe sistema paramétrico completo de cocina/clóset/nicho con módulos compuestos, frentes y fondos definidos.
- No hay compensación de cantos, optimizador de corte, software CAD, cálculo de cargas, recomendaciones de tornillería validadas, información de proveedores/stock ni coordenadas finales de perforación.
- Las cotas 37/32 de placa Blum son referencias de croquis de fabricante, **no** autorizan perforaciones por sí mismas.
- El libro preserva `UNRESOLVED` y RuleSpecs no ejecutables: buscar texto no autoriza un plano de fabricación.
- Los resultados indican `fabrication_ready=false`, `purchase_ready=false`, `cutting_ready=false` y `drilling_ready=false`.

## Próximas tareas
1. Revisar CI exact-head y auditar errores del paquete completo del libro.
2. Validación humana de los PR F1, F2, F3, F4 sin mezclar los deltas.
3. Tras integrarlos, aprobar PR F5 con tests de árbol final y evidencia de un proyecto de gabinete.
4. Diseñar modelo paramétrico modular para cocinas/clósets, y catálogo actual de fichas de herrajes.
5. Para un agente verdaderamente conversacional, incorporar LLM y/o UI que use exclusivamente estas herramientas para cálculos y citas.
