import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(
    title="GETAC ERP API",
    version="0.1.0",
    description="Backend para sincronizar Mercado Libre y Amazon con PostgreSQL.",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "GETAC ERP API",
        "status": "online",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/auth/mercadolibre")
async def mercadolibre_auth() -> JSONResponse:
    client_id = os.getenv("MELI_CLIENT_ID")
    redirect_uri = os.getenv("MELI_REDIRECT_URI")

    if not client_id or not redirect_uri:
        return JSONResponse(
            status_code=500,
            content={
                "error": "missing_configuration",
                "detail": "Faltan MELI_CLIENT_ID o MELI_REDIRECT_URI.",
            },
        )

    auth_url = (
        "https://auth.mercadolibre.com.mx/authorization"
        f"?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"
    )

    return JSONResponse(
        content={
            "authorization_url": auth_url,
        }
    )


@app.get("/auth/mercadolibre/callback")
async def mercadolibre_callback(code: str | None = None) -> JSONResponse:
    if not code:
        return JSONResponse(
            status_code=400,
            content={
                "error": "missing_code",
                "detail": "Mercado Libre no envió el código de autorización.",
            },
        )

    # En el siguiente módulo intercambiaremos este código por access_token
    # y refresh_token, y los guardaremos cifrados en PostgreSQL.
    return JSONResponse(
        content={
            "status": "authorization_code_received",
            "code_received": True,
        }
    )


@app.post("/webhooks/mercadolibre")
async def mercadolibre_webhook(request: Request) -> JSONResponse:
    try:
        payload: Any = await request.json()
    except Exception:
        payload = {}

    # Por ahora confirmamos recepción rápidamente.
    # En el siguiente módulo guardaremos el evento en PostgreSQL
    # y procesaremos órdenes de forma asíncrona.
    print(
        {
            "source": "mercadolibre",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
        },
    )
