# Conexión de CarpiNova-Agente con Codex, AntiGravity y ChatGPT

## Estado verificado y objetivo

El Agente tiene cuatro skills, la base Knowledge como dependencia externa, Maestro como único orquestador, un motor F1/F6/F7C y CADExchange común para FreeCAD/Blender. El piloto de gabinete genera cinco archivos. Antes faltaba la conexión estándar a clientes de agentes.

Este incremento añade un MCP local por **stdio**, con cuatro herramientas y sin un nuevo motor:

| Herramienta | Resultado |
| --- | --- |
| carpinova_estado | Acciones soportadas, skills y bloqueos |
| carpinova_consultar(solicitud_json) | Preguntas, Knowledge con bundle local, herrajes referenciales o proyecto de Maestro |
| carpinova_generar_borrador(solicitud_json, proyecto) | Carpeta nueva con 5 archivos de revisión nominal |
| carpinova_leer_entregable(proyecto, archivo) | Leer JSON/SVG/CSV/CAD/manifest del proyecto guardado |

Los archivos son: maestro-review.json, front-review.svg, parts-review.csv, cad-exchange.json y manifest.json. El usuario debe confirmar medidas, unidades, materiales, fondo, puertas, soporte, cantos y herrajes antes de considerar el diseño completo. Un CSV nominal no autoriza corte.

### Configuración local de Windows (una vez)

1. Clonar en Windows la rama/commit certificada del PR MCP; abrirla en Codex o AntiGravity.
2. Abrir PowerShell en la raíz del repo: python -m venv .venv
3. Instalar el SDK opcional en ese venv: .\.venv\Scripts\python.exe -m pip install "mcp>=1.27,<2"
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
2. Abrir front-review.svg en navegador: es ya un archivo de imagen **vectorial**; la conversión a PNG para entregas comerciales está pendiente de certificación.
3. Abrir parts-review.csv para revisar lista de piezas, material, cantos y las limitaciones. No es hoja final de corte.
4. En equipo autorizado con FreeCAD y Blender realmente instalados, reutilizar exactamente cad-exchange.json en integrations/freecad_from_contract.py e integrations/blender_from_contract.py. Guardar .FCStd y .blend y cotejar hash/IDs/piezas. NO hay MCP FreeCAD/Blender interactivo instalado por este PR.
5. Vista 3D estética, cámara, iluminación, texturas, láminas explicativas, PDFs de planos y despiece terminado requieren nuevas tareas de **salida**, no un nuevo motor o nuevas skills duplicadas.

## Conexión directa desde ChatGPT

El conector GitHub disponible en este chat permite inspeccionar/cambiar código, no ejecutar un servidor Python persistente en tu PC. Un MCP local stdio se puede usar desde Codex/AntiGravity en el computador, pero no se conecta automáticamente a este chat. Para integrar ChatGPT se necesita un servidor remoto HTTPS con autenticación, compatible con las capacidades del plan y las políticas de Apps/MCP. No exponer un puerto de tu PC a Internet sin controles; primero probar el camino local.

## Cierre por evidencias

- El cliente descubre cuatro herramientas mediante protocolo MCP real.
- Consulta Maestro y genera los cinco archivos a partir del mismo JSON.
- Rechaza rutas arbitrarias y sobrescritura; solo admite proyecto con nombre seguro en carpeta autorizada.
- El croquis y CSV tienen exactamente las piezas del CAD y hash reproducible.
- Las cuatro banderas de fabricación permanecen falsas.
- El operador ejecuta aparte FreeCAD y Blender, compara piezas y revisa visualmente.
- A continuación se implementa presentación de imagen PNG/PDF y validación con el primer mueble real.

Fuentes:
https://developers.openai.com/codex/mcp
https://antigravity.google/docs/mcp
https://github.com/modelcontextprotocol/python-sdk
https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta
