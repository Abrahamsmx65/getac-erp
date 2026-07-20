# GETAC ERP v0.7.1 — Fechas y filtros

Nuevas funciones del dashboard:

- Rango de fechas personalizado
- Atajos de 7, 30, 90 y 365 días
- Buscador por SKU
- Buscador por modelo
- Buscador por nombre de producto
- Filtro por categoría o dominio de Mercado Libre
- Gráficas y métricas recalculadas según los filtros
- Top modelos y top SKUs filtrados

## Uso

En el dashboard:

1. Selecciona `Fechas específicas`
2. Elige fecha inicial y fecha final
3. Escribe un SKU, modelo o nombre si deseas
4. Selecciona una categoría
5. Presiona `Aplicar filtros`

## Nota de categoría

El sistema utiliza `category_id` y `domain_id` cuando Mercado Libre los incluye
dentro de la información de la orden. También permite coincidencias por el título
del producto para categorías descriptivas.
