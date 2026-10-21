# Primer mueble piloto — CarpiNova-Agente (F7D Task 5)

**Objetivo:** generar en una sola ejecución un paquete revisable derivado de Maestro y la geometría F1/F6/F7C. No requiere API, credenciales, Blender, FreeCAD, MCP ni web. Es un primer circuito técnico verificable para conectar Codex/otros clientes mediante un adaptador de comandos *de confianza* posterior. No equivale a una conexión directa de este chat ni al diseño liberado para taller.

## Paso 1 — proyecto de demostración

Se incluye `examples/pilot-open-kitchen-800.json`, un gabinete de cocina ABIERTO de **800 mm ancho × 720 mm alto × 550 mm profundidad**, tablero nominal de 18 mm, costados completos, tapa y base entre laterales, apoyo al piso, **sin puertas, sin fondo y sin cajones**. El ejemplo sirve únicamente para probar el motor. **No es una recomendación de diseño para cocina real**: falta comprobar instalación, estabilidad y condiciones del lugar; no decide servicios, cantos o anclajes.

Para un mueble propio se debe copiar el JSON y sustituir **solamente** los datos confirmados por el usuario; si faltan, usar Maestro y sus preguntas. No rellenar medidas para producir resultados.

## Paso 2 — ejecutar sin instalar dependencias de CAD

Desde la raíz de Carpinova-Agente (en la rama PR #15 o posterior aprobada):

```bash
python -m unittest discover -s tests -v
python -m carpinova_agent.pilot_cli \
  --input examples/pilot-open-kitchen-800.json \
  --output-dir scratch/piloto-800
```

El directorio **padre** `scratch` debe existir, y `scratch/piloto-800` NO debe existir previamente. En Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path .\scratch | Out-Null
python -m carpinova_agent.pilot_cli --input .\examples\pilot-open-kitchen-800.json --output-dir .\scratch\piloto-800
```

La salida se prepara completamente en una carpeta temporal y se renombra sin sobrescribir una ejecución anterior. Si Maestro rechaza el proyecto (medidas incompatibles, layout distinto, hueco empotrado sin medir, material inválido), la carpeta final no se genera.

## Paso 3 — qué se obtiene

| Archivo | Contenido |
| --- | --- |
| maestro-review.json | Respuesta Maestro con advertencias y preguntas |
| front-review.svg | Croquis frontal nominal |
| parts-review.csv | Lista de las cuatro piezas físicas sin cotas finales de corte |
| cad-exchange.json | Único contrato geométrico CAD para FreeCAD y Blender |
| manifest.json | SHA-256 de geometría, cantidad de piezas y banderas de seguridad |

El CADExchange es el mismo que consumen los adaptadores nativos existentes (no es un segundo generador). Cualquier visualización posterior debe cotejar cantidad de piezas, IDs y hash. El SVG y el CSV son **BORRADORES**, no el PDF o plano de fabricación. Ni la confirmación humana de un JSON ni un modelo 3D validan por sí solos cantos, cargas, anclajes, mecanizados o corte.

## Paso 4 — usar FreeCAD / Blender en un entorno local autorizado

Si el operador ya tiene los programas instalados y autoriza ejecutarlos, utilice `integrations/freecad_from_contract.py` y `integrations/blender_from_contract.py` con **cad-exchange.json** del paquete y rutas absolutas a un directorio de pruebas. Seguir `docs/PILOTO_FREECAD_BLENDER.md` y su política de aislamiento. No conectar MCP ni ejecutar macros de terceros automáticamente.

## Próximos gates

- Integrar un cliente capaz de invocar explícitamente el comando (Codex/Work/CLI autorizada) y recibir manifest y archivos sin inferir acceso de este chat al PC.
- Desplegar una UI autenticada solo sobre un host con sesiones/CSRF seguros, sin copiar un login casero.
- Probar un mueble real *con medidas tomadas in situ*; discutir terminaciones, cantos, fondos, patas, adhesivos y herrajes.
- Validar físicamente cotas, cargas, estabilidad, uniones, permisos de taller, hoja de corte, tolerancias y seguridad **antes** de emitir planos fabricables.

KISS · anti-ruido · anti-parches · cuatro banderas de fabricación false.
