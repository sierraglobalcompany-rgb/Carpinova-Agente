# CarpiNova Agente

Agente especialista en diseño, enseñanza y preparación de fabricación de muebles, integrado con la fuente canónica [CarpiNova-Knowledge](https://github.com/sierraglobalcompany-rgb/CarpiNova-Knowledge).

## Objetivo
Ayudar a diseñar cocinas, clósets, cajones, nichos, escritorios y mobiliario personalizado desde necesidades iniciales hasta entregables verificables: requerimientos, esquema 2D, lista de piezas, dirección de veta, cantos, herrajes, ubicaciones de perforación, compras y procedimiento de ensamblaje.

**Estado:** repositorio de especificación inicial. No existe todavía un motor geométrico de producción, CAD verificado ni recomendador certificado de herrajes. No usar las salidas narrativas como planos liberados a fabricación.

## Arquitectura KISS
1. Agente orquestador e interrogatorio mínimo por proyecto.
2. Skill 'diseño de muebles' para flujo de preguntas, decisiones, validación y entregables.
3. Adaptador de conocimiento de lectura, con citas de libro/página/registro, versión y estado de confianza. La fuente permanece en Knowledge; no copiarla ni modificarla aquí.
4. Motores deterministas futuros: geometría paramétrica, despiece, holguras/cantos, perforación y optimización de tablero.
5. Catálogo de herrajes versionado por fabricante y referencia exacta, no equivalencias implícitas.
6. QA: límites, piezas, colisiones, montaje, orientación de vetas, tolerancias, cargas y validación humana previa a fabricación.

## Fuentes y límites
CarpiNova-Knowledge v1.2.0 describe un libro de 295 páginas físicas, 252 técnicas distribuidas y 43 excluidas. La extracción canónica conserva su procedencia; el libro PDF permanece fuera de Git. Una figura normalizada 2D de presentación NO proporciona dimensiones de fabricación. Ningún RuleSpec distribuido debe tratarse como autoridad ejecutable de fabricación.

La ingeniería de muebles nueva se incorporará mediante reglas explícitas validadas, pruebas y fichas de fabricantes, **nunca inventándola ni atribuyéndola al libro**. Para herrajes no hay distancia universal: consultar ficha exacta de bisagra/corredera, ancho y espesor del material, superposición, luz, carga y configuración.

## Gobierno
- KISS, anti-ruido, anti-parches, fidelidad a fuentes y diseño consistente.
- Separar datos conocidos, supuestos aprobados, recomendaciones, valores por verificar y bloqueos.
- Preguntar únicamente datos necesarios, agrupar preguntas relacionadas sin abrumar.
- Cambios por PR con tests, sin merge automático.
- La salida fabricable requiere geometría, especificación y revisión humana verificadas.

## Primer objetivo de implementación
Leer Knowledge por SHA fijo, diseñar modelo paramétrico de gabinete rectangular y un cajón, generar despiece con test de cierre dimensional y representar vistas 2D con cotas. Sin bibliotecas CAD pesadas hasta que las pruebas lo justifiquen.

Consulta [AGENTS.md](AGENTS.md), [skill de diseño](skills/diseno-muebles/SKILL.md) y [contrato de entrega](docs/contrato-fabricacion.md).

## CarpiNova Maestro — interfaz unificada (F5)
La interfaz F5 coordina en una sola solicitud el cálculo preliminar F1, las preguntas F3, la recuperación con citas F2 y la sugerencia de bisagras F4:
```bash
python -m carpinova_agent.maestro_cli --input examples/maestro-questions.json
python -m carpinova_agent.maestro_cli --input examples/maestro-combined.json --bundle-dir /ruta/al/knowledge-1.2.0 --sketch /tmp/croquis.svg
python -m carpinova_agent.maestro_cli --question "bisagras" --bundle-dir /ruta/al/knowledge-1.2.0
python -m unittest discover -s tests -v
```
El modo pregunta libre es **búsqueda documental**, no una IA generativa. El modo proyecto aún es entrada JSON (más un cuestionario básico por terminal F3). No exporta planos liberados para taller. El workflow `.github/workflows/maestro-ci.yml` genera y verifica Knowledge **completo** con SHA de origen fijo en CI.

Consultar [skill principal](skills/maestro-carpintero/SKILL.md) y [manual de integración](docs/f5-maestro-integracion.md). No fusionar PRs pendientes sin revisión; el estado de la ejecución está en GitHub.

## F6 — ensamble modular y despiece nominal revisable (en rama de desarrollo)
Cocinas y clósets se pueden estructurar como filas de gabinetes abiertos independientes con medidas derivadas del motor F1. Cada panel físico tiene ID, ubicación, material, orientación de veta y bordes a tapacantar expresamente elegidos.
```bash
python -m carpinova_agent.modular_cli --input examples/modular-closet.json --svg /tmp/closet.svg --csv /tmp/piezas-revision.csv
python -m carpinova_agent.maestro_cli --input examples/maestro-modular.json --sketch /tmp/closet-maestro.svg --csv /tmp/piezas-maestro.csv
```
El SVG y CSV son **BORRADORES**, no datos de corte autorizados: no incluyen medidas ajustadas por tapacanto, uniones, puertas, cajones, fondos o anclajes. Para parámetros, limitaciones y ejemplos consultar [F6 módulos/vetas/cantos](docs/f6-modulos-vetas-cantos.md).

## Auditoría V2 / F7A (rama de integración)
Se añadió un asesor consultivo de canto, fondos, patas/zócalo, soportes a pared y uniones, además de un intercambio CAD único en milímetros con adaptadores **opcionales** para FreeCAD y Blender. No hay instalación ni sesión MCP confirmada.
```bash
python -m carpinova_agent.maestro_cli --input examples/construction-bathroom.json
python -m carpinova_agent.cad_cli --input examples/modular-closet.json --output /tmp/closet-cad.json
python -m unittest discover -s tests -v
```
El `/tmp/closet-cad.json` puede abrirse mediante los adaptadores locales tras instalar FreeCAD/Blender por separado. Solo muestra paneles nominales, sin puertas/fondos/cajones/perforaciones. Consulte [auditoría y arquitectura](docs/ARQUITECTURA_V2_AUDITORIA.md), [skill constructiva](skills/tecnicas-constructivas/SKILL.md) y [piloto de ejecución CAD](docs/PILOTO_FREECAD_BLENDER.md).
