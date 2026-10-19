# Contrato mínimo de paquete de fabricación (propuesta v0)

**Estados**: DRAFT (sin medidas completas), REVIEW (calculado, falta validación), RELEASED (validado con fuente, QA y aprobación humana).

## Entradas requeridas
- Proyecto/unidad mm, ubicación y referencia.
- Dimensiones finales X(ancho),Y(alto),Z(profundidad) y tolerancias de instalación; medidas reales en varios puntos.
- Material: tipo, espesor medido, formato, sentido de veta y tratamiento del canto.
- Construcción: laterales continuos o tapas interiores; fondo, tapa/base, zócalo y uniones.
- Módulos interiores, cargas, frentes/puertas, holguras; bisagras/correderas por fabricante, SKU y ficha revisada.

## Salidas verificables
- Boceto: vistas con ejes, cotas, leyenda, revisión y estatus (no basta render).
- BOM: pieza_id, longitud_mm, ancho_mm, espesor_mm, cantidad, material, cara_visible, veta_eje, cantos_lados, operaciones, origen_de_medida.
- Herrajes: función, modelo exacto, unidades, carga nominal, montaje, fuente/versión de ficha, validación.
- Perforaciones: sistema de coordenadas fijo y origen, cara y eje, diámetro, profundidad, tolerancia y fuente; solo con ficha confirmada.
- Corte: separación entre medidas de corte y medidas acabadas; kerf real, margen de escuadra, veta, rotación permitida, optimización/merma.
- Montaje: pasos, herramientas, secuencia, control de calidad y seguridad.
- Auditoría: cierre de dimensión, espesor, colisiones/aperturas, holguras, estabilidades y bloqueo ante incógnitas.

## Prohibiciones
Nunca convertir geometría normalizada de reconstrucciones pedagógicas en medidas físicas; nunca atribuir medidas nuevas al libro. No imprimir 'apto para fabricar' ante faltantes críticos. Toda regla nueva exige pruebas reproducibles y trazabilidad.
