import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "")
MELI_CLIENT_ID = os.getenv("MELI_CLIENT_ID", "")
MELI_CLIENT_SECRET = os.getenv("MELI_CLIENT_SECRET", "")
MELI_REDIRECT_URI = os.getenv("MELI_REDIRECT_URI", "")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


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
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("marketplace", "external_order_id", name="uq_order_marketplace_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("marketplace_accounts.id"), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False, default="MERCADO_LIBRE")
    external_order_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pack_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str | None] = mapped_column(String(60))
    status_detail: Mapped[str | None] = mapped_column(Text)
    currency_id: Mapped[str | None] = mapped_column(String(10))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    buyer_id: Mapped[int | None] = mapped_column(BigInteger)
    seller_id: Mapped[int | None] = mapped_column(BigInteger)
    shipment_id: Mapped[int | None] = mapped_column(BigInteger)
    date_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_closed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tags: Mapped[list[Any] | None] = mapped_column(JSON)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint(
            "order_id", "line_number", name="uq_order_item_order_line"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    external_item_id: Mapped[str | None] = mapped_column(String(40))
    variation_id: Mapped[int | None] = mapped_column(BigInteger)
    user_product_id: Mapped[str | None] = mapped_column(String(80))
    seller_sku: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    full_unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    currency_id: Mapped[str | None] = mapped_column(String(10))
    sale_fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    variation_attributes: Mapped[list[Any] | None] = mapped_column(JSON)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    order: Mapped[Order] = relationship(back_populates="items")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("marketplace", "external_payment_id", name="uq_payment_external"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False, default="MERCADO_LIBRE")
    external_payment_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str | None] = mapped_column(String(60))
    status_detail: Mapped[str | None] = mapped_column(String(100))
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    total_paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    marketplace_fee: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    currency_id: Mapped[str | None] = mapped_column(String(10))
    date_approved: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    order: Mapped[Order] = relationship(back_populates="payments")


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
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processing_error: Mapped[str | None] = mapped_column(Text)


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False)
    sync_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
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
    version="0.3.0",
    description="Backend para sincronizar Mercado Libre y Amazon con PostgreSQL.",
)


@app.on_event("startup")
def startup() -> None:
    if engine is not None:
        Base.metadata.create_all(bind=engine)


def get_account(session) -> MarketplaceAccount | None:
    return session.scalar(
        select(MarketplaceAccount).where(
            MarketplaceAccount.marketplace == "MERCADO_LIBRE",
            MarketplaceAccount.is_active.is_(True),
        )
    )


async def refresh_access_token(account: MarketplaceAccount, session) -> str:
    payload = {
        "grant_type": "refresh_token",
        "client_id": MELI_CLIENT_ID,
        "client_secret": MELI_CLIENT_SECRET,
        "refresh_token": account.refresh_token,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.mercadolibre.com/oauth/token",
            data=payload,
            headers={"accept": "application/json"},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"No se pudo renovar el token: {response.text}")

    data = response.json()
    account.access_token = data["access_token"]
    account.refresh_token = data["refresh_token"]
    account.expires_in = data.get("expires_in")
    account.token_type = data.get("token_type")
    account.scope = data.get("scope")
    account.token_expires_at = utcnow() + timedelta(seconds=int(data.get("expires_in", 21600)))
    account.updated_at = utcnow()
    session.commit()
    return account.access_token


async def meli_get(url: str, account: MarketplaceAccount, session, params: dict | None = None):
    if account.token_expires_at and account.token_expires_at <= utcnow() + timedelta(minutes=5):
        await refresh_access_token(account, session)

    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {account.access_token}"},
        )
        if response.status_code == 401:
            token = await refresh_access_token(account, session)
            response = await client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
    response.raise_for_status()
    return response.json()


