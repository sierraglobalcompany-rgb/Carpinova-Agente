# F2 — Lector verificable de conocimiento

## Propósito
Permitir búsquedas explicativas sobre contenido del libro **sin** convertir datos pedagógicos en especificaciones automáticas de corte, anclaje o perforación.

El lector consume artefactos publicados por CarpiNova-Knowledge. No incorpora el PDF ni duplica las fuentes en este repositorio.

## Generar bundle completo desde repositorio canónico
En un checkout autenticado/revisado de `sierraglobalcompany-rgb/CarpiNova-Knowledge`:
```bash
uv sync --all-groups
uv run python -m carpinova_knowledge validate --root .
uv run python -m carpinova_knowledge build-book-dist --root . --book-id cpnc-2025 --out work/knowledge-1.2.0
```

Copiar o montar la carpeta de salida como fuente local **sin alterar archivos**. Documentar SHA del commit Knowledge usado para generar el bundle.

En un checkout de Carpinova-Agente:
```bash
python -m knowledge_client --bundle-dir /ruta/a/knowledge-1.2.0 --query "bisagras" --limit 5
```

## Verificaciones fail-closed
- Libro `cpnc-2025` y SHA declarado del PDF canónico, preservado desde manifest.
- Tres hashes SHA-256 exactos del manifiesto sobre bytes locales de los tres bundles.
- Coincidencia entre `book_id`, `schema_version`, `knowledge_version`, listas y contadores.
- ID de página canónico, origen y página PDF de cada registro consultable.
- `FULL_BOOK` solo cuando `scope=BOOK`, versión 1.2.0, 252 páginas distribuidas, 295 fuente y 43 excluidas.
- El PDF original NO se verifica criptográficamente aquí: únicamente se valida la declaración de su hash en el manifiesto.

## Restricciones
- Es un buscador lexical básico sin respuestas conversacionales ni promesa de cobertura semántica.
- Un match de texto no autoriza taladro, herraje, carga ni una regla `EXECUTABLE`.
- El resultado cita `book_id`, `page_id`, página física y página impresa, `content_id` y estado editorial.
- `PARTIAL_CORPUS` se etiqueta explícitamente (como el bundle histórico piloto).
- Falta orquestador conversacional que combine búsquedas y cálculos, y falta QA de consulta humana contra las páginas originales.
- Próximo: integración versionada por SHA y pruebas con artefactos **reales** del libro completo, seguida de experiencia de entrevista para el usuario.
