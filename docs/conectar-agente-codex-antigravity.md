# CarpiNova Agente — conectar con Codex o AntiGravity en Windows

## Fuente y alcance

Este manual corresponde exclusivamente al repositorio sierraglobalcompanyv2/Carpinova-Agente, PR #16 DRAFT. CarpiNova-Knowledge se consume como fuente externa de solo lectura y CarpiNova-PC está fuera del alcance.

**Estructura KISS:** cuatro skills existentes, un Maestro, un motor dimensional F1/F6/F7C, un CADExchange y seis herramientas MCP **local stdio**. No hay MCP remoto de ChatGPT; la sexta herramienta de exportación nativa está deshabilitada por defecto y exige permisos explícitos del host. Nunca presentar el despiece nominal como documento de producción.

## 1. Preparar un Windows limpio

Se requiere Python **3.12**, PowerShell y un clon de la rama/comisión del Agente validada en CI. No usar el contenido de main mientras los PR no hayan sido integrados por el propietario.

Desde la raíz del repositorio:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\prepare_windows.ps1
~~~

El script:
1. Comprueba que Python sea 3.12, crea el entorno aislado .venv y ejecuta la instalación desde **requirements-mcp.txt**, archivo único de versiones directas comprobadas en CI.
2. Ejecuta pruebas unitarias y un **cliente MCP real** contra el servidor local, descubre las seis herramientas y genera dos muebles conocidos: 4 y 13 piezas, SVG, CSV, CADExchange, PNG y PDF.
3. Compara el hash original con los manifiestos y bloquea todo lo relacionado con fabricación, corte, perforación y compra.
4. Deposita el informe en work/preflight-*/mcp-preflight-report.json y crea únicamente **ejemplos de configuración** en work/configuracion-local. No modifica tus configuraciones de Codex/AntiGravity ni sobrescribe trabajos anteriores.

La carpeta .venv y work están ignoradas en Git. El script no usa llaves API, no lanza FreeCAD ni Blender, no contacta servicios LLM y **no controla otros programas de tu PC**. Puede instalar paquetes de Python desde los índices configurados en tu equipo; revisa las dependencias antes de ejecutarlo. 

**Fuente única de dependencias:** [requirements-mcp.txt](../requirements-mcp.txt). Actualmente fija mcp 1.30.0, resvg_py 0.5.0 y Pillow 13.0.0. Se trata de versiones directas, no de un lock de todas las dependencias transitivas.

## 2. Conectar el servidor en el agente del IDE

Inspeccionar el resultado de la primera prueba:

- Configuración Codex: work/configuracion-local/codex-config.toml.example
- Configuración AntiGravity: work/configuracion-local/antigravity-mcp.json.example

Copiar manualmente el bloque relevante a la configuración MCP que indique el cliente, sin sobreescribir otros servidores. Los ejemplos generados contienen la ruta real de tu .venv, el repositorio y la carpeta privada de entregables; no contienen credenciales ni permisos elevados.

Mantener las herramientas en **modo Ask/confirmación**. Reiniciar el cliente y ejecutar la consulta de estado para comprobar conexión. Las seis herramientas esperadas son:

| MCP | Función |
| --- | --- |
| carpinova_estado | Estado, capacidades y bloqueos |
| carpinova_consultar | Maestro, preguntas de diseño, consulta de libro/herrajes si hay fuentes |
| carpinova_generar_borrador | Cinco archivos nominales desde una solicitud JSON confirmada |
| carpinova_renderizar_lamina | Vistas frontal, lateral y planta en SVG, PNG y PDF desde el CAD original |
| carpinova_exportar_3d | Exportar archivos nativos FreeCAD/Blender solamente con consentimiento y entorno local habilitado |
| carpinova_leer_entregable | Lectura restringida a archivos **textuales** del proyecto; no devuelve PDF binario |

El preflight en Windows dentro de GitHub **no** certifica que el IDE de tu PC ya esté conectado. Requiere la comprobación real en ese equipo. El conector GitHub usado en ChatGPT no inicia servidores MCP locales en tu computadora.

## 3. Diseño de tu primer mueble

Prompt práctico para Codex o AntiGravity:

> Usa Maestro y sus cuatro skills. Necesito diseñar un mueble para cocina o baño. Pregunta por espacio real, ancho/alto/profundidad, instalaciones y obstáculos, tablero/espesor, frentes, cajones, fondo, cantos y veta, apoyo y fijaciones. No inventes medidas ni herrajes. Muéstrame una solicitud JSON y las decisiones pendientes para aprobar. Solo después consulta Maestro, genera un borrador de nombre nuevo, produce tres vistas y entrégame despiece, CAD y bloqueos.

**Flujo correcto:** entrevista → JSON explícito → confirmación humana → consultar → generar borrador → renderizar láminas → revisar. El Agente puede preguntar pero el motor **no** transforma automáticamente cualquier mensaje libre en un diseño final sin datos confirmados.

Cada borrador incluye maestro-review.json, front-review.svg, parts-review.csv, cad-exchange.json y manifest.json. El subdirectorio lamina contiene three-views.svg, three-views.png, three-views.pdf y render-manifest.json.

El SVG es vectorial; el PDF es **rasterizado, de revisión**, y no reemplaza planos profesionales de taller. Las vistas proyectan las mismas cajas CAD nominales y cotas exteriores, no dibujan agujeros, bisagras, uniones físicas ni líneas ocultas resueltas.

## 4. FreeCAD y Blender

