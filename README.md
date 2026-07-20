# GETAC ERP v0.8.2 — Corrección de SKU en FULL

Corrige los registros que aparecían como `SIN SKU`.

## Fuentes utilizadas para resolver el SKU

1. `seller_custom_field` de la publicación.
2. `seller_custom_field` de la variación.
3. Atributos `SELLER_SKU`, `SELLER_CUSTOM_FIELD` o `SKU`.
4. Historial de órdenes, relacionado por:
   - Inventory ID
   - Item ID + Variation ID
   - Item ID

## Qué hacer después de instalar

1. Abre `/full`.
2. Presiona `Actualizar stock FULL`.
3. La actualización volverá a recorrer las publicaciones.
4. Los registros existentes se actualizarán usando el mismo `inventory_id`.
5. Los SKU encontrados reemplazarán los valores `SIN SKU`.

No es necesario borrar tablas ni volver a sincronizar las ventas.