def upsert_order(session, account: MarketplaceAccount, data: dict[str, Any]) -> Order:
    external_order_id = int(data["id"])
    order = session.scalar(
        select(Order).where(
            Order.marketplace == "MERCADO_LIBRE",
            Order.external_order_id == external_order_id,
        )
    )
    if order is None:
        order = Order(
            account_id=account.id,
            marketplace="MERCADO_LIBRE",
            external_order_id=external_order_id,
            raw_data=data,
        )
        session.add(order)
        session.flush()

    shipping = data.get("shipping") or {}
    shipment_id = shipping.get("id") if isinstance(shipping, dict) else None
    status_detail = data.get("status_detail")
    if isinstance(status_detail, dict):
        status_detail = status_detail.get("description") or status_detail.get("code")

    order.account_id = account.id
    order.pack_id = data.get("pack_id")
    order.status = data.get("status")
    order.status_detail = str(status_detail) if status_detail is not None else None
    order.currency_id = data.get("currency_id")
    order.total_amount = decimal_or_zero(data.get("total_amount"))
    order.paid_amount = decimal_or_zero(data.get("paid_amount"))
    order.buyer_id = (data.get("buyer") or {}).get("id")
    order.seller_id = (data.get("seller") or {}).get("id")
    order.shipment_id = shipment_id
    order.date_created = parse_datetime(data.get("date_created"))
    order.date_closed = parse_datetime(data.get("date_closed"))
    order.date_last_updated = parse_datetime(
        data.get("date_last_updated") or data.get("last_updated")
    )
    order.tags = data.get("tags") or []
    order.raw_data = data
    order.synced_at = utcnow()
    session.flush()

    session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    session.execute(delete(Payment).where(Payment.order_id == order.id))
    session.flush()

    for index, item_data in enumerate(data.get("order_items") or [], start=1):
        item = item_data.get("item") or {}
        seller_sku = item.get("seller_sku")
        if not seller_sku:
            seller_sku = item_data.get("seller_sku")

        order_item = OrderItem(
            order_id=order.id,
            line_number=index,
            external_item_id=item.get("id"),
            variation_id=item.get("variation_id"),
            user_product_id=item.get("user_product_id"),
            seller_sku=seller_sku,
            title=item.get("title"),
            quantity=int(item_data.get("quantity") or 0),
            unit_price=decimal_or_zero(item_data.get("unit_price")),
            full_unit_price=decimal_or_zero(item_data.get("full_unit_price")),
            currency_id=item_data.get("currency_id") or data.get("currency_id"),
            sale_fee=decimal_or_zero(item_data.get("sale_fee")),
            variation_attributes=item.get("variation_attributes") or [],
            raw_data=item_data,
        )
        session.add(order_item)

    for payment_data in data.get("payments") or []:
        payment_id = payment_data.get("id")
        if payment_id is None:
            continue
        payment = Payment(
            order_id=order.id,
            marketplace="MERCADO_LIBRE",
            external_payment_id=int(payment_id),
            status=payment_data.get("status"),
            status_detail=payment_data.get("status_detail"),
            transaction_amount=decimal_or_zero(payment_data.get("transaction_amount")),
            total_paid_amount=decimal_or_zero(payment_data.get("total_paid_amount")),
            shipping_cost=decimal_or_zero(payment_data.get("shipping_cost")),
            marketplace_fee=decimal_or_zero(payment_data.get("marketplace_fee")),
            currency_id=payment_data.get("currency_id") or data.get("currency_id"),
            date_approved=parse_datetime(payment_data.get("date_approved")),
            date_created=parse_datetime(payment_data.get("date_created")),
            raw_data=payment_data,
        )
        session.add(payment)

    return order


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "GETAC ERP API", "status": "online", "version": "0.3.0"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": utcnow().isoformat()}


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
                    "orders",
                    "order_items",
                    "payments",
                    "webhook_events",
                    "sync_logs",
                ],
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "database": "disconnected", "detail": str(exc)},
        )


