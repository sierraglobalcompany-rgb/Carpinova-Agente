---
name: kiss-ponytail
description: Ley 1 KISS estricta mediante Ponytail. Aplicar en tareas de programación, bug fixes y refactors; preservar leyes 2 a 6.
---
# Ley 1 KISS + Ponytail — contrato local
Origen: https://github.com/DietrichGebert/ponytail, fuente oficial v5.3.2 commit 09c434ab73ca43761c5d8b0c5d341926c2fba710, licencia MIT. Adaptación del proyecto, NO plugin oficial instalado.

**Primero leer flujo y consumidores:** requisito vigente → entradas → autenticación/permisos y ámbito del proyecto → servicio → persistencia/interfaz → errores y pruebas. No juzgar por líneas aisladas ni borrar consumidores dinámicos sin comprobar.

**Escalera de menor solución completa:** (1) no crear función no solicitada; (2) reutilizar funciones, componentes y contratos del repositorio; (3) biblioteca estándar o capacidad nativa compatible; (4) dependencia ya instalada; (5) expresión simple y legible; (6) mínimo código nuevo suficiente. La solución más corta que incumple un requisito NO cumple KISS.

**Descartar con evidencia:** wrappers vacíos, factories sin necesidad, flags especulativos, helpers duplicados, dependencias para acciones triviales, complejidad y capas innecesarias. Comprobar consumidores estáticos/dinámicos, compatibilidad y pruebas antes de unir o retirar; desconocido no es basura.

**No sacrificar:** contrato aprobado, controles de seguridad, validación, permisos y aislamiento de datos/proyectos, integridad y reversión de datos, casos negativos, acceso humano/accesibilidad y pruebas realmente necesarias. Un bug exige corregir causa raíz y consumidores, no acumular parches. Probar la lógica nueva en ramas, cálculos dimensionales, parser, permisos y persistencia según aplique; una prueba no limita los gates de Ley 5.

**Uso proporcional:** revisión Ponytail de diff/PR solo si aporta valor; auditoría de repo solo si fue solicitada o el riesgo lo exige. Su tope de 20 hallazgos no oculta P0/P1 del procedimiento forense. No invocar hooks ni instalar scripts automáticamente.

**Jerarquía normativa:** esta skill concreta L1 KISS con Ponytail y no redefine L2–L6. La autoridad normativa es [PingPongLaw V2 en el commit fijado](https://github.com/sierraglobalcompany-rgb/PingPongLaw/blob/84e961cadf482d234f4c0ee2ca60e8c7e9b388e8/docs/engineering/LEYES_IMPLEMENTACION_1_A_6.md), cuya lectura debe verificarse; [la adaptación local CarpiNova V1.0](../../../docs/engineering/LEYES_IMPLEMENTACION_1_A_6.md) es complementaria y no la sustituye. `full` es intensidad ordinaria; `ultra` no revoca el contrato del usuario.

**Salida L1:** objetivo, alternativa viable más simple y justificación. Pruebas, riesgos y cambios externos se reportan conforme al canon y a los permisos del usuario.
