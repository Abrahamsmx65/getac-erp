# GETAC ERP v1.2 — Corrección de variantes sin SKU

## Nueva sección

`/sku-pending`

## Reparación automática

Consulta cada publicación y variación con:

- `include_attributes=all`
- atributo `SELLER_SKU`
- detalle individual de la variación

Cuando encuentra el SKU actualiza:

- `product_catalog`
- `full_inventory`
- `order_items` históricos del mismo item y variation_id

## Corrección manual

Los registros que Mercado Libre no devuelve con SKU permanecen en la tabla
de pendientes.

Se muestra:

- Producto
- Item ID
- Variation ID
- Inventory ID
- Color/talla u otros atributos

Solo se escribe el SKU correcto y se presiona Guardar.

## Flujo

1. Abrir `/sku-pending`
2. Presionar `Buscar SKUs automáticamente`
3. Esperar `SUCCESS`
4. Completar manualmente únicamente los restantes
5. Actualizar stock FULL
