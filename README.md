# GETAC ERP v0.8 — Inventario FULL

Incluye una nueva sección:

`/full`

Muestra:

- SKU
- Producto
- Inventory ID
- Stock disponible en FULL
- Stock no disponible
- Ventas de los últimos 30 días
- Promedio diario
- Días estimados de inventario
- Alertas por cobertura baja
- Buscador
- Botón para actualizar stock FULL

## Primera ejecución

Después del despliegue:

1. Abre `/full`
2. Presiona `Actualizar stock FULL`
3. El sistema recorrerá las publicaciones y variaciones de la cuenta
4. Consultará el stock real de cada `inventory_id`
5. Guardará el resultado en PostgreSQL

La primera actualización puede tardar por el número de publicaciones.
Las siguientes consultas del dashboard usan PostgreSQL y son rápidas.

## Tablas automáticas

- `full_inventory`
- `full_sync_runs`
