# F7C Task 1 — Fondos embutidos nominales, sin perforaciones

## Motivación y límites

Para clósets/cocinas/baños NO existe una respuesta universal de «con o sin fondo»: tuberías, válvulas, tomas, humedad, pared, rigidez y mantenimiento deciden el uso. F7C convierte la decisión explícita en **paneles nominales de geometría comprobable** sin inventar servicios, agujeros o herrajes.

### Opciones válidas en `module.back`

- `"none"`: ningún fondo; sigue pendiente demostrar rigidez y fijaciones.
- `"pending"`: falta la elección; el asistente pregunta, no calcula.
- `{"style":"inset_full",...}`: **un** panel interior de fondo, rectangular, entre cuatro laterales/tapas; rechazado si `services_present=true`.
- `{"style":"inset_two_strips",...}`: **dos** piezas rectangulares (franja superior e inferior); espacio vertical continuo entre ellas. No es un agujero taladrado ni un registro individual de plomería.

Ambas variantes en objeto requieren: `material_id` seguro, `thickness_mm` entero positivo menor que profundidad, `services_present` booleano **expreso**; `grain_axis` opcional `face_x|face_y|none`, de lo contrario `UNCONFIRMED`. Para franjas también requieren `top_strip_height_mm` y `bottom_strip_height_mm` positivos, con suma **menor** que altura interior.

## Geometría única

La carcasa se calcula por F1→F6, sin copiar fórmulas a otro motor. El fondo, como una nueva pieza que el usuario decidió, ocupa el hueco interno según dimensiones **del mismo módulo F6**:

- `ancho_fondo_nominal = ancho_módulo - 2*espesor_costado`.
- `alto_fondo_nominal = alto_módulo - 2*espesor_costado`.
- Plano interior **XY**. Origen `x = inicio_módulo + espesor_costado`, `z = profundidad_módulo - espesor_fondo`.
- Fondo completo: `y = espesor_costado`, altura = alto libre.
- Franjas: inferior `y=espesor_costado`; superior `y=alto_módulo - espesor_costado - alto_franja_superior`.
- Luz libre entre franjas `=alto_libre - alto_franja_inferior - alto_franja_superior`.

Las medidas son **nominales**. No se ha modelado ranura, encastre, holgura de instalación, junta, atornillado ni resistencia. El sistema prohíbe fabricar desde estas dimensiones.

## Ejemplo de cocina con paso de tuberías

`examples/modular-kitchen-services.json`: dos módulos de 600 mm, conjunto 1200 × 720 × 560 mm y tablero 18 mm. Primer módulo `SINK`: franjas posteriores de HDF 6 mm con alturas 120 mm inferior y 90 mm superior; ambas de **564 mm de ancho**. Luz sin panel entre ellas **474 mm**. `back_bottom` parte de `[18,18,554]`, `back_top` de `[18,612,554]` (mm). Segundo módulo `STORAGE` se mantiene sin fondo.

**No se afirma que esa abertura sea suficiente ni esté correctamente situada para las tuberías reales**. Requiere comprobar coordenadas, acceso a llaves, alturas de sifones, pared, humedad y posibles dispositivos de gas/electricidad.

`examples/modular-closet-inset-back.json` valida un cuerpo de 900 × 1800 × 550 mm con fondo nominal 864 × 1764 mm de HDF 6 mm, sin instalaciones declaradas. Se siguen bloqueando tolerancias y fijaciones.

## Herramientas / verificación

```bash
python -m unittest discover -s tests -v
python -m carpinova_agent.modular_cli --input examples/modular-kitchen-services.json --svg /tmp/back.svg --csv /tmp/back.csv
python -m carpinova_agent.cad_cli --input examples/modular-kitchen-services.json --output /tmp/back-cad.json
```

El CSV incluye diez paneles físicos con ID/roles `back_bottom` y `back_top`; el SVG frontal muestra las franjas detrás de la carcasa. CADExchange contiene esas **mismas** diez cajas, con rol/plano y SHA-256; FreeCAD y Blender consumen el mismo contrato.

### Gates

- 24+ pruebas propias de geometría/cambio de panel/acceso inválido, suite total y fuente Knowledge completa.
- CI debe exportar SVG/CSV/JSON y generar `.FCStd` y `.blend` reales de **diez** piezas, comparar bounds medidos en aplicaciones nativas, dejar evidencia descargable.
- **No** registrar dimensiones de corte finales, patrones de bisagra, tornillos, tuberías o mecanizado. `cutting_ready=false`, `drilling_ready=false`, `purchase_ready=false`, `fabrication_ready=false`.
- No ejecutar MCP de terceros ni crear un segundo cálculo geométrico.
- Revisión humana: acceso a instalaciones, estructura de fondo, rigidez de carcasa sin fondo y tratamiento humedad. Prohibido merge automático de PR #11 o este F7C antes de consolidación aprobada.

## NEXT

F7C Task 2 (frentes), luego Task 3 (cajones), con pruebas de interferencia y veta. No añadir puertas/cajones por suposición ni clonar nuevas herramientas de CAD.
