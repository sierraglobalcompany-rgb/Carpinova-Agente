# F4 — Catálogo de herrajes con evidencias (módulo autónomo)

## Objetivo
El asistente comienza a distinguir aplicaciones de bisagras Blum; en esta primera implementación **no** hace planos de taladro ni libera compras. Se mantiene independiente de F1/F2/F3 hasta revisar sus PR.

## Verificación de fabricante
Fuente original examinada visualmente: *Perfecting your doors with Blum hinges* (Blum), PDF físico 22 (bisagras) y 23 (bases):
https://d2.blum.com/services/BEC003/bro024_ep_dok_bsg_%24sen_%24aof_%24v1.pdf

- **71B3550**: 110°, CLIP top BLUMOTION, sobrepuesta / overlay.
- **71B3650**: 110°, aplicación dual (dos puertas compartiendo costado).
- **71B3750**: 110°, embutida / inset.
- Bases cruciformes con regulación por excéntrica: **173H7100** (0 mm) y **173H7130** (3 mm). La ilustración de página 23 muestra línea a 37 mm de la parte frontal del costado y distancia entre agujeros de 32 mm. Estas cotas son **solo referencia documental**: no se infiere la cara ni origen completo de mecanizado, ubicación vertical, broca piloto ni compatibilidad final bisagra/base.
- Página oficial de montaje Blum: https://www.blum.com/us/en/products/hingesystems/clip-top-blumotion/assembly/ ; informa profundidad de perforación general de 13 mm de esa familia, pero no asegura que un SKU y espesor concreto puedan taladrarse de ese modo.

El folleto PDF es **histórico**: comprobar la referencia y la ficha vigente del mercado antes de comprar. No convertir una ficha de familia en la validación de un sistema completo de bisagra, placa, frente y tornillos.

## Operación
```bash
python -m unittest discover -s tests -p 'test_hardware.py' -v
python -m hardware --input examples/hinge-overlay.json
python -m hardware --input examples/hinge-inset-missing.json
```

## Contrato de seguridad
- La función `suggest_hinge` ofrece candidato para *overlay / dual / inset*, con fuente y página verificadas.
- Si usuario pide SKU incorrecto para la aplicación, rechaza la correspondencia; si falta configuración no inventa una.
- Una base identificada muestra cotas **referenciales** 37/32, pero `drilling_coordinates=[]`, `drilling_ready=false`, `purchase_ready=false` siempre.
- Bloquea cuando el espesor no supera la profundidad nominal de familia 13 mm; con espesor mayor **no** afirma aptitud para taladrar.
- Nunca calcula cantidad de bisagras, posiciones verticales, perforaciones de cazoleta ni tornillos sin fichas completas y revisión de ingeniería, carga y material.

## Pendiente de certificación
1. Verificar vigencia de **SKU exacto** y documentos técnicos actuales de Blum para país/sistema de montaje.
2. Obtener combinaciones verificadas bisagra/placa con distancias de montaje, superposición del frente, tamaño y carga.
3. Crear coordenadas con origen, cara y eje de la pieza, diámetro y profundidad del taladro, tolerancias y espesor final.
4. Revisar colisiones de apertura, distancia al canto, estabilidad y tornillería.
5. Demostrar QA con una ficha oficial y prototipo real; antes de esto, siempre **NO PERFORAR / NO COMPRAR POR RESULTADO**.

No recopilar SKUs de tiendas ni atribuir patrones de otro fabricante a Blum.
