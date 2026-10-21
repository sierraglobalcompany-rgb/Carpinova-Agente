# CarpiNova Agente — continuidad maestra del repositorio

**Fuente de continuidad:** este documento versionado, README, AGENTS y los tests/CI. **No** depender del historial de ChatGPT para reconstruir. **Código del piloto 3D verificado:** PR #16 commit `ec139352c83d3d32def9d1421bcf83cf1ca8e2bc`, seis workflows SUCCESS; este documento puede avanzar el HEAD sin cambiar esos resultados históricos. Actualizar evidencia únicamente tras comprobarla en GitHub. El commit real de `main` es `0bdb386a4875eaf2d1dcab99301348ae4bce7657`, todavía anterior a las funciones en DRAFT.

## Objetivo vinculante
El usuario debe conversar desde un cliente compatible con CarpiNova-Agente, recabar medidas y datos faltantes, consultar sus cuatro skills y Knowledge, diseñar módulos de muebles, entregar bocetos SVG, láminas PNG/PDF, BOM/despiece de revisión, y modelos FreeCAD/Blender con render basado en el mismo contrato. **La autorización para cortar, perforar, comprar o fabricar es una puerta distinta**, no lograda por disponer de render o pruebas de software.

## Alcance
Único repositorio que se puede cambiar en este hilo: `sierraglobalcompanyv2/Carpinova-Agente`. CarpiNova-Knowledge y CarpiNova-PC: dependencias **solo lectura**; no editar ni mezclar proyectos. Fecha local del checkpoint: 20-oct-2026 Colombia.

### Leyes de arquitectura
1. **KISS:** un Maestro, un motor de geometría F1/F6/F7C, una fuente Knowledge de lectura, un CADExchange, cuatro skills, un servidor MCP. No duplicar cálculos en FreeCAD/Blender o en el renderizador.
2. **Anti-ruido:** mejorar, integrar o eliminar con evidencia de consumo y regresiones. No añadir PR/skill/CLI/README histórico si un elemento existente se puede extender sin perder contrato.
3. **Anti-parches:** reproducir defecto, localizar raíz, corregir fuente, probar exact HEAD Linux + Windows + CAD nativo pertinente. No fallback silencioso, no ignorar error o test para poner GREEN.

## Estado del código comprobado
- `carpinova_agent.maestro.consult_maestro`: única capa de asesoría/diseño estructurado, sin autorización de fabricación.
- Cuatro skills existentes: `maestro-carpintero`, `diseno-muebles`, `tecnicas-constructivas`, `seleccion-herrajes`.
- `core` y `modular`: carcasas, paneles y F7C (puertas, fondos de servicios, cajones) **nominales**. Herrajes candidatos y consejo constructivo: consultivos, no pernos/taladros certificados.
- `cad_exchange`: contrato de geometría único con hash SHA-256 para identidad/reproducibilidad, **no** firma ni dimensiones de corte.
- `mcp_bridge`: **6 herramientas locales stdio** verificadas con sesión real en Linux + Windows CI: `carpinova_estado`, `carpinova_consultar`, `carpinova_generar_borrador`, `carpinova_renderizar_lamina`, `carpinova_exportar_3d`, `carpinova_leer_entregable`. El PC del propietario y ChatGPT directo NO están conectados.
- Paquete de revisión: `maestro-review.json`, `front-review.svg`, `parts-review.csv`, `cad-exchange.json`, `manifest.json`, más `lamina/three-views.svg/.png/.pdf` y `render-manifest.json`; PDF es raster y SVG es vectorial.
- `integrations/freecad_from_contract.py`, `integrations/blender_from_contract.py`, `integrations/blender_presentation.py`: adaptadores nativos reutilizados por `carpinova_agent.native_export.export_native_project`, llamado desde la **sexta herramienta MCP** únicamente con habilitación confiable `CARPINOVA_NATIVE_EXECUTION_ENABLED=1`, rutas absolutas a FreeCADCmd/Blender configuradas por el host y confirmación `AUTORIZO_EXPORTAR_BORRADOR_3D`. En CI Ubuntu ambos proyectos (4/13 piezas) generaron `.FCStd`, `.blend`, `presentation.blend`, `presentation.png` y `native-manifest.json`, con hash y medidas nativas contrastados; sin ejecución arbitraria por LLM.
- Windows `scripts/prepare_windows.ps1`: crea .venv, instala una única fuente de dependencias directas `requirements-mcp.txt`, prueba 456 casos, inicia MCP real, comprueba muestras, valida ejemplos TOML/JSON de Codex/AntiGravity, guarda entorno `resolved-packages-windows.txt`. No edita IDE ni instala CAD.
- `scripts/verify_local_mcp.py`: única prueba de protocolo; no duplicar su contenido en YAML.

