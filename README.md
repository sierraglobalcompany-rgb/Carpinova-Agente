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
