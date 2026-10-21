# Conexión de CarpiNova-Agente con Codex, AntiGravity y ChatGPT

## Estado verificado y objetivo

El Agente tiene cuatro skills, la base Knowledge como dependencia externa, Maestro como único orquestador, un motor F1/F6/F7C y CADExchange común para FreeCAD/Blender. El piloto de gabinete genera cinco archivos. Antes faltaba la conexión estándar a clientes de agentes.

Este incremento añade un MCP local por **stdio**, con **cinco herramientas** y sin un nuevo motor:

| Herramienta | Resultado |
| --- | --- |
| carpinova_estado | Acciones soportadas, skills y bloqueos |
| carpinova_consultar(solicitud_json) | Preguntas, Knowledge con bundle local, herrajes referenciales o proyecto de Maestro |
| carpinova_generar_borrador(solicitud_json, proyecto) | Carpeta nueva con 5 archivos de revisión nominal |
| carpinova_renderizar_lamina(proyecto) | Plano de tres vistas SVG, PNG y PDF, desde el mismo CADExchange (requiere CairoSVG) |
| carpinova_leer_entregable(proyecto, archivo) | Leer JSON/SVG/CSV/CAD/manifest del proyecto guardado |

Los archivos son: maestro-review.json, front-review.svg, parts-review.csv, cad-exchange.json y manifest.json. El usuario debe confirmar medidas, unidades, materiales, fondo, puertas, soporte, cantos y herrajes antes de considerar el diseño completo. Un CSV nominal no autoriza corte.

### Configuración local de Windows (una vez)

1. Clonar en Windows la rama/commit certificada del PR MCP; abrirla en Codex o AntiGravity.
2. Abrir PowerShell en la raíz del repo: python -m venv .venv
3. Instalar el SDK opcional en ese venv: .\.venv\Scripts\python.exe -m pip install "mcp==1.30.0" "CairoSVG==2.9.1"
4. Correr: .\.venv\Scripts\python.exe -m unittest discover -s tests -v
5. Crear carpeta de entregables privada, por ejemplo C:\CarpiNova\entregables, y no reutilizar nombres de proyecto ya creados.
6. Solo si hay un bundle Knowledge compilado y validado, configurar CARPINOVA_KNOWLEDGE_BUNDLE_DIR apuntando a su carpeta en el PC. No es necesario para el primer módulo sin citas del libro.

Al iniciar el servidor por stdio, NO se verá un menú ni un chat independiente. El cliente MCP es quien negocia el protocolo con el proceso.

### Configuración Codex (config.toml local, NO subir a Git)

    [mcp_servers.carpinova]
    command = "C:\\CarpiNova\\Carpinova-Agente\\.venv\\Scripts\\python.exe"
    args = ["-m", "carpinova_agent.mcp_bridge"]
    startup_timeout_sec = 20
    tool_timeout_sec = 60

    [mcp_servers.carpinova.env]
    PYTHONPATH = "C:\\CarpiNova\\Carpinova-Agente"
    CARPINOVA_OUTPUT_ROOT = "C:\\CarpiNova\\entregables"

Si el usuario quiere el lector del libro, añadir CARPINOVA_KNOWLEDGE_BUNDLE_DIR con ruta del bundle aprobado. Rutas de arriba son **ejemplos**, no rutas detectadas en su PC.

### Configuración AntiGravity IDE

Desde la barra del agente, menú de MCP Servers > Manage > View raw config; actualizar el archivo de configuración del espacio de trabajo (.agents/mcp_config.json) con:

    {
      "mcpServers": {
        "carpinova": {
          "command": "C:\\CarpiNova\\Carpinova-Agente\\.venv\\Scripts\\python.exe",
          "args": ["-m", "carpinova_agent.mcp_bridge"],
          "env": {
            "PYTHONPATH": "C:\\CarpiNova\\Carpinova-Agente",
            "CARPINOVA_OUTPUT_ROOT": "C:\\CarpiNova\\entregables"
          }
        }
      }
    }

