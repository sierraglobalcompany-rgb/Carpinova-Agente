# F1 — Motor geométrico preliminar

Implementado en `carpinova_agent/core.py`, solo Python estándar, sin dependencia de servicios externos.

## Ejecutar
```bash
python -m unittest discover -s tests -v
python -m carpinova_agent --input examples/cabinet.json
python -m carpinova_agent --input examples/drawer.json --output /tmp/despiece.json
```

## Modos incluidos
- **cabinet/sides_full:** dos laterales completos y tapas/base encajadas entre laterales.
- **cabinet/top_bottom_full:** tapas/base completas y laterales encajados entre ambas.
- **drawer:** costados completos; frente/trasera estructurales entre ellos; fondo aplicado por debajo. No modela frente decorativo, ranura ni guías.

Las dimensiones de los ejemplos son **datos ficticios de prueba geométrica**, no especificaciones recomendadas.

## Contrato actual
- Entrada: JSON completo; valores enteros de milímetros; sin defaults ocultos; campos extra se rechazan.
- Salida: dimensiones, paneles agrupados con cantidad y fórmula, orientación de ejes, verificaciones geométricas, supuestos y bloqueos.
- **Jamás** marca la salida como `RELEASED`; los cantos y la veta quedan `UNCONFIRMED`.
- Aún no compensa espesor de tapacantos ni mecanizados. **No usar las dimensiones de corte directamente en taller.**
- No se calculan bisagras, tornillos, cazoletas, correderas, anclajes ni capacidad de carga.
- Datos del libro: este módulo no importa ni atribuye reglas de fabricación a Knowledge.

## Siguiente tarea
F2: lector de bundles de Knowledge reproducibles y versionados, con citación a página/registro y estado editorial; sin transformar figuras pedagógicas en medidas.

F3: definir fichas reales de fabricantes, sistemas de uniones, tapacantos, confirmación de veta, compensación de mecanizado y pruebas de taller antes de habilitar un estado fabricable.

## QA obligatoria
Auditar cierre de medidas, casos límite, rechazo de datos ambiguos, estabilidad del JSON y prueba de CLI. En todo cambio a geometría, agregar prueba RED antes de implementación GREEN. No merge sin CI exact-head revisada.
