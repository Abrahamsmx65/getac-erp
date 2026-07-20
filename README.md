# GETAC ERP v0.9 — Paquete completo

Incluye en un solo ZIP:

## Dashboard
- Ventas por 7, 30, 90 y 365 días
- Fechas específicas
- Buscador por SKU, modelo o producto
- Filtro por categoría con nombres de Mercado Libre
- Top modelos agrupados
- Variantes separadas por SKU

## Automatización
- Sincronización automática diaria a la 1:00 AM
- Zona horaria: America/Mexico_City
- Descarga las órdenes del día anterior
- Evita duplicados mediante UPSERT
- Reintentos por errores 429 y 5xx
- Página `/automation`
- Botón `Sincronizar ayer ahora`

## Inventario FULL
- Stock real por inventory_id
- Corrección robusta de SKU
- Ventas 7, 14 y 30 días
- Promedio y cobertura
- Recomendación de envío para 30 días
- Excel descargable con cantidades sugeridas

## Rutas principales
- `/dashboard`
- `/full`
- `/automation`
- `/docs`

## Configuración
Mantener en Railway:

SERVICE_ROLE=all

No requiere variables nuevas.
Las tablas nuevas se crean automáticamente al desplegar.
