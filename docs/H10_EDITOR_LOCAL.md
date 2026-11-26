# Editor local CarpiNova H10

El editor local reabre un paquete D19 o una solicitud JSON, permite revisar cambios nominales y guarda cada aplicación como un nuevo D19. La revisión permanece en estado `REVIEW_ONLY`; no libera fabricación, corte, perforación, compra ni instalación.

## Abrir el último D19 de la prueba H10-M1

Desde la raíz de este checkout, en PowerShell, use una carpeta de salida absoluta que todavía no exista:

```powershell
python -m carpinova_agent.room_editor_local `
  --input "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\QA\M1\RUN_01\HOST\editor-v000004-room-review.zip" `
  --output-dir "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\USER_REVIEW_M1" `
  --y-mm 350
```

El host imprime una URL loopback temporal. Ábrala en el navegador mientras el proceso siga activo. No exponga esa URL ni el token de sesión en redes o registros compartidos. Detenga el host con `Ctrl+C`.

## Revisar y guardar

1. Seleccione un mueble en el visor y revise el estado de fondo, apoyo y fijación.
2. Cambie únicamente campos que el editor habilite. Un cambio visible en el formulario no modifica el modelo hasta seleccionar **Aplicar cambios y recalcular**.
3. Si el host acepta el cambio, abrirá una versión nueva y guardará `editor-vNNNNNN-room-review.zip` bajo la carpeta `editor-vNNNNNN` de `--output-dir`. Use ese ZIP como entrada para continuar en una carpeta de salida nueva.
4. Si el host rechaza una decisión, conserva el último ZIP válido y muestra el motivo. No intente recrear la versión por una duda de captura; verifique primero la carpeta de salida.

El HTML incluido en un D19 se puede consultar sin iniciar el host y permite exportar la solicitud fuente completa tras seleccionar un módulo. Esa descarga es una intención JSON que debe revalidarse en el host; no recalcula geometría por sí sola. Ni los renders ni las reservas conceptuales certifican montaje o herrajes.

## Abrir el D19 francés nominal de H10-M2

El siguiente paquete conserva el borrador con dos perfiles franceses nominales de revisión. Use una carpeta de salida absoluta nueva:

```powershell
python -m carpinova_agent.room_editor_local `
  --input "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\QA\M2\RUN_02\HOST\editor-v000002-room-review.zip" `
  --output-dir "D:\codex\_REPORTES\CarpiNova-Agente\CARPN_H10_M1_M2_V4\USER_REVIEW_M2" `
  --y-mm 350
```

El D19 se abre en `REVIEW_ONLY`. Los perfiles son geometría nominal conceptual; material, encuentro, pared, holguras físicas y montaje siguen sin verificar. La prueba negativa de reserva de 14 mm fue rechazada; no es una dimensión admisible para el perfil de 15 mm. Cambiar el sistema a «Ninguno» elimina los dos perfiles y conserva los 45 tableros. No usar estas opciones para fabricar, cortar, perforar, comprar ni instalar.

### Cierre de seguridad

`fabrication_ready`, `cutting_ready`, `drilling_ready`, `purchase_ready`, `can_generate_f7c` e `install_ready` permanecen falsos. No se modela una autorización física ni se generan patrones de taladro.
