# GETAC ERP v0.9.1 — Corrección de actualización FULL y SKU

## Problema corregido 1: actualización detenida

Cuando Railway despliega una versión nueva, las tareas en memoria terminan.
La base de datos podía quedarse mostrando `RUNNING` para siempre.

Ahora:

- Las ejecuciones interrumpidas se marcan `INTERRUPTED`.
- El botón `Actualizar / reiniciar stock FULL` crea una ejecución nueva.
- El endpoint de estado valida que exista una tarea real.
- Al arrancar el servidor se limpian ejecuciones antiguas atascadas.

## Problema corregido 2: solo aparecían SKU de GT110

La relación estaba intentando leer item_id y variation_id desde el JSON.
Ahora usa directamente:

- `order_items.external_item_id`
- `order_items.variation_id`
- `order_items.seller_sku`

También evita usar un SKU genérico del item cuando el mismo item tiene
varias variantes, para no asignar el SKU de una talla a todas las demás.

## Después de instalar

1. Espera a que Railway quede Online.
2. Abre `/full`.
3. Presiona `Actualizar / reiniciar stock FULL`.
4. La ejecución anterior en 600 se marcará como interrumpida.
5. Se iniciará una actualización nueva con el cruce de SKU corregido.

## Diagnóstico

La ruta `/api/full/sku-diagnostics` muestra:

- inventarios totales
- inventarios con SKU
- inventarios sin SKU
- modelos distintos encontrados
