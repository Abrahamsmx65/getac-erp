# GETAC ERP v1.0 — Envíos Mercado Libre FULL

Esta versión se enfoca únicamente en dejar estable el flujo de envíos a FULL.

## Catálogo maestro

Nueva tabla:

- `product_catalog`

Guarda por variante:

- Item ID
- Variation ID
- Inventory ID
- SKU
- Modelo
- Color
- Talla
- Título
- Categoría
- Estado

## Flujo recomendado

1. Abrir `/full`
2. Presionar `Actualizar catálogo`
3. Presionar `Actualizar / reiniciar stock FULL`
4. Revisar ventas y cobertura
5. Descargar el Excel de envío sugerido

## Reabasto

Para cada SKU calcula:

- Ventas 7 días
- Ventas 14 días
- Ventas 30 días
- Proyección mensual por ritmo reciente
- Objetivo de stock para 30 días
- Stock FULL disponible
- Cobertura estimada
- Cantidad sugerida a enviar
- Prioridad:
  - CRITICO
  - ALTO
  - MEDIO
  - OK

## Excel

El archivo incluye:

- SKU
- Producto
- Inventory ID
- Item ID
- Variation ID
- Stock FULL
- Ventas 7, 14 y 30 días
- Proyecciones
- Objetivo 30 días
- Cobertura
- Cantidad sugerida
- Prioridad

## Automatización

Mantiene:

- sincronización diaria a la 1:00 AM
- manejo de errores 429
- detección de procesos interrumpidos
- reinicio seguro de la actualización FULL

## Diagnóstico

- `/api/catalog/diagnostics`
- `/api/full/sku-diagnostics`
