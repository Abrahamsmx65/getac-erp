# GETAC ERP Starter

Backend inicial para:

- Mercado Libre OAuth
- Webhook de notificaciones
- PostgreSQL / Supabase
- Railway
- Futuro conector Amazon SP-API

## Rutas iniciales

- `GET /`
- `GET /health`
- `GET /auth/mercadolibre`
- `GET /auth/mercadolibre/callback`
- `POST /webhooks/mercadolibre`

## Despliegue

Railway detectará el `Dockerfile` y ejecutará FastAPI.

## Variables privadas en Railway

Configura posteriormente:

- `DATABASE_URL`
- `MELI_CLIENT_ID`
- `MELI_CLIENT_SECRET`
- `MELI_REDIRECT_URI`
- `MELI_WEBHOOK_URL`

Nunca subas `.env` ni contraseñas a GitHub.
