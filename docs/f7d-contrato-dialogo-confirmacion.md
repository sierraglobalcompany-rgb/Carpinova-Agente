# F7D Task 1 — Entrada conversacional con revisión explícita

**Estado:** primer puente auditable, NO chatbot inteligente ni MCP instalado. Rama F7D derivada del HEAD verde de PR #14. Nada de este módulo autoriza fabricar o fusionar los PR precedentes.

## Problema

Maestro ya dispone de seis acciones estructuradas: `project`, `knowledge`, `hardware`, `combined`, `modular` y `construction`. Un texto libre ("quiero una cocina...") **no** demuestra por sí solo material, espesores, ubicación de instalaciones, medida real del sitio, montaje, SKU o carga. Convertirlo automáticamente en valores JSON o CAD sería una adivinación.

## Contrato mínimo de F7D

`carpinova_agent.natural_intake.preview_natural_request(texto, propuesta=None)`:

1. Si falta una propuesta externa, devuelve `NEEDS_STRUCTURED_PROPOSAL`. No pretende que exista un LLM local o un parser genérico.
2. Si un intérprete externo proporciona una propuesta, valida únicamente el **sobre estructural Maestro** usando `_normalize_request`; comprueba que sea JSON serializable sin conversiones silenciosas, sin NaN y con tamaño limitado. Devuelve `NEEDS_USER_CONFIRMATION` y copia fiel del JSON.
3. En ambos casos `executed_tools=[]`, `source_provenance=[]` y los cuatro flags de liberación permanecen `false`. No ejecuta motor de geometría, Knowledge, herrajes, Blender ni FreeCAD.
4. La UI conversacional muestra el texto original junto a **todos** los campos propuestos, su unidad/interpretación y cualquier dato incierto. Solo tras confirmación explícita **del usuario real**, llama por separado a `consult_maestro(JSON_aprobado)`, que revalida especificación, fuentes y bloqueos.
5. Un campo no declarado no puede viajar como orden: `fabrication_ready`, `cutting_ready`, `authorized_drilling` y similares en el sobre Maestro son rechazados. No confiar en un booleano `confirmed=true` producido por un modelo: la aprobación debe venir del control de la aplicación/usuario.
6. La revisión **no** avala semánticamente las dimensiones propuestas: la UI y el usuario deben cotejar medidas, unidades, módulos y campos. No genera ni solicita un código de autorización criptográfica: eso corresponde al cliente que autentica la sesión, no a un hash de JSON.

## CLI de prueba sin side-effects

```bash
python -m carpinova_agent.maestro_cli --utterance "Quiero diseñar un gabinete"
python -m carpinova_agent.maestro_cli --utterance "Gabinete de 60 cm" \
  --candidate examples/maestro-questions.json --output /tmp/f7d-preview.json
```

En este modo se rechazan `--sketch`, `--csv` y `--bundle-dir`, porque serían señales engañosas de ejecución real. Para ejecutar el proyecto confirmado se sigue usando `--input` con el JSON validado, **en otra acción**.

## Pruebas y límites de aceptación

- Tests: `tests/test_f7d_natural_intake.py` (texto solo, propuesta, fidelidad de datos, desconocidos, datos no JSON, no ejecución, CLI).
- No se incluye LLM, extracción de medidas en lenguaje natural, memoria de conversación, sesiones, credenciales ni servidor MCP.
- **NEXT F7D Task 2:** conectar un intérprete intercambiable y una UI de confirmación real, con evidencia de usuario y pruebas adversariales; no crear un segundo motor geométrico ni extraer Knowledge por fuera del bundle.
- **NEXT F7D Task 3:** evaluar MCP FreeCAD/Blender con fuente/version/permiso fijo en entorno aislado. Mantener el único `CADExchange` y las verificaciones nativas.
