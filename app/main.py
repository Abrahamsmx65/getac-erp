import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "")
MELI_CLIENT_ID = os.getenv("MELI_CLIENT_ID", "")
MELI_CLIENT_SECRET = os.getenv("MELI_CLIENT_SECRET", "")
MELI_REDIRECT_URI = os.getenv("MELI_REDIRECT_URI", "")


class Base(DeclarativeBase):
    pass


class MarketplaceAccount(Base):
    __tablename__ = "marketplace_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False, default="MERCADO_LIBRE")
    external_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    nickname: Mapped[str | None] = mapped_column(String(255))
    country_id: Mapped[str | None] = mapped_column(String(10))
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str | None] = mapped_column(String(30))
    expires_in: Mapped[int | None] = mapped_column(Integer)
    scope: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False, default="MERCADO_LIBRE")
    topic: Mapped[str | None] = mapped_column(String(100))
    resource: Mapped[str | None] = mapped_column(Text)
    external_user_id: Mapped[int | None] = mapped_column(BigInteger)
    application_id: Mapped[int | None] = mapped_column(BigInteger)
    attempts: Mapped[int | None] = mapped_column(Integer)
    sent_at: Mapped[str | None] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processing_error: Mapped[str | None] = mapped_column(Text)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False)
    sync_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


engine = None
SessionLocal = None

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"sslmode": "require"},
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


app = FastAPI(
    title="GETAC ERP API",
    version="0.2.0",
    description="Backend para Mercado Libre, Amazon y PostgreSQL.",
)


@app.on_event("startup")
def startup() -> None:
    if engine is not None:
        Base.metadata.create_all(bind=engine)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "GETAC ERP API", "status": "online", "version": "0.2.0"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/health/database")
def database_health() -> JSONResponse:
    if engine is None:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": "DATABASE_URL no está configurada."},
        )

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return JSONResponse(
            content={
                "status": "ok",
                "database": "connected",
                "tables": [
                    "marketplace_accounts",
                    "webhook_events",
                    "sync_logs",
                ],
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "database": "disconnected",
                "detail": str(exc),
            },
        )


@app.get("/auth/mercadolibre")
def mercadolibre_auth() -> JSONResponse:
    if not MELI_CLIENT_ID or not MELI_REDIRECT_URI:
        return JSONResponse(
            status_code=500,
            content={
                "error": "missing_configuration",
                "detail": "Faltan MELI_CLIENT_ID o MELI_REDIRECT_URI.",
            },
        )

    query = urlencode(
        {
            "response_type": "code",
            "client_id": MELI_CLIENT_ID,
            "redirect_uri": MELI_REDIRECT_URI,
        }
    )
    return JSONResponse(
        content={
            "authorization_url": f"https://auth.mercadolibre.com.mx/authorization?{query}",
            "next_step": "Abre authorization_url para autorizar tu cuenta.",
        }
    )


@app.get("/auth/mercadolibre/start", response_model=None)
def mercadolibre_auth_start():
    response = mercadolibre_auth()
    if response.status_code != 200:
        return response

    query = urlencode(
        {
            "response_type": "code",
            "client_id": MELI_CLIENT_ID,
            "redirect_uri": MELI_REDIRECT_URI,
        }
    )
    return RedirectResponse(
        url=f"https://auth.mercadolibre.com.mx/authorization?{query}",
        status_code=302,
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

    if not all([MELI_CLIENT_ID, MELI_CLIENT_SECRET, MELI_REDIRECT_URI]):
        return JSONResponse(
            status_code=500,
            content={
                "error": "missing_configuration",
                "detail": "Faltan variables privadas de Mercado Libre.",
            },
        )

    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={
                "error": "database_not_configured",
                "detail": "DATABASE_URL no está configurada.",
            },
        )

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": MELI_CLIENT_ID,
        "client_secret": MELI_CLIENT_SECRET,
        "code": code,
        "redirect_uri": MELI_REDIRECT_URI,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        token_response = await client.post(
            "https://api.mercadolibre.com/oauth/token",
            data=token_payload,
            headers={"accept": "application/json"},
        )

        if token_response.status_code >= 400:
            return JSONResponse(
                status_code=token_response.status_code,
                content={
                    "error": "token_exchange_failed",
                    "detail": token_response.text,
                },
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        external_user_id = token_data.get("user_id")

        if not access_token or not refresh_token:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "invalid_token_response",
                    "detail": "La respuesta no incluyó los tokens esperados.",
                },
            )

        profile_data: dict[str, Any] = {}
        profile_response = await client.get(
            "https://api.mercadolibre.com/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if profile_response.status_code < 400:
            profile_data = profile_response.json()

    with SessionLocal() as session:
        account = None
        if external_user_id is not None:
            account = session.scalar(
                select(MarketplaceAccount).where(
                    MarketplaceAccount.external_user_id == int(external_user_id)
                )
            )

        if account is None:
            account = MarketplaceAccount(
                marketplace="MERCADO_LIBRE",
                external_user_id=int(external_user_id) if external_user_id is not None else None,
                access_token=access_token,
                refresh_token=refresh_token,
            )
            session.add(account)

        account.nickname = profile_data.get("nickname")
        account.country_id = profile_data.get("country_id")
        account.access_token = access_token
        account.refresh_token = refresh_token
        account.token_type = token_data.get("token_type")
        account.expires_in = token_data.get("expires_in")
        account.scope = token_data.get("scope")
        account.is_active = True
        account.updated_at = datetime.now(timezone.utc)

        session.commit()

    return JSONResponse(
        content={
            "status": "connected",
            "marketplace": "MERCADO_LIBRE",
            "user_id": external_user_id,
            "nickname": profile_data.get("nickname"),
            "message": "La cuenta quedó autorizada y los tokens se guardaron en PostgreSQL.",
        }
    )


@app.post("/webhooks/mercadolibre")
async def mercadolibre_webhook(request: Request) -> JSONResponse:
    try:
        payload: Any = await request.json()
    except Exception:
        payload = {}

    if SessionLocal is not None:
        try:
            with SessionLocal() as session:
                event = WebhookEvent(
                    marketplace="MERCADO_LIBRE",
                    topic=payload.get("topic") if isinstance(payload, dict) else None,
                    resource=payload.get("resource") if isinstance(payload, dict) else None,
                    external_user_id=(
                        int(payload["user_id"])
                        if isinstance(payload, dict) and payload.get("user_id") is not None
                        else None
                    ),
                    application_id=(
                        int(payload["application_id"])
                        if isinstance(payload, dict) and payload.get("application_id") is not None
                        else None
                    ),
                    attempts=(
                        int(payload["attempts"])
                        if isinstance(payload, dict) and payload.get("attempts") is not None
                        else None
                    ),
                    sent_at=payload.get("sent") if isinstance(payload, dict) else None,
                    payload=payload if isinstance(payload, dict) else {"raw": str(payload)},
                )
                session.add(event)
                session.commit()
        except Exception as exc:
            print({"webhook_database_error": str(exc), "payload": payload})

    return JSONResponse(status_code=200, content={"status": "received"})
