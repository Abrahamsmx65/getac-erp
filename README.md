# GETAC ERP v0.7.2 — Nombres correctos de categorías

Corrige el filtro de categorías.

Antes mostraba códigos internos como:

- MLM192062
- MLM192717

Ahora consulta el catálogo oficial de categorías de Mercado Libre y muestra
el nombre y la ruta entendible de cada categoría.

Ejemplo:

Calzado › Sandalias y chanclas

Internamente el filtro continúa usando el ID de Mercado Libre, por lo que
los resultados siguen siendo precisos.

## Nueva tabla automática

- category_cache

Guarda los nombres para no consultar Mercado Libre cada vez que se abre el dashboard.
La tabla se crea automáticamente al desplegar.
