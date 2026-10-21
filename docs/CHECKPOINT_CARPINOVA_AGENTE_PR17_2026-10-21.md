# CarpiNova-Agente — Checkpoint de pausa (2026-10-21)

## Orden de operación
**Usuario pidió checkpoint y detener el trabajo. NO continuar ni utilizar Codex hasta nueva instrucción.**

## Fuente única de continuidad
- Repositorio: `sierraglobalcompanyv2/Carpinova-Agente`
- Rama en desarrollo: `feat/f7c-overlay-drawer-codex-ready`
- PR: [#17](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/17) **DRAFT**, base `feat/connect-carpinova-mcp-stdio` (PR #16).
- **HEAD funcional auditado antes de este checkpoint:** `82d4de2a9c42aacafa0f3768a148d1d5832149f9`.
- `main` NO se modificó; 12 PR históricos permanecían sin integrar.
- Proyecto limitado a CarpiNova-Agente. No modificar CarpiNova-Knowledge ni CarpiNova-PC.

## Avance real
- F7C existente ampliado: fachadas de cajón `inset` y `overlay`, holguras/solapes explícitos, detección de colisión; método de apertura solo decisión, NO geometría de herraje certificada.
- Contrato único `carpinova_agent/cad_exchange.py` ajustado para trasladar uniformemente en Z los frentes sobrepuestos sin romper la validación de volúmenes.
- `scripts/install_codex_skills.py`: instalación controlada de cuatro skills y configuración opcional MCP Codex, evitando sobrescribir configuración ajena.
- `AGENTS.md` y skill Maestro aclaran conversación natural vía Codex, **un Maestro**, aprobación de propuestas, sin segundo motor.
- Ejemplos de gabinete 500×500×800 mm con cuatro cajones, `inset` y `overlay`, y pruebas de CSV/SVG/CAD.
- Corrección puntual `82d4de2`: las pruebas sintéticas del instalador escribían rutas Windows inválidas para TOML; corregido el fixture. **El `prepare_windows.ps1` de producción no se modificó** porque ya escapaba rutas correctamente.
- Cuatro banderas de fabricación/corte/taladro/compra **false**. No son planos de producción.

## QA del HEAD funcional `82d4de2...` a la hora del checkpoint
PASS: Python geometry, hardware, Knowledge, Maestro integrated-tests, source-backed-full-book y MCP-protocol Linux.
EN EJECUCIÓN / NO CERTIFICADOS AÚN: Windows MCP preflight, FreeCAD + Blender nativo por MCP y prueba Blender headless.
NO declarar CI completo ni owner-PC aprobado antes de comprobar conclusión y SHA exactos.
Las 490 pruebas Windows corresponden al HEAD anterior del PR #16; la nueva ampliación exige nueva cifra y CI del HEAD actual.

## Próximo paso permitido al reanudar
1. Consultar GitHub HEAD y [CI del PR #17](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/17/checks); comparar contra SHA de este checkpoint. Leer logs de cualquier FAILURE; corregir causa raíz, no omitir pruebas.
2. Ejecutar flujo exacto 500×500×800 mm para 3 cajones + una gaveta en modalidad embutida y sobrepuesta: 28 piezas, checks dimensionales, dibujo, CSV y CAD, exportación nativa; recordar que valores de fixtures son ilustrativos y no aprobados para fabricación.
3. Auditar entrevista de Codex, instalación Skills/MCP Windows sin escrituras inseguras ni duplicación. Poner todas las correcciones en el PR #17 y validar CI por SHA final.
4. Consolidar PRs/ramas únicamente con verificación de linajes, SHA, resolución del conflicto F4/F5 README y CI; usuario ya autorizó integración, pero no forzar merges de comprobación fallida.
5. **Codex exclusivamente al final**, para QA final en el PC del usuario, si resulta técnicamente indispensable.

## Leyes innegociables
- KISS: simple, eficiente, optimizado, un Maestro, un motor y un CADExchange.
- Anti-ruido: eliminar, unir u optimizar solo con evidencia y sin perder funcionalidad.
- Anti-parches: corregir causa raíz y validar consumidores, no remiendos aislados.
- UX/UI Pro Max para la presentación/interacción que lo necesite; no crear interfaz adicional si Codex sirve.
- No adelantar bandera de fabricación sin datos del sitio, fichas verificadas de herrajes, cargas y validación competente.
