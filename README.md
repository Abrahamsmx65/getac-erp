# GETAC ERP v0.4 — Dashboard

Incluye un dashboard web compatible con Mac, iPhone y cualquier navegador.

## Dashboard

- `GET /dashboard`

## API del dashboard

- `GET /api/dashboard/summary?days=30`

## Indicadores incluidos

- Ventas acumuladas
- Órdenes
- Unidades
- Ticket promedio
- Ventas del día
- Gráfica diaria
- Estatus de órdenes
- Top 10 SKUs

## Sincronización

- `POST /sync/mercadolibre/orders?days=30&max_orders=1000`

## Nota

Esta versión corrige el cálculo de venta total para evitar duplicar el importe de una orden
cuando contiene más de un artículo.
