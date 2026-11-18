# CarpiNova D5 · distribución espacial nominal, zonas de servicio y vista superior

**Desarrollo directo por ChatGPT Director, 17-nov-2026 (hora Colombia).**

## Implementado

- Nuevo `room_layout_v1`: acepta 1–6 especificaciones F6 `module_spec` completas; para cada una invoca `consult_maestro` y luego `cad_exchange`/`validate_exchange`. **Nunca acepta una geometría o SHA suministrado por el cliente** en la ruta pública.
- Colocación en XYZ **enteros en mm**, con rotaciones de vista superior 0/90/180/270 grados (sentido horario en el plano XZ); transforma los paneles CADExchange ya calculados, **sin recalcular espesores, tablas ni herrajes**.
- Identificación global de cada panel (`group_id:piece_id`), hash determinista del layout, AABB de envolventes e intersecciones concretas entre paneles. Los contactos solo de caras no son penetraciones.
- Hasta 12 **reservas geométricas conceptuales** de `plumbing`, `electric`, `appliance` o `access`; si una zona se cruza con un panel o solo está parcialmente dentro de la envolvente, queda `INTERFERENCE_REVIEW_REQUIRED`.
- Vista superior SVG generada desde las mismas coordenadas, solo para revisión.
- Todos los permisos de fabricación/corte/perforación/compra quedan desactivados; no hay habilitación de F7C.

## Integración del endpoint MCP existente

Dentro de `carpinova_agent/mcp_bridge.py`, mantener las seis herramientas MCP y agregar en `carpinova_consultar`:

```python
from .room_spatial import review_room_from_specs

# dentro del dispatch review_kind, antes del fallback P5
if request["review_kind"] == "room_layout_v1":
    return review_room_from_specs(request)
```

El `PATCH/BRIDGE_INTEGRATION.patch` es relativo al PR23 D3 `72c877d` y se aplica también sobre D4 R2 con ajuste focal si ya se introdujo `kitchen_linear_v1`. No sobrescribir el despacho D4.

Ejemplo funcional de estructura de entrada en `fixtures/room-layout-L-example.json`: dos módulos abiertos F6 con orientación a 90°, más reserva de tubería. El archivo es *boceto nominal*, no describe un verdadero mueble de esquina.

## Evidencia local

- Focales: **21 pruebas ejecutadas, 0 fallos, 0 omisiones**, en Python 3.13.5 (entorno de este análisis).
- Datos CAD reales procedentes del ZIP D4 R2, SHA de ZIP `9318ddc93fbef631dc66ebf695ecc314592b35dfc01c47c2ec199c127097a6da`: BAJO 29, ALTO 6 y TORRE 7 piezas. Todas las huellas CADExchange originales se validaron mediante digest canónico y permanecen sin cambios.
- Verificados rotaciones, intersecciones AABB, zonas despejadas/obstruidas/parciales, cambios de SHA, duplicados, entradas inválidas, banderas físicas, vista superior SVG, y ruta pública con **stubs locales** de Maestro y CADExchange. No se ejecutó el repositorio completo ni se probó la conexión real MCP Desktop en este entorno.

## Pendientes que NO deben simularse como terminados

1. **D4 en PR23**: el desarrollo D4 R2 estaba certificado localmente, pero aún no publicado al comenzar D5. La rama D5 independiente puede integrarse después conservando el nuevo despacho D4.
2. **Módulos esquineros reales**: se muestra distribución en L, pero sin geometría de unión/corner, material de relleno ni apertura de puertas.
3. **Servicios reales**: no se modelan perforaciones, cortes para lavamanos, rutas de tubería, ventilación o cargas eléctricas.
4. **Fabricación**: faltan herrajes por referencia/SKU, holguras verificadas, cargas y anclajes, compensación de cantos, planos de taller y validación física.
5. **UAT y CAD nativo**: el Desktop instalado, Knowledge 1.2.0, FreeCAD/Blender y UAT visual del usuario no se alteraron ni validaron con el código D5.
6. **CI**: no ejecutar GitHub Actions mientras no haya cuota. Las 21 focales no sustituyen la suite general de 907 tests de D4 ni una suite integrada del futuro árbol combinado.

## Próximo paso más corto

Integrar el despacho `room_layout_v1` en el mismo `carpinova_consultar`, publicar con `[skip ci]` y rama sin triggers `push` de Actions, correr una única suite local con el árbol combinado D4+D5 cuando haya checkout; después continuar módulos esquineros reales y baños con lavamanos/tuberías.

**Estado:** `PASS_FOCAL_LOCAL` para revisión espacial, `NOT_FULL_REPO_CERTIFIED`, `PRODUCT_COMPLETE=false`, `RELEASE=NO_GO`, `FABRICATION=false`.
