---
name: seleccion-herrajes
description: Selección fundamentada de bisagras, correderas, tornillos y bases para muebles; pregunta por tipo de puerta, SKU exacto, carga, tablero y ficha oficial, bloqueando taladros sin datos completos.
---

# CarpiNova — Selección segura de herrajes

## Activación
Usar si la persona pregunta qué bisagra/corredera/tornillo comprar, qué cazoleta necesita, cómo perforar, distancia de orificios, cuánto cubre una puerta, si el cajón lleva guías, dónde instalar bases, o cómo elegir herrajes para cocinas y clósets.

## Método de consulta
1. Precisar qué se mueve (puerta/cajón), el uso y la configuración: sobrepuesto `overlay`, compartido `dual` o embutido `inset`. No traducir informalmente `pata externa` a una de estas configuraciones sin preguntar.
2. Pedir medidas **reales** del frente y tablero: alto, ancho, espesor, material, peso estimado o medido y carga de trabajo. Evaluar interferencias con cajones interiores y puertas vecinas.
3. Definir fabricante, familia y **SKU exacto**; distinguir una recomendación conceptual de una referencia vigente disponible en el mercado.
4. Consultar solamente las fichas **primarias oficiales** del SKU y base; anotar edición, fuente, página, modelo, tipo de fijación, superposición, apertura, restricciones y condiciones de instalación.
5. Si se habla de bisagras Blum CLIP top BLUMOTION 110°, ejecutar `hardware.catalog.suggest_hinge()` sobre solicitud estructurada, o `python -m hardware --input ejemplos.json`. Devuelve solo **candidatos referenciales** en versión actual.
6. Si la pregunta incluye tornillería o taladros, comprobar un sistema completo aprobado: bisagra+placa, cazoleta, posición, espesor, distancia, profundidad, broca, tornillo, resistencia y tolerancia. **Si falta algo: BLOQUEAR, no completar con práctica general.**
7. Recomendación de compra: proporcionar la cantidad únicamente con tabla de carga/alto/peso del fabricante y compatibilidad comprobada. En caso contrario, explicar cómo consultar la ficha y mostrar las variables faltantes.

## Ejemplo de conocimiento ya validado de forma documental
- Blum `71B3550`: candidata a puerta sobrepuesta.
- Blum `71B3650`: candidata para dos frentes compartiendo costado.
- Blum `71B3750`: candidata a puerta embutida.
- Las placas `173H7100` y `173H7130` aparecen con cotas 37/32 en folleto oficial histórico, **no son plantilla completa ni combinación certificada con cualquiera de las tres bisagras**.
- Folleto *Perfecting your doors with Blum hinges*: https://d2.blum.com/services/BEC003/bro024_ep_dok_bsg_%24sen_%24aof_%24v1.pdf, páginas físicas 22 y 23. Verificar ficha actual antes de comprar.

## Salida obligatoria
Mostrar tipo de mueble, configuración de frente, candidatura de marca/modelo, documentos, datos confirmados, preguntas pendientes, compatibilidad por validar y estado. Usar siempre `BLOCKED_HARDWARE_SPEC` si falta documento o coordenada de perforación. Nunca producir `drilling_coordinates` no respaldadas, nunca decir `listo para taladrar` o `listo para comprar` en este MVP.

## Condiciones de detención
Sin ficha oficial exacta, combinación real con base, taladro especificado, profundidad mínima segura, anclajes suficientes, condiciones de carga o revisión competente, detener la autorización. Material del libro CarpiNova es pedagógico, no reemplaza ficha técnica del fabricante.

## Gobierno
KISS; anti-ruido (no duplicar fichas; enlace a fuente); anti-parches; solo cambios probados en PR sin mezclar el ERP o extraer otra vez el libro.