Dejar permisos de las herramientas en Ask. Leer AGENTS.md y skills/maestro-carpintero/SKILL.md al iniciar el agente en el IDE. La existencia de una carpeta skills no demuestra que todos los clientes la carguen automáticamente.

### Primera conversación de prueba

"Usa CarpiNova Maestro y sus skills. Quiero hacer un mueble de cocina; antes de diseñar pregunta alto, ancho, profundidad, ubicación, espesor, cantos vistos, fondo/instalaciones, puertas, soportes y herrajes. No supongas datos. Muéstrame para aprobar el JSON. Llama carpinova_consultar para comprobarlo y carpinova_generar_borrador solo con medidas confirmadas. Dame SVG, CSV, CAD JSON, limitaciones y archivos. Nunca declares que está listo para cortar."

Para comprobar la conexión sin datos del usuario, se puede usar exclusivamente examples/pilot-open-kitchen-800.json, gabinete abierto 800x720x550 mm en tablero nominal de 18 mm, cuatro piezas. El resultado no es una recomendación estructural de cocina.

## De boceto a FreeCAD y Blender

1. CarpiNova determina proyecto y módulos desde medidas del usuario y devuelve los cinco archivos con hash de geometría.
2. Abrir `front-review.svg` como boceto frontal y llamar a `carpinova_renderizar_lamina` para obtener `lamina/three-views.svg`, `three-views.png` y `three-views.pdf`; son vistas nominales, no planos de corte.
3. Abrir parts-review.csv para revisar lista de piezas, material, cantos y las limitaciones. No es hoja final de corte.
4. En equipo autorizado con FreeCAD y Blender realmente instalados, reutilizar exactamente cad-exchange.json en integrations/freecad_from_contract.py e integrations/blender_from_contract.py. Guardar .FCStd y .blend y cotejar hash/IDs/piezas. NO hay MCP FreeCAD/Blender interactivo instalado por este PR.
5. FreeCAD `.FCStd` y Blender `.blend` nativos ya se validaron en CI con la geometría original. El render opcional de Blender agrega cámara, luces y colores de referencia, pero no texturas fotorrealistas ni mecanizados. Los planos de fabricación siguen requiriendo ingeniería y taller.

## Conexión directa desde ChatGPT

El conector GitHub disponible en este chat permite inspeccionar/cambiar código, no ejecutar un servidor Python persistente en tu PC. Un MCP local stdio se puede usar desde Codex/AntiGravity en el computador, pero no se conecta automáticamente a este chat. Para integrar ChatGPT se necesita un servidor remoto HTTPS con autenticación, compatible con las capacidades del plan y las políticas de Apps/MCP. No exponer un puerto de tu PC a Internet sin controles; primero probar el camino local.

## Cierre por evidencias

- El cliente descubre cinco herramientas mediante protocolo MCP real.
- Consulta Maestro y genera los cinco archivos a partir del mismo JSON.
- Rechaza rutas arbitrarias y sobrescritura; solo admite proyecto con nombre seguro en carpeta autorizada.
- El croquis y CSV tienen exactamente las piezas del CAD y hash reproducible.
- Las cuatro banderas de fabricación permanecen falsas.
- El operador ejecuta aparte FreeCAD y Blender, compara piezas y revisa visualmente.
- La presentación de tres vistas SVG/PNG/PDF ya está verificada. Los archivos nativos `.FCStd`, `.blend` y render 3D se certifican de forma separada. Falta un mueble real medido en sitio y validación de taller.

Fuentes:
https://developers.openai.com/codex/mcp
https://antigravity.google/docs/mcp
https://github.com/modelcontextprotocol/python-sdk
https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta


## Plano de tres vistas en SVG, PNG y PDF — segundo paso opcional