FreeCAD y Blender consumen **el mismo** cad-exchange.json, usando sus adaptadores nativos ya existentes. No introducir un segundo cálculo de piezas. La herramienta nativa MCP opcional solo ejecuta adaptadores fijos con ejecutables previamente configurados por el host; no acepta comandos arbitrarios.

1. En FreeCAD instalado en tu PC y con autorización, usar el adaptador integrations/freecad_from_contract.py con el contrato y una nueva ruta .FCStd.
2. En Blender instalado en tu PC, usar integrations/blender_from_contract.py; si quieres un render de presentación, usar integrations/blender_presentation.py para guardar presentation.blend y presentation.png. Ver el [manual nativo](PILOTO_FREECAD_BLENDER.md).
3. Abrir los documentos en las aplicaciones reales; revisar identificación y dimensiones de piezas, orientaciones, acabados, vista y calidad visual. Coincidencia de hash **no** equivale a aprobación de ensamblaje/cargas/corte.

GitHub ya creó .FCStd, .blend y renders nativos con 4 y 13 piezas usando FreeCAD/Blender **Linux**; eso no garantiza compatibilidad de las instalaciones del usuario en Windows. La validación de CAD nativo Windows y de un mueble real continúa pendiente.

## 5. Knowledge y fuentes de carpintería

Para responder sobre técnicas documentadas en el libro, disponer de un bundle Knowledge canónico **validado**, producido fuera del Agente. En los ejemplos MCP, agregar CARPINOVA_KNOWLEDGE_BUNDLE_DIR a las variables del servidor solo después de comprobar integridad y procedencia del bundle. No atribuir una recomendación o medida a una página no leída. Los resultados de búsqueda de libro son candidatos con fuente/página; la pertinencia técnica para el mueble debe revisarse.

El Agente conserva las skills diseño, maestro, selección de herrajes y técnicas constructivas; **no crear una skill adicional** para repetir canto, zócalos, fondos de instalaciones o diseño CAD.

## 6. Estado de las pruebas y puertas de salida

| Comprobación | Estado |
| --- | --- |
| MCP con cliente auténtico, 6 herramientas | GREEN en Linux y Windows CI |
| 456 pruebas Python y dos muebles de ejemplo en Windows | GREEN CI |
| SVG, PNG, PDF, BOM y CADExchange coherentes | GREEN nominal |
| FreeCAD/Blender Linux, archivos editables y PNG | GREEN CI, no QA visual humano |
| Ensayo de integración de 12 PR, árbol idéntico | GREEN sin merge |
| Codex/AntiGravity conectados en tu PC | PENDIENTE |
| FreeCAD/Blender ejecutados en tu Windows | PENDIENTE |
| Uso y citas de Knowledge en PC | PENDIENTE |
| main final tras merges autorizados | PENDIENTE |
| Corte, perforación, herrajes, cargas, anclajes | BLOQUEADO para fabricar |

Evidencias de referencia: [Windows y nativos](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39532122868) y [ensayo de los 12 PR](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39532122902). La evidencia de Actions caduca: preservar archivos clave si se necesitan.

**Leyes CarpiNova:** KISS (una arquitectura, una fuente de medidas), anti-ruido (un instalador/una prueba/una lista de dependencias), anti-parches (reparar origen y añadir regresiones) y no fusionar PR sin autorización. Ninguna prueba de software habilita fabricación.

### Exportación 3D nativa mediante el Agente (desactivada por defecto)

La nueva herramienta MCP `carpinova_exportar_3d(proyecto, confirmacion)` aprovecha los adaptadores existentes. Solo el **operador del host** puede definir `CARPINOVA_FREECADCMD` (ruta absoluta a FreeCADCmd.exe/freecadcmd), `CARPINOVA_BLENDER` (ruta absoluta a blender.exe/blender) y `CARPINOVA_NATIVE_EXECUTION_ENABLED=1`. Después de ver el proyecto revisado y dar autorización específica en el IDE, invocar con `confirmacion="AUTORIZO_EXPORTAR_BORRADOR_3D"`.

Produce en `muebles/<proyecto>/native/` el paquete `native.FCStd`, `native.blend`, `presentation.blend`, `presentation.png`, `native-manifest.json` a partir del **mismo** `cad-exchange.json`; no reescribe el motor ni sobrescribe otro proyecto. Sin habilitación, confirmación, binarios válidos o geometría coherente, no ejecuta ni publica archivos. Nunca permite liberar compras, corte, perforaciones o fabricación. **Ya pasó** la prueba [MCP→FreeCAD/Blender nativo Linux con 4/13 piezas](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39536762720); **aún requiere** aceptación del propietario en Windows.

**Continuidad al cambiar de chat:** consultar [PROJECT_CONTINUITY_CURRENT.md](PROJECT_CONTINUITY_CURRENT.md) y los PR de GitHub, no un snapshot de conversación.

### Evidencia exacta posterior a la exportación MCP→CAD

Commit certificado del circuito completo: `ec139352c83d3d32def9d1421bcf83cf1ca8e2bc`, [Actions #39536762720](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39536762720) 3/3 jobs SUCCESS, 468 pruebas Windows, dos muebles nominales completos 2D y 3D. El job native llama a la **sexta herramienta MCP real**, no a scripts de geometría alternativos. FreeCADCmd Ubuntu utiliza el enlace a `freecadcmd-python3`, validado por su nombre de paquete, no un shell genérico. El propietario debe abrir los modelos y validar visualmente antes de cualquier avance a taller.
