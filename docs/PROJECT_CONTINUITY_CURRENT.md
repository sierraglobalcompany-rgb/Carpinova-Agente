# CarpiNova Agente — continuidad y reconstrucción canónicas

## ESTADO VIGENTE — G27: G23 y MCP local verificados (23–24 oct 2026 UTC)

**Fuente de verdad:** [CarpiNova-Agente](https://github.com/sierraglobalcompany-rgb/Carpinova-Agente), `main@3775ca84503873ed7ed888da29ce1a6a70357e25`, comprobado en GitHub. Los apartados G13 y PR #32/33 inferiores son **historia**, no el estado operativo actual. Siempre comparar con el HEAD vivo antes de actuar.

**G23 — explicación humana de la Gola de madera:** [PR #5](https://github.com/sierraglobalcompany-rgb/Carpinova-Agente/pull/5) fusionado en `3775ca84503873ed7ed888da29ce1a6a70357e25`. Solo modificó `carpinova_agent/opening_guide.py` y `tests/test_opening_guide_recovered.py`. Quinta lámina: **A entrada bloqueada** por tapa superior y **B acceso posible** por ranura al canto del **frente móvil**; **T invertida fija, no manija**. H es la altura libre y V el vuelo de tapa, ambos sin validar. Aproximadamente 20 mm es propuesta del usuario, NO mínimo documentado del libro. Las cuatro aperturas anteriores se conservaron. El libro PDF 124–125 ilustra T para **puertas**; su uso en cajones, tope, fijación y ergonomía real **no está aprobado**.

**Pruebas exact-HEAD posteriores al merge:** **5/5 workflows SUCCESS** en `main@3775ca84`: Knowledge adapter, Python geometry, Manufacturer hardware, Maestro F5 y MCP stdio real. El último incluyó protocolo, Windows y FreeCAD/Blender nativos **SUCCESS** en GitHub CI. Una ejecución **anterior al merge** quedó cancelada por descarga apt al límite del job; histórica y registrada, no confundirla con el PASS del nuevo `main`. CI no autoriza taller ni acredita CAD nativo instalado en Windows del dueño.

**Validación real del PC:** G24 `STATIC=PASS`: clon Windows `C:\codex\Agente Carpinteria` sincronizado mediante fast-forward hasta `3775ca84`, árbol limpio; siete pruebas focales y smoke G23 PASS; no cambios en configuración/skills. G25 tuvo transporte PASS pero guía desactualizada en memoria (BLOCKED). G26 `CARPN-G26-MCP-FRESH=PASS`, reportado por Codex en sesión nueva: código directo y `carpinova_consultar` coinciden en A/B/H≈20 mm; `carpinova_estado` por stdio `DRAFT_DESIGN_ONLY`; `NEEDS_USER_CONFIRMATION`, cero piezas, `can_generate_f7c=false`, cuatro banderas false. No fue necesario atribuir PID, reinstalar ni alterar configuración. G26 **cierra el bloqueo de frescura MCP**.

**NEXT — prueba guiada G27, sin Codex para programar:** usar la herramienta MCP existente `carpinova_consultar` → `action=modular`, `module_spec.type=drawer_layout_guide`, ancho 500, fondo 500, alto 800 mm, `small_drawers=3`, gaveta D abajo. Presentar **ambas** construcciones por separado, frente y costado: `top_bottom_full` (C01; T/BS 500×500×18, LI/LD 764×500×18) y `sides_full` (C02; T/BS 464×500×18, LI/LD 800×500×18). Alturas ilustrativas A=B=C=136, D=272; franjas 28 mm **no son divisores ni juntas reales de frente**. Datos de tablero/proporción siguen sin aprobar. No generar paneles, CSV, CAD ni render 3D desde la propuesta. Revisar con el usuario claridad visual, opción preferida y modificaciones antes de F7C. Ninguna aprobación visual autoriza fabricación.

**Cuatro leyes:** KISS (un Maestro y único F1/CADExchange), antirruido (sin skills/motores/docs paralelos; cambios con evidencia), antiparches (corregir causa raíz y consumidores), diseño humano UX/UI legible y verificable. `fabrication_ready=false`, `cutting_ready=false`, `drilling_ready=false`, `purchase_ready=false`. No tocar CarpiNova-PC ni CarpiNova-Knowledge.

---

## ARCHIVO HISTÓRICO — G13: cuatro PR integrados (23-oct-2026 UTC)

**Repositorio operativo único:** https://github.com/sierraglobalcompany-rgb/Carpinova-Agente · rama `main`. Verificar `git rev-parse HEAD` contra el HEAD vivo antes de actuar. **Commit de integración confirmado:** `753dcac69fa235bf897f614a36e43b524161b5d4`; cualquier commit exclusivamente documental posterior puede avanzar HEAD sin modificar la funcionalidad.

**Integración aprobada expresamente por el propietario y completada en orden (método merge, sin squash/force):**
- [PR #1 — Blender recuperado](https://github.com/sierraglobalcompany-rgb/Carpinova-Agente/pull/1): HEAD histórico `7848a69bb1839b0e29e5883cdb1bc898d6b8e3e7`; merge `e2ecf82b76a72d864c1166be31c1d2c4c11b722f`. Cuatro commits originales preservados.
- [PR #3 — bocetos UX F1 reconstruidos](https://github.com/sierraglobalcompany-rgb/Carpinova-Agente/pull/3): `184d354fb63de3dcec81d34a115abc0052c61778`; merge `204530f1701f9f18dd60e5cc994d79815c178878`. Reconstrucción funcional, **no** el antiguo commit #36.
- [PR #2 — guía de aperturas reconstruida](https://github.com/sierraglobalcompany-rgb/Carpinova-Agente/pull/2): `112fd76374d11e7683187e983e092b8027058ed4`; merge `1047ce306fabd74250124cee6468974efe0c13af`. Reconstrucción funcional, **no** el antiguo commit #37.
- [PR #4 — recuperación documental](https://github.com/sierraglobalcompany-rgb/Carpinova-Agente/pull/4): `4563f79dbb1e90efd32cf3860537ca47e648a011`; merge `753dcac69fa235bf897f614a36e43b524161b5d4`. Recupera continuidad, **no** el antiguo commit #34.

**Verificaciones de integración:** GitHub confirma cuatro PR cerrados por merge, cuatro commits de fusión con ambos padres correctos. Diferencia desde `e17d9c61793ca8f2333b2ca7d760952647e0b1f5`: 15 rutas previstas, 11 commits por delante, sin divergencia. **G10** probó *antes de fusionar* exactamente estas cuatro ramas en una copia aislada, con siete cherry-picks, Python 3.12.10 y **584 pruebas = 577 PASS, 7 SKIP, 0 FAIL**. C01/C02 PNG 1160×1325 fueron renderizados y revisados visualmente; 10 SVG de referencia verificados en G8. Es evidencia de la **composición funcional**, no sustituto automático de CI del nuevo HEAD `main`.

**CI y limitaciones:** al integrar, PR #2/#3/#4 tenían 5/5 workflows GREEN. PR #1 tuvo 4/5 GREEN y un trabajo FreeCAD/Blender **cancelado por tiempo en descarga apt Ubuntu (25 minutos)**, antes de ejecutar CAD. El propietario **aceptó expresamente la integración con esta excepción**; no marcar ese trabajo como aprobado ni afirmar certificación nativa actual. Revisar los runs del HEAD vivo de `main` sin reiniciar pruebas ya suficientes. Artefactos nativos históricos y hashes permanecen preservados como evidencia, no como liberación industrial.

**Reglas inmutables:** KISS (motor único), antirruido (demostrar el impacto al unir/eliminar), antiparches (causa raíz + regresión integral), diseño UX/UI Pro (comparar dibujos/render legibles). Para bocetos/revisión: `NEEDS_USER_CONFIRMATION`, `piece_count=0`, `fabrication_ready=false`, `cutting_ready=false`, `drilling_ready=false`, `purchase_ready=false`. No fabricar, cortar, perforar, comprar ni instalar/autorizar CAD automáticamente. No modificar CarpiNova-PC o CarpiNova-Knowledge desde este proyecto.

**Continuidad sin trabajo repetido:** G1–G12 se cerraron; no repetir rescates `.codex`, exportación de 43 fuentes, PR36/37, suite G10 o auditorías de cherry-picks. Siguiente paso operativo: verificar CI del HEAD actual de `main` y realizar solo la aceptación local necesaria en PC (MCP seis herramientas, comparación de skill instalada, C01/C02 sobre instalación real) si procede; documentar lo no certificado. El historial bajo el encabezado siguiente corresponde a PR #32/33 **antes de la migración**, y no manda sobre este estado.

---

**Corte de referencia anterior:** 21-oct-2026; las secciones históricas bajo esta cabecera conservan evidencias de PR #32/33. **El estado vigente de recuperación figura arriba**; no reconstruir el estado sumando entregas históricas.

## Registro histórico de PR #32/33 (mantener como evidencia, no instrucciones de estado actual)

## 1. Identidad y evidencia exacta — checkpoint PR #32

- **Repositorio histórico PR #32:** [sierraglobalcompanyv2/Carpinova-Agente](https://github.com/sierraglobalcompanyv2/Carpinova-Agente), rama `main` en octubre de 2026. Para trabajo vigente utilizar `sierraglobalcompany-rgb/Carpinova-Agente` y las refs del bloque inicial; no acumular handoffs, ZIP ni motores duplicados.
- **Último commit FUNCIONAL de main certificado antes de este cambio documental:** `e39037fdac0466300428e866a41ddbc176f8055e`, merge del [PR #32](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/32). Su commit probado `ad0b17dffe5dd5ca0a35843c54833269042b2b0a` comparte árbol Git **`e2bf87e3277fc22d8552cae0b5023a13b2fa1707`** con el merge. El HEAD puede cambiar al fusionar esta **actualización solo documental**: verificar SHA vivo, diff y CI del nuevo HEAD, no usar el antiguo SHA como obligación inmutable.
- **CI certificado en el merge PR #32:** **5/5 workflows GREEN**: Knowledge adapter checks [#39663721549](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39663721549), Maestro F5 [#39663721368](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39663721368), Python geometry [#39663721372](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39663721372), manufacturer hardware [#39663721399](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39663721399), MCP real/Windows/CAD [#39663721395](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39663721395). **570 tests Windows Python 3.12 PASS**, seis herramientas MCP stdio, cuatro skills instalables, preflight aislado, FreeCAD/Blender nativos de CI PASS; las cuatro banderas de fabricación siguen falsas.
- **Historia reciente:** PR #28 introdujo boceto conversacional etiquetado y revisiones; #29 actualizó continuidad; #30 corrigió cotas y panel inferior BS; #31 corrigió la profundidad sin interpolar en SVG; **#32 corrigió el desacuerdo constructivo entre frente y costado y pasó a sugerir T y BS cubriendo laterales**. Todos están **MERGED**. No volver a fusionarlos.
- **Aceptación reportada en Windows del propietario antes de PR #32:** clon local limpio en `b6afdf8b47e3e137718c9f73fdb0010d5d6ac40b` (PR #31); seis herramientas `carpinova_*` y `carpinova_estado` **PASS**, respuesta `DRAFT_DESIGN_ONLY`; cuatro permisos false; `drawer_layout_guide` por MCP y bocetos PNG **PASS** tras reinicio; **skill `maestro-carpintero` instalada desactualizada/diferente de GitHub = FAIL**. Se informó SHA256 instalado `EAAA693D…E8E64F6` vs clon anterior `5FB3F4B7…F88F5A8C`. No hay evidencia de instalación del HEAD #32 ni de repetición visual de sus dos construcciones en ese PC. **No declarar PC final PASS**.
- **Knowledge local del propietario:** `knowledge_bundle_configured=false`; FreeCAD/Blender nativos **no conectados** a Codex local y exportación nativa desactivada. Esos pendientes no bloquean el modo guiado F1. Los tests GitHub no acreditan programas instalados en el PC del propietario.
- **Fuentes externas fuera de alcance de edición:** [CarpiNova-Knowledge](https://github.com/sierraglobalcompany-rgb/CarpiNova-Knowledge) fijado al SHA `4df02ef54562fac5a820cbad92b0edee547c310b` para pruebas; CarpiNova-PC pertenece a otro flujo. No editarlos desde este checkpoint.
- Los artifacts de Actions son evidencia temporal, NO dependencias de reconstrucción. Recuperar desde `main`, los scripts y las skills versionadas.

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
git clone https://github.com/sierraglobalcompany-rgb/Carpinova-Agente.git
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

La **quinta herramienta MCP (`carpinova_exportar_3d`)** necesita **tres puertas**: `CARPINOVA_NATIVE_EXECUTION_ENABLED=1` configurado por el host, ejecutables permitidos FreeCADCmd/Blender con rutas absolutas, **y** aprobación del operador en terminal TTY independiente `python -m carpinova_agent.native_export --approve-project <proyecto> --approval-dir <carpeta externa>`. El operador lee el nombre, piezas y SHA y confirma; el ticket de un solo uso, vinculado a la ruta y geometría, vence como máximo en 15 minutos y se consume antes de lanzar CAD. La frase MCP **no** sustituye ese acto. Mantener la carpeta externa protegida contra escritura por herramientas del agente; un proceso con acceso a ella podría falsificar aprobaciones. No ejecutar CAD como consecuencia automática del texto del usuario.

## 5. Contrato funcional vigente para retomar sin perder decisiones

1. **Arquitectura única:** F1 `core.design` para geometría, F6/F7C para módulos y cajones, Maestro para orquestación, `modular_outputs` para SVG/CSV, **CADExchange único** para FreeCAD/Blender. No se añadieron otros motores ni herramientas MCP. `action=modular`, `module_spec.type=drawer_layout_guide` se consulta con la herramienta existente `carpinova_consultar`.
2. **Diálogo humano primero:** persona dice «mueble 50 cm ancho × 50 fondo × 80 alto, tres cajones y una gaveta» y recibe **un boceto visible**, no interrogatorio técnico; 18 mm de material, 28 mm de franja interior y proporciones son **sugerencias** no aprobadas. Una pregunta sencilla: «¿Qué cambiarías?». Mostrar de ser posible SVG/PNG, no código sin render; si el cliente no renderiza imágenes, presentar `sketch_text` y advertir la limitación.
3. **Referencias que permanecen estables:** A/B/C/D de arriba a abajo (mapeo exacto con los D4…D1 internos); **T** tapa superior; **BS** base inferior; **LI/LD** laterales izquierdo y derecho; **AP** apoyo; **MF** relación/fijación con muro; **FP** panel de fondo posterior. `large_drawer_ref` conserva la gaveta original D aunque A crezca y pase a tener más altura. `element_refs` ofrece nominales por pieza.
4. **Ediciones conversacionales:** `drawer_adjustments_mm={"A":100}` sube la abertura A 100 mm y redistribuye el resto manteniendo alto total, registrando `revisions` de todas las afectadas. Conservar `review_state` acumulado para siguientes solicitudes. Si hay patas de 100 mm dentro de alto total 800 mm, carcasa pasa a 700 mm y se recalcula F1. Separación de 28 mm = **franjas geométricas entre aberturas**, NO separaciones visibles de frentes ni separadores físicos.
5. **Dos construcciones F1, NUNCA combinarlas visualmente:** el modo guiado propone `construction=top_bottom_full` sin aprobación, por preferencia estética de tapa cubriendo cantos laterales. Con carcasa 500 × 500 × 800 y tablero supuesto 18 mm, **T y BS nominales 500 × 500 × 18 mm; LI y LD de 764 × 500 × 18 mm**. En ambos dibujos T cubre laterales arriba y BS queda debajo. Alternativa `construction=sides_full`: **LI/LD 800 × 500 × 18 mm; T/BS 464 × 500 × 18 mm**, entre laterales; de perfil se ve el lateral completo, **las tapas van ocultas**, nunca placas dibujadas encima/abajo. `data-view` y `data-ref` del SVG permiten probar que frente y costado tienen la misma junta F1. En vista de costado el lateral visible se marca **LD** (LI opuesto), con referencias a T y BS. **La variante mixta** (T sobre laterales y BS entre ellos) **NO existe en F1/F7C**: no inventar geometría ni aprobar corte.
6. **T/BS configurables en el boceto, no fabricación:** `top_overhang_left/right/front/rear_mm` y `bottom_overhang_left/right/front/rear_mm` representan salientes independientes dibujados punteados. `concept_envelope` compara envolvente exterior ilustrativa con límites de espacio; **F1/F7C no modelan esos salientes como paneles estructurales**, por lo que `unvalidated_top_extension`/`unvalidated_bottom_extension` y cuatro flags impiden despiece productivo. No confundir el ancho nominal de T/BS con el ancho exterior de carcasa ni con `concept_outer_width_mm`.
7. **AP/MF/FP opcionales y seguros:** mueble apoyado, patas, zócalo/banqueo o suspendido; contra muro no equivale a suspendido. Fijación por listón francés, directa o riel es **intención** pendiente de material de pared, carga, anclaje y servicios; FP sin fondo, lámina delgada ilustrativa de 2 mm, fondo completo o franjas; 2 mm NO implica rigidez ni anclaje. Ningún boceto valida resistencia o taladros.
8. **Apertura de cajones:** símbolos explicativos para `handle`, `finger_pull`, `push_to_open`, `profile`, sin inventar SKU, perfil T, fresados o compatibilidades. PR #26 conserva `drawer_facade_style` y `opening_system_intent` en CSV/SVG de **revisión** solo cuando un diseño F7C confirmado proceda.
9. **Integridad:** propuestas F1 son `NEEDS_USER_CONFIRMATION`, `piece_count=0`, `can_generate_f7c=false`, cuatro permisos false. PR #24 vigila `max_assembled_depth_mm` (fachada overlay aumenta fondo exterior); PR #25 vincula `drawer_layout_reference` entre propuesta aprobada y F7C final; el usuario siempre aprueba físicamente las decisiones antes de generar borrador. F1 sin frontales **no conoce fondo ensamblado completo**. FreeCAD/Blender nativos del pipeline verifican geometría nominal, no ingeniería de taller.
10. **Calidad validada PR #32:** 570 Windows PASS y los cinco workflows GREEN en el commit de merge. Las pruebas de boceto comparan **dos vistas de la MISMA construcción**; `top_bottom_full` T/BS sobre/bajo costados, `sides_full` lateral completo con T/BS ocultos, identidades SVG, alturas nominales, dibujos PNG y seguridad. El código está en `main` y las reglas de usuario en `skills/maestro-carpintero/SKILL.md`. No abrir PR solo para continuar sin fallo comprobado.

## 6. Gates, bloqueos y NEXT seguro — STOP de este chat

| Gate | Estado |
| --- | --- |
| PR #28–#32 integrados en `main`; PR #32 frente/costado coherentes F1 | **PASS GitHub**, árbol PR #32 probado = árbol merge |
| Windows Python 3.12, pruebas MCP, cuatro skills, SVG/PNG/PDF | **570 pruebas PASS** en `e39037fd...` |
| Knowledge adapter, Maestro F5, geometría, herrajes | **GREEN** en `e39037fd...` |
| FreeCAD + Blender nativos y seis tools MCP de CI | **GREEN** en `e39037fd...` |
| CI del HEAD posterior a este cambio **documental** | **Consultar los runs del SHA vivo tras fusionarlo; no inventar resultados** |
| MCP `carpinova_estado` y modo guiado en Windows del usuario hasta PR #31 | **PASS reportado** |
| Skill `maestro-carpintero` instalada frente a GitHub; boceto PR #32 en Windows | **PENDIENTE / diferencia detectada**, debe actualizarse y probar |
| Knowledge completo y FreeCAD/Blender nativos en Windows del usuario | **NO VALIDADOS localmente** |
| Unión híbrida T completa + BS empotrada, salientes de panel, SKU, cargas, anclajes | **NO IMPLEMENTADO/NO AUTORIZADO PARA FABRICAR** |
| `fabrication_ready`, `cutting_ready`, `drilling_ready`, `purchase_ready` | **FALSE**; no liberar fabricación, corte, perforación ni compra |

### Próxima única prueba real en PC del propietario (sin usar Codex para programar)

1. Entrar al clon **ya existente**, hacer `git status`, `git fetch origin`, actualizar `main` sin perder modificaciones, revisar `git rev-parse HEAD` contra GitHub. **No reinstalar todo** ni tocar `config.toml`/otros MCP si funcionan.
2. Verificar las cuatro skills; comparar SHA de la skill `maestro-carpintero` instalada con `skills/maestro-carpintero/SKILL.md` actual. **Respaldar la divergente** y actualizar solamente esa skill con procedimiento controlado del instalador/repositorio; las otras tres quedan intactas si coinciden.
3. **Cerrar Codex por completo y reabrir nueva sesión MCP** después del checkout/skill. El servidor Python en memoria puede servir el código anterior aunque `git status` esté limpio. Ejecutar `carpinova_estado` y descubrir las seis herramientas.
4. Con `carpinova_consultar(action=modular,module_spec.type=drawer_layout_guide)`, mueble de **500 ancho × 500 fondo × 800 alto mm**, cuatro cajones (tres pequeños y gaveta D), generar **dos bocetos PNG visibles** del **mismo caso**: `construction=top_bottom_full` (propuesta por defecto) y `construction=sides_full` (alternativa). Mostrar y verificar las **uniones en frente y costado**, con T/BS/LI/LD identificados y cotas coherentes.
5. Probar «A 10 cm más alto» y confirmar que D sigue siendo la gaveta original; comparar revisiones antes/después. Probar **T +50 mm al frente** y **BS +100 mm al frente** por separado, comprobando `concept_envelope`, líneas punteadas y que las ideas no se conviertan en paneles CAD. Si el usuario pide un híbrido T arriba + BS entre costados, indicar que **no está modelado** y no dibujarlo como solución validada.
6. Entregar **un solo informe PASS/FAIL** con captura de frente y costado, comparación SHA de la skill, HEAD local y respuestas de MCP. Si falla, reportar defecto exacto; no commits ni cambios de código en Codex. No generar despiece/FreeCAD/Blender ni liberar fabricación en esta aceptación del boceto.

**Detener desarrollo aquí**. Próxima decisión solamente tras observar esas imágenes reales en Codex. Los módulos F7C de 28 piezas y sus CAD son pilotos geométricos, **no** planos profesionales de taller.

**En cualquier chat nuevo:** abrir este archivo primero, después `AGENTS.md`, `skills/maestro-carpintero/SKILL.md` y `docs/conectar-agente-codex-antigravity.md`; verificar SHA, estado de CI, PR abiertos y diferencias local/GitHub. Conservar las cuatro leyes **KISS, anti-ruido con evidencia, anti-parches integral y diseño UX/UI Pro Max**. Nada de ping-pong con Codex: solo la aceptación final local. No tocar CarpiNova-Knowledge ni CarpiNova-PC. Cualquier funcionalidad futura requiere fallo real o petición explícita, pruebas, un PR único y cierre de documentación.