## Estructura de 12 PR, no fusionar automáticamente
Pila de dependencia: **#1 → #4 → #2 → #6 → #7 → #9 → #11 → #12 → #13 → #14 → #15 → #16**. Todos se encontraban OPEN/DRAFT. PR #16 `feat/connect-carpinova-mcp-stdio` se basa en PR #15 `feat/f7d-natural-request-review`; PR #15 se basa en #14. `main` SHA anterior citado arriba. El ensayo `.github/workflows/pr-stack-rehearsal.yml` hizo merge temporal de los 12 con árbol idéntico y 456 pruebas. **No sustituye la aprobación del propietario ni QA posterior a la integración real en main.** El conflicto conocido del README F4/F5 debe resolverse en fuente e inspeccionarse durante merge; no inventar cambios.

## Prueba exacta del checkpoint anterior
HEAD funcional `ec139352c83d3d32def9d1421bcf83cf1ca8e2bc`, 6 workflows GREEN:
- [MCP de 6 herramientas + CAD nativo vía MCP](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39536762720) — 3/3 jobs SUCCESS, **Windows 468 tests**, modelos de 4 y 13 piezas; exportación 3D mediante el cliente MCP auténtico en runner Linux; archivos FreeCAD/Blender reales, manifiesto 3D, render PNG, y configuraciones TOML/JSON validadas en Windows. Artifact `carpinova-mcp-freecad-blender-real` ID 12318271134, `carpinova-mcp-windows-preflight` ID 12318420684.
- [Ensayo de 12 PR](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39536759219) — árbol idéntico al HEAD certificado, sin tocar `main`.
- Evidence artifacts expirarán el 04-nov-2026; conservar los necesarios fuera de Actions. Los archivos de fuente y scripts están versionados en GitHub.

## Pendientes y gates antes de aceptar el PC
P0 **RESUELTO EN RAMA DRAFT:** exportación 3D **desde MCP del Agente**, con 11 tests nativos de autorización/integridad, salida temporal atómica, rechazo de binarios/comandos del LLM y gate Linux FreeCAD/Blender real PASS. **No ejecutada ni validada en PC del propietario**. La frase de confirmación por sí sola no autentica al usuario; el host IDE debe obtener consentimiento humano real.
P0 — Revisión del dueño y merge lineal autorizado de los 12 PR, reconstrucción fresca desde el **nuevo main** y repetición completa de suites Linux/Windows/CAD. Hasta entonces GitHub contiene el trabajo **en ramas PR, no en main**.
P1 — Aplicar instalación real en PC Windows, configurar Codex/AntiGravity de forma consciente y verificar llamadas de las herramientas dentro del IDE. No afirmar que CI equivale a ese entorno.
P1 — Bundle Knowledge canónico presente y consultable con citas en el PC; también importación y apertura visual real de FreeCAD/Blender Windows.
P1 — Ejercicio completo real de mueble (cocina, baño con tuberías, clóset): entrevista, variables confirmadas, cantos, fondos, sistema de soporte, herrajes, dibujos, lista de piezas, render, decisión de acabado, evidencia de pantallas y validación humana.
P2 — Fabricación: ajuste dimensional de corte por cantos, optimización de tableros, cotas de perforaciones según SKU/ficha, unión estructural, cargas y anclajes, medidas in situ, tolerancias propias del taller y prueba física. `fabrication_ready=cutting_ready=drilling_ready=purchase_ready=false` hasta cierre y responsable de taller.

