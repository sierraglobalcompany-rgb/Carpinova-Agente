# CarpiNova Agente — continuidad y reconstrucción canónicas

**Fecha del estado comprobado:** 21-oct-2026, GitHub. **Solo este archivo es el checkpoint maestro vigente:** no reconstruir el estado sumando entregas de chats o archivos históricos.

## 1. Identidad y evidencia exacta

- **Fuente única:** repositorio [sierraglobalcompanyv2/Carpinova-Agente](https://github.com/sierraglobalcompanyv2/Carpinova-Agente), rama **main**. Esta continuidad pertenece al mismo repositorio; los chats, PRs cerrados y artifacts de Actions NO son dependencias de reconstrucción.
- **Consolidación:** PR #17 integró F1–F7D y seis herramientas MCP; #20–#27 consolidaron seguridad, instalación y continuidad. [PR #28](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/28) **MERGED** incorpora bocetos conversacionales identificados, cambios revisables y opciones conceptuales de apoyos/muro/fondo. Commit funcional probado `885cbf903e9296ee5d36ba231634e2c8aba11ab5`; merge a `main` `09c972619329f62a26358b4908188661345d9e37`.
- **Igualdad de árboles verificada:** merge PR #28 y commit funcional tienen el mismo árbol Git `d2845a486a9426ba2389f1d8eeefd35c483f92e5`. El PR #29 cambió solo continuidad; PR #30 mejora el boceto identificado, pero siempre comprobar SHA vivo de main y sus Actions antes de certificar cualquier HEAD posterior.
- **QA del PR #28:** **553 pruebas Windows Python 3.12 PASS**; cinco workflows success en HEAD funcional, incluidos protocolo MCP 6 tools, instalador aislado 4 skills, boceto SVG y seguridad, Maestro, geometría, herrajes, Knowledge, FreeCAD y Blender reales (4, 13 y 28 piezas). [CI Windows/MCP/CAD](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39646073870). No extrapolar green a nuevos SHAs; verificar el CI posterior al merge por separado.
- **Knowledge externo solo lectura:** [CarpiNova-Knowledge](https://github.com/sierraglobalcompany-rgb/CarpiNova-Knowledge), fuente fijada SHA `4df02ef54562fac5a820cbad92b0edee547c310b`; CarpiNova-PC fuera de alcance en este chat.
- Los artifacts de Actions son temporales; reconstruir desde `main` y scripts versionados. **Aceptación local reportada por el propietario (21-oct-2026):** cuatro skills detectadas y seis herramientas `carpinova_*` disponibles; `carpinova_estado` respondió `DRAFT_DESIGN_ONLY`, cuatro flags false, native export disabled, `knowledge_bundle_configured=false`, y FreeCAD/Blender no conectados. La consulta F1 de cuatro cajones respondió correctamente. **No equivale a aceptación completa** de bocetos PR #28, despiece ni CAD nativo en su PC.


## 2. Objetivo, arquitectura y leyes

Construir muebles **preliminares revisables** desde conversación guiada: pedir medidas confirmadas, consultar las cuatro skills y Knowledge, producir la propuesta JSON para aprobación, geometría nominal, croquis SVG, despiece CSV, láminas SVG/PNG/PDF y modelos `.FCStd`, `.blend` y render PNG mediante **un mismo CADExchange**. No inventar datos faltantes ni asignar precisión industrial a imágenes.

**Leyes obligatorias:**
1. **KISS:** simple, eficiente, optimizado, eficaz; **un** Maestro, **un** cálculo dimensional F1/F6/F7C y **un** CADExchange. Los adaptadores FreeCAD/Blender y vistas 2D **no recalculan** piezas.
2. **Anti-ruido:** para eliminar, unir o mejorar demostrar consumidores y regresiones; no añadir skills, workflows, motores o handoffs redundantes. Este documento sustituye checkpoints anteriores.
3. **Anti-parches:** reproducir el fallo, corregir su **fuente**, cubrir todos los componentes afectados, probar Windows/Linux y CAD real pertinente; no silenciar errores.
4. **Diseño UX/UI:** seguir la skill/agente UX/UI Pro Max para interfaces de usuario cuando corresponda, con pruebas de accesibilidad y revisión visual. El CAD solo representa geometría nominal.

**Cuatro skills existentes:** `skills/maestro-carpintero/SKILL.md`, `skills/diseno-muebles/SKILL.md`, `skills/tecnicas-constructivas/SKILL.md`, `skills/seleccion-herrajes/SKILL.md`. No crear una quinta sin necesidad demostrada.

**Seis herramientas MCP stdio locales:** `carpinova_estado`, `carpinova_consultar`, `carpinova_generar_borrador`, `carpinova_renderizar_lamina`, `carpinova_exportar_3d`, `carpinova_leer_entregable`. Entrada: `python -m carpinova_agent.mcp_bridge`. **La quinta herramienta exporta 3D y la sexta lee entregables; el contrato conserva exactamente seis herramientas MCP.** La herramienta existente `carpinova_leer_entregable` devuelve texto en JSON/CSV/SVG y contenido MCP `image/png` al solicitar `lamina/three-views.png` o `native/presentation.png` (sin exponer binarios arbitrarios, PDF ni archivos nativos); controla el SHA-256 del archivo PNG en el manifiesto, su integridad básica y tamaño máximo 4 MiB. El cliente debe admitir contenido de imagen para visualizarlo. ChatGPT conectado a GitHub **no** equivale a tener estas herramientas ejecutándose dentro del PC del dueño.

**Fuente Knowledge:** repositorio [CarPiNova-Knowledge](https://github.com/sierraglobalcompany-rgb/CarpiNova-Knowledge), SHA probado `4df02ef54562fac5a820cbad92b0edee547c310b`; el bundle `FULL_BOOK` (v1.2.0, 252 páginas distribuidas, 295 fuente) se construye en `.github/workflows/maestro-ci.yml`. `.github/workflows/knowledge-ci.yml` prueba además un **piloto parcial**. No están versionados aquí ni el PDF original ni el bundle completo. Un resultado textual con cita no es especificación fabricable.

**Límites de fabricación:** `fabrication_ready=false`, `cutting_ready=false`, `drilling_ready=false`, `purchase_ready=false`. Canto, taladros exactos por SKU, uniones, anclajes, cargas, optimización de tablero, medición de obra y QA de taller **pendientes**. No dar una orden de corte ni de compra.

## 3. Reconstrucción desde CERO (sin chats ni artifacts de Actions)

Requisitos Windows: Git, **Python 3.12**, PowerShell, conectividad para instalar paquetes; FreeCAD/Blender son **posteriores y opcionales** durante el preflight. Desde PowerShell:

```powershell
git clone https://github.com/sierraglobalcompanyv2/Carpinova-Agente.git
cd Carpinova-Agente
git fetch origin
git switch main
git rev-parse HEAD
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_windows.ps1
# Solo en la validación final y con permiso expreso del propietario:
python scripts/install_codex_skills.py --scope user --with-mcp
```

**Puerta de seguridad del checkout:** comparar `git rev-parse HEAD` con el SHA **vivo de main**, no con el antiguo PR #16. El commit `7420940` identifica la integración funcional, pero el HEAD puede avanzar por revisiones de documentación. Verificar por árbol y CI; no usar un branch DRAFT como fuente principal.

`scripts/prepare_windows.ps1` es el **mismo que usa Windows Actions**: crea `.venv`, instala solo las versiones directas de `requirements-mcp.txt` (`mcp==1.30.0`, `resvg_py==0.5.0`, `Pillow==13.0.0`), corre todos los tests y un cliente MCP real, genera dos borradores y comprueba los formatos y flags. Deja evidencia bajo `work/preflight-*/`, incluyendo `resolved-packages-windows.txt`, lista efectiva de dependencias transitivas. **No hay lockfile transitorio completo multiplataforma**, por lo que el entorno no es una reproducción binaria idéntica garantizada.

El preflight genera **ejemplos** sin cambiar todavía la configuración real. El instalador opt-in `scripts/install_codex_skills.py --scope user --with-mcp` registra cuatro skills y el MCP en la fase final, sin sobrescribir configuraciones divergentes. Los ejemplos son: `work/configuracion-local/codex-config.toml.example` y `antigravity-mcp.json.example`. La carpeta de autorizaciones `%LOCALAPPDATA%\CarpiNova\native-approvals` se crea **fuera del repositorio**. CAD nativo permanece **desactivado**. Guía de uso y aprobación: [conectar-agente-codex-antigravity.md](conectar-agente-codex-antigravity.md).

### Knowledge completo para un nuevo PC (dependencia externa)

Con el repositorio Knowledge accesible, clonarlo **por separado** al lado del Agente, fijar el SHA anterior y usar `uv` (conforme al workflow `maestro-ci.yml`) para validar y generar el bundle:

```powershell
git clone https://github.com/sierraglobalcompany-rgb/CarpiNova-Knowledge.git ..\CarpiNova-Knowledge
git -C ..\CarpiNova-Knowledge checkout 4df02ef54562fac5a820cbad92b0edee547c310b
uv run --project ..\CarpiNova-Knowledge python -m carpinova_knowledge validate --root ..\CarpiNova-Knowledge
uv run --project ..\CarpiNova-Knowledge python -m carpinova_knowledge build-book-dist --root ..\CarpiNova-Knowledge --book-id cpnc-2025 --out work/knowledge-1.2.0
```

**Este paso NO es parte de `prepare_windows.ps1` ni está probado automáticamente en Windows del propietario.** Si Knowledge no puede descargarse, queda **BLOCKED** la consulta al libro completo, no el motor geométrico local. Validar el bundle antes de configurar `CARPINOVA_KNOWLEDGE_BUNDLE_DIR` en el servidor MCP. No copiar el libro al Agente ni inferir citas.

## 4. Integridad del paquete y aprobación de 3D

**Cinco archivos de origen:** `maestro-review.json`, `front-review.svg`, `parts-review.csv`, `cad-exchange.json`, `manifest.json`. `verify_pilot_bundle()` los contrasta **contra el mismo Maestro** antes de las láminas 2D y 3D. CSV UTF-8 se escribe como bytes exactos (evita alteraciones de CRLF en Windows).

**Exportación nativa:** `native_export.export_native_project()` toma una copia temporal **congelada** y validada de los cinco archivos; FreeCAD y las dos etapas de Blender leen exactamente el mismo CAD. Si cambian los originales durante la exportación, no publica `native/`. La identidad SHA-256 es consistencia interna, **no firma ni prueba criptográfica de autorización humana**.

La sexta herramienta MCP necesita **tres puertas**: `CARPINOVA_NATIVE_EXECUTION_ENABLED=1` configurado por el host, ejecutables permitidos FreeCADCmd/Blender con rutas absolutas, **y** aprobación del operador en terminal TTY independiente `python -m carpinova_agent.native_export --approve-project <proyecto> --approval-dir <carpeta externa>`. El operador lee el nombre, piezas y SHA y confirma; el ticket de un solo uso, vinculado a la ruta y geometría, vence como máximo en 15 minutos y se consume antes de lanzar CAD. La frase MCP **no** sustituye ese acto. Mantener la carpeta externa protegida contra escritura por herramientas del agente; un proceso con acceso a ella podría falsificar aprobaciones. No ejecutar CAD como consecuencia automática del texto del usuario.

## 5. Integración consolidada, capacidades vigentes y no-ruido

- Integración F1 → F3 → F2 → F4 → F5 → F6 → F7A → F7C → F7D y MCP efectuada mediante PR #17; los once PRs históricos adicionales se cerraron sin doble merge. PRs de mejoras #20 a #26 se integraron en `main`, sin motores, MCP ni skills paralelos.
- **PR #20–#21:** las cuatro skills de Codex conservan referencias navegables aun instaladas fuera del clon; preflight y bootstrap de MCP en Windows comprobados conjuntamente sin modificar `~/.codex` ni `~/.agents` reales del runner.
- **PR #22–#23:** `action=modular` con `module_spec.type=drawer_layout_proposal` propone de 1 a 4 aperturas desde medidas confirmadas con F1, pesos proporcionales y milímetros enteros por mayores residuos. Estado `NEEDS_USER_CONFIRMATION`, cero piezas; no es CAD ni prueba de consentimiento.
- **PR #24:** el `modular_run` permite opcional `max_assembled_depth_mm` para comparar fondo **total montado** con el límite confirmado; carcasa 500 + fachada overlay 18 = 518 mm. Si excede máximo de 500 mm, `NEEDS_DEPTH_REVISION` bloquea el borrador/CAD.
- **PR #25:** referencia opcional `modules[i].drawer_layout_reference` verifica con **el mismo** F1 la distribución antes de generar piezas; no cambia silenciosamente IDs, proporciones, alturas, posiciones o geometría de carcasa. No es firma de aprobación humana.
- **PR #26:** `parts-review.csv` conserva al final `drawer_facade_style` y `opening_system_intent`; `front-review.svg` muestra ambos en títulos con marca **SIN MECANIZADO**. `handle`, `push_to_open`, `finger_pull`, `profile` son intenciones, no herrajes ni taladros certificados. Para piezas no fachada, esos campos quedan vacíos.
- **PR #28 — modo guiado:** `module_spec.type=drawer_layout_guide` en la **misma consulta MCP** con medidas exteriores y cantidad de cajones devuelve `sketch_svg`, `sketch_text`, `element_refs`, `review_state` y una pregunta sencilla «¿qué cambiarías?». A-D identifican cajones de arriba a abajo; T tapa, LI/LD laterales, AP apoyo, FP fondo trasero y MF muro. `drawer_adjustments_mm` ajusta alturas en mm, recalcula el resto y registra `revisions` antes/después; `opening_heights_mm` se revalida con F1. `opening_systems` ilustra manijas, uñero, push-to-open y perfil, sin mecanizados.
- **AP/MF/FP conceptuales:** mueble al piso, patas, zócalo/banqueo o suspendido; si se agregan 100 mm de patas, los 800 mm totales pasan a 700 mm de carcasa, F1 recalcula aberturas. Alturas de apoyo no especificadas se proponen como ejemplos **sin aprobar**. Contra muro: listón francés, fijación directa o riel; elevación de suspendido no dada = **por definir**, no cero. Fondo posterior: ninguno, lámina delgada ilustrativa de 2 mm, completo o dos franjas; jamás inferir que 2 mm dan arriostramiento o que pared/anclajes soportan cargas. T saliente izquierda/derecha se dibuja como idea punteada, pero F7C NO genera panel estructural de voladizo. `piece_count=0`, `can_generate_f7c=false` y 4 flags de producción false hasta confirmar diseño e ingeniería.

- **PR #30 — boceto estructural de revisión:** el boceto ahora presenta T tapa, **BS base inferior** y LI/LD costados en vistas de frente y costado, con cotas nominales tomadas de F1. Para carcasa de 500 mm, tablero supuesto 18 mm y laterales continuos, T/BS nominales **464 × 500 × 18 mm** (no se debe etiquetar T como panel de 500 mm). T y BS pueden proponer salientes por separado en izquierda/derecha/frente/fondo mediante `top_overhang_*` y `bottom_overhang_*`; son ideas punteadas NO materializadas en F1/F7C. `concept_envelope` calcula dimensiones exteriores ilustrativas para contrastarlas con límites del usuario. `large_drawer_ref` fija qué cajón era la gaveta solicitada aunque otro se agrande; A-D no cambian de identidad. Todos los permisos de fabricación y `can_generate_f7c` siguen false, 0 piezas. Una consulta nueva requiere **reiniciar Codex/MCP** si el proceso Python aún usa el clon anterior.
- **Fuente de cálculo:** un Maestro, un F1/F6/F7C, un CADExchange; FreeCAD/Blender solo traducen/validan geometría. Los módulos legacy sin referencia de propuesta siguen admitidos, con los bloqueos de fabricación. Este archivo es el único checkpoint canónico, sin handoffs paralelos.


## 6. Gates, bloqueos y NEXT operativo

| Gate | Estado comprobado |
| --- | --- |
| F1/F6/F7C, propuestas y boceto humano A-D/T/BS/LI/LD/AP/MF/FP | **PR #30: cotas de paneles y salientes conceptuales auditables; verificar CI del HEAD vivo** |
| Windows Python 3.12 | **553 PASS en PR #28; PR #30 agrega pruebas de paneles, contornos y render PNG (consultar QA exact-HEAD)** |
| Maestro, Knowledge, herrajes, geometría y MCP real 6 tools | **GREEN histórico; comprobar 5 workflows del HEAD vivo tras fusionar PR #30** |
| FreeCAD + Blender nativos, 4/13/28 inset/28 overlay | **GREEN histórico; confirmar nuevamente en HEAD posterior a PR #30** |
| Preflight/instalador cuatro skills y MCP en Windows runner aislado | **GREEN en CI; sin tocar el HOME del usuario** |
| GitHub Actions posterior al merge/documentación | **CONSULTAR SIEMPRE CI y SHA vivo de main** |
| Codex real instalado, cuatro skills y seis MCP en PC del propietario | **PASS reportado para skills + estado MCP; bocetos nuevos aún sin aceptación local** |
| FreeCAD/Blender y Knowledge completo en PC del propietario | **NO COMPROBADO** |
| Referencias de correderas, tornillos, perfiles tipo T, pesos y cargas | **SIN FICHA/VALIDACIÓN DE FABRICACIÓN** |
| `fabrication_ready`, `cutting_ready`, `drilling_ready`, `purchase_ready` | **FALSE: BLOQUEO ABSOLUTO de producción** |

**NEXT_SAFE_ACTION:** si el último `main` está GREEN, actualizar el clon local en Windows, reinstalar las cuatro skills con el instalador existente (el propietario conserva los cambios locales y sus demás servidores) y reiniciar Codex para que cargue el nuevo Maestro. Ejecutar **una consulta guiada** con 500×500×800 mm y tres cajones más gaveta, mostrar el SVG real sin exigir espesor/separación individual, solicitar «A 10 cm más alto» (registrar todos los cambios), «T sobresalga 5 cm», «BS más ancha», «T más profunda» (todos solo conceptos), «pon patas de 10 cm» (alto total constante), «suspendido con francés» y «FP delgado/completo/ninguno». Verificar referencias A-D/T/BS/LI/LD/AP/MF/FP, medidas nominales (464 mm para T/BS con 500 mm carcasa y 18 mm laterales continuos), envolvente conceptual, etiqueta fija de gaveta, avisos, alturas y 0 piezas; no generar despiece ni CAD de supports/voladizos/fondos no modelados. Solo después del boceto aceptado pedir materiales, guías, cargas, frente y dimensiones de fabricación. La aceptación nativa FreeCAD/Blender y Knowledge local quedan pendientes. Una sola evidencia PASS/FAIL; no más PR hipotéticos.

Los pilotos de 28 piezas son diseños NOMINALES: carecen de aprobación de taller, dimensiones finales con compensación de cantos/merma, herrajes SKU validados, taladros y anclajes. No llamar a eso planos de fabricación.


**Para cualquier chat nuevo:** iniciar por `main/docs/PROJECT_CONTINUITY_CURRENT.md`, `AGENTS.md`, la skill Maestro y el manual Windows; corroborar HEAD y CI vivos. Mantener las cuatro leyes KISS, anti-ruido con evidencia, anti-parches y diseño UX sin duplicar motores. No modificar CarpiNova-Knowledge ni CarpiNova-PC. No inferir que la PC del usuario está certificada a partir de GitHub Actions.
