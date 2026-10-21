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

**Última clasificación verificable (SHA `ec139352`):** AGENT_SOURCE_ON_GITHUB=YES · SIX_MCP_TOOLS=PASS · MCP_NATIVE_3D_LINUX=PASS · PR_STACK_CI=GREEN · WINDOWS_MCP_468_TESTS=GREEN · OWNER_PC_IDE=NOT_VERIFIED · WINDOWS_NATIVE_CAD=NOT_VERIFIED · MAIN_RELEASE=PENDING_OWNER · FABRICATION=BLOCKED.
