# F7C Task 2 — Frentes de una o dos hojas, sobrepuestos o embutidos

**Estado: DRAFT_NOT_FOR_CUTTING.** Modela hojas rectangulares, vetas, tapacantos solicitados y separación geométrica. No escoge bisagras, calcula cazoletas ni garantiza el giro.

## Decisiones explícitas de la persona
`module.fronts` puede seguir siendo `"none"` / `"pending"` o convertirse en objeto:

- `style: "overlay" | "inset"` — sobrepuesta vs embutida.
- `leaf_count: 1 | 2`; `material_id` y `thickness_mm` reales de la hoja.
- `hinge_sides: ["left"] | ["right"]` para una hoja; `["left","right"]` para dos. Describe intención, **no herraje aprobado**.
- Para `overlay`: `left_reveal_mm`, `right_reveal_mm`, `top_reveal_mm`, `bottom_reveal_mm` declarados en mm (cero permitido); todos menores que espesor estructural para asegurar cierto solape nominal.
- Para `inset`: `left_clearance_mm`, `right_clearance_mm`, `top_clearance_mm`, `bottom_clearance_mm`, todos positivos y explícitos. No inventar una holgura general para puertas.
- `center_gap_mm` requerido y positivo para dos hojas; prohibido para una hoja. La división en dos hojas iguales debe cerrar exactamente en milímetros enteros.
- Opcionales: `grain_axis=face_x|face_y|none`, `edgebanding_edges` como bordes de cara `x_min/x_max/y_min/y_max`, `edgeband_thickness_mm` cuando hay canto. Faltantes = `UNCONFIRMED`, sin defaults silenciosos.

## Fórmulas y ejes

Se conserva la única geometría de carcasa F1→F6. Para `overlay`:

- Ancho total visible = ancho exterior del módulo − revelado izquierdo − revelado derecho.
- Alto = alto exterior − revelado superior − revelado inferior.
- Ancho de cada hoja = (ancho total visible − separación central, si aplica) / número de hojas.
- Origen X = inicio del módulo + revelado izquierdo; Y = revelado inferior; Z = **menos espesor de hoja**, porque se encuentra delante de la carcasa.

Para `inset`:

- Ancho total = **ancho libre F1** − luz izquierda − luz derecha.
- Alto = **alto libre F1** − luz superior − luz inferior.
- Si son dos hojas, restar separación central y dividir por dos; origen X = módulo + espesor carcasa + luz izquierda, origen Y = espesor carcasa + luz inferior, Z = 0.
- Se preserva `face_plane=XY`, `grain_axis` y `piece_id`. La relación física no depende de Blender o FreeCAD.

La capa `CADExchange` traslada **todos** los objetos en Z por un mismo `front_shift_mm` cuando hay puertas sobrepuestas; así el CAD mantiene un origen físico no negativo y los paneles quedan realmente delante del cuerpo, sin modificar F1 ni sus medidas originales. Esta translación se declara y entra en el SHA-256 del contrato. La vista frontal SVG y el CSV leen la misma lista de piezas; el CSV **no** se puede enviar como orden de corte.

## Ejemplo reproducible

`examples/modular-kitchen-door-fronts.json`: cocina de 1200×720×560 mm, dos gabinetes de 600 mm. Primero: fondo parcial con acceso posterior, **dos** puertas sobrepuestas de 295×712 mm, espesor 18 mm, separación de 4 mm y origen de puerta izquierda `[3,4,-18]` en el modelo nominal. Segundo: una puerta embutida de **560×680 mm**, origen `[620,20,0]`. La unión entre módulos no se modifica.

`examples/modular-closet-inset-doors.json`: clóset de 900×1800×550 mm con dos hojas embutidas de **428×1760 mm** y fondo posterior interior. Las cotas dependen estrictamente de los datos explícitos de estos ejemplos, no representan una recomendación estándar.

```bash
python -m unittest discover -s tests -v
python -m carpinova_agent.modular_cli --input examples/modular-kitchen-door-fronts.json --svg /tmp/frentes.svg --csv /tmp/frentes-revision.csv
python -m carpinova_agent.cad_cli --input examples/modular-kitchen-door-fronts.json --output /tmp/frentes-cad.json
```

## QA y límites críticos

1. Prueba de dos hojas, puertas contiguas que toquen o se solapen, holguras no enteras, material/veta/canto inválido, giro sin lado declarado, fórmula y sin modificaciones de datos de origen.
2. CAD con 13 paneles desde una única fuente, validación de cambios SHA y comparación real de cajas con FreeCAD y Blender.
3. **NO** incluye bisagra/placa SKU, cálculo de overlay del herraje, centro de cazoleta, diámetro de broca, perforaciones, plantilla de tornillos, colisión durante el arco de apertura ni carga de puerta. Una separación estática no demuestra que el giro no choque.
4. No genera cajones, tiradores, bisagras o herrajes comprables; no asegura continuidad estética de veta entre dos frentes hasta que la persona confirme material/lote y orientación.
5. `fabrication_ready=false`, `cutting_ready=false`, `drilling_ready=false`, `purchase_ready=false` siempre. **El resultado no es un plano de taller.**

Siguiente incremento: interfaz de selección de bisagras respaldada por **SKU+placa+tablero+distancias aprobadas** y ensayos de giro/colisiones. Después Task 3: cajones integrados (el motor F1 para caja de cajón ya existe, no duplicarlo).
