# F6 — Gabinetes modulares abiertos con veta y canto por pieza

## Estado
Motor preliminar integrado con `CarpiNova Maestro`, **NO PLANOS DE FABRICACIÓN**. Permite organizar una fila de **módulos independientes y rectangulares** destinados a futuro clóset, cocina o estantería. Reutiliza matemáticas de F1 y jamás inventa frentes, fondos, agujeros, soportes o rellenos.

## Contrato
Entrada JSON `type=modular_run`, `application=closet|kitchen|cabinet_run`, ancho/alto/profundidad nominales del conjunto, `installation`, ancho del sitio medido en tres alturas (si está empotrado) y entre uno y doce módulos. Cada módulo requiere:
- `module_id` único, `width_mm`, `material_id`, `panel_thickness_mm`, estructura `sides_full` o `top_bottom_full`.
- `fronts=none|pending`, `back=none|pending` y `support=floor|wall|pending`. Estas declaraciones **no generan** aún frentes, fondo ni tornillería.
- `finish` opcional. Si no existe, veta y canto quedan `UNCONFIRMED`. Si existe, debe declarar para cada `left_side`, `right_side`, `top`, `bottom` su `grain=face_x|face_y|none` y `edgebanding` (lista de lados `x_min,x_max,y_min,y_max`). Si hay cantos, exige espesor del tapacanto en mm.
- Toda pieza física tiene identificador por módulo y rol. Dos gabinetes contiguos tienen **costados propios**; el motor no fusiona paredes compartidas.

## Convención de coordenadas
- X aumenta a la derecha, Y aumenta hacia arriba y Z hacia el fondo.
- Los costados usan cara `YZ`: `face_x` equivale a profundidad física, `face_y` a altura.
- Tapa y base usan cara `XZ`: `face_x` equivale al ancho, `face_y` a profundidad.
- La veta se define sobre ejes de cara, **no** en coordenadas imprecisas de un render.
- Los cantos se definen por los bordes de la cara del panel; su metraje es **nominal**, sin exceso de corte, desperdicio, merma ni ajuste por grosor de tapacanto.
- El campo `finished_cut_dimensions_mm` siempre es `null`: hasta que exista un modelo verificado de espesores finales y bordes, las medidas de cara **NO** son aptas para corte.

## Ejecutar
```bash
python -m unittest discover -s tests -v
python -m carpinova_agent.modular_cli --input examples/modular-closet.json
python -m carpinova_agent.modular_cli --input examples/modular-kitchen.json
python -m carpinova_agent.maestro_cli --input examples/maestro-modular.json
```
La CLI `modular_cli` sale con código 3 si hay bloqueo del espacio/distribución (no es aprobación parcial). El comando Maestro devuelve JSON con `cutting_ready=false`, `fabrication_ready=false`.

## Ejemplo comprobable
El clóset ilustrativo es 2000×2400×600 mm, con dos cuerpos de 950 y 1050 mm, tablero de 18 mm. Si tienen laterales completos y tapas/base entre costados, el primero genera tapas de ancho **914 mm** (950 - 2×18). El segundo está configurado al revés: tapa y base exteriores, laterales interiores de **2364 mm** de alto (2400 - 2×18). No implica que esta distribución sea óptima, estable ni instalable sin supervisión.

## Limitaciones
- El origen nominal de cada panel es un dato de construcción preliminar, sin mecanizado ni compensación de uniones.
- No hay fondo, puertas, cajones interiores, patas, zócalo, sistemas de fijación, tablero compartido ni aparatos de cocina.
- No calcula equipos de agua, gas o electricidad. Para cocinas con servicios hay que revisar medidas e interferencias con una persona competente.
- No optimiza planos de corte; no informa porcentaje de desperdicio ni costo de tableros.
- No se liberan cantidades finales de herrajes/tornillos, perforaciones, capacidades de carga o métodos de fijación.
- Los 12 mm de espacio residual que arroja el ejemplo entre el clóset nominal y la menor medida del hueco no son una recomendación de holgura.
- La figura 2D de F3 solo representa una carcasa individual. El modelo modular F6 **no** dispone aún de su propio SVG o plano completo.

## Próximos incrementos
1. Modelo estructural de fondos/apoyos/puertas con holguras y tolerancias verificadas.
2. Validar cara visible y continuidad de vetas entre frentes.
3. Modelo de corte final (canto, dimensiones acabadas, mecanizados, formato de tablero y grosor de sierra).
4. Vistas frontal/lateral/planta **derivadas exclusivamente** del mismo estado paramétrico.
5. Ejemplo verificado en taller con firma humana, fichas de herrajes exactas y QA de cargas.
6. Reorganizar PRs #1/#2/#4/#6/#7 antes de merge, evitando que F6 arrastre duplicación histórica.

Sin autorización de fabricación hasta validación de producto real y documentación completa. KISS/anti-ruido/anti-parches.

## Exportación de revisión
- `--svg /ruta/archivo.svg` dibuja una elevación frontal proporcional con las coordenadas generadas por F6, no a partir de números copiados a mano.
- `--csv /ruta/archivo.csv` contiene una fila por panel, medidas nominales de cara, ejes, veta, cantos, material, origen y fórmula; cada fila se rotula `BORRADOR_NO_CORTAR`.
- El CLI de Maestro acepta `--sketch` (SVG) y `--csv` con `action=modular`.
- Las funciones de exportación rechazan modelos con distribución incompleta, hueco incompatible o estado falsamente autorizado. El SVG no reemplaza un plano estructural, detalle de junta, lista de bisagras ni optimización de corte.
```bash
python -m carpinova_agent.modular_cli --input examples/modular-closet.json --svg /tmp/closet.svg --csv /tmp/despiece-revision.csv
python -m carpinova_agent.maestro_cli --input examples/maestro-modular.json --sketch /tmp/maestro-modulos.svg --csv /tmp/maestro-desglose.csv
```