@app.get("/auth/mercadolibre")
def mercadolibre_auth() -> JSONResponse:
    if not MELI_CLIENT_ID or not MELI_REDIRECT_URI:
        return JSONResponse(
            status_code=500,
            content={"error": "missing_configuration", "detail": "Faltan variables de Mercado Libre."},
        )
    query = urlencode(
        {"response_type": "code", "client_id": MELI_CLIENT_ID, "redirect_uri": MELI_REDIRECT_URI}
    )
    return JSONResponse(
        content={
            "authorization_url": f"https://auth.mercadolibre.com.mx/authorization?{query}"
        }
    )


@app.get("/auth/mercadolibre/start", response_model=None)
def mercadolibre_auth_start():
    if not MELI_CLIENT_ID or not MELI_REDIRECT_URI:
        return JSONResponse(
            status_code=500,
            content={"error": "missing_configuration", "detail": "Faltan variables de Mercado Libre."},
        )
    query = urlencode(
        {"response_type": "code", "client_id": MELI_CLIENT_ID, "redirect_uri": MELI_REDIRECT_URI}
    )
    return RedirectResponse(
        url=f"https://auth.mercadolibre.com.mx/authorization?{query}", status_code=302
    )


@app.get("/auth/mercadolibre/callback")
async def mercadolibre_callback(code: str | None = None) -> JSONResponse:
    if not code:
        return JSONResponse(status_code=400, content={"error": "missing_code"})
    if not all([MELI_CLIENT_ID, MELI_CLIENT_SECRET, MELI_REDIRECT_URI]) or SessionLocal is None:
        return JSONResponse(status_code=500, content={"error": "missing_configuration"})

    payload = {
        "grant_type": "authorization_code",
        "client_id": MELI_CLIENT_ID,
        "client_secret": MELI_CLIENT_SECRET,
        "code": code,
        "redirect_uri": MELI_REDIRECT_URI,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.mercadolibre.com/oauth/token",
            data=payload,
            headers={"accept": "application/json"},
        )
        if response.status_code >= 400:
            return JSONResponse(
                status_code=response.status_code,
                content={"error": "token_exchange_failed", "detail": response.text},
            )
        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        external_user_id = token_data.get("user_id")
        profile_response = await client.get(
            "https://api.mercadolibre.com/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        profile_data = profile_response.json() if profile_response.status_code < 400 else {}

    with SessionLocal() as session:
        account = session.scalar(
            select(MarketplaceAccount).where(
                MarketplaceAccount.external_user_id == int(external_user_id)
            )
        )
        if account is None:
            account = MarketplaceAccount(
                marketplace="MERCADO_LIBRE",
                external_user_id=int(external_user_id),
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
        account.token_expires_at = utcnow() + timedelta(seconds=int(token_data.get("expires_in", 21600)))
        account.scope = token_data.get("scope")
        account.is_active = True
        account.updated_at = utcnow()
        session.commit()

    return JSONResponse(
        content={
            "status": "connected",
            "marketplace": "MERCADO_LIBRE",
            "user_id": external_user_id,
            "nickname": profile_data.get("nickname"),
        }
    )


@app.post("/sync/mercadolibre/orders")
async def sync_mercadolibre_orders(
    days: int = Query(default=30, ge=1, le=365),
    max_orders: int = Query(default=1000, ge=1, le=5000),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(status_code=500, content={"error": "database_not_configured"})

    with SessionLocal() as session:
        account = get_account(session)
        if account is None:
            return JSONResponse(status_code=400, content={"error": "mercadolibre_not_connected"})

        sync_log = SyncLog(
            marketplace="MERCADO_LIBRE",
            sync_type="ORDERS",
            status="RUNNING",
            started_at=utcnow(),
        )
        session.add(sync_log)
        session.commit()

        try:
            date_from = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:00:00.000-00:00")
            offset = 0
            limit = 50
            processed = 0
            total_available = 0

            while processed < max_orders:
                params = {
                    "seller": account.external_user_id,
                    "order.date_last_updated.from": date_from,
                    "sort": "date_desc",
                    "offset": offset,
                    "limit": limit,
                }
                result = await meli_get(
                    "https://api.mercadolibre.com/orders/search",
                    account,
                    session,
                    params=params,
                )
                orders_data = result.get("results") or []
                total_available = int((result.get("paging") or {}).get("total") or 0)

                if not orders_data:
                    break

                for order_data in orders_data:
                    upsert_order(session, account, order_data)
                    processed += 1
                    if processed >= max_orders:
                        break

                session.commit()
                offset += len(orders_data)
                if offset >= total_available or len(orders_data) < limit:
                    break

            sync_log.status = "SUCCESS"
            sync_log.finished_at = utcnow()
            sync_log.records_processed = processed
            session.commit()

            totals = session.execute(
                text(
                    """
                    SELECT
                        COUNT(DISTINCT o.external_order_id) AS orders,
                        COALESCE(SUM(oi.quantity), 0) AS units,
                        COALESCE(SUM(o.paid_amount), 0) AS paid_amount
                    FROM orders o
                    LEFT JOIN order_items oi ON oi.order_id = o.id
                    WHERE o.marketplace = 'MERCADO_LIBRE'
                      AND o.date_last_updated >= :date_from
                    """
                ),
                {"date_from": utcnow() - timedelta(days=days)},
            ).mappings().one()

            return JSONResponse(
                content={
                    "status": "success",
                    "days_requested": days,
                    "orders_processed": processed,
                    "orders_available": total_available,
                    "database_summary": {
                        "orders": int(totals["orders"] or 0),
                        "units": int(totals["units"] or 0),
                        "paid_amount": float(totals["paid_amount"] or 0),
                    },
                }
            )
        except Exception as exc:
            session.rollback()
            sync_log = session.get(SyncLog, sync_log.id)
            if sync_log:
                sync_log.status = "ERROR"
                sync_log.finished_at = utcnow()
                sync_log.error_message = str(exc)[:4000]
                session.commit()
            return JSONResponse(
                status_code=500,
                content={"status": "error", "detail": str(exc)},
            )


@app.get("/reports/mercadolibre/summary")
def mercadolibre_summary(days: int = Query(default=30, ge=1, le=365)) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(status_code=500, content={"error": "database_not_configured"})
    since = utcnow() - timedelta(days=days)
    with SessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT
                    COUNT(DISTINCT o.external_order_id) AS orders,
                    COALESCE(SUM(oi.quantity), 0) AS units,
                    COALESCE(SUM(o.paid_amount), 0) AS paid_amount,
                    COUNT(DISTINCT oi.seller_sku) FILTER (WHERE oi.seller_sku IS NOT NULL) AS skus
                FROM orders o
                LEFT JOIN order_items oi ON oi.order_id = o.id
                WHERE o.marketplace = 'MERCADO_LIBRE'
                  AND o.date_created >= :since
                """
            ),
            {"since": since},
        ).mappings().one()
    return JSONResponse(
        content={
            "status": "ok",
            "days": days,
            "orders": int(row["orders"] or 0),
            "units": int(row["units"] or 0),
            "paid_amount": float(row["paid_amount"] or 0),
            "distinct_skus": int(row["skus"] or 0),
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
                session.add(
                    WebhookEvent(
                        marketplace="MERCADO_LIBRE",
                        topic=payload.get("topic") if isinstance(payload, dict) else None,
                        resource=payload.get("resource") if isinstance(payload, dict) else None,
                        external_user_id=int(payload["user_id"]) if isinstance(payload, dict) and payload.get("user_id") is not None else None,
                        application_id=int(payload["application_id"]) if isinstance(payload, dict) and payload.get("application_id") is not None else None,
                        attempts=int(payload["attempts"]) if isinstance(payload, dict) and payload.get("attempts") is not None else None,
                        sent_at=payload.get("sent") if isinstance(payload, dict) else None,
                        payload=payload if isinstance(payload, dict) else {"raw": str(payload)},
                    )
                )
                session.commit()
        except Exception as exc:
            print({"webhook_database_error": str(exc)})

    return JSONResponse(status_code=200, content={"status": "received"})
