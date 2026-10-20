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

## Catálogo de herrajes (desarrollo F4)
Existe un módulo **referencial** de selección por configuración de puerta, revisado contra documentación Blum. En esta rama:
```bash
python -m hardware --input examples/hinge-overlay.json
python -m unittest discover -s tests -p 'test_hardware.py' -v
```
La salida **nunca** autoriza perforaciones ni compras (`BLOCKED_HARDWARE_SPEC`); no reemplaza la revisión de una ficha actualizada ni valida un sistema bisagra+base. Consulta [skill de selección](skills/seleccion-herrajes/SKILL.md) y [documentación F4](docs/f4-hardware-source-policy.md).

El módulo de herrajes es independiente de F1/F2/F3 mientras se revisan sus PR.

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

### Prueba real de Blender (F7B)
GitHub Actions instaló Blender 4.0.2 en runner Ubuntu y generó `.blend` de 8 paneles, validando bbox real por pieza contra el `CADExchange` sellado. Resultado: `NATIVE_GEOMETRY_MATCH` y máximo error de 0.00012589 mm con tolerancia de verificación de 0.05 mm; [artefacto y log](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39355333219). No significa que exista MCP conectado ni que el mueble pueda fabricarse. La prueba posterior de FreeCAD real también está aprobada, como se documenta abajo.

### Prueba real de FreeCAD (F7B)
Se ejecutó FreeCAD 0.19.2 sin interfaz en GitHub Actions, creó `.FCStd` y midió ocho sólidos `Part::Feature` de la escena real. Verificación `NATIVE_GEOMETRY_MATCH`, **8/8** y `max_abs_error_mm=0.0` con el mismo `geometry_sha256` usado por Blender. [Archivo y evidencia de FreeCAD](https://github.com/sierraglobalcompanyv2/Carpinova-Agente/actions/runs/39356003860) → Artifacts → `f7b-native-freecad-validation`. Aún no hay MCP conectados, verificación humana de escenas ni planos de fabricación listos.

### F7C — fondos de revisión con paso de instalaciones
Se pueden modelar fondos embutidos completos (sin instalaciones) o **dos franjas** con un espacio posterior entre ellas explícitamente dimensionado. Un único proyecto alimenta despiece CSV, elevación SVG y la escena CAD de FreeCAD/Blender. Se trata de un **borrador de paneles nominales**, no de un registro de tubería validado ni de una lista apta para cortar. Véanse [contrato F7C](docs/f7c-fondos-servicios.md) y [ejemplo cocina](examples/modular-kitchen-services.json).

### F7C Task 2 — puertas sobrepuestas y embutidas (borrador)
`module.fronts` ahora admite un frente de 1 o 2 hojas, con `style=overlay|inset`, holguras o revelados explícitos, separación central, material, veta, canto e intención de giro. Los paneles se integran en el mismo modelo que la carcasa/fondos y alimentan CSV/SVG/FreeCAD/Blender desde un solo contrato CAD. La puerta sobrepuesta queda físicamente al frente (Z nominal negativo; CAD incluye translación común `front_shift_mm`). **No** hay cálculo de bisagras, perforaciones ni giros certificados. Ver [contrato Task 2](docs/f7c-frentes-holguras-vetas.md) y [cocina con puertas](examples/modular-kitchen-door-fronts.json).

### F7C Task 3 — cajas de cajón desde F1
`module.drawers` incorpora hasta cuatro cajas por cuerpo, cada una con abertura y holguras de corredera **expresamente suministradas**, cinco paneles calculados por el motor único F1 y frente embutido decorativo opcional. Carcasa, fondo, cajón y fachada comparten IDs, modelo nominal y exportaciones CSV/SVG/FreeCAD/Blender. **No** hay compatibilidad de corredera demostrada, frentes sobrepuestos de cajón, taladros, montaje ni autorización de corte. Véanse [especificación](docs/f7c-cajones-f1-integracion.md) y [ejemplo](examples/modular-two-drawers-inset.json).

### Preguntar al libro mientras se diseña el mueble

El modo Maestro `action=modular` admite opcionalmente `query` (por ejemplo `"bisagras"`) y `--bundle-dir`: produce la geometría del módulo y referencias de Knowledge con **páginas de PDF y libro impreso** en la misma respuesta. La consulta solo recupera registros del bundle canónico previamente validado; sin fuente falla, no atribuye recomendaciones a páginas no encontradas ni selecciona automáticamente herrajes. **No apto para corte/perforación**. [Contrato detallado](docs/f7c-cajones-f1-integracion.md).


La consulta modular opcional también admite un filtro léxico `evidence_topic` para cantos, fondos e instalaciones, tornillos/conectores y soportes. Usa la **misma búsqueda Knowledge**, revisa contexto por registro y muestra máximo cinco referencias con páginas; ninguna se convierte automáticamente en una regla de fabricación. Véase [auditoría temática](docs/f7c-cajones-f1-integracion.md).
