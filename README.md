# GETAC ERP v0.3

Esta versión agrega la primera sincronización real de ventas de Mercado Libre.

## Nuevas tablas

- `orders`
- `order_items`
- `payments`

## Rutas

- `GET /health/database`
- `POST /sync/mercadolibre/orders?days=30&max_orders=1000`
- `GET /reports/mercadolibre/summary?days=30`
- `GET /docs`

## Ejecutar la primera sincronización

1. Abre `/docs`.
2. Busca `POST /sync/mercadolibre/orders`.
3. Presiona **Try it out**.
4. Usa `days=30` y `max_orders=1000`.
5. Presiona **Execute**.

La aplicación renueva automáticamente el access token cuando sea necesario y guarda el nuevo refresh token.
