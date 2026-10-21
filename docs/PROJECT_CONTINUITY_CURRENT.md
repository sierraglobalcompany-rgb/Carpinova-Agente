# CarpiNova Agente — continuidad maestra del repositorio

**Fuente de continuidad:** este documento versionado, README, AGENTS y los tests/CI. **No** depender del historial de ChatGPT para reconstruir. Último checkpoint anterior: PR #16 HEAD `66cc8c9839afa7d218961c75a4dec66b77163e53`, seis workflows SUCCESS; actualizar HEAD y resultados solo tras comprobarlos. El commit real de `main` es `0bdb386a4875eaf2d1dcab99301348ae4bce7657`, todavía anterior a las funciones en DRAFT.

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
- `mcp_bridge`: 5 herramientas locales stdio verificadas con sesión real en Linux + Windows CI: `carpinova_estado`, `carpinova_consultar`, `carpinova_generar_borrador`, `carpinova_renderizar_lamina`, `carpinova_leer_entregable`. No se ha conectado el PC del propietario ni ChatGPT directamente.
- Paquete de revisión: `maestro-review.json`, `front-review.svg`, `parts-review.csv`, `cad-exchange.json`, `manifest.json`, más `lamina/three-views.svg/.png/.pdf` y `render-manifest.json`; PDF es raster y SVG es vectorial.
- `integrations/freecad_from_contract.py`, `integrations/blender_from_contract.py`, `integrations/blender_presentation.py`: aplicaciones nativas probadas en Ubuntu CI para gabinete 4 piezas y cocina 13 piezas; `.FCStd`, `.blend`, `presentation.blend`, `presentation.png`; actualmente fuera de invocación MCP (requieren autorización/operador).
- Windows `scripts/prepare_windows.ps1`: crea .venv, instala una única fuente de dependencias directas `requirements-mcp.txt`, prueba 456 casos, inicia MCP real, comprueba muestras, valida ejemplos TOML/JSON de Codex/AntiGravity, guarda entorno `resolved-packages-windows.txt`. No edita IDE ni instala CAD.
- `scripts/verify_local_mcp.py`: única prueba de protocolo; no duplicar su contenido en YAML.

## Estructura de 12 PR, no fusionar automáticamente
Pila de dependencia: **#1 → #4 → #2 → #6 → #7 → #9 → #11 → #12 → #13 → #14 → #15 → #16**. Todos se encontraban OPEN/DRAFT. PR #16 `feat/connect-carpinova-mcp-stdio` se basa en PR #15 `feat/f7d-natural-request-review`; PR #15 se basa en #14. `main` SHA anterior citado arriba. El ensayo `.github/workflows/pr-stack-rehearsal.yml` hizo merge temporal de los 12 con árbol idéntico y 456 pruebas. **No sustituye la aprobación del propietario ni QA posterior a la integración real en main.** El conflicto conocido del README F4/F5 debe resolverse en fuente e inspeccionarse durante merge; no inventar cambios.

## Prueba exacta del checkpoint anterior
HEAD `66cc8c9839afa7d218961c75a4dec66b77163e53`, 6 workflows GREEN:
- [MCP/Windows + CAD Linux](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39534069387) — 3/3 jobs PASS, Windows 456 tests; ejemplo 4 y 13 piezas; archivos FreeCAD/Blender reales y render PNG en Ubuntu; configuración TOML/JSON validada en Windows.
- [Ensayo de 12 PR](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39534069371) — árbol idéntico a HEAD, sin tocar `main`.
- Evidence artifacts expirarán el 04-nov-2026; conservar los necesarios fuera de Actions. Los archivos de fuente y scripts están versionados en GitHub.

## Pendientes y gates antes de aceptar el PC
P0 — Completar e integrar de forma controlada la exportación 3D **desde el Agente** sobre rutas localmente aprobadas, sin shell arbitraria, reutilizando los scripts existentes. Esta capacidad aún **no está implementada** en el checkpoint anterior. Requiere pruebas de rechazo y CI nativo.
P0 — Revisión del dueño y merge lineal autorizado de los 12 PR, reconstrucción fresca desde el **nuevo main** y repetición completa de suites Linux/Windows/CAD. Hasta entonces GitHub contiene el trabajo **en ramas PR, no en main**.
P1 — Aplicar instalación real en PC Windows, configurar Codex/AntiGravity de forma consciente y verificar llamadas de las herramientas dentro del IDE. No afirmar que CI equivale a ese entorno.
P1 — Bundle Knowledge canónico presente y consultable con citas en el PC; también importación y apertura visual real de FreeCAD/Blender Windows.
P1 — Ejercicio completo real de mueble (cocina, baño con tuberías, clóset): entrevista, variables confirmadas, cantos, fondos, sistema de soporte, herrajes, dibujos, lista de piezas, render, decisión de acabado, evidencia de pantallas y validación humana.
P2 — Fabricación: ajuste dimensional de corte por cantos, optimización de tableros, cotas de perforaciones según SKU/ficha, unión estructural, cargas y anclajes, medidas in situ, tolerancias propias del taller y prueba física. `fabrication_ready=cutting_ready=drilling_ready=purchase_ready=false` hasta cierre y responsable de taller.

## Instrucciones para el próximo chat/agente
1. Conectarse a **este** repo en GitHub; leer **este documento**, `AGENTS.md`, README, las 4 SKILL.md y `docs/conectar-agente-codex-antigravity.md`. Consultar estado vivo de los 12 PR y los workflows antes de asumir el SHA.
2. Trabajar exclusivamente en la rama DRAFT del Agente, no editar otros repos, no ejecutar merge a main sin consentimiento específico.
3. Desarrollar primero las funciones faltantes de entrega de muebles sobre los contratos existentes, y certificar exact HEAD. No crear un segundo motor de geometría ni más skills redundantes.
4. Mantener **esta misma ruta** `docs/PROJECT_CONTINUITY_CURRENT.md` actualizada con SHA, QA, bloqueos y NEXT al final de cada checkpoint. Registrar enlaces de PR/actions; no crear V1/V2/V3 de handoff que acumulen ruido.
5. Cuando el usuario diga «continúa», ejecutar cambios concretos en la fuente y pruebas; no desviarse al desarrollo de Knowledge/PC. Cuando la dependencia sea externa, clasificar BLOCKED con evidencia, no inventar éxito.

**Última clasificación verificable:** AGENT_SOURCE_ON_GITHUB=YES · PR_STACK_CI=GREEN · WINDOWS_MCP_CI=GREEN · NATIVE_LINUX_CAD=GREEN · OWNER_PC_IDE=NOT_VERIFIED · MAIN_RELEASE=PENDING_OWNER · FABRICATION=BLOCKED.