## Instrucciones para el próximo chat/agente
1. Conectarse a **este** repo en GitHub; leer **este documento**, `AGENTS.md`, README, las 4 SKILL.md y `docs/conectar-agente-codex-antigravity.md`. Consultar estado vivo de los 12 PR y los workflows antes de asumir el SHA.
2. Trabajar exclusivamente en la rama DRAFT del Agente, no editar otros repos, no ejecutar merge a main sin consentimiento específico.
3. El circuito MCP→borrador→2D→3D ya pasó CI: **no crear otro motor, otra skill ni un duplicado de MCP**. Enfocar ahora en QA post-merge autorizado, conexión local real y taller; clasificar cualquier extensión futura por evidencia.
4. Mantener **esta misma ruta** `docs/PROJECT_CONTINUITY_CURRENT.md` actualizada con SHA, QA, bloqueos y NEXT al final de cada checkpoint. Registrar enlaces de PR/actions; no crear V1/V2/V3 de handoff que acumulen ruido.
5. Cuando el usuario diga «continúa», ejecutar cambios concretos en la fuente y pruebas; no desviarse al desarrollo de Knowledge/PC. Cuando la dependencia sea externa, clasificar BLOCKED con evidencia, no inventar éxito.

**Checkpoint funcional anterior (SHA `ec139352`):** AGENT_SOURCE_ON_GITHUB=YES · SIX_MCP_TOOLS=PASS · MCP_NATIVE_3D_LINUX=PASS · PR_STACK_CI=GREEN · WINDOWS_MCP_468_TESTS=GREEN · OWNER_PC_IDE=NOT_VERIFIED · WINDOWS_NATIVE_CAD=NOT_VERIFIED · MAIN_RELEASE=PENDING_OWNER · FABRICATION=BLOCKED.

## Última mejora auditada — integridad de cinco archivos y UTF-8 (21-oct-2026)

