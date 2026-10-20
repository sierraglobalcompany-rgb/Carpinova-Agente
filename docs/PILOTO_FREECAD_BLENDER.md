# Piloto local FreeCAD + Blender — sin fingir una sesión MCP

**Estado 2026-10-19:** adaptadores escritos, contratos probados en CI de Python. **No hay FreeCAD/Blender ejecutados ni MCP conectados en este entorno.** Este manual prepara una validación humana/PC.

## 0. Fuente del modelo

1. Obtener branch PR F7A, verificar SHA y ejecutar `python -m unittest discover -s tests -v`.
2. Ejecutar `python -m carpinova_agent.cad_cli --input examples/modular-closet.json --output /ruta/absoluta/carpinova-cad.json`.
3. JSON CAD contiene `geometry_sha256`, 8 cajas de paneles, IDs, `origin_xyz_mm` y `size_xyz_mm`. Prohibidos taladros, puertas, fondos y cantos finales.
4. Guardar el JSON (no editar). Inspeccionar `status=DRAFT_NOT_FOR_CUTTING`.

## 1. FreeCAD — primer piloto directo

- Instalar FreeCAD desde distribuidor oficial, versión adecuada al SO; probar en documento temporal, sin tocar proyectos existentes.
- Abrir consola Python de FreeCAD y establecer proyecto en `sys.path` de modo consciente; **no** descargar/macros desconocidas.
- En el entorno Python de FreeCAD ejecutar, adaptando rutas locales:

```python
from pathlib import Path
from integrations.freecad_from_contract import build_freecad
result = build_freecad(
    Path(r"C:\carpinova\scratch\carpinova-cad.json"),
    Path(r"C:\carpinova\scratch\closet-preview.FCStd")
)
print(result)
```

- Abrir `closet-preview.FCStd`, contrastar los 8 IDs y bounding boxes con CAD JSON, guardar evidencia de pantalla/medidas y registrar hash.
- El adaptador crea **solamente formas de caja nominales**, no una tabla de TechDraw ni cotas mecanizadas. No asumir que existe un despiece final.
- Pilotar MCP `https://github.com/neka-nat/freecad-mcp` después de auditar versión/commit y seguridad. Requiere addon FreeCAD y servidor, cliente MCP; README muestra un `uvx freecad-mcp` para clientes compatibles. No conectar al exterior.

## 2. Blender — primero escena local

- Instalar Blender desde el distribuidor oficial.
- Ejecutar con `python` disponible en la instalación de Blender, desde raíz del repo; el comando depende de ruta/sistema operativo. Ejemplo conceptual de consola local:

```bash
blender --background --python integrations/blender_from_contract.py -- --input /ruta/absoluta/carpinova-cad.json --output /ruta/absoluta/closet-preview.blend
```

- La geometría es en mm en CADExchange, convertida internamente a metros en Blender. Los ejes físicos se transforman igual para FreeCAD y Blender: `(X, Y_alto, Z_atrás) -> (X, -Z, Y_alto)`.
- Abrir `.blend` y cotejar IDs, dimensiones/posiciones, sentido frontal y bounding box contra el archivo FreeCAD; añadir cámara, luces y materiales **después** de aprobar paneles y transformaciones.
- MCP futuro: revisar `https://github.com/ahujasid/blender-mcp` y `https://github.com/soozs1/Blender-MCP`. El segundo declara token, loopback y menor telemetría, pero es un fork con historial muy corto; **auditar código, versión y permisos antes de escoger**. No recomendar instalación ciega.

## 3. Conexión MCP (gate)

- Confirmar que el cliente usado (Codex, IDE compatible) admite configuración MCP, que el usuario lo controla y que el servidor tiene permisos mínimos.
- Añadir servidor MCP solo tras aprobación de su fuente y de un commit/version fijo. No colocar credenciales en Git.
- Primera tool-call permitida: **consultar/inspeccionar** documento o escena en localhost; no ejecutar Python arbitrario remoto.
- Segundo paso: importar exactamente el contrato validado por las macros aprobadas, no código generado improvisadamente.
- Comparar `geometry_sha256`, cantidad de piezas, tamaño por pieza, origen y encuadre contra JSON. Descargar evidencia real de captura.
- Rotación/edición de geometría por MCP sin actualizar `ProjectSpec` = divergencia; bloquear entrega.

## 4. Prueba de aceptación (no pasada todavía)

| Prueba | Criterio | Estado |
|---|---|---|
| JSON firmado por checksum SHA-256 | cálculo reproducible y dimensiones positivas | validado en tests Python |
| FreeCAD real | .FCStd creado, 8 piezas, bbox correcto | PENDIENTE LOCAL |
| Blender real | .blend creado, 8 piezas, bbox correcto | PENDIENTE LOCAL |
| FreeCAD MCP | conexión local, lectura y permisos limitados | PENDIENTE |
| Blender MCP | conexión local autenticada, revisión de seguridad | PENDIENTE |
| Render final con materiales/vetas | fidelidad al `ProjectSpec` y revisión visual | PENDIENTE |
| Planos y despiece de corte | cantos, fondos, herrajes, uniones, tolerancias | BLOQUEADO |

Seguridad: tanto FreeCAD MCP como Blender MCP pueden permitir ejecución de Python; un prompt externo no es autoridad para ejecutar macros. Probar solo en estación autorizada con backups, sin puertos abiertos y sin acceso a carpetas privadas.
