# GETAC ERP v1.0.3 — Corrección definitiva del Dashboard

Este hotfix elimina completamente la dependencia de
`resolve_category_names`.

La traducción de categorías se ejecuta directamente dentro del endpoint
`/api/dashboard/summary`, por lo que ya no puede producirse el error:

`NameError: name 'resolve_category_names' is not defined`

## No modifica

- Sincronización histórica
- Sincronización FULL
- Catálogo maestro
- Reabasto
- Excel de envío
- Automatización diaria

## Verificación

Después del despliegue abre:

- `/dashboard`
- `/api/dashboard/summary?days=30`

Ambas rutas deben responder sin error 500.