**Código certificado SHA `5950b786ca72d38637bc460d9740460d80ea649b`: 6/6 workflows SUCCESS.** [MCP/Windows/CAD Actions #39539281697](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39539281697) verificó **476 pruebas Windows**, seis herramientas MCP, gabinete FreeCAD/Blender de 4 piezas, cocina de 13 piezas, ambas desde el CAD original; [ensayo de integración de 12 PR #39539281693](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39539281693) SUCCESS sin tocar main.

**Causa raíz corregida:** `write_pilot_bundle()` escribe ahora los cinco archivos como **bytes UTF-8** exactos, evitando que Windows duplique retornos de carro producidos por `csv.writer`. No introducir normalizadores de archivos que oculten defectos. La regresión de bytes exactos y siete controles nuevos de procedencia están en `tests/test_pilot_source_integrity.py`. CSV anteriores alterados por saltos de línea deben regenerarse desde fuente; no asumir que sirven para entregar despieces.

**Validador único:** `pilot_cli.verify_pilot_bundle()` comprueba Maestro JSON, croquis SVG, CSV, CADExchange y manifest antes de producir láminas 2D o archivos 3D. Regenera el contrato desde **el mismo motor Maestro**, rechaza cambios parciales aunque se recalcule SHA-256, archivos faltantes/enlazados/excesivos y banderas de producción distintas de false. No crea segundo motor. SHA-256 sin clave **no demuestra autoría ni aprobación humana**: la prueba garantiza consistencia interna, no firma digital.

**Evidencia:** `REAL_MCP_STDIO=PASS; SIX_TOOLS=PASS`; `MCP_NATIVE_CAD_PASS=primer_mueble; PIECES=4`; `MCP_NATIVE_CAD_PASS=cocina_dos_modulos; PIECES=13`; `MCP_NATIVE_FREECAD_BLENDER=PASS; FABRICATION_AUTHORITY=NO`. Los artifacts de Actions vencen el 04-nov-2026; el código y su reconstrucción permanecen en GitHub.

**NEXT antes de usar PC:** PR #16 continúa DRAFT; primero consolidación de 12 PR únicamente con aprobación del propietario, QA desde el main resultante, y luego Windows real con Codex/AntiGravity, bundle Knowledge y FreeCAD/Blender local, seguido de un mueble real con medidas confirmadas. No declarar manufacturabilidad, mecanizados ni cortes finales.

**Estado comprobado de código:** GITHUB_SOURCE=YES · PILOT_FIVE_FILE_PROVENANCE=GREEN · WINDOWS_476_TESTS=GREEN · SIX_MCP_TOOLS=GREEN · LINUX_NATIVE_3D=GREEN · STACK_12_PR_REHEARSAL=GREEN · OWNER_WINDOWS_IDE=NOT_VERIFIED · MAIN_MERGE=PENDING_OWNER · FABRICATION=BLOCKED.

## Puerta de aprobación nativa independiente del modelo — CI verificado (21-oct-2026)

**SHA funcional certificado `4aba273133e56202332cd810317805eeb67f37f7`: seis workflows SUCCESS**, [Windows + MCP real + FreeCAD/Blender Actions #39541383858](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39541383858). Windows Python 3.12 **483 pruebas PASS**; MCP real seis herramientas; FreeCAD/Blender 4/13 piezas; [ensayo stack 12 PR #39541383869](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39541383869) SUCCESS sin fusionar main.

**Control nuevo en `carpinova_agent/native_export.py`:** `carpinova_exportar_3d` permanece desactivada salvo opt-in del host, ejecutables permitidos y aprobación local de uso único. La frase `AUTORIZO_EXPORTAR_BORRADOR_3D` **NO** constituye consentimiento humano por sí sola. El operador configura `CARPINOVA_NATIVE_APPROVAL_DIR` absoluto, existente y fuera del directorio de proyectos; el usuario ejecuta **en su terminal independiente con TTY** `python -m carpinova_agent.native_export --approve-project <RUTA_MUEBLE> --approval-dir <RUTA_APROBACIONES>`, lee nombre/piezas/hash y escribe `AUTORIZO` más los últimos ocho caracteres del SHA. Se emite autorización SHA-bound, vinculada a ubicación del proyecto, máximo 15 minutos, un solo uso. El servidor la consume antes de lanzar FreeCAD/Blender. Sin archivo válido, con permiso vencido o fuente alterada, falla sin ejecutar. En caso de error CAD se debe autorizar de nuevo. No confundir el comprobante de archivo con firma criptográfica robusta frente a procesos con escritura en ese directorio.

**Límite de confianza:** la aprobación debe ser una decisión humana fuera del agente. Codex/AntiGravity **NO** pueden crearla o simularla mediante shell; si el cliente tiene permisos de escritura a la carpeta de aprobaciones, la barrera deja de ser independiente. El operador debe proteger dicha carpeta y mantener el IDE en Ask. El CI crea autorizaciones programáticamente **solo dentro del harness de prueba confiable**, nunca se declara consentimiento humano real.

**Archivos y fuente:** `native_export.py` integra validación, CLI TTY y consumo. `tests/test_native_export.py` conserva las pruebas nativas existentes; `tests/test_native_host_approval.py` añade siete casos nuevos (sin ticket, SHA/proyecto, expiración, ubicación, integridad, terminal y TTL), `scripts/verify_local_mcp.py` utiliza autorización temporal controlada en CI, y `docs/conectar-agente-codex-antigravity.md` contiene el procedimiento Windows. No se añadió una quinta skill, segundo motor geométrico ni workflow duplicado.

**NEXT operativo:** autorización específica del propietario para la integración ordenada de los **12 PR todavía DRAFT**, QA en el main efectivamente fusionado, instalación/QA visual en su Windows de FreeCAD/Blender y un mueble real con medidas confirmadas, instalaciones, vetas, cantos y herrajes. Las banderas `fabrication_ready`, `cutting_ready`, `drilling_ready` y `purchase_ready` permanecen false hasta revisión de ingeniería/taller.

**Estado de este checkpoint funcional:** SIX_MCP_TOOLS=PASS · HOST_NATIVE_ONE_USE_APPROVAL=PASS_IN_CI · WINDOWS_483_TESTS=GREEN · NATIVE_LINUX_CAD_4_13=GREEN · FULL_STACK_REHEARSAL=GREEN · MAIN_MERGE=WAITING_OWNER · OWNER_PC_CAD=NOT_VERIFIED · FABRICATION=BLOCKED.
