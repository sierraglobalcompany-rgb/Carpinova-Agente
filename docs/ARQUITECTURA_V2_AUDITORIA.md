# CarpiNova Agente — Arquitectura V2 y auditoría de consolidación

**Fuente de verdad**: `sierraglobalcompany-rgb/CarpiNova-Knowledge` `4df02ef54562fac5a820cbad92b0edee547c310b` (libro `cpnc-2025`), geometría F1/F6 de `Carpinova-Agente`. No se duplica el PDF ni su extracción.

## Diagnóstico antes de ampliar

1. Existen PR #1, #2, #4, #6, #7, #9 abiertos DRAFT. El código F5/F6 funciona en ramas con **dependencia acumulada**; F5 contiene blobs idénticos de F2/F4 como *test fixture de integración*. Antes del merge se debe limpiar historial y reconciliar deltas. Aumentar ramas sin integrar aumenta deuda de revisión.
2. La búsqueda F2 es léxica. Los registros cubren una distribución de 252 páginas técnicas a partir de un PDF de 295 páginas, pero **no significa** que todas sus ilustraciones o instrucciones sean operables para fabricar. Faltarían pruebas de recuperación de cada tema, estados editoriales, referencias y semántica de imágenes.
3. F6 genera carcasas abiertas y metraje nominal de canto. No sabe determinar automáticamente cara visible, tipo de canto, sistema de pegado, fondos/tuberías, patas, zócalos, listón francés, tornillería o estructura de puertas/cajones.
4. La skill actual enumera intenciones; crear una skill por cada subtema sería ruido. Se justifica **una** skill temática de técnicas constructivas y un único motor consultivo pequeño, no diez motores.
5. FreeCAD y Blender **no están conectados al runtime de esta conversación**. Los MCP de terceros pueden ejecutar Python arbitrario. No debemos informar que fueron instalados, probar renders ficticios ni establecer conexión a una estación del usuario sin autorización.
6. La geometría debe seguir **F1 → F6 → CADExchange**; FreeCAD recibe piezas de ese contrato y Blender las visualiza. Ni FreeCAD ni Blender corrigen medidas por su cuenta o vuelven a calcular el despiece.
7. Ficha actual del fabricante + validación de cargas/anclajes son necesarias para liberar perforación. La resistencia ensayada de un colgador no equivale a resistencia del muro real.
8. Se requiere resolver vocabulario: «banquero» y «pata externa» pueden referirse a elementos distintos según taller. No mapear términos dudosos a un objeto físico sin confirmación.

## Arquitectura objetivo KISS

```text
Consulta humana
  -> Maestro (intención, entrevista <=3 preguntas, sin medidas asumidas)
     -> Knowledge (libro indexado, páginas y revisión; educación)
     -> ConstructionAdvice (alternativas, condiciones, bloqueos)
     -> Hardware (SKU, ficha vigente; autorización pendiente)
     -> ProjectSpec / F1/F6 (ÚNICA geometría)
        -> despiece/veta/canto/CSV/SVG de revisión
        -> CADExchange JSON mm + SHA-256
           -> FreeCAD Python/MCP opcional: documento CAD y planos técnicos
           -> Blender Python/MCP opcional: vista/materiales/render 3D
  -> QA (fichas, medidas, colisiones, soporte, evidencia taller)
  -> aprobación humana -> eventual RELEASED, aún no implementado
```

No se recomienda crear un `freecad-mcp` o `blender-mcp` propietario: la comunidad ya mantiene servidores. Nuestro código debe ser un **adaptador seguro de un contrato neutral**. Dos objetos Blender de medidas distintas a FreeCAD son un BUG, no dos variantes de diseño.

## Matriz de conocimiento del libro y competencias técnicas

El índice del libro canónico indica rangos **impresos** y páginas físicas entre paréntesis:
- Materiales: páginas impresas **60–82** (PDF 82–104). Recabar tableros, espesores, cantos, vetas y superficies.
- Herrajes: **83–123** (PDF 105–145). Recuperación de tipos, usos, nociones de fijación; nunca copiar taladros a producción sin SKU/ficha actual.
- Herramientas: **124–150** (PDF 146–172). Herramientas para taller y domésticas, uso seguro, operaciones.
- Despiece/optimización: **151–210** (PDF 173–232). Despiece, corte, organización de tablas, dibujo, orientación, sobrantes.
- Proyectar mobiliario: **211–250** (PDF 233–272). Proyectos, métodos de montaje y composición.
- Glosario: **255–272** (PDF 277–294). Terminología y sinonimia.
Algunas páginas dentro de esos rangos están explícitamente excluidas de distribución por el canon; no afirmar cobertura uniforme por sección. Metadatos reproducibles en `books/cpnc-2025/index.json`, `distribution.json` y `manifest.json`.