El **quinto** método `carpinova_renderizar_lamina(proyecto)` utiliza el
`cad-exchange.json` verificado del proyecto ya generado y produce en
`entregables/<proyecto>/lamina/` cuatro archivos: `three-views.svg`,
`three-views.png`, `three-views.pdf` y `render-manifest.json`.
Requiere instalar en el mismo Python `CairoSVG>=2.7,<3` y las bibliotecas
Cairo compatibles con el sistema operativo. Es opcional: si no está instalado,
el diseño SVG frontal, el CSV y el CADExchange anteriores siguen funcionando.

Se muestran FRENTE (X/Y), LATERAL (Z/Y) y PLANTA (X/Z), siempre sobre
las **mismas piezas del CADExchange**, con anotaciones de dimensiones
exteriores y su SHA-256. Las caras se muestran **superpuestas y translúcidas**:
no es un render 3D ni resuelve líneas ocultas, no representa uniones,
calados, tornillos o materiales fotográficos. **No imprimir estas láminas
como instrucciones de corte.**

El cliente MCP lee el archivo vectorial vía `carpinova_leer_entregable`
con `archivo="lamina/three-views.svg"`; para PNG y PDF, la herramienta
devuelve la ubicación local en la carpeta de entregables. En Codex o
AntiGravity se abren desde esa ruta y se pueden adjuntar al chat.
No se puede leer un PDF binario mediante la herramienta de texto ni usar
rutas de terceros. La lámina nunca sobrescribe trabajos anteriores.

Ejemplo de diálogo: “Usa carpinova_generar_borrador para mi proyecto
verificado de mueble, luego carpinova_renderizar_lamina y enséñame
three-views.png y three-views.pdf, conservando el hash del CAD”.


## Entrega 3D nativa certificada (CI — 21-oct-2026)

