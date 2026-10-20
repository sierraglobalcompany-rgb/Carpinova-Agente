# F7D Task 4 — puerta de revisión para una futura interfaz autenticada

**Estado: biblioteca Python con pruebas; NO existe todavía una interfaz web desplegada, inicio de sesión, controlador HTTP ni proveedor de identidad propio.** Trabajo exclusivo de Carpinova-Agente PR #15 (DRAFT).

## Contrato KISS

Se reutilizan preview_natural_request y consult_maestro; no se crea otro motor de geometría, lector de Knowledge ni catálogo de herrajes. carpinova_agent.web_review.ReviewGate almacena una propuesta temporal y tras una confirmación devuelve la misma instantánea JSON. La biblioteca no ejecuta Maestro, LLM, FreeCAD, Blender ni ningún MCP.

**El servidor anfitrión tiene que proporcionar** authenticated_identity(request_context), un callback confiable que devuelva una pareja (usuario_autenticado, id_sesion_servidor) obtenida de su middleware de autenticación. No aceptar ID, identidad o sesión enviados directamente por el navegador, un formulario, un parámetro URL, el texto del LLM o una cabecera sin validar.

## Flujo de la futura UI

1. El HOST verifica autenticación, permisos, seguridad de cookies, origen y CSRF. Si no dispone de esas garantías, no debe exponer estos métodos como rutas HTTP.
2. El backend invoca gate.stage(contexto_verificado, texto_original, propuesta_no_confiable). Devuelve texto original, todos los campos propuestos, fingerprint, review_id y confirmation_challenge. Mostrar todos los valores para cotejar medidas/unidades.
3. El usuario realiza un clic **deliberado** de aprobación en la aplicación autenticada. Ni el modelo ni el JSON candidato pueden simular ese evento. El host comprueba de nuevo sesión, origen, CSRF y permisos.
4. El backend llama gate.consume(contexto_verificado, review_id=..., confirmation_challenge=..., fingerprint=...). Si hay sesión distinta, caducidad, cambio o reutilización, falla. Consume atómicamente el ticket y devuelve approved_request; **no ejecuta** herramientas.
5. Solo entonces el host puede llamar **por separado** a consult_maestro(approved_request), que revalida y conserva fabrication_ready/cutting_ready/drilling_ready/purchase_ready en falso.
6. gate.cancel(...) revoca una propuesta dentro de la misma sesión.

## Seguridad y límites

- Ticket aleatorio, nonce aleatorio, TTL predeterminado de 600 segundos, huella SHA-256 y bloqueo por RLock: una confirmación concurrente tiene un solo ganador. El fingerprint **no es firma, autenticación ni licencia para fabricar**.
- review_id y confirmation_challenge deben mantenerse fuera de URLs y logs; son secretos de capacidad. La aplicación necesita además CSRF, TLS, same-origin, autorización, limitación de solicitudes y una política de revocación de sesión.
- La implementación usa un diccionario **solo en memoria de un proceso**. Para producción con varios workers o reinicios se requiere almacenamiento compartido con TTL y consumo atómico; no declarar esta versión apta para desplegar.
- Los tests usan identidad simulada. No se ha validado un login real ni una interfaz accesible en navegador. No se instala MCP ni se consulta API externa en estas pruebas.
- La aprobación de JSON no certifica espesor real, cantos, rigidez, cargas, anclajes, taladros, compra ni corte. Los cuatro bloqueos siguen activos.

## QA y NEXT

Pruebas: tests/test_web_review.py — aislamiento de usuario/sesión, caducidad, replay, cancelación, nonce/huella, integridad de la copia, capacidad, doble clic concurrente y llamada posterior al único Maestro.

**NEXT F7D Task 5:** integrar en un host con identidad/CSRF reales una UI móvil accesible, probarla con navegador autenticado, y únicamente después estudiar servidores MCP FreeCAD/Blender en un entorno aislado con versiones, permisos y fuentes verificados.