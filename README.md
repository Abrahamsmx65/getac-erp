# GETAC ERP v0.5 — Sincronización masiva

Esta versión elimina el límite artificial de 5,000 órdenes.

## Funcionamiento

- La carga histórica se ejecuta en segundo plano.
- Divide el periodo en bloques de 6 horas.
- Cada bloque se pagina en grupos de 50 órdenes.
- El progreso se guarda en PostgreSQL.
- Si Railway reinicia, el trabajo se retoma desde el último bloque guardado.
- Solo se permite una carga histórica activa al mismo tiempo.

## Iniciar desde el dashboard

Abre:

`/dashboard`

Presiona:

`Sincronizar 365 días`

## Endpoints

- `POST /sync/mercadolibre/historical?days=365`
- `GET /sync/jobs`
- `GET /sync/jobs/{job_id}`
- `POST /sync/jobs/{job_id}/cancel`

## Importante

No cierres ni mantengas abierta una petición larga. El trabajo continúa en Railway aunque cierres la pestaña.
