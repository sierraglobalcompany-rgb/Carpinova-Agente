# CarpiNova Agente — continuidad y reconstrucción canónicas

**Fecha del estado comprobado:** 21-oct-2026, GitHub. **Solo este archivo es el checkpoint maestro vigente:** no reconstruir el estado sumando entregas de chats o archivos históricos.

## 1. Identidad y evidencia exacta

- **Repositorio y fuente de reconstrucción:** [sierraglobalcompanyv2/Carpinova-Agente](https://github.com/sierraglobalcompanyv2/Carpinova-Agente), rama **main**, no PRs históricos.
- **Integración funcional:** [PR #17](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/17) **MERGED**, con documentación normalizada después en [PR #18](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/18) **MERGED**. Commit de merge en main: `7420940843649bf2c0939bcb36167b98be27dd79`; HEAD funcional probado antes del merge: `db5336783d9426b6e3b73a44f4234266bfc2ba56`.
- **Igualdad de árboles comprobada:** Git tree de ambos commits = `841d2da3846e3b4d7c639064651ee2ad9d52acdc`. Main incluye los 130 archivos frente al antiguo main, sin perder el contenido auditado de la pila F1–F7D/MCP y F7C de cuatro cajones.
- **QA funcional SHA db533678:** **505 pruebas en Windows Python 3.12 PASS**, MCP stdio seis herramientas, SVG/PNG/PDF, configuraciones de cliente; geometría, Maestro, Knowledge y herrajes GREEN; FreeCAD y Blender reales con muebles de 4, 13 y **28 piezas embutidas y 28 sobrepuestas** GREEN. [MCP/Windows/CAD](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39561886879). El CI de main posterior al merge debe comprobarse **por el SHA exacto** antes de certificar estado del repositorio.
- **Source Knowledge de solo lectura:** [CarpiNova-Knowledge](https://github.com/sierraglobalcompany-rgb/CarpiNova-Knowledge) SHA `4df02ef54562fac5a820cbad92b0edee547c310b`. CarpiNova-PC fuera de alcance.
- Artifacts de Actions son evidencias temporales, no dependencia: reconstruir desde código versionado y `requirements-mcp.txt` manteniendo las limitaciones de compatibilidad documentadas.
- **No hay QA de la PC física del dueño ni liberación de fabricación.** No inventar ese resultado.


## 2. Objetivo, arquitectura y leyes

Construir muebles **preliminares revisables** desde conversación guiada: pedir medidas confirmadas, consultar las cuatro skills y Knowledge, producir la propuesta JSON para aprobación, geometría nominal, croquis SVG, despiece CSV, láminas SVG/PNG/PDF y modelos `.FCStd`, `.blend` y render PNG mediante **un mismo CADExchange**. No inventar datos faltantes ni asignar precisión industrial a imágenes.

**Leyes obligatorias:**
1. **KISS:** simple, eficiente, optimizado, eficaz; **un** Maestro, **un** cálculo dimensional F1/F6/F7C y **un** CADExchange. Los adaptadores FreeCAD/Blender y vistas 2D **no recalculan** piezas.
2. **Anti-ruido:** para eliminar, unir o mejorar demostrar consumidores y regresiones; no añadir skills, workflows, motores o handoffs redundantes. Este documento sustituye checkpoints anteriores.
3. **Anti-parches:** reproducir el fallo, corregir su **fuente**, cubrir todos los componentes afectados, probar Windows/Linux y CAD real pertinente; no silenciar errores.
4. **Diseño UX/UI:** seguir la skill/agente UX/UI Pro Max para interfaces de usuario cuando corresponda, con pruebas de accesibilidad y revisión visual. El CAD solo representa geometría nominal.

**Cuatro skills existentes:** `skills/maestro-carpintero/SKILL.md`, `skills/diseno-muebles/SKILL.md`, `skills/tecnicas-constructivas/SKILL.md`, `skills/seleccion-herrajes/SKILL.md`. No crear una quinta sin necesidad demostrada.

**Seis herramientas MCP stdio locales:** `carpinova_estado`, `carpinova_consultar`, `carpinova_generar_borrador`, `carpinova_renderizar_lamina`, `carpinova_exportar_3d`, `carpinova_leer_entregable`. Entrada: `python -m carpinova_agent.mcp_bridge`. **La sexta herramienta sigue siendo exportar CAD; no se añade una séptima.** La herramienta existente `carpinova_leer_entregable` devuelve texto en JSON/CSV/SVG y contenido MCP `image/png` al solicitar `lamina/three-views.png` o `native/presentation.png` (sin exponer binarios arbitrarios, PDF ni archivos nativos); controla el SHA-256 del archivo PNG en el manifiesto, su integridad básica y tamaño máximo 4 MiB. El cliente debe admitir contenido de imagen para visualizarlo. ChatGPT conectado a GitHub **no** equivale a tener estas herramientas ejecutándose dentro del PC del dueño.

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

## 5. Integración consolidada y cierre de PR históricos

- La pila F1 → F3 → F2 → F4 → F5 → F6 → F7A → F7C → F7D → MCP, más overlay/inset de cuatro cajones y bootstrap Codex, quedó incorporada a main mediante **un solo merge PR #17** (aprobación explícita del dueño; QA exact-head antes del merge).
- La reconciliación histórica F4/F5 de README se preservó en el árbol del PR #17. El ensayo original había verificado `STACK_TREE_EQUAL_TO_FEATURE_HEAD=YES`; la comparación de árboles entre el merge main y el PR #17 es **idéntica**.
- El PR #1 se marcó merged automáticamente al integrarse su ancestro. Los otros **11 PR históricos ya fueron cerrados administrativamente**, cada uno con comentario que enlaza a la integración PR #17; sus ramas y commits siguen disponibles. Verificación posterior: **0 PR abiertos**. No reintroducir cambios superpuestos.
- No borrar ramas ni Knowledge. Reabrir incidencias solamente con evidencia y arreglarlas donde corresponde, nunca recrear una pila paralela.


## 6. NEXT, límites y criterios de salida

| Gate | Estado |
| --- | --- |
| Pila integrada en main, árbol idéntico a SHA funcional | **MERGED / TREE VERIFIED** |
| Windows 505 pruebas, Maestro, Knowledge, hardware, MCP e imágenes | **GREEN en HEAD funcional db533678** |
| FreeCAD + Blender 4/13/28 inset/28 overlay piezas | **GREEN en HEAD funcional db533678** |
| CI del HEAD main luego del merge/documentación | **VERIFICAR SHA VIVO** |
| Instalador de cuatro skills y MCP en PC del usuario | **IMPLEMENTADO / NO EJECUTADO EN PC** |
| Knowledge completo y FreeCAD/Blender instalados en PC del usuario | **NO VERIFICADO** |
| Diseño real revisado por el dueño con medidas y herrajes reales | **PENDIENTE** |
| Corte final, taladros, cargas, anclajes y fabricación certificada | **BLOQUEADO** |

**NEXT_SAFE_ACTION:** comprobar siempre el CI del HEAD real de main; la consolidación de código y el cierre de los PR históricos ya están completados (0 abiertos). No repetir esas integraciones ni añadir nuevos handoffs. Usar Codex **solo al final**, en una sesión limitada de PC para instalar las cuatro skills/MCP y probar el diseño verbal 50 × 50 × 80 cm, tres cajones y una gaveta: confirmar 500×500×800 mm, 4 cajas, solapes o embutido, manijas/perfil T, material y espesores antes de producir el paquete. No pedir al usuario JSON manual. El piloto de 28 piezas sigue siendo **nominal**: ningún cálculo de corte, corredera SKU o perforación está autorizado hasta corroboración real.

**Para cualquier chat nuevo:** iniciar por `main/docs/PROJECT_CONTINUITY_CURRENT.md`, `AGENTS.md`, la skill Maestro y el manual Windows; corroborar HEAD y CI vivos. Mantener las cuatro leyes KISS, anti-ruido con evidencia, anti-parches y diseño UX sin duplicar motores. No modificar CarpiNova-Knowledge ni CarpiNova-PC. No inferir que la PC del usuario está certificada a partir de GitHub Actions.
