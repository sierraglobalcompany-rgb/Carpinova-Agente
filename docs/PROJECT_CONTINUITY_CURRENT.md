# CarpiNova Agente — continuidad y reconstrucción canónicas

**Fecha del estado comprobado:** 21-oct-2026, GitHub. **Solo este archivo es el checkpoint maestro vigente:** no reconstruir el estado sumando entregas de chats o archivos históricos.

## 1. Identidad y evidencia exacta

- **Repositorio exclusivo:** [sierraglobalcompanyv2/Carpinova-Agente](https://github.com/sierraglobalcompanyv2/Carpinova-Agente). CarpiNova-Knowledge y CarpiNova-PC son dependencias **solo lectura** y no deben modificarse desde este proyecto.
- **Rama de desarrollo operativa:** `feat/connect-carpinova-mcp-stdio`, [PR #16](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/16) **OPEN / DRAFT**.
- **SHA funcional certificado previo a esta actualización documental:** `2d8affe4b36b4a5eadc63ec24454347475f69185`. **`main` todavía es** `0bdb386a4875eaf2d1dcab99301348ae4bce7657`. No confundir el repositorio actualizado en una rama PR con un `main` ya integrado.
- **QA del SHA funcional:** [MCP + Windows + CAD #39548887879](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39548887879), **3/3 jobs SUCCESS**; **490 tests Windows Python 3.12**; cliente MCP recibió `image/png` **real** para las dos láminas y ambos renders Blender; modelos nativos de **4 y 13 piezas** verificados en FreeCAD/Blender Ubuntu. Los bytes PNG también se cotejan contra `png_sha256` o `presentation_png_sha256` de los manifiestos existentes, y una imagen modificada se rechaza. Ensayo de 12 PR, geometría, Knowledge, herrajes y Maestro SUCCESS en ese SHA: **6/6 workflows GREEN**.
- Este documento puede tener un commit posterior **solo documental**. Para cualquier afirmación de GREEN, **comprobar los workflows del HEAD actual**, no atribuir automáticamente el resultado anterior al nuevo SHA.
- Artifacts de CI (`carpinova-first-mcp-furniture`, `carpinova-mcp-windows-preflight`, `carpinova-mcp-freecad-blender-real`) caducan el **04-nov-2026**. Son evidencia de demostración, **no** dependencia de reconstrucción: el código, los ejemplos y los scripts están versionados.

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
git switch feat/connect-carpinova-mcp-stdio
git rev-parse HEAD
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_windows.ps1
```

**Puerta de seguridad del checkout:** comparar el SHA mostrado por `git rev-parse HEAD` con el HEAD **vivo** del [PR #16](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/16), o usar `git switch --detach 6a114e4297ac43e9aef43a99531ae3f3ffbed800` para reproducir el checkpoint exacto anterior (en ese caso, comprobar las seis ejecuciones y no trabajar sobre detached HEAD). Nunca ejecutar un clon de `main` antiguo como si contuviera el nuevo Agente.

`scripts/prepare_windows.ps1` es el **mismo que usa Windows Actions**: crea `.venv`, instala solo las versiones directas de `requirements-mcp.txt` (`mcp==1.30.0`, `resvg_py==0.5.0`, `Pillow==13.0.0`), corre todos los tests y un cliente MCP real, genera dos borradores y comprueba los formatos y flags. Deja evidencia bajo `work/preflight-*/`, incluyendo `resolved-packages-windows.txt`, lista efectiva de dependencias transitivas. **No hay lockfile transitorio completo multiplataforma**, por lo que el entorno no es una reproducción binaria idéntica garantizada.

Genera únicamente **ejemplos** de conexión (sin instalarlos en clientes reales): `work/configuracion-local/codex-config.toml.example` y `antigravity-mcp.json.example`. La carpeta de autorizaciones `%LOCALAPPDATA%\CarpiNova\native-approvals` se crea **fuera del repositorio**. CAD nativo permanece **desactivado**. Guía de uso y aprobación: [conectar-agente-codex-antigravity.md](conectar-agente-codex-antigravity.md).

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

## 5. Los 12 PR siguen DRAFT: orden y reglas para integrarlos

Los PR **#1 → #4 → #2 → #6 → #7 → #9 → #11 → #12 → #13 → #14 → #15 → #16** están OPEN/DRAFT; `main` continúa intacto. Las ramas base no son todas la anterior (F2/F4 dependen de `main`): respetar el orden de integración **comprobado** en el ensayo y revisar cada HEAD/base antes de hacer merge. Existe un conflicto histórico **README F4/F5**, reconciliado únicamente en el ensayo temporal mediante `scripts/reconcile_stack_readme.py`. No interpretar ese ensayo como aprobación para actualizar `main`.

**Nunca fusionar sin autorización expresa del propietario.** Si se autoriza, fusionar de forma controlada y repetir CI/QA desde un clon limpio del **`main` resultante**, no usar los 487 tests de la rama como certificado automático del release final.

## 6. NEXT y salida de etapa

| Gate | Estado |
| --- | --- |
| Fuente, skills, MCP 2D/3D e imágenes 2D/3D visualizables por MCP, ejemplo 4/13 piezas | **GREEN CI** en SHA funcional indicado |
| Seis workflows + integración temporal de 12 PR | **GREEN CI** |
| `main` fusionado y reconstruido | **PENDING OWNER APPROVAL** |
| Codex/AntiGravity MCP en Windows real del dueño | **NOT VERIFIED** |
| Knowledge completo y CAD nativo abiertos en ese Windows | **NOT VERIFIED** |
| Mueble real con revisión visual y medidas del sitio | **NOT VERIFIED** |
| Ingeniería de corte, taladro, estructura y fabricación | **BLOCKED** |

**Para el siguiente chat:** conectar este repo, leer primero este documento **en la rama PR #16**, `AGENTS.md`, README, las cuatro skills y el manual Windows; verificar SHA/PR/workflows vivos. Continuar solo con funciones faltantes demostradas, cumplir KISS/anti-ruido/anti-parches y dejar evidencia en el mismo archivo + PR. No usar Codex por ping-pong innecesario ni modificar Knowledge/PC. **Próximo avance real: autorización para integración a main, seguida de QA nuevo; luego validar en PC y diseñar un mueble real.**