**Evidencia de [Actions #39529257090](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39529257090), SHA `70fe113de16bb91276ce2179aedd893669ffceda`:** cinco workflows GREEN. El job `native-cad-deliverables` NO crea otra geometría: descarga el artifact producido por el cliente MCP real en el **mismo run**. FreeCADCmd y Blender consumen exactamente el `cad-exchange.json` de cada carpeta y leen las medidas de sus sólidos/mallas reales.

Se certificaron dos muestras del motor existente: `primer_mueble` (4 piezas, FreeCAD error 0 mm, Blender error máximo 0,00002861 mm) y `cocina_dos_modulos` (13 piezas, tres frentes, dos fondos parciales, FreeCAD 0 mm, Blender máximo 0,00011253 mm). El resultado tiene estos archivos **por cada proyecto**:

| Archivo | Función |
| --- | --- |
| `native.FCStd` | Documento FreeCAD editable, paneles geométricos nominales |
| `native.blend` | Escena Blender editable, medidas verificadas |
| `presentation.blend` | Escena Blender editable con cámara, iluminación y materiales ilustrativos |
| `presentation.png` | Render 3D de revisión a 960 × 720 píxeles |
| `freecad-native.log`, `blender-native.log`, `blender-presentation.log` | Evidencias reales y errores de medidas |
| `cad-exchange.json`, `manifest.json`, `lamina/*`, CSV/SVG | Datos de origen y vistas 2D que comparten hash |
| `native-deliverable-summary.json` (raíz) | Resumen de ambos proyectos y hashes verificados |

Descargar en esa ejecución el artifact **`carpinova-mcp-freecad-blender-real`**. El artifact expira según la retención de GitHub Actions; se debe preservar una copia privada si va a utilizarse más adelante. Los archivos proceden del runner de CI: **no** demuestran que FreeCAD, Blender o el MCP estén instalados o conectados en el PC del usuario.

### Uso posterior en Codex/AntiGravity local

1. Conectar el MCP stdio como se explica arriba y obtener `cad-exchange.json` y el manifiesto del mueble con medidas previamente aprobadas. Revisar `geometry_sha256` y `fabrication_ready=false`.
2. Para FreeCAD, en su consola Python local (con este repositorio disponible en el entorno de Python de FreeCAD), ejecutar `integrations.freecad_from_contract.build_freecad(Path(archivo_cad), Path(salida_fcstd))`. Las rutas deben ser absolutas, la salida nueva y el proceso autorizado por el operador. El manual `docs/PILOTO_FREECAD_BLENDER.md` da la entrada técnica.
3. Para Blender, en una terminal autorizada desde la raíz del repositorio, usar el ejecutable instalado en el PC y el script auditado (adaptar rutas reales; no copiar rutas de CI):

```powershell
$env:PYTHONPATH = (Get-Location).Path
& 'RUTA_ABSOLUTA_DEL_EJECUTABLE_BLENDER' --background --factory-startup --disable-autoexec --python-use-system-env --python-exit-code 12 --python integrations/blender_from_contract.py -- --input 'RUTA_ABSOLUTA_CAD_JSON' --output 'RUTA_ABSOLUTA_NATIVE_BLEND'
& 'RUTA_ABSOLUTA_DEL_EJECUTABLE_BLENDER' --background --factory-startup --disable-autoexec --python-use-system-env --python-exit-code 12 --python integrations/blender_presentation.py -- --input-cad 'RUTA_ABSOLUTA_CAD_JSON' --input-blend 'RUTA_ABSOLUTA_NATIVE_BLEND' --output-blend 'RUTA_ABSOLUTA_PRESENTATION_BLEND' --output-png 'RUTA_ABSOLUTA_PRESENTATION_PNG'
```

4. Abrir `.FCStd`, `presentation.blend` y `presentation.png` para revisión. Comparar IDs, cantidad de piezas, orientación, aspecto y el mismo hash con el manifiesto original.

**Límite de confianza:** la herramienta MCP todavía **no lanza programas nativos por sí misma**: un operador o un cliente Codex/AntiGravity con permisos explícitos debe ejecutar los adaptadores. No instalar MCP FreeCAD/Blender de terceros sin auditoría de código, permisos, procedencia, versiones y aislamiento. Un render bonito o una comprobación numérica de 0,05 mm no equivalen a instrucciones seguras de corte, perforación, anclaje o fabricación. Mantener los cuatro flags en falso.


## Certificación pendiente antes de PC — gates obligatorios

La última CI Linux verificó específicamente **MCP 1.30.0 y CairoSVG 2.9.1** (Python 3.12), fijados como dependencias directas para reproducir el ensayo. **No es un lockfile de todas las dependencias indirectas ni una validación de Windows.** Antes de declarar `PC_READY=YES`, verificar la instalación limpia de Windows, arranque y descubrimiento de las cinco herramientas en Codex/AntiGravity, configuración del bundle Knowledge si se van a responder preguntas del libro, lectura de SVG/PNG/PDF reales, apertura de `.FCStd` y `.blend` en los programas locales, una inspección humana de las imágenes y al menos un mueble con dimensiones aportadas y confirmadas. También se debe integrar la cadena de 12 PR con aprobación del propietario y correr QA en el SHA final de `main`. Sin ello no afirmar 100%.


### Una sola prueba de conexión repetible en Linux y Windows

La misma prueba del protocolo (sin duplicar JSON, dibujo ni fórmulas) está en `scripts/verify_local_mcp.py`. Tras instalar Python 3.12, `mcp==1.30.0` y `CairoSVG==2.9.1`, ejecutarla desde la raíz del repositorio:

```powershell
python scripts/verify_local_mcp.py --output-root 'C:\CarpiNova\preflight_nuevo'
```

El destino debe ser una carpeta **nueva y vacía**. La prueba inicia un MCP stdio real, descubre cinco herramientas, genera dos muebles de muestra (4 y 13 piezas), devuelve sus resultados, coteja CAD/SVG/CSV/PNG/PDF, y produce `mcp-preflight-report.json`. **No ejecuta FreeCAD ni Blender**, no consulta el libro si no se configuró su bundle, no envía datos a una API y no significa autorización de producción. Esta misma prueba corre sobre `windows-latest` y Linux en GitHub CI: el resultado real de Windows debe ser GREEN antes de considerarla reproducible allí. El PC del propietario requerirá una prueba adicional en el IDE que use.
