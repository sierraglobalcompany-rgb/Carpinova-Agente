---
name: tecnicas-constructivas
description: Guía con preguntas mínimas sobre cantos flexibles/rígidos, fabricación en taller o en casa, fondos de muebles, patas, zócalos, soportes franceses/rieles y uniones con tornillos o escuadras, sin inventar dimensiones de fabricación.
---

# CarpiNova — Técnicas de fabricación, cantos y montaje

Esta skill **no duplica el libro**: para una consulta pedagógica buscar la página de origen en `knowledge_client`, y para especificaciones de adhesivo/canto/herraje consultar ficha real de fabricante. No convertir figuras normalizadas a cotas físicas.

## Cómo actuar
1. Averiguar aplicación: cocina, baño, clóset u otro. No imponer sistema constructivo por categoría.
2. Canto: preguntar **qué bordes de qué piezas** quedan expuestos/visibles/húmedos, material (PVC, ABS, melamina, chapa), variante comercial flexible/rígida, espesor, marca, si instala taller o usuario, y si viene preencolado.
3. Taller de corte: generar orden legible por `piece_id` y cada borde específico; validar retorno del taller, espesor/aplicación, compatibilidad y acabado. No asumir que la máquina usa un adhesivo concreto.
4. Pegado casero: explicar pasos **solo** para canto preencolado compatible cuando se conozcan ficha y herramientas; hacer prueba en retal; limpieza, presión, enfriamiento, recorte, inspección. Si EVA/PUR hot melt industrial sin equipo o ficha, indicar taller, no inventar temperatura.
5. Fondos: preguntar tuberías, desagüe, gas/electricidad, acceso futuro, humedad y necesidad de escuadra. Permitir completo/parcial con registro/sin fondo, pero no afirmar rigidez estructural ni dibujar perforaciones sin datos.
6. Apoyos: comparar patas ajustables, zócalo/base continua, piso directo, suspensión mediante listón francés o riel + colgadores. Preguntar muro, cargas, fijaciones y estabilidad. **«Banquero» es término ambiguo**: confirmar qué elemento designa en este proyecto.
7. Uniones: explicar tornillos visibles, escuadras internas ocultas o conectores desmontables; consultar fabricante y espesor antes de definir tornillo, cazoleta, piloto, distancias a cantos o capacidad.
8. Elegir la alternativa con razones (facilidad, mantenimiento, humedad, desmontaje, estética, carga), y marcar su evidencia. No dar absolutos del tipo «la cocina nunca lleva fondo» o «todos los cantos ocultos van sin sellar».

## Herramienta disponible
`carpinova_agent.construction_advice.construction_advice(request)` o `consult_maestro({"action":"construction","construction":request})`.
Devuelve máximo tres preguntas por turno, recomendaciones condicionales, referencias oficiales, bloqueos y banderas `fabrication_ready=false`, `cutting_ready=false`, `drilling_ready=false`.

## Salidas diferenciadas
- **Consejo conceptual**: explicación simple y opciones.
- **Diseño preliminar**: geometría desde el modelo canónico F1/F6, veta/cantos en cada pieza.
- **Orden para taller**: solo cuando cliente confirme datos y especificación; la versión de hoy NO genera corte final.
- **Instalación real**: bloqueada si faltan ficha, soporte, cargas, anclajes, accesibilidad y control de humedad.

## Prohibido
Atribuir métodos de pegado a todos los cantos; asumir «flexible=PVC» y «rígido=ABS»; taladrar sin patrón del modelo exacto; fijar muebles a drywall solo por dimensiones de un folleto; fusionar piezas en el render y no en el despiece. Mantener KISS, anti-ruido y anti-parches.

## F7C — fondo posterior calculado cuando el usuario ya tomó la decisión
El asesor conceptual de fondos se conserva; si el usuario quiere materializar la opción, el motor F6 recibe `module.back` de tipo `inset_full` o `inset_two_strips`. Exigir estado real de instalaciones, espesor/material de fondo y medidas explícitas de las dos franjas; no dibujar **agujeros** si faltan ubicación y tamaño reales de las tuberías. La salida siempre conserva dimensiones NOMINALES y flags de fabricación en falso. Ver `docs/f7c-fondos-servicios.md`.

## Puerta sobrepuesta o embutida (F7C Task 2)
Explicar en palabras qué tapa exteriormente un `overlay` y qué queda dentro del hueco un `inset`. Consultar módulo y espesor, material, luces de los cuatro lados, si son 1 o 2 hojas, separación central, veta, tapacanto y mano de apertura; sin completar vacíos con reglas no comprobadas. El modelo detecta interferencias estáticas entre frentes de cuerpos contiguos, **no** el recorrido del giro ni choques con tiradores. Ningún agujero o bisagra se certifica con el libro solo. Más detalles en `docs/f7c-frentes-holguras-vetas.md`.

## Cajones, frente estructural y frente decorativo
Distinguir la caja con laterales, frente y trasera estructurales y fondo inferior aplicado (motor F1) del frente visible. Indicar cuándo un hueco tiene que permitir guías, apertura y limpieza; preguntar fabricante/longitud/capacidad de carga y posición real de la corredera, nunca sugerir un taladro universal. La habilidad acompaña el contrato nominal en `docs/f7c-cajones-f1-integracion.md`, no añade una segunda fórmula ni autoriza fabricación.
