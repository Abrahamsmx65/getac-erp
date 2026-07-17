# GETAC ERP v0.2

Incluye:

- Comprobación real de PostgreSQL: `/health/database`
- Creación automática de tablas
- Inicio OAuth: `/auth/mercadolibre/start`
- Intercambio del código por tokens
- Guardado de la cuenta y tokens en PostgreSQL
- Registro de webhooks en PostgreSQL

## Rutas

- `GET /`
- `GET /health`
- `GET /health/database`
- `GET /auth/mercadolibre`
- `GET /auth/mercadolibre/start`
- `GET /auth/mercadolibre/callback`
- `POST /webhooks/mercadolibre`


## v0.2.1

Corrige el error de FastAPI en la ruta `/auth/mercadolibre/start`.