Cada habilidad responde combinando **cita real** (book_id, SHA Knowledge, page_id, content_id, pdf_page, printed_page, review_status) + **decisión ingenieril** y, si hay herraje, fabricante/modelo/versión. Prohibido sustituir una de las tres autoridades por otra.

### Matriz de competencias de experiencia

| Caso | Preguntar | Opciones | Restricción |
| --- | --- | --- | --- |
| Canto flexible/rígido | SKU/material/radio/espesor | comparar usabilidad | términos comerciales no son norma material |
| Canto taller/casa | equipo, adhesivo, preencolado, bordes | taller EVA/PUR o manual compatible | sin tiempo/temperatura inventados |
| Borde visible/oculto | cara visible, humedad, limpieza | canto decorativo, sellado, sin canto | por pieza y borde, no global |
| Fondo en cocina/baño | tuberías, registros, humedad, escuadra | completo, parcial registrable, sin fondo | acceso a servicios; rigidez |
| Patas / base / «banquero» | suelo, limpieza, altura, vocabulario | niveladores, zócalo, apoyo directo | cargas/estabilidad/humedad |
| Suspensión | sustrato, peso/uso, acceso | listón francés, riel/colgadores | muro/anclajes verificados |
| Ensamble sin tornillo visible | espesores, tensiones, desmontaje | tornillos, escuadras, levas/tarugos | prueba de carga y plantilla |
| FreeCAD / Blender | versión local, cliente MCP, autorización | CAD técnico / render | no ejecutar código arbitrario sin revisión |

## MCP — opciones externas y seguridad

**FreeCAD candidato**: `https://github.com/neka-nat/freecad-mcp`, requiere FreeCAD instalado, addon y servidor local MCP. Establecer versión/commit fijo tras inspección de código y probar en entorno desechable.

**Blender candidato**: `https://github.com/soozs1/Blender-MCP` (fork orientado a seguridad de `ahujasid/blender-mcp`); requiere Blender, addon, autenticación y cliente MCP. Revisar personalmente licencia, versión, permisos y evolución del fork; no aceptar automáticamente garantías del README.

- Preferir **servicios locales** enlazados a loopback, sin acceso remoto ni puertos públicos; acceso de archivos a directorio de trabajo acotado, sin archivos personales.
- Desactivar herramientas de ejecutar Python arbitrario cuando sea posible. Si no es posible, aprobación humana de código de adaptador y uso solo en sesión local aislada; no exponer a usuarios finales.
- Deshabilitar por defecto descargas, extensiones y egress de terceros. No instalar servidores de forma automática ni permitir ejecución remota no supervisada.
- El primer pilotaje se puede hacer con `integrations/freecad_from_contract.py` e `integrations/blender_from_contract.py` en la instalación local, **sin MCP**; solo cuando validen dimensiones/ID y salidas, conectar el MCP al mismo contrato.
- Mantener un `geometry_sha256` por solicitud para cotejar los artefactos. Es **checksum reproducible**, no firma criptográfica de identidad o autorización de fabricación.

## Gates de liberación, no negociables

1. GitHub main y PR HEAD exactos, PR funcionales aislados, historia limpia.
2. Knowledge completo validado con todos los metadatos del bundle.
3. Matriz de 20+ consultas reales por dominio, referencias y respuestas correctas auditadas.
4. Pruebas de encolado de los sistemas seleccionados y ficha de canto/adhesivo.
5. Validación de diseño de fondos, servicios, cargas, pared y métodos de unión.
6. F6→CAD mismo hash/IDs/piezas/cotas en FreeCAD y Blender.
7. Visual 3D y dibujo técnico manualmente revisados (no solo la existencia de un archivo).
8. Lista de herramientas, herrajes y tornillos cotejados con referencias actuales.
9. Revisión humana de seguridad, corte, montaje y mantenimiento.
10. Último CI exact-head verde más pruebas físicas documentadas; no fusionar si pendientes.

## Siguiente trabajo con mínima deuda

**F7A (esta rama):** documentación de decisión, asesor consultivo, contrato CAD y dos exportadores locales. CI Python sin afirmar FreeCAD/Blender instalados.
**F7B:** fixtures CAD en PC con FreeCAD y Blender reales, comparación bbox por ID/hash y captura verificable.
**F7C:** validación concreta de fondos y juntas, materiales de canto y soporte con documentación y pruebas de taller.
**F7D:** skill y flujo de preguntas naturales con IA/cliente MCP, sujeto a pruebas y permisos del dueño.
**F7E:** liberación humana de piezas solo tras geometría, cantos, tolerancias, herrajes y carga.

No iniciar una reextracción del libro ni añadir motores de cálculo/retrieval alternativos hasta demostrar que el actual falla una consulta concreta.
