# Editor local CarpiNova H10

El editor local reabre un paquete D19 o una solicitud JSON, permite revisar cambios nominales y guarda cada aplicación como un nuevo D19. La revisión permanece en estado `REVIEW_ONLY`; no libera fabricación, corte, perforación, compra ni instalación.

## Runtime MCP aislado para Windows (H10-M4)

Para preparar únicamente el runtime MCP de este checkout, sin ejecutar el preflight histórico, las suites generales ni modificar la configuración de Codex Desktop:

```powershell
.\scripts\prepare_windows.ps1 -RuntimeOnly -PythonExe "C:\ruta\Python312\python.exe" -AllowDownload
```

`-PythonExe` debe apuntar a Python 3.12. El helper crea y valida un venv bajo `work/mcp-runtime/venv`, instala solo wheels binarias fijadas en `requirements-mcp.txt` y limita la descarga a PyPI oficial cuando se especifica `-AllowDownload`. Para modo desconectado se puede indicar un wheelhouse absoluto con `-Wheelhouse "C:\ruta\wheelhouse"`; si no existe un runtime válido y falta una fuente autorizada de ruedas, la operación queda bloqueada sin instalar paquetes globales. `-AllowDownload`, `-Wheelhouse` y `-PythonExe` se rechazan fuera de `-RuntimeOnly`; este modo también rechaza `-OutputRoot` y retorna antes del preflight ordinario.

El helper guarda `runtime.json`, el registro de instalación y un ejemplo TOML en `work/mcp-runtime/configuracion-local/codex-config.toml.example`; la carpeta local de proyectos es `work/mcp-runtime/projects`. El TOML es una referencia para revisión manual, no una edición ni instalación de la configuración del usuario. La ejecución nativa permanece deshabilitada, no se configura directorio de aprobaciones y la preparación no valida fabricación ni montaje.

En H10-M4 el runtime se preparó con Python 3.12.10 y los pines MCP `1.30.0`, `resvg_py 0.5.0` y `Pillow 13.0.0`. La única llamada stdio del lote generó un D19 de revisión nominal; su respuesta estructurada y el producto se conservaron. El cierre automatizado de fase encontró un defecto en el helper local, por lo que el resultado de transporte se registra como parcial; el producto se auditó offline y no se repitió la llamada. Consulte el informe H10-M4 para resultados y límites.

## Lanzador Windows y descarga del último D19 guardado (H10-M3)

En Windows, ejecute `ABRIR_CARPINOVA.cmd` desde el explorador o una consola. Sin argumentos abre un selector de archivo; con un argumento acepta la ruta de un D19 `.zip` o una solicitud `.json`. El argumento puede contener espacios y caracteres Unicode. Para un ZIP, el valor de sección Y del manifiesto se conserva; para JSON, si falta, el lanzador lo solicita. El editor crea una sesión nueva bajo `work/editor-local` y muestra una dirección loopback temporal. Cierre únicamente esa ventana de consola para detener el servidor.

Desde la raíz del repositorio también puede abrir una fuente explícita:

```powershell
python -m carpinova_agent.editor_launcher --input "C:\ruta\mi proyecto.zip"
python -m carpinova_agent.editor_launcher --input "C:\ruta\solicitud.json" --y-mm 350
```

En el segundo ejemplo, sustituya `350` por la cota de sección ya acordada. `--output-root "C:\ruta\carpeta-existente"` permite elegir una carpeta absoluta existente; `--no-browser` deja la URL en consola sin abrir el navegador. No se instala Python ni se modifica el `PATH`.

En una sesión host conectada, **Descargar proyecto guardado (ZIP)** descarga la última versión persistida, con nombre `editor-vNNNNNN-room-review.zip`. Los cambios pendientes del formulario no se aplican ni se incluyen: primero se requiere la acción explícita **Aplicar cambios y recalcular**. El endpoint requiere el token de la sesión y entrega solo el archivo guardado cuya suma coincide con el estado de la sesión. El HTML extraído del D19 permanece offline: permite inspección y exportar una solicitud JSON, no inicia el host, no recalcula y no valida geometría.

La comprobación H10-M3 usó el D19 H10-M2 de ocho miembros; resultado `REVIEW_ONLY`, 45 piezas, dos perfiles franceses nominales. Los perfiles, fijación, montaje y geometría siguen sin validación física. Esta prueba no autoriza CAD nativo ni fabricación.

## Abrir el último D19 de la prueba H10-M1

Desde la raíz de este checkout, en PowerShell, use una carpeta de salida absoluta que todavía no exista:

```powershell
python -m carpinova_agent.room_editor_local `
  --input "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\QA\M1\RUN_01\HOST\editor-v000004-room-review.zip" `
  --output-dir "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\USER_REVIEW_M1" `
  --y-mm 350
```

El host imprime una URL loopback temporal. Ábrala en el navegador mientras el proceso siga activo. No exponga esa URL ni el token de sesión en redes o registros compartidos. Detenga el host con `Ctrl+C`.

## Revisar y guardar

1. Seleccione un mueble en el visor y revise el estado de fondo, apoyo y fijación.
2. Cambie únicamente campos que el editor habilite. Un cambio visible en el formulario no modifica el modelo hasta seleccionar **Aplicar cambios y recalcular**.
3. Si el host acepta el cambio, abrirá una versión nueva y guardará `editor-vNNNNNN-room-review.zip` bajo la carpeta `editor-vNNNNNN` de `--output-dir`. Use ese ZIP como entrada para continuar en una carpeta de salida nueva.
4. Si el host rechaza una decisión, conserva el último ZIP válido y muestra el motivo. No intente recrear la versión por una duda de captura; verifique primero la carpeta de salida.

El HTML incluido en un D19 se puede consultar sin iniciar el host y permite exportar la solicitud fuente completa tras seleccionar un módulo. Esa descarga es una intención JSON que debe revalidarse en el host; no recalcula geometría por sí sola. Ni los renders ni las reservas conceptuales certifican montaje o herrajes.

## Abrir el D19 francés nominal de H10-M2

El siguiente paquete conserva el borrador con dos perfiles franceses nominales de revisión. Use una carpeta de salida absoluta nueva:

```powershell
python -m carpinova_agent.room_editor_local `
  --input "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\QA\M2\RUN_02\HOST\editor-v000002-room-review.zip" `
  --output-dir "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\USER_REVIEW_M2" `
  --y-mm 350
```

El D19 se abre en `REVIEW_ONLY`. Los perfiles son geometría nominal conceptual; material, encuentro, pared, holguras físicas y montaje siguen sin verificar. La prueba negativa de reserva de 14 mm fue rechazada; no es una dimensión admisible para el perfil de 15 mm. Cambiar el sistema a «Ninguno» elimina los dos perfiles y conserva los 45 tableros. No usar estas opciones para fabricar, cortar, perforar, comprar ni instalar.

### Cierre de seguridad

`fabrication_ready`, `cutting_ready`, `drilling_ready`, `purchase_ready`, `can_generate_f7c` e `install_ready` permanecen falsos. No se modela una autorización física ni se generan patrones de taladro.
