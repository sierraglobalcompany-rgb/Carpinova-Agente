> **Documento histórico de F7B, no instrucción vigente de instalación.** Para el procedimiento único MCP con seis herramientas, exportación 2D/3D y gate de Windows, usar [la guía actual](conectar-agente-codex-antigravity.md) y el [checkpoint maestro](PROJECT_CONTINUITY_CURRENT.md). No instalar por este documento MCP externos sin auditoría.

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
| FreeCAD real (Ubuntu 22.04 CI) | .FCStd creado, 8 piezas, bbox correcto | PASS headless CI #39356003860; revisión humana pendiente |
| Blender real | .blend creado, 8 piezas, bbox correcto | PENDIENTE LOCAL |
| FreeCAD MCP | conexión local, lectura y permisos limitados | PENDIENTE |
| Blender MCP | conexión local autenticada, revisión de seguridad | PENDIENTE |
| Render final con materiales/vetas | fidelidad al `ProjectSpec` y revisión visual | PENDIENTE |
| Planos y despiece de corte | cantos, fondos, herrajes, uniones, tolerancias | BLOQUEADO |

Seguridad: tanto FreeCAD MCP como Blender MCP pueden permitir ejecución de Python; un prompt externo no es autoridad para ejecutar macros. Probar solo en estación autorizada con backups, sin puertos abiertos y sin acceso a carpetas privadas.

## 5. Verificación real de geometría incorporada (F7B)

Los dos adaptadores ahora miden las **cajas ya creadas** en su aplicación, no solo repiten los valores esperados:

- FreeCAD crea objetos independientes `Part::Feature`, obtiene `Shape.BoundBox` de cada sólido, compara origen y tamaño XYZ reales con el mismo CADExchange y **solo después** guarda `.FCStd`.
- Blender mide las ocho esquinas `bound_box` transformadas por `matrix_world` en coordenadas globales, convierte metros a mm, compara pieza por pieza y **solo después** guarda `.blend`.
- Ambas rutas utilizan `integrations.geometry_audit.verify_native_boxes`: rechaza piezas faltantes, duplicadas, fuera de ubicación, mal escaladas o con dimensiones alteradas. La tolerancia por defecto es **0,05 mm**, explícita y solo para cotejo informático; no es tolerancia de fabricación.
- Al completar la ejecución local, cada adaptador retorna `native_measurements.status=NATIVE_GEOMETRY_MATCH`, `geometry_sha256`, cantidad de piezas y máxima desviación. Adjuntar esa salida de consola y capturas de la escena real al checkpoint.
- **Límite:** las 16 pruebas CI añadidas prueban esta comparación con fixtures sintéticos; NO demuestran que FreeCAD o Blender se hayan ejecutado. El gate de apps sigue PENDIENTE hasta disponer de archivos reales, reporte y revisión humana.

Seguridad MCP verificada documentalmente: `neka-nat/freecad-mcp` expone `execute_code` y `execute_code_headless`; el proyecto upstream `ahujasid/mcp-for-blender` tiene `BLENDER_MCP_SAFE_MODE=1` como control optativo, **desactivado por defecto** y que no aísla el socket del addon. Por tanto, no instalar por confianza en el nombre «safe mode»; seguir en aislamiento local con directorios y permisos mínimos y aprobación humana de scripts. Fuentes: https://github.com/neka-nat/freecad-mcp/blob/main/docs/tools.md y https://github.com/ahujasid/mcp-for-blender/blob/main/src/blender_mcp/safe_mode.py .

## 6. Evidencia REAL de Blender en runner aislado (F7B)

GitHub Actions `39355333219` ejecutó **Blender 4.0.2** de los paquetes Ubuntu, con `--background --factory-startup --python-use-system-env --python-exit-code 12`. La instalación del paquete no instaló ni habilitó MCP de terceros. Se construyó `closet-native.blend` de ocho paneles y se midieron sus límites a partir de `matrix_world @ Vector(bound_box)` antes del guardado. Resultado registrado: `NATIVE_GEOMETRY_MATCH`, 8 piezas, desviación absoluta máxima **0.00012589 mm** frente al CADExchange, tolerancia informática 0.05 mm. Contrato SHA-256 geométrico: `0e6b713db071e2c4fdc63fb7b3c63ac93b4ac05f2aa74aadac905860f661af6d`.

Descargar evidencia desde https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39355333219 → Artifacts → `f7b-native-blender-validation`, con `.blend`, contrato CAD y log. **No confundir esta prueba en Linux headless con Blender MCP conectado al PC del propietario, render fotorrealista, diseño completo de clóset ni plano de taller.** Faltan validación humana de la escena/archivo y piloto MCP; FreeCAD real se verificó posteriormente en el apartado 7.

## 7. Evidencia REAL de FreeCAD en runner aislado (F7B)

GitHub Actions [run #39356003860](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39356003860) instaló **FreeCAD 0.19.2** desde Ubuntu 22.04 Jammy (repositorio oficial `universe`) y ejecutó la entrada fija `integrations/freecad_headless_proof.FCScript` con FreeCADCmd (sin MCP). La macro invocó el adaptador aprobado `integrations/freecad_from_contract.py`, creó 8 objetos `Part::Feature`, midió cada `Shape.BoundBox` **desde el sólido real** antes del guardado y generó `closet-native.FCStd`.

Resultado: `NATIVE_GEOMETRY_MATCH`, **8/8 piezas**, desviación `max_abs_error_mm=0.0`, tolerancia de cotejo digital `0.05 mm`; verificación adicional del contenedor ZIP de FreeCAD `FREECAD_FCSTD_REAL=PASS` y sus objetos XML. Misma firma de geometría que Blender: `0e6b713db071e2c4fdc63fb7b3c63ac93b4ac05f2aa74aadac905860f661af6d`.

Artefacto `f7b-native-freecad-validation`: contiene `.FCStd`, `closet-contract.json` y `freecad-proof.log`. Compara con el artefacto Blender: ambas apps comparten ID geométrico y 8 paneles, pero **no** se ha realizado inspección visual humana ni test de uniones/perforaciones. Versiones nativas probadas en CI: FreeCAD 0.19.2 y Blender 4.0.2; validar además versión objetivo de Windows antes de integrar MCP.

## Incidencia de render casi negro — detectada el 21-oct-2026

Se descargaron los cuatro PNG reales del [CI #39674737156](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39674737156): gabinete de 4 piezas, cocina de 13 y cajoneras `inset`/`overlay` de 28. Todos tienen 960×720 píxeles y **solo valores RGB 0 o 1 sobre 255**, prácticamente invisibles. Su archivo PNG, manifiesto y geometría eran válidos, pero eso **no** demostraba calidad de imagen. Por ello se considera **FAIL de presentación**, aunque los workflows anteriores terminaran GREEN.

La corrección propuesta mantiene un único CADExchange y los mismos paneles/cámaras, cambia únicamente la presentación a Blender Workbench con colores por objeto y fondo de estudio, y recarga el PNG final para medir brillo y contraste reales. El adaptador falla cerrado ante fotogramas negros o planos sin contenido visible; las regresiones distinguen el caso 0–1/255 del caso contrastado. La verificación definitiva requiere inspeccionar **los cuatro nuevos renders nativos del CI exact-HEAD**, además de contrastar las pruebas Windows y los estados de fabricación bloqueados. Ningún render sirve para fijar taladros/cortes ni sustituye la revisión visual humana en el PC del propietario.
