# GETAC ERP v1.1 — Automatizaciones y correo

## Horarios automáticos

Zona horaria: America/Mexico_City

- 1:00 AM — sincroniza las órdenes del día anterior
- 2:00 AM — actualiza inventario FULL
- 3:00 AM — recalcula el envío sugerido, genera Excel y lo envía por correo

## Destinatarios predeterminados

- danidarwish@gmail.com
- abraham.darwish@yapanizcel.com.mx

Se pueden cambiar con:

FULL_REPORT_RECIPIENTS=correo1,correo2

## Variables de correo necesarias en Railway

SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
SMTP_USE_TLS=true

Ejemplo para Gmail:

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=tu_correo@gmail.com
SMTP_PASSWORD=contraseña_de_aplicación
SMTP_FROM=tu_correo@gmail.com
SMTP_USE_TLS=true

Importante: Gmail requiere una contraseña de aplicación, no la contraseña normal.

## Nueva página

/automation

Permite:

- ver horarios
- ejecutar órdenes manualmente
- ejecutar FULL manualmente
- enviar el reporte manualmente
- revisar historial y errores

## Reintentos

Cada automatización reintenta hasta 3 veces, esperando 5 minutos entre intentos.
