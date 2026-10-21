# CarpiNova Agente — conectar con Codex o AntiGravity en Windows

## Fuente y alcance

Este manual corresponde exclusivamente al repositorio `sierraglobalcompanyv2/Carpinova-Agente`, rama canónica **`main`**, con integración funcional [PR #17](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/17) ya fusionada. CarpiNova-Knowledge se consume como fuente externa de solo lectura y CarpiNova-PC está fuera del alcance.

**Estructura KISS:** cuatro skills existentes, un Maestro, un motor dimensional F1/F6/F7C, un CADExchange y seis herramientas MCP **local stdio**. No hay MCP remoto de ChatGPT; la sexta herramienta de exportación nativa está deshabilitada por defecto y exige permisos explícitos del host. Nunca presentar el despiece nominal como documento de producción.

## 1. Preparar un Windows limpio

Se requiere Git, Python **3.12**, PowerShell y un clon del Agente desde **`main`**. Antes de instalar, verificar que ese HEAD esté probado en GitHub Actions; los PR #1–#19 del desarrollo original ya quedaron integrados o cerrados, sin PR históricos pendientes.

Desde PowerShell, al preparar la prueba final en tu PC:

~~~powershell
git clone https://github.com/sierraglobalcompanyv2/Carpinova-Agente.git
cd Carpinova-Agente
git switch main
git rev-parse HEAD
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_windows.ps1
~~~

Si ya existe el clon, no volver a clonarlo: entrar al directorio, revisar cambios locales y actualizar `main` sin sobrescribir trabajos.

El script:
1. Comprueba que Python sea 3.12, crea el entorno aislado .venv y ejecuta la instalación desde **requirements-mcp.txt**, archivo único de versiones directas comprobadas en CI.
2. Ejecuta pruebas unitarias y un **cliente MCP real** contra el servidor local, descubre las seis herramientas y genera dos muebles conocidos: 4 y 13 piezas, SVG, CSV, CADExchange, PNG y PDF.
3. Compara el hash original con los manifiestos y bloquea todo lo relacionado con fabricación, corte, perforación y compra.
4. Deposita el informe en work/preflight-*/mcp-preflight-report.json y crea únicamente **ejemplos de configuración** en work/configuracion-local. No modifica tus configuraciones de Codex/AntiGravity ni sobrescribe trabajos anteriores.

La carpeta .venv y work están ignoradas en Git. El script no usa llaves API, no lanza FreeCAD ni Blender, no contacta servicios LLM y **no controla otros programas de tu PC**. Puede instalar paquetes de Python desde los índices configurados en tu equipo; revisa las dependencias antes de ejecutarlo. 

**Fuente única de dependencias:** [requirements-mcp.txt](../requirements-mcp.txt). Actualmente fija mcp 1.30.0, resvg_py 0.5.0 y Pillow 13.0.0. Se trata de versiones directas, no de un lock de todas las dependencias transitivas.

## 2. Conectar el servidor en el agente del IDE

**Solo después de que termine el preflight y cuando el propietario decida instalar en Codex**, ejecutar desde la raíz del clon:

~~~powershell
python scripts/install_codex_skills.py --scope user --with-mcp
~~~

El instalador copia las **cuatro skills canónicas** a `~/.agents/skills/` y añade exclusivamente `mcp_servers.carpinova` a `~/.codex/config.toml`, preservando otros servidores y ajustes. Verifica las rutas generadas por el preflight, no sobrescribe skills divergentes ni cambia una configuración MCP existente diferente, y puede repetirse sin modificar una instalación idéntica. Después, **reiniciar Codex** y comprobar las cuatro skills y `carpinova_estado`.

Como referencias auditables permanecen `work/configuracion-local/codex-config.toml.example` y `antigravity-mcp.json.example`. Para AntiGravity, integrar manualmente solo su bloque JSON después de inspeccionarlo. Los ejemplos contienen rutas locales reales, sin credenciales ni privilegios elevados.

Mantener las herramientas en **modo Ask/confirmación**. Reiniciar el cliente y ejecutar la consulta de estado para comprobar conexión. Las seis herramientas esperadas son:

| MCP | Función |
| --- | --- |
| carpinova_estado | Estado, capacidades y bloqueos |
| carpinova_consultar | Maestro, preguntas de diseño, consulta de libro/herrajes si hay fuentes |
| carpinova_generar_borrador | Cinco archivos nominales desde una solicitud JSON confirmada |
| carpinova_renderizar_lamina | Vistas frontal, lateral y planta en SVG, PNG y PDF desde el CAD original |
| carpinova_exportar_3d | Exportar archivos nativos FreeCAD/Blender solamente con consentimiento y entorno local habilitado |
| carpinova_leer_entregable | Lee JSON/CSV/SVG permitidos como texto y devuelve **image/png** por MCP para `lamina/three-views.png` o `native/presentation.png`; nunca PDF binario |

El preflight en Windows dentro de GitHub **no** certifica que el IDE de tu PC ya esté conectado. Requiere la comprobación real en ese equipo. El conector GitHub usado en ChatGPT no inicia servidores MCP locales en tu computadora.

## 3. Diseño de tu primer mueble

Prompt práctico para Codex o AntiGravity:

> Usa CarpiNova y sus cuatro skills. Diseña conmigo un mueble de 50 cm de ancho, 50 cm de profundidad y 80 cm de alto. Quiero tres cajones y una gaveta grande. Pregúntame si prefiero manijas, apertura sin manija o un perfil tipo T, y si quiero frentes sobrepuestos o embutidos. Confirma materiales, espesores, holguras, correderas y distribución antes de calcular. Después de que apruebe la propuesta, genera el despiece nominal, las vistas 2D y, si está habilitado y lo autorizo independientemente, el modelo 3D. No inventes herrajes ni medidas de fabricación.

**Flujo correcto:** entrevista → propuesta íntegra y revisable → confirmación humana → JSON interno preparado por Codex → Maestro → borrador → láminas → revisión. **El usuario no tiene que escribir JSON.** El Maestro valida una solicitud estructurada; Codex la construye a partir de datos confirmados, sin inventar los faltantes. «Tres cajones y una gaveta» debe aclararse como cuatro cajas, y «perfil T» requiere sección/fabricante exactos. Con la carcasa ilustrativa sin fondo, el modelo de cuatro cajas produce **28 piezas nominales**, no un plan autorizado de corte.

Cada borrador incluye maestro-review.json, front-review.svg, parts-review.csv, cad-exchange.json y manifest.json. El subdirectorio lamina contiene three-views.svg, three-views.png, three-views.pdf y render-manifest.json.

El SVG es vectorial; el PDF es **rasterizado, de revisión**, y no reemplaza planos profesionales de taller. **Para que el Agente vea la imagen dentro del protocolo**, después de `carpinova_renderizar_lamina` debe llamar `carpinova_leer_entregable(proyecto, archivo="lamina/three-views.png")`. La respuesta es un bloque `image/png` MCP (no una ruta). Para el render 3D, solo después de la exportación CAD autorizada, usar `archivo="native/presentation.png"`. Se limita a imágenes PNG válidas de hasta 4 MiB y proyecto/manifiesto coherentes; no devuelve `.blend`, `.FCStd` ni PDF binario. Algunos clientes pueden no visualizar estos bloques aunque el protocolo funcione; validar la interfaz en Windows del propietario. Las vistas proyectan las mismas cajas CAD nominales y cotas exteriores, no dibujan agujeros, bisagras, uniones físicas ni líneas ocultas resueltas.

## 4. FreeCAD y Blender

FreeCAD y Blender consumen **el mismo** cad-exchange.json, usando sus adaptadores nativos ya existentes. No introducir un segundo cálculo de piezas. La herramienta nativa MCP opcional solo ejecuta adaptadores fijos con ejecutables previamente configurados por el host; no acepta comandos arbitrarios.

1. En FreeCAD instalado en tu PC y con autorización, usar el adaptador integrations/freecad_from_contract.py con el contrato y una nueva ruta .FCStd.
2. En Blender instalado en tu PC, usar integrations/blender_from_contract.py; si quieres un render de presentación, usar integrations/blender_presentation.py para guardar presentation.blend y presentation.png. Ver el [manual nativo](PILOTO_FREECAD_BLENDER.md).
3. Abrir los documentos en las aplicaciones reales; revisar identificación y dimensiones de piezas, orientaciones, acabados, vista y calidad visual. Coincidencia de hash **no** equivale a aprobación de ensamblaje/cargas/corte.

GitHub generó y verificó `.FCStd`, `.blend` y renders nativos con **4, 13 y 28 piezas** (para estas últimas, tanto `inset` como `overlay`) en FreeCAD/Blender **Linux**. El pipeline también ejecutó **505 pruebas Windows Python** y el MCP real. Eso no verifica que FreeCAD/Blender estén correctamente instalados en **el Windows del propietario**, ni sustituye la revisión física o visual de un mueble real.

## 5. Knowledge y fuentes de carpintería

Para responder sobre técnicas documentadas en el libro, disponer de un bundle Knowledge canónico **validado**, producido fuera del Agente. En los ejemplos MCP, agregar CARPINOVA_KNOWLEDGE_BUNDLE_DIR a las variables del servidor solo después de comprobar integridad y procedencia del bundle. No atribuir una recomendación o medida a una página no leída. Los resultados de búsqueda de libro son candidatos con fuente/página; la pertinencia técnica para el mueble debe revisarse.

El Agente conserva las skills diseño, maestro, selección de herrajes y técnicas constructivas; **no crear una skill adicional** para repetir canto, zócalos, fondos de instalaciones o diseño CAD.

## 6. Estado de las pruebas y puertas de salida

| Comprobación | Estado |
| --- | --- |
| Pila CarpiNova integrada en `main`, histórico cerrado | **GREEN, PR #17–#19 fusionados; 0 PR abiertos** |
| Python Windows 3.12, 505 pruebas y seis MCP | **GREEN CI** |
| Despiece y láminas nominales SVG/PNG/PDF/CADExchange | **GREEN CI** |
| FreeCAD/Blender Linux, archivos editables y render: 4/13/28 piezas | **GREEN CI**, sin QA físico de taller |
| Cuatro skills y registro MCP para Codex | **Instalador implementado y probado**, pendiente en PC del propietario |
| Codex interactuando con las seis herramientas en PC del propietario | **PENDIENTE de aceptación final** |
| FreeCAD/Blender ejecutándose en ese Windows | **PENDIENTE de aceptación final** |
| Knowledge completo con citas verificadas en ese PC | **PENDIENTE** |
| Corte, perforación, herrajes, cargas, anclajes de fabricación | **BLOQUEADO para producir** |

Evidencia del [CI MCP, Windows y CAD de 28 piezas](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39561886879), del [merge funcional](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/pull/17) y del `main` vigente. Los artifacts de Actions caducan: el repositorio y sus pruebas son la fuente reconstruible.

**Leyes CarpiNova:** KISS (un Maestro, un contrato), anti-ruido (sin duplicados), anti-parches (corregir origen más regresión) y UX/UI solo cuando aporte. Ningún check autoriza fabricación.

### Exportación 3D nativa mediante el Agente (desactivada por defecto)

La nueva herramienta MCP `carpinova_exportar_3d(proyecto, confirmacion)` aprovecha los adaptadores existentes. Solo el **operador del host** puede definir `CARPINOVA_FREECADCMD` (ruta absoluta a FreeCADCmd.exe/freecadcmd), `CARPINOVA_BLENDER` (ruta absoluta a blender.exe/blender) y `CARPINOVA_NATIVE_EXECUTION_ENABLED=1`. Después de ver el proyecto revisado y dar autorización específica en el IDE, invocar con `confirmacion="AUTORIZO_EXPORTAR_BORRADOR_3D"`.

Produce en `muebles/<proyecto>/native/` el paquete `native.FCStd`, `native.blend`, `presentation.blend`, `presentation.png`, `native-manifest.json` a partir del **mismo** `cad-exchange.json`; no reescribe el motor ni sobrescribe otro proyecto. Sin habilitación, confirmación, binarios válidos o geometría coherente, no ejecuta ni publica archivos. Nunca permite liberar compras, corte, perforaciones o fabricación. **Ya pasó** la prueba [MCP→FreeCAD/Blender nativo Linux con 4/13 piezas](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39536762720); **aún requiere** aceptación del propietario en Windows.

**Continuidad al cambiar de chat:** consultar [PROJECT_CONTINUITY_CURRENT.md](PROJECT_CONTINUITY_CURRENT.md) y los PR de GitHub, no un snapshot de conversación.

### Evidencia histórica de la primera exportación MCP→CAD

Commit certificado del circuito completo: `ec139352c83d3d32def9d1421bcf83cf1ca8e2bc`, [Actions #39536762720](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39536762720) 3/3 jobs SUCCESS, 468 pruebas Windows, dos muebles nominales completos 2D y 3D. El job native llama a la **sexta herramienta MCP real**, no a scripts de geometría alternativos. FreeCADCmd Ubuntu utiliza el enlace a `freecadcmd-python3`, validado por su nombre de paquete, no un shell genérico. El propietario debe abrir los modelos y validar visualmente antes de cualquier avance a taller.


### Aprobación humana independiente de la frase enviada por MCP (obligatoria)

**La frase de la herramienta no acredita consentimiento humano.** El instalador Windows **ya crea** la carpeta de aprobaciones en `%LOCALAPPDATA%\CarpiNova\native-approvals`, fuera del repositorio y de `CARPINOVA_OUTPUT_ROOT`, y la incluye en los ejemplos TOML/JSON mediante `CARPINOVA_NATIVE_APPROVAL_DIR`. No habilita ejecución nativa. El operador debe proteger el directorio frente a escritura por el agente. En Linux u otras instalaciones manuales, configurar un directorio externo equivalente en el entorno del host, nunca como argumento del modelo. El servidor seguirá necesitando `CARPINOVA_NATIVE_EXECUTION_ENABLED=1`, `CARPINOVA_FREECADCMD` y `CARPINOVA_BLENDER`.

Desde una terminal **humana e interactiva** separada del agente, con Python del proyecto y tras revisar el modelo, ejecutar:

~~~powershell
.\.venv\Scripts\python.exe -m carpinova_agent.native_export --approve-project "C:\RUTA\A\work\muebles\NOMBRE_PROYECTO" --approval-dir "$env:LOCALAPPDATA\CarpiNova\native-approvals"
~~~

El comando presenta la ubicación del proyecto, cantidad de piezas, SHA-256 y el bloqueo de fabricación. **La persona debe escribir `AUTORIZO` seguido de los últimos ocho caracteres del SHA**. Solo así genera una autorización de uso único, ligada al proyecto y al hash, que vence en máximo quince minutos. La sexta herramienta comprueba y **consume** esa autorización antes de lanzar los programas. Si falla o vence, hay que aprobar nuevamente desde terminal humana. **Codex/AntiGravity no deben emitir ese archivo mediante sus herramientas de terminal**, pues perdería su propósito de límite confiable. La carpeta de aprobaciones debe tener permisos controlados por el operador; no es una firma criptográfica resistente a un proceso que ya tenga acceso de escritura a esa carpeta. Los tests GitHub crean aprobaciones simuladas únicamente como parte del *harness* controlado: no equivalen a la firma del propietario.
