# F7D Tasks 1–3 — Entrada conversacional y aprobación humana en terminal

**Estado:** puente auditable + confirmación interactiva TTY con ejecución de Maestro tras autorización expresa, NO chatbot inteligente ni MCP instalado. Rama F7D derivada del HEAD verde de PR #14. Nada de este módulo autoriza fabricar o fusionar los PR precedentes.

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

Sin `--confirm-execute`, el modo anterior continúa siendo **solo previsualización** y rechaza `--sketch`, `--csv` y `--bundle-dir`.

## F7D Task 2 — confirmación interactiva y ejecución explícita de Maestro

```bash
# 1. Revisar primero la propuesta no confiable (puede provenir de cualquier intérprete):
python -m carpinova_agent.maestro_cli --utterance "Quiero un gabinete de 600 mm" \
  --candidate examples/maestro-questions.json

# 2. Solo el operador humano, EN TERMINAL INTERACTIVA:
python -m carpinova_agent.maestro_cli --utterance "Quiero un gabinete de 600 mm" \
  --candidate examples/maestro-questions.json --confirm-execute
```

El segundo comando exige stdin y stderr conectados a **TTY**, imprime el texto original y **todo el JSON propuesto** y pide escribir `CONFIRMAR <código>` calculado sobre lo mostrado. Respuestas diferentes, EOF, pipelines/no-TTY o ausencia de `--candidate` bloquean la llamada al motor y no escriben archivos de salida. El código corto es solamente un comprobante visual de que se revisa la propuesta exacta, **NO** una firma, autenticación ni permiso de fabricación.

Tras la confirmación, la CLI llama una sola vez a `consult_maestro` con la copia revisada y deja que el **único** motor existente revalide datos, fuentes y bloqueos. El archivo de entrada se lee una sola vez y se protege contra duplicados de claves, JSON no finito y carga excesiva. Si el proveedor externo modifica su archivo después de mostrar la propuesta, la ejecución usa únicamente la instantánea revisada.

Se permiten `--bundle-dir` y `--output` **solo durante ejecución confirmada**, y `--sketch`/`--csv` siguen bloqueados en esta ruta. Para exportaciones de revisión se utiliza el flujo estructurado anterior como segundo paso separado. Ningún flag convierte geometría nominal en planos de taller. La CLI **no** tiene API de LLM ni MCP: el adaptador universal de intérprete es exclusivamente el JSON candidato recibido.

**Límite de autenticidad:** una TTY interactiva no es identidad/autenticación fuerte. Una futura interfaz web/móvil requiere usuario autenticado y control de aprobación propio del cliente; no debe tratar el texto o `confirmed=true` propuesto por un modelo como aprobación humana.

## Pruebas y límites de aceptación

- Tests: `tests/test_f7d_natural_intake.py` (texto solo, propuesta, fidelidad de datos, desconocidos, datos no JSON, no ejecución, CLI).
- Existe un adaptador **opcional** de clasificación con API LLM, pero NO extrae medidas, materiales, herrajes ni cargas, NO almacena historial, NO inicia sesión y NO conecta MCP.
- **F7D Task 2:** el contrato JSON permite candidatos de cualquier intérprete y la CLI tiene revisión/confirmación humana con rechazo no-TTY. No existe aún una interfaz web/móvil ni proveedor LLM conectado.
- **NEXT F7D Task 4:** interfaz de chat autenticada y evaluación separada de MCP FreeCAD/Blender con versiones y permisos fijos. Mantener el único `CADExchange` y las verificaciones nativas.

## F7D Task 3 — intérprete real de intención mediante Responses API (OPCIONAL)

El operador puede elegir enviar **únicamente la frase actual** a la API de OpenAI con consentimiento explícito:

```bash
# El operador configura OPENAI_API_KEY en su entorno; no en Git.
# Requiere modelo compatible con Structured Outputs, seleccionado por el operador.
python -m carpinova_agent.maestro_cli \
  --utterance "Quiero diseñar un gabinete" \
  --interpret-openai --consent-send-text --interpret-model MODELO_COMPATIBLE

# La ejecución posterior de Maestro requiere además --confirm-execute,
# una terminal real TTY y la confirmación exacta de la propuesta completa.
```

**Privacidad, coste y permisos:** esta opción NO está activada por defecto; cada invocación exige `--consent-send-text`, clave `OPENAI_API_KEY` y `--interpret-model`. Envía únicamente el texto del usuario y una instrucción mínima de clasificación a `https://api.openai.com/v1/responses`. No envía PDFs, contenido de Knowledge, datos de proyectos, historial, fotos ni credenciales de API como texto del mensaje. Se utiliza `store=false`, sin herramientas, sin redirecciones, sin reintentos y sin modelo por defecto. La API puede facturar el uso y está sujeta a las políticas del proveedor.

**Alcance y protección:** Structured Outputs solo permite `intent=project|knowledge|unclear` y `project_type` opcional limitado. El servidor comprueba la estructura de la respuesta, que el tipo figure expresamente en el mensaje según los alias F3 existentes y que el texto de una consulta al libro se conserve exactamente. Si hay dos muebles mencionados, no elige arbitrariamente uno: la entrevista solicita aclaración. Nunca extrae dimensiones, espesores, bisagras, perforaciones, carga, materiales ni hace cálculos. No se crea un segundo motor.

**QA:** todas las pruebas usan respuestas simuladas, sin consumo real de API ni secretos. El adaptador está **implementado, no probado contra la API real ni conectado por defecto**. Si el proveedor rechaza una respuesta, devuelve varios mensajes, omite JSON, presenta campos no permitidos o no está disponible, se bloquea sin ejecución. Para una solicitud clara que genere una propuesta, la única puerta hacia Maestro continúa siendo la confirmación humana TTY previa y la validación determinista posterior.

Documentación de protocolo: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). Una futura interfaz web o móvil deberá implementar autenticación real, CSRF/sesiones y permisos; la confirmación TTY **no equivale** a autenticación.
