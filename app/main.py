import asyncio
import io
import math
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
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
SERVICE_ROLE = os.getenv("SERVICE_ROLE", "all").strip().lower()


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


def parse_date_range(
    date_from: str | None,
    date_to: str | None,
    days: int,
) -> tuple[datetime, datetime]:
    now = utcnow()

    if date_from:
        try:
            start_date = date.fromisoformat(date_from)
            start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("date_from debe tener formato YYYY-MM-DD") from exc
    else:
        start = now - timedelta(days=days)

    if date_to:
        try:
            end_date = date.fromisoformat(date_to)
            end = datetime.combine(
                end_date + timedelta(days=1),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
        except ValueError as exc:
            raise ValueError("date_to debe tener formato YYYY-MM-DD") from exc
    else:
        end = now

    if start >= end:
        raise ValueError("La fecha inicial debe ser anterior a la fecha final.")

    return start, end


def normalize_search(value: str | None) -> str:
    return (value or "").strip().upper()


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


class FullInventory(Base):
    __tablename__ = "full_inventory"

    inventory_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    item_id: Mapped[str | None] = mapped_column(String(80), index=True)
    variation_id: Mapped[str | None] = mapped_column(String(80), index=True)
    sku: Mapped[str | None] = mapped_column(String(180), index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    category_id: Mapped[str | None] = mapped_column(String(80))
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_available_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    not_available_detail: Mapped[list[Any] | None] = mapped_column(JSON)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class FullSyncRun(Base):
    __tablename__ = "full_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    items_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inventories_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inventories_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class CategoryCache(Base):
    __tablename__ = "category_cache"

    category_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path_from_root: Mapped[list[Any] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    marketplace: Mapped[str] = mapped_column(String(30), nullable=False, default="MERCADO_LIBRE")
    job_type: Mapped[str] = mapped_column(String(50), nullable=False, default="HISTORICAL_ORDERS")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    date_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    date_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_chunk_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_chunk_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    orders_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    last_error: Mapped[str | None] = mapped_column(Text)


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
    version="0.9.1",
    description="Backend para sincronizar Mercado Libre y Amazon con PostgreSQL.",
)

worker_task: asyncio.Task | None = None
daily_scheduler_task: asyncio.Task | None = None
full_sync_tasks: dict[str, asyncio.Task] = {}


@app.on_event("startup")
async def startup() -> None:
    global worker_task, daily_scheduler_task

    if engine is not None:
        Base.metadata.create_all(bind=engine)

        if SessionLocal is not None:
            with SessionLocal() as session:
                stale_runs = session.scalars(
                    select(FullSyncRun).where(
                        FullSyncRun.status.in_(
                            ["PENDING", "RUNNING"]
                        )
                    )
                ).all()
                for stale_run in stale_runs:
                    stale_run.status = "INTERRUPTED"
                    stale_run.finished_at = utcnow()
                    stale_run.last_error = (
                        "Ejecución interrumpida por un despliegue "
                        "o reinicio anterior."
                    )
                session.commit()

    if SERVICE_ROLE in ("all", "worker"):
        print({"service_role": SERVICE_ROLE, "worker": "started"})
        worker_task = asyncio.create_task(sync_worker_loop())
        daily_scheduler_task = asyncio.create_task(
            daily_sync_scheduler_loop()
        )
    else:
        print({"service_role": SERVICE_ROLE, "worker": "disabled"})


@app.on_event("shutdown")
async def shutdown() -> None:
    global worker_task
    if worker_task is not None:
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass


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


async def meli_get(
    url: str,
    account: MarketplaceAccount,
    session,
    params: dict | None = None,
    max_retries: int = 8,
):
    if account.token_expires_at and account.token_expires_at <= utcnow() + timedelta(minutes=5):
        await refresh_access_token(account, session)

    base_delay = 3.0

    async with httpx.AsyncClient(timeout=60) as client:
        for attempt in range(max_retries + 1):
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

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else base_delay * (2 ** attempt)
                except ValueError:
                    delay = base_delay * (2 ** attempt)

                delay = min(delay, 300)
                print(
                    {
                        "rate_limit": True,
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                        "url": str(response.request.url),
                    }
                )
                await asyncio.sleep(delay)
                continue

            if 500 <= response.status_code < 600:
                delay = min(base_delay * (2 ** attempt), 120)
                print(
                    {
                        "temporary_meli_error": response.status_code,
                        "attempt": attempt + 1,
                        "delay_seconds": delay,
                    }
                )
                await asyncio.sleep(delay)
                continue

            response.raise_for_status()
            return response.json()

    raise RuntimeError(
        f"Mercado Libre siguió respondiendo 429/5xx después de {max_retries + 1} intentos."
    )


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


def format_meli_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000-00:00")


def build_six_hour_chunks(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    chunks: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(hours=6), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


async def process_historical_job(job_id: str) -> None:
    if SessionLocal is None:
        return

    with SessionLocal() as session:
        job = session.get(SyncJob, job_id)
        account = get_account(session)
        if job is None or account is None:
            return

        job.status = "RUNNING"
        job.started_at = job.started_at or utcnow()
        job.updated_at = utcnow()
        session.commit()

        chunks = build_six_hour_chunks(job.date_from, job.date_to)
        job.total_chunks = len(chunks)
        session.commit()

        start_index = 0
        if job.current_chunk_from is not None:
            for idx, (chunk_from, _) in enumerate(chunks):
                if chunk_from >= job.current_chunk_from:
                    start_index = idx
                    break

        try:
            for chunk_index in range(start_index, len(chunks)):
                chunk_from, chunk_to = chunks[chunk_index]

                with SessionLocal() as chunk_session:
                    job = chunk_session.get(SyncJob, job_id)
                    account = get_account(chunk_session)
                    if job is None or account is None:
                        return
                    if job.status == "CANCELLED":
                        return

                    offset = job.current_offset if job.current_chunk_from == chunk_from else 0
                    job.current_chunk_from = chunk_from
                    job.current_chunk_to = chunk_to
                    job.current_offset = offset
                    job.updated_at = utcnow()
                    chunk_session.commit()

                    while True:
                        params = {
                            "seller": account.external_user_id,
                            "order.date_created.from": format_meli_datetime(chunk_from),
                            "order.date_created.to": format_meli_datetime(chunk_to),
                            "sort": "date_asc",
                            "offset": offset,
                            "limit": 50,
                        }

                        result = await meli_get(
                            "https://api.mercadolibre.com/orders/search",
                            account,
                            chunk_session,
                            params=params,
                        )
                        orders_data = result.get("results") or []
                        total = int((result.get("paging") or {}).get("total") or 0)

                        if not orders_data:
                            break

                        for order_data in orders_data:
                            upsert_order(chunk_session, account, order_data)

                        job = chunk_session.get(SyncJob, job_id)
                        if job is None:
                            return

                        processed_now = len(orders_data)
                        job.orders_processed += processed_now
                        offset += processed_now
                        job.current_offset = offset
                        job.updated_at = utcnow()
                        chunk_session.commit()

                        if offset >= total or processed_now < 50:
                            break

                        await asyncio.sleep(0.75)

                    job = chunk_session.get(SyncJob, job_id)
                    if job is None:
                        return
                    job.chunks_completed = chunk_index + 1
                    job.current_offset = 0
                    job.current_chunk_from = chunks[chunk_index + 1][0] if chunk_index + 1 < len(chunks) else None
                    job.current_chunk_to = chunks[chunk_index + 1][1] if chunk_index + 1 < len(chunks) else None
                    job.updated_at = utcnow()
                    chunk_session.commit()

            with SessionLocal() as final_session:
                job = final_session.get(SyncJob, job_id)
                if job:
                    job.status = "SUCCESS"
                    job.finished_at = utcnow()
                    job.current_chunk_from = None
                    job.current_chunk_to = None
                    job.current_offset = 0
                    job.updated_at = utcnow()
                    final_session.commit()

        except Exception as exc:
            with SessionLocal() as error_session:
                job = error_session.get(SyncJob, job_id)
                if job:
                    job.status = "ERROR"
                    job.last_error = str(exc)[:4000]
                    job.updated_at = utcnow()
                    error_session.commit()


async def sync_orders_for_exact_range(
    start_utc: datetime,
    end_utc: datetime,
    sync_type: str,
) -> dict[str, Any]:
    if SessionLocal is None:
        raise RuntimeError("database_not_configured")

    with SessionLocal() as session:
        account = get_account(session)
        if account is None:
            raise RuntimeError("mercadolibre_not_connected")

        existing = session.scalar(
            select(SyncLog).where(
                SyncLog.marketplace == "MERCADO_LIBRE",
                SyncLog.sync_type == sync_type,
                SyncLog.status == "SUCCESS",
            )
        )
        if existing:
            return {
                "status": "already_completed",
                "records_processed": existing.records_processed,
            }

        running = session.scalar(
            select(SyncLog).where(
                SyncLog.marketplace == "MERCADO_LIBRE",
                SyncLog.sync_type == sync_type,
                SyncLog.status == "RUNNING",
            )
        )
        if running:
            return {"status": "already_running"}

        sync_log = SyncLog(
            marketplace="MERCADO_LIBRE",
            sync_type=sync_type,
            status="RUNNING",
            started_at=utcnow(),
        )
        session.add(sync_log)
        session.commit()
        log_id = sync_log.id

        processed = 0
        offset = 0
        limit = 50

        try:
            while True:
                params = {
                    "seller": account.external_user_id,
                    "order.date_created.from": (
                        start_utc.strftime(
                            "%Y-%m-%dT%H:%M:%S.000-00:00"
                        )
                    ),
                    "order.date_created.to": (
                        end_utc.strftime(
                            "%Y-%m-%dT%H:%M:%S.000-00:00"
                        )
                    ),
                    "sort": "date_asc",
                    "offset": offset,
                    "limit": limit,
                }

                payload = await meli_get(
                    "https://api.mercadolibre.com/orders/search",
                    account,
                    session,
                    params=params,
                )
                orders_data = payload.get("results") or []
                total = int(
                    (payload.get("paging") or {}).get("total") or 0
                )

                if not orders_data:
                    break

                for order_data in orders_data:
                    upsert_order(session, account, order_data)
                    processed += 1

                session.commit()
                offset += len(orders_data)

                if offset >= total or len(orders_data) < limit:
                    break

                await asyncio.sleep(0.2)

            sync_log = session.get(SyncLog, log_id)
            if sync_log:
                sync_log.status = "SUCCESS"
                sync_log.finished_at = utcnow()
                sync_log.records_processed = processed
                sync_log.error_message = None
                session.commit()

            return {
                "status": "success",
                "records_processed": processed,
            }

        except Exception as exc:
            session.rollback()
            sync_log = session.get(SyncLog, log_id)
            if sync_log:
                sync_log.status = "ERROR"
                sync_log.finished_at = utcnow()
                sync_log.records_processed = processed
                sync_log.error_message = str(exc)[:4000]
                session.commit()
            raise


async def run_previous_day_sync() -> dict[str, Any]:
    mexico_tz = ZoneInfo("America/Mexico_City")
    now_local = datetime.now(mexico_tz)
    previous_date = now_local.date() - timedelta(days=1)

    start_local = datetime.combine(
        previous_date,
        datetime.min.time(),
        tzinfo=mexico_tz,
    )
    end_local = start_local + timedelta(days=1)

    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    return await sync_orders_for_exact_range(
        start_utc=start_utc,
        end_utc=end_utc,
        sync_type=f"DAILY_ORDERS_{previous_date.isoformat()}",
    )


async def daily_sync_scheduler_loop() -> None:
    mexico_tz = ZoneInfo("America/Mexico_City")

    while True:
        try:
            now_local = datetime.now(mexico_tz)

            if now_local.hour >= 1:
                previous_date = (
                    now_local.date() - timedelta(days=1)
                )
                sync_type = (
                    f"DAILY_ORDERS_{previous_date.isoformat()}"
                )

                should_run = True
                if SessionLocal is not None:
                    with SessionLocal() as session:
                        existing = session.scalar(
                            select(SyncLog).where(
                                SyncLog.marketplace
                                == "MERCADO_LIBRE",
                                SyncLog.sync_type == sync_type,
                                SyncLog.status.in_(
                                    ["SUCCESS", "RUNNING"]
                                ),
                            )
                        )
                        should_run = existing is None

                if should_run:
                    print({
                        "event": "daily_sync_start",
                        "date": previous_date.isoformat(),
                        "timezone": "America/Mexico_City",
                    })
                    await run_previous_day_sync()

            await asyncio.sleep(60)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print({
                "event": "daily_sync_error",
                "error": str(exc),
            })
            await asyncio.sleep(300)


async def sync_worker_loop() -> None:
    while True:
        try:
            if SessionLocal is not None:
                with SessionLocal() as session:
                    job = session.scalar(
                        select(SyncJob)
                        .where(SyncJob.status.in_(["PENDING", "RUNNING"]))
                        .order_by(SyncJob.created_at.asc())
                    )
                    job_id = job.id if job else None

                if job_id:
                    await process_historical_job(job_id)
                else:
                    await asyncio.sleep(5)
            else:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print({"sync_worker_error": str(exc)})
            await asyncio.sleep(10)


def extract_sku(data: dict[str, Any]) -> str | None:
    candidates = [
        data.get("seller_custom_field"),
        data.get("seller_sku"),
        data.get("sku"),
        data.get("seller_custom_field_id"),
    ]

    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip().upper()

    for attribute in data.get("attributes") or []:
        attribute_id = str(attribute.get("id") or "").upper()
        if attribute_id in (
            "SELLER_SKU",
            "SELLER_CUSTOM_FIELD",
            "SKU",
        ):
            value = (
                attribute.get("value_name")
                or attribute.get("value_id")
                or attribute.get("value_struct", {}).get("number")
            )
            if value is not None and str(value).strip():
                return str(value).strip().upper()

    return None


def build_order_sku_maps(
    session,
) -> tuple[
    dict[tuple[str, str], str],
    dict[str, str],
    dict[str, str],
]:
    """
    Build reliable SKU maps from normalized order_items columns.

    The previous version tried to read item_id and variation_id only
    from raw JSON. Those values already exist in external_item_id and
    variation_id, so using the columns is substantially more reliable.
    """

    rows = session.execute(
        select(
            OrderItem.external_item_id,
            OrderItem.variation_id,
            OrderItem.seller_sku,
            OrderItem.raw_data,
        )
        .where(
            OrderItem.seller_sku.is_not(None),
            OrderItem.seller_sku != "",
        )
        .order_by(OrderItem.id.desc())
    ).all()

    by_item_variation: dict[tuple[str, str], str] = {}
    by_inventory: dict[str, str] = {}
    item_candidates: dict[str, set[str]] = {}

    for external_item_id, variation_id, seller_sku, raw_data in rows:
        sku = str(seller_sku or "").strip().upper()
        if not sku:
            continue

        item_id = str(external_item_id or "").strip()
        variation_text = (
            str(variation_id).strip()
            if variation_id is not None
            else ""
        )

        if item_id and variation_text:
            by_item_variation.setdefault(
                (item_id, variation_text),
                sku,
            )

        if item_id:
            item_candidates.setdefault(item_id, set()).add(sku)

        payload = raw_data or {}
        inventory_id = (
            payload.get("inventory_id")
            or (payload.get("item") or {}).get("inventory_id")
        )
        if inventory_id:
            by_inventory.setdefault(str(inventory_id), sku)

    # Only use item-only fallback when one item maps to exactly one SKU.
    # This prevents assigning one size's SKU to every variation.
    by_item = {
        item_id: next(iter(skus))
        for item_id, skus in item_candidates.items()
        if len(skus) == 1
    }

    return by_item_variation, by_inventory, by_item


async def list_all_seller_item_ids(
    account: MarketplaceAccount,
    session,
) -> list[str]:
    item_ids: list[str] = []
    url = (
        f"https://api.mercadolibre.com/users/"
        f"{account.external_user_id}/items/search"
    )
    params: dict[str, Any] = {"search_type": "scan", "limit": 100}

    while True:
        payload = await meli_get(url, account, session, params=params)
        results = payload.get("results") or []
        item_ids.extend(str(value) for value in results)

        scroll_id = payload.get("scroll_id")
        if not scroll_id or not results:
            break

        params = {
            "search_type": "scan",
            "limit": 100,
            "scroll_id": scroll_id,
        }
        await asyncio.sleep(0.4)

    return list(dict.fromkeys(item_ids))


async def sync_full_inventory_run(run_id: str) -> None:
    if SessionLocal is None:
        return

    try:
        with SessionLocal() as session:
            run = session.get(FullSyncRun, run_id)
            account = get_account(session)
            if run is None or account is None:
                return

            run.status = "RUNNING"
            run.started_at = utcnow()
            session.commit()

            item_ids = await list_all_seller_item_ids(account, session)
            run.items_found = len(item_ids)
            session.commit()

            (
                sku_by_item_variation,
                sku_by_inventory,
                sku_by_item,
            ) = build_order_sku_maps(session)

            inventory_records: list[dict[str, Any]] = []

            for index in range(0, len(item_ids), 20):
                batch = item_ids[index:index + 20]
                payload = await meli_get(
                    "https://api.mercadolibre.com/items",
                    account,
                    session,
                    params={"ids": ",".join(batch)},
                )

                responses = payload if isinstance(payload, list) else []
                for response_item in responses:
                    body = response_item.get("body") or {}
                    item_id = body.get("id")
                    title = body.get("title")
                    category_id = body.get("category_id")

                    main_inventory_id = body.get("inventory_id")
                    if main_inventory_id:
                        main_inventory_id = str(main_inventory_id)
                        item_id_text = str(item_id) if item_id else ""
                        resolved_sku = (
                            extract_sku(body)
                            or sku_by_inventory.get(main_inventory_id)
                            or sku_by_item.get(item_id_text)
                        )

                        inventory_records.append({
                            "inventory_id": main_inventory_id,
                            "item_id": item_id_text or None,
                            "variation_id": None,
                            "sku": resolved_sku,
                            "title": title,
                            "category_id": category_id,
                        })

                    for variation in body.get("variations") or []:
                        inventory_id = variation.get("inventory_id")
                        if not inventory_id:
                            continue

                        inventory_id_text = str(inventory_id)
                        item_id_text = str(item_id) if item_id else ""
                        variation_id_text = (
                            str(variation.get("id"))
                            if variation.get("id") is not None
                            else ""
                        )

                        resolved_sku = (
                            extract_sku(variation)
                            or sku_by_inventory.get(inventory_id_text)
                            or sku_by_item_variation.get(
                                (item_id_text, variation_id_text)
                            )
                            or extract_sku(body)
                        )

                        inventory_records.append({
                            "inventory_id": inventory_id_text,
                            "item_id": item_id_text or None,
                            "variation_id": variation_id_text or None,
                            "sku": resolved_sku,
                            "title": title,
                            "category_id": category_id,
                        })

                await asyncio.sleep(0.5)

            unique_records = {
                record["inventory_id"]: record
                for record in inventory_records
            }
            run.inventories_found = len(unique_records)
            session.commit()

            for record in unique_records.values():
                stock = await meli_get(
                    (
                        "https://api.mercadolibre.com/inventories/"
                        f"{record['inventory_id']}/stock/fulfillment"
                    ),
                    account,
                    session,
                )

                existing_row = session.get(
                    FullInventory,
                    record["inventory_id"],
                )
                resolved_sku = (
                    record["sku"]
                    or (
                        existing_row.sku
                        if existing_row and existing_row.sku
                        else None
                    )
                )

                row = FullInventory(
                    inventory_id=record["inventory_id"],
                    item_id=record["item_id"],
                    variation_id=record["variation_id"],
                    sku=resolved_sku,
                    title=record["title"],
                    category_id=record["category_id"],
                    total_quantity=int(stock.get("total") or 0),
                    available_quantity=int(
                        stock.get("available_quantity") or 0
                    ),
                    not_available_quantity=int(
                        stock.get("not_available_quantity") or 0
                    ),
                    not_available_detail=(
                        stock.get("not_available_detail") or []
                    ),
                    last_synced_at=utcnow(),
                )
                session.merge(row)

                run.inventories_processed += 1
                if run.inventories_processed % 20 == 0:
                    session.commit()

                await asyncio.sleep(0.8)

            run.status = "SUCCESS"
            run.finished_at = utcnow()
            run.last_error = None
            session.commit()

    except asyncio.CancelledError:
        with SessionLocal() as session:
            run = session.get(FullSyncRun, run_id)
            if run:
                run.status = "INTERRUPTED"
                run.last_error = (
                    "La actualización fue interrumpida por un reinicio "
                    "del servidor. Presiona Actualizar stock FULL para "
                    "continuar con una nueva ejecución."
                )
                run.finished_at = utcnow()
                session.commit()
        raise
    except Exception as exc:
        with SessionLocal() as session:
            run = session.get(FullSyncRun, run_id)
            if run:
                run.status = "ERROR"
                run.last_error = str(exc)[:4000]
                run.finished_at = utcnow()
                session.commit()
    finally:
        full_sync_tasks.pop(run_id, None)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "GETAC ERP API", "status": "online", "version": "0.9.1", "role": SERVICE_ROLE}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": utcnow().isoformat()}

@app.get("/health/service")
def service_health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": "0.9.1",
        "service_role": SERVICE_ROLE,
        "worker_enabled": SERVICE_ROLE in ("all", "worker"),
        "worker_running": bool(worker_task and not worker_task.done()),
        "timestamp": utcnow().isoformat(),
    }


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
                    "sync_jobs",
                    "full_inventory",
                    "full_sync_runs",
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


@app.get("/sync/jobs")
def list_sync_jobs(
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    with SessionLocal() as session:
        jobs = session.scalars(
            select(SyncJob)
            .order_by(SyncJob.created_at.desc())
            .limit(limit)
        ).all()

        return JSONResponse(content={
            "jobs": [
                {
                    "job_id": job.id,
                    "status": job.status,
                    "job_type": job.job_type,
                    "orders_processed": job.orders_processed,
                    "chunks_completed": job.chunks_completed,
                    "total_chunks": job.total_chunks,
                    "created_at": job.created_at.isoformat(),
                    "last_error": job.last_error,
                }
                for job in jobs
            ]
        })


@app.get("/sync/jobs/{job_id}")
def get_sync_job(job_id: str) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    with SessionLocal() as session:
        job = session.get(SyncJob, job_id)
        if job is None:
            return JSONResponse(
                status_code=404,
                content={"error": "job_not_found"},
            )

        progress = 0.0
        if job.total_chunks:
            progress = round(
                job.chunks_completed / job.total_chunks * 100,
                2,
            )

        return JSONResponse(content={
            "job_id": job.id,
            "marketplace": job.marketplace,
            "job_type": job.job_type,
            "status": job.status,
            "date_from": job.date_from.isoformat(),
            "date_to": job.date_to.isoformat(),
            "orders_processed": job.orders_processed,
            "chunks_completed": job.chunks_completed,
            "total_chunks": job.total_chunks,
            "progress_percent": progress,
            "current_chunk_from": (
                job.current_chunk_from.isoformat()
                if job.current_chunk_from else None
            ),
            "current_chunk_to": (
                job.current_chunk_to.isoformat()
                if job.current_chunk_to else None
            ),
            "started_at": (
                job.started_at.isoformat()
                if job.started_at else None
            ),
            "finished_at": (
                job.finished_at.isoformat()
                if job.finished_at else None
            ),
            "last_error": job.last_error,
        })


@app.post("/sync/mercadolibre/yesterday")
async def sync_yesterday_now() -> JSONResponse:
    try:
        result = await run_previous_day_sync()
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": str(exc)},
        )


@app.get("/api/automation/daily-status")
def daily_sync_status() -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    mexico_tz = ZoneInfo("America/Mexico_City")
    now_local = datetime.now(mexico_tz)
    previous_date = now_local.date() - timedelta(days=1)
    sync_type = f"DAILY_ORDERS_{previous_date.isoformat()}"

    with SessionLocal() as session:
        latest = session.scalar(
            select(SyncLog)
            .where(
                SyncLog.marketplace == "MERCADO_LIBRE",
                SyncLog.sync_type.like("DAILY_ORDERS_%"),
            )
            .order_by(SyncLog.started_at.desc())
            .limit(1)
        )

        today_run = session.scalar(
            select(SyncLog).where(
                SyncLog.marketplace == "MERCADO_LIBRE",
                SyncLog.sync_type == sync_type,
            )
        )

    next_run_date = now_local.date()
    if now_local.hour >= 1:
        next_run_date += timedelta(days=1)

    next_run = datetime.combine(
        next_run_date,
        datetime.min.time().replace(hour=1),
        tzinfo=mexico_tz,
    )

    return JSONResponse(content={
        "enabled": True,
        "timezone": "America/Mexico_City",
        "schedule": "01:00",
        "previous_day": previous_date.isoformat(),
        "previous_day_status": (
            today_run.status if today_run else "PENDING"
        ),
        "next_run": next_run.isoformat(),
        "last_run": (
            {
                "sync_type": latest.sync_type,
                "status": latest.status,
                "records_processed": latest.records_processed,
                "started_at": latest.started_at.isoformat(),
                "finished_at": (
                    latest.finished_at.isoformat()
                    if latest.finished_at else None
                ),
                "error": latest.error_message,
            }
            if latest else None
        ),
    })


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
@app.get("/api/dashboard/summary")
async def dashboard_summary(
    days: int = Query(default=30, ge=1, le=730),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(status_code=500, content={"error": "database_not_configured"})

    try:
        start, end = parse_date_range(date_from, date_to, days)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    search_value = normalize_search(search)
    category_value = normalize_search(category)

    filters = """
        o.marketplace = 'MERCADO_LIBRE'
        AND o.date_created >= :start
        AND o.date_created < :end
        AND COALESCE(o.status, '') NOT IN ('cancelled', 'invalid')
        AND (
            :search_value = ''
            OR UPPER(COALESCE(oi.seller_sku, '')) LIKE :search_like
            OR UPPER(COALESCE(oi.title, '')) LIKE :search_like
            OR UPPER(
                CASE
                    WHEN POSITION('-' IN COALESCE(oi.seller_sku, '')) > 0
                        THEN SPLIT_PART(BTRIM(oi.seller_sku), '-', 1)
                    ELSE BTRIM(COALESCE(oi.seller_sku, ''))
                END
            ) LIKE :search_like
        )
        AND (
            :category_value = ''
            OR UPPER(COALESCE(oi.raw_data #>> '{item,category_id}', '')) LIKE :category_like
            OR UPPER(COALESCE(oi.raw_data #>> '{item,domain_id}', '')) LIKE :category_like
            OR UPPER(COALESCE(oi.title, '')) LIKE :category_like
        )
    """

    params = {
        "start": start,
        "end": end,
        "search_value": search_value,
        "search_like": f"%{search_value}%",
        "category_value": category_value,
        "category_like": f"%{category_value}%",
    }

    with SessionLocal() as session:
        totals = session.execute(
            text(
                f"""
                WITH filtered AS (
                    SELECT
                        o.id AS order_id,
                        o.external_order_id,
                        o.paid_amount,
                        oi.quantity
                    FROM orders o
                    JOIN order_items oi ON oi.order_id = o.id
                    WHERE {filters}
                ),
                order_totals AS (
                    SELECT
                        order_id,
                        MAX(external_order_id) AS external_order_id,
                        MAX(paid_amount) AS paid_amount,
                        SUM(quantity) AS units
                    FROM filtered
                    GROUP BY order_id
                )
                SELECT
                    COUNT(*) AS orders,
                    COALESCE(SUM(units), 0) AS units,
                    COALESCE(SUM(paid_amount), 0) AS paid_amount,
                    COALESCE(AVG(paid_amount), 0) AS average_ticket
                FROM order_totals
                """
            ),
            params,
        ).mappings().one()

        daily_rows = session.execute(
            text(
                f"""
                WITH filtered_orders AS (
                    SELECT DISTINCT
                        o.id,
                        o.date_created,
                        o.paid_amount
                    FROM orders o
                    JOIN order_items oi ON oi.order_id = o.id
                    WHERE {filters}
                )
                SELECT
                    DATE(date_created AT TIME ZONE 'America/Mexico_City') AS sale_date,
                    COUNT(*) AS orders,
                    COALESCE(SUM(paid_amount), 0) AS paid_amount
                FROM filtered_orders
                GROUP BY 1
                ORDER BY 1
                """
            ),
            params,
        ).mappings().all()

        top_skus = session.execute(
            text(
                f"""
                SELECT
                    COALESCE(NULLIF(UPPER(BTRIM(oi.seller_sku)), ''), 'SIN SKU') AS sku,
                    MAX(oi.title) AS title,
                    COALESCE(SUM(oi.quantity), 0) AS units,
                    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS gross_sales
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE {filters}
                GROUP BY 1
                ORDER BY units DESC, gross_sales DESC
                LIMIT 25
                """
            ),
            params,
        ).mappings().all()

        status_rows = session.execute(
            text(
                f"""
                SELECT
                    COALESCE(o.status, 'unknown') AS status,
                    COUNT(DISTINCT o.id) AS orders
                FROM orders o
                JOIN order_items oi ON oi.order_id = o.id
                WHERE {filters}
                GROUP BY 1
                ORDER BY orders DESC
                """
            ),
            params,
        ).mappings().all()

        category_ids = session.execute(
            text(
                """
                SELECT DISTINCT category_id
                FROM (
                    SELECT NULLIF(
                        UPPER(
                            COALESCE(
                                oi.raw_data #>> '{item,category_id}',
                                ''
                            )
                        ),
                        ''
                    ) AS category_id
                    FROM order_items oi
                ) q
                WHERE category_id IS NOT NULL
                  AND category_id LIKE 'MLM%'
                ORDER BY category_id
                LIMIT 500
                """
            )
        ).scalars().all()

        categories = await resolve_category_names(
            category_ids,
            session,
        )

    return JSONResponse(
        content={
            "status": "ok",
            "date_from": start.date().isoformat(),
            "date_to": (end - timedelta(days=1)).date().isoformat(),
            "search": search or "",
            "category": category or "",
            "metrics": {
                "orders": int(totals["orders"] or 0),
                "units": int(totals["units"] or 0),
                "paid_amount": float(totals["paid_amount"] or 0),
                "average_ticket": float(totals["average_ticket"] or 0),
            },
            "daily_sales": [
                {
                    "date": str(row["sale_date"]),
                    "orders": int(row["orders"] or 0),
                    "paid_amount": float(row["paid_amount"] or 0),
                }
                for row in daily_rows
            ],
            "top_skus": [
                {
                    "sku": row["sku"],
                    "title": row["title"],
                    "units": int(row["units"] or 0),
                    "gross_sales": float(row["gross_sales"] or 0),
                }
                for row in top_skus
            ],
            "order_statuses": [
                {"status": row["status"], "orders": int(row["orders"] or 0)}
                for row in status_rows
            ],
            "categories": categories,
        }
    )


@app.get("/api/products/models")
def product_models(
    days: int = Query(default=30, ge=1, le=730),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(status_code=500, content={"error": "database_not_configured"})

    try:
        start, end = parse_date_range(date_from, date_to, days)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    search_value = normalize_search(search)
    category_value = normalize_search(category)

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                WITH parsed_items AS (
                    SELECT
                        o.id AS order_id,
                        oi.seller_sku,
                        oi.title,
                        oi.quantity,
                        oi.unit_price,
                        CASE
                            WHEN oi.seller_sku IS NULL OR BTRIM(oi.seller_sku) = ''
                                THEN 'SIN MODELO'
                            WHEN POSITION('-' IN oi.seller_sku) > 0
                                THEN SPLIT_PART(UPPER(BTRIM(oi.seller_sku)), '-', 1)
                            ELSE UPPER(BTRIM(oi.seller_sku))
                        END AS product_model,
                        CASE
                            WHEN ARRAY_LENGTH(STRING_TO_ARRAY(oi.seller_sku, '-'), 1) >= 2
                                THEN SPLIT_PART(UPPER(BTRIM(oi.seller_sku)), '-', 2)
                            ELSE NULL
                        END AS product_color,
                        CASE
                            WHEN ARRAY_LENGTH(STRING_TO_ARRAY(oi.seller_sku, '-'), 1) >= 3
                                THEN (
                                    STRING_TO_ARRAY(UPPER(BTRIM(oi.seller_sku)), '-')
                                )[ARRAY_LENGTH(STRING_TO_ARRAY(oi.seller_sku, '-'), 1)]
                            ELSE NULL
                        END AS product_size
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    WHERE o.marketplace = 'MERCADO_LIBRE'
                      AND o.date_created >= :start
                      AND o.date_created < :end
                      AND COALESCE(o.status, '') NOT IN ('cancelled', 'invalid')
                      AND (
                          :search_value = ''
                          OR UPPER(COALESCE(oi.seller_sku, '')) LIKE :search_like
                          OR UPPER(COALESCE(oi.title, '')) LIKE :search_like
                          OR UPPER(
                              CASE
                                  WHEN POSITION('-' IN COALESCE(oi.seller_sku, '')) > 0
                                      THEN SPLIT_PART(BTRIM(oi.seller_sku), '-', 1)
                                  ELSE BTRIM(COALESCE(oi.seller_sku, ''))
                              END
                          ) LIKE :search_like
                      )
                      AND (
                          :category_value = ''
                          OR UPPER(COALESCE(oi.raw_data #>> '{item,category_id}', '')) LIKE :category_like
                          OR UPPER(COALESCE(oi.raw_data #>> '{item,domain_id}', '')) LIKE :category_like
                          OR UPPER(COALESCE(oi.title, '')) LIKE :category_like
                      )
                )
                SELECT
                    product_model,
                    MAX(title) AS example_title,
                    COUNT(DISTINCT seller_sku) AS sku_count,
                    COUNT(DISTINCT product_color)
                        FILTER (WHERE product_color IS NOT NULL) AS color_count,
                    COUNT(DISTINCT product_size)
                        FILTER (WHERE product_size IS NOT NULL) AS size_count,
                    COALESCE(SUM(quantity), 0) AS units,
                    COALESCE(SUM(quantity * unit_price), 0) AS gross_sales,
                    COUNT(DISTINCT order_id) AS orders
                FROM parsed_items
                GROUP BY product_model
                ORDER BY units DESC, gross_sales DESC
                LIMIT :limit
                """
            ),
            {
                "start": start,
                "end": end,
                "search_value": search_value,
                "search_like": f"%{search_value}%",
                "category_value": category_value,
                "category_like": f"%{category_value}%",
                "limit": limit,
            },
        ).mappings().all()

    return JSONResponse(
        content={
            "status": "ok",
            "date_from": start.date().isoformat(),
            "date_to": (end - timedelta(days=1)).date().isoformat(),
            "models": [
                {
                    "model": row["product_model"],
                    "title": row["example_title"],
                    "sku_count": int(row["sku_count"] or 0),
                    "color_count": int(row["color_count"] or 0),
                    "size_count": int(row["size_count"] or 0),
                    "units": int(row["units"] or 0),
                    "gross_sales": float(row["gross_sales"] or 0),
                    "orders": int(row["orders"] or 0),
                }
                for row in rows
            ],
        }
    )


@app.get("/api/products/models/{model}")
def product_model_detail(
    model: str,
    days: int = Query(default=30, ge=1, le=365),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    since = utcnow() - timedelta(days=days)
    normalized_model = model.strip().upper()

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT
                    UPPER(BTRIM(oi.seller_sku)) AS sku,
                    MAX(oi.title) AS title,
                    CASE
                        WHEN ARRAY_LENGTH(STRING_TO_ARRAY(oi.seller_sku, '-'), 1) >= 2
                            THEN SPLIT_PART(
                                UPPER(BTRIM(oi.seller_sku)),
                                '-',
                                2
                            )
                        ELSE NULL
                    END AS color,
                    CASE
                        WHEN ARRAY_LENGTH(STRING_TO_ARRAY(oi.seller_sku, '-'), 1) >= 3
                            THEN (
                                STRING_TO_ARRAY(
                                    UPPER(BTRIM(oi.seller_sku)),
                                    '-'
                                )
                            )[ARRAY_LENGTH(STRING_TO_ARRAY(oi.seller_sku, '-'), 1)]
                        ELSE NULL
                    END AS size,
                    COALESCE(SUM(oi.quantity), 0) AS units,
                    COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS gross_sales,
                    COUNT(DISTINCT o.external_order_id) AS orders
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.marketplace = 'MERCADO_LIBRE'
                  AND o.date_created >= :since
                  AND COALESCE(o.status, '') NOT IN ('cancelled', 'invalid')
                  AND (
                      CASE
                          WHEN POSITION('-' IN oi.seller_sku) > 0
                              THEN SPLIT_PART(UPPER(BTRIM(oi.seller_sku)), '-', 1)
                          ELSE UPPER(BTRIM(oi.seller_sku))
                      END
                  ) = :model
                GROUP BY
                    UPPER(BTRIM(oi.seller_sku)),
                    color,
                    size
                ORDER BY units DESC, sku
                """
            ),
            {"since": since, "model": normalized_model},
        ).mappings().all()

    if not rows:
        return JSONResponse(
            status_code=404,
            content={"error": "model_not_found", "model": normalized_model},
        )

    return JSONResponse(
        content={
            "status": "ok",
            "model": normalized_model,
            "days": days,
            "variants": [
                {
                    "sku": row["sku"],
                    "title": row["title"],
                    "color": row["color"],
                    "size": row["size"],
                    "units": int(row["units"] or 0),
                    "gross_sales": float(row["gross_sales"] or 0),
                    "orders": int(row["orders"] or 0),
                }
                for row in rows
            ],
        }
    )


def full_replenishment_rows(
    session,
    search_value: str = "",
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            WITH sales AS (
                SELECT
                    UPPER(BTRIM(oi.seller_sku)) AS sku,
                    COALESCE(SUM(
                        CASE
                            WHEN o.date_created >= :since_7
                            THEN oi.quantity ELSE 0
                        END
                    ), 0) AS sales_7,
                    COALESCE(SUM(
                        CASE
                            WHEN o.date_created >= :since_14
                            THEN oi.quantity ELSE 0
                        END
                    ), 0) AS sales_14,
                    COALESCE(SUM(
                        CASE
                            WHEN o.date_created >= :since_30
                            THEN oi.quantity ELSE 0
                        END
                    ), 0) AS sales_30
                FROM order_items oi
                JOIN orders o ON o.id = oi.order_id
                WHERE o.marketplace = 'MERCADO_LIBRE'
                  AND o.date_created >= :since_30
                  AND COALESCE(o.status, '') NOT IN (
                      'cancelled',
                      'invalid'
                  )
                  AND oi.seller_sku IS NOT NULL
                GROUP BY UPPER(BTRIM(oi.seller_sku))
            )
            SELECT
                fi.inventory_id,
                fi.item_id,
                fi.variation_id,
                fi.sku,
                fi.title,
                fi.available_quantity,
                fi.not_available_quantity,
                COALESCE(s.sales_7, 0) AS sales_7,
                COALESCE(s.sales_14, 0) AS sales_14,
                COALESCE(s.sales_30, 0) AS sales_30
            FROM full_inventory fi
            LEFT JOIN sales s
              ON s.sku = UPPER(BTRIM(fi.sku))
            WHERE (
                :search_value = ''
                OR UPPER(COALESCE(fi.sku, '')) LIKE :search_like
                OR UPPER(COALESCE(fi.title, '')) LIKE :search_like
                OR UPPER(fi.inventory_id) LIKE :search_like
            )
            ORDER BY COALESCE(s.sales_30, 0) DESC, fi.sku
            """
        ),
        {
            "since_7": utcnow() - timedelta(days=7),
            "since_14": utcnow() - timedelta(days=14),
            "since_30": utcnow() - timedelta(days=30),
            "search_value": search_value,
            "search_like": f"%{search_value}%",
        },
    ).mappings().all()

    result: list[dict[str, Any]] = []

    for row in rows:
        sales_7 = int(row["sales_7"] or 0)
        sales_14 = int(row["sales_14"] or 0)
        sales_30 = int(row["sales_30"] or 0)
        available = int(row["available_quantity"] or 0)

        projected_7 = sales_7 * 30 / 7
        projected_14 = sales_14 * 30 / 14

        # Suaviza una aceleración reciente:
        # ejemplo: 31 ventas en 30 días y 21 en 7 días
        # proyectado semanal = 90; promedio con histórico = 60.5.
        adjusted_7 = (sales_30 + projected_7) / 2
        adjusted_14 = (sales_30 + projected_14) / 2

        target_30_days = math.ceil(max(
            float(sales_30),
            adjusted_7,
            adjusted_14,
        ))

        suggested_shipment = max(0, target_30_days - available)

        result.append({
            "inventory_id": row["inventory_id"],
            "item_id": row["item_id"],
            "variation_id": row["variation_id"],
            "sku": row["sku"],
            "title": row["title"],
            "available_quantity": available,
            "not_available_quantity": int(
                row["not_available_quantity"] or 0
            ),
            "sales_7": sales_7,
            "sales_14": sales_14,
            "sales_30": sales_30,
            "projected_7": round(projected_7, 2),
            "projected_14": round(projected_14, 2),
            "target_30_days": target_30_days,
            "suggested_shipment": suggested_shipment,
        })

    return result


@app.post("/sync/mercadolibre/full")
async def start_full_sync() -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    with SessionLocal() as session:
        account = get_account(session)
        if account is None:
            return JSONResponse(
                status_code=400,
                content={"error": "mercadolibre_not_connected"},
            )

        active_runs = session.scalars(
            select(FullSyncRun).where(
                FullSyncRun.status.in_(["PENDING", "RUNNING"])
            )
        ).all()

        for active in active_runs:
            task = full_sync_tasks.get(active.id)
            if task is not None and not task.done():
                return JSONResponse(
                    status_code=409,
                    content={
                        "status": "already_running",
                        "run_id": active.id,
                    },
                )

            # The database says RUNNING, but no process owns it.
            # This happens after a Railway deployment or restart.
            active.status = "INTERRUPTED"
            active.finished_at = utcnow()
            active.last_error = (
                "Ejecución anterior interrumpida por reinicio "
                "del servidor."
            )

        session.commit()

        run = FullSyncRun(id=str(uuid.uuid4()), status="PENDING")
        session.add(run)
        session.commit()
        run_id = run.id

    task = asyncio.create_task(sync_full_inventory_run(run_id))
    full_sync_tasks[run_id] = task

    return JSONResponse(
        status_code=202,
        content={"status": "queued", "run_id": run_id},
    )


@app.get("/sync/mercadolibre/full/status")
def full_sync_status() -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    with SessionLocal() as session:
        run = session.scalar(
            select(FullSyncRun)
            .order_by(FullSyncRun.created_at.desc())
            .limit(1)
        )

        if run is None:
            return JSONResponse(content={"status": "NEVER_RUN"})

        if run.status in ("PENDING", "RUNNING"):
            task = full_sync_tasks.get(run.id)
            if task is None or task.done():
                run.status = "INTERRUPTED"
                run.finished_at = utcnow()
                run.last_error = (
                    "La actualización fue interrumpida por un "
                    "reinicio del servidor."
                )
                session.commit()

        progress = 0.0
        if run.inventories_found:
            progress = round(
                run.inventories_processed
                / run.inventories_found
                * 100,
                2,
            )

        return JSONResponse(content={
            "run_id": run.id,
            "status": run.status,
            "items_found": run.items_found,
            "inventories_found": run.inventories_found,
            "inventories_processed": run.inventories_processed,
            "progress_percent": progress,
            "started_at": (
                run.started_at.isoformat()
                if run.started_at else None
            ),
            "finished_at": (
                run.finished_at.isoformat()
                if run.finished_at else None
            ),
            "last_error": run.last_error,
            "task_active": bool(
                full_sync_tasks.get(run.id)
                and not full_sync_tasks[run.id].done()
            ),
        })


@app.get("/api/full/sku-diagnostics")
def full_sku_diagnostics() -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    with SessionLocal() as session:
        totals = session.execute(
            text(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (
                        WHERE sku IS NOT NULL
                          AND BTRIM(sku) <> ''
                    ) AS with_sku,
                    COUNT(*) FILTER (
                        WHERE sku IS NULL
                           OR BTRIM(sku) = ''
                    ) AS without_sku,
                    COUNT(DISTINCT SPLIT_PART(sku, '-', 1))
                        FILTER (
                            WHERE sku IS NOT NULL
                              AND BTRIM(sku) <> ''
                        ) AS distinct_models
                FROM full_inventory
                """
            )
        ).mappings().one()

    return JSONResponse(content={
        "total": int(totals["total"] or 0),
        "with_sku": int(totals["with_sku"] or 0),
        "without_sku": int(totals["without_sku"] or 0),
        "distinct_models": int(totals["distinct_models"] or 0),
    })


@app.get("/api/full/inventory")
def full_inventory_report(
    search: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=5000, ge=1, le=20000),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    since = utcnow() - timedelta(days=days)
    search_value = (search or "").strip().upper()

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                WITH sales AS (
                    SELECT
                        UPPER(BTRIM(oi.seller_sku)) AS sku,
                        COALESCE(SUM(oi.quantity), 0) AS units_sold
                    FROM order_items oi
                    JOIN orders o ON o.id = oi.order_id
                    WHERE o.marketplace = 'MERCADO_LIBRE'
                      AND o.date_created >= :since
                      AND COALESCE(o.status, '') NOT IN (
                          'cancelled',
                          'invalid'
                      )
                      AND oi.seller_sku IS NOT NULL
                    GROUP BY UPPER(BTRIM(oi.seller_sku))
                )
                SELECT
                    fi.inventory_id,
                    fi.item_id,
                    fi.variation_id,
                    fi.sku,
                    fi.title,
                    fi.category_id,
                    fi.total_quantity,
                    fi.available_quantity,
                    fi.not_available_quantity,
                    fi.last_synced_at,
                    COALESCE(s.units_sold, 0) AS units_sold,
                    CASE
                        WHEN COALESCE(s.units_sold, 0) > 0
                            THEN ROUND(
                                fi.available_quantity::numeric
                                / (s.units_sold::numeric / :days),
                                1
                            )
                        ELSE NULL
                    END AS days_of_stock
                FROM full_inventory fi
                LEFT JOIN sales s
                  ON s.sku = UPPER(BTRIM(fi.sku))
                WHERE (
                    :search_value = ''
                    OR UPPER(COALESCE(fi.sku, ''))
                        LIKE :search_like
                    OR UPPER(COALESCE(fi.title, ''))
                        LIKE :search_like
                    OR UPPER(fi.inventory_id)
                        LIKE :search_like
                )
                ORDER BY
                    CASE
                        WHEN COALESCE(s.units_sold, 0) > 0
                            THEN fi.available_quantity::numeric
                                 / (s.units_sold::numeric / :days)
                        ELSE 999999
                    END ASC,
                    COALESCE(s.units_sold, 0) DESC
                LIMIT :limit
                """
            ),
            {
                "since": since,
                "days": days,
                "search_value": search_value,
                "search_like": f"%{search_value}%",
                "limit": limit,
            },
        ).mappings().all()

    return JSONResponse(content={
        "status": "ok",
        "days": days,
        "items": [
            {
                "inventory_id": row["inventory_id"],
                "item_id": row["item_id"],
                "variation_id": row["variation_id"],
                "sku": row["sku"],
                "title": row["title"],
                "category_id": row["category_id"],
                "total_quantity": int(
                    row["total_quantity"] or 0
                ),
                "available_quantity": int(
                    row["available_quantity"] or 0
                ),
                "not_available_quantity": int(
                    row["not_available_quantity"] or 0
                ),
                "units_sold": int(row["units_sold"] or 0),
                "daily_average": round(
                    float(row["units_sold"] or 0) / days,
                    2,
                ),
                "days_of_stock": (
                    float(row["days_of_stock"])
                    if row["days_of_stock"] is not None
                    else None
                ),
                "last_synced_at": (
                    row["last_synced_at"].isoformat()
                    if row["last_synced_at"] else None
                ),
            }
            for row in rows
        ],
    })


@app.get("/api/full/replenishment")
def full_replenishment(
    search: str | None = Query(default=None),
) -> JSONResponse:
    if SessionLocal is None:
        return JSONResponse(
            status_code=500,
            content={"error": "database_not_configured"},
        )

    search_value = (search or "").strip().upper()

    with SessionLocal() as session:
        rows = full_replenishment_rows(session, search_value)

    return JSONResponse(content={
        "status": "ok",
        "method": (
            "Mayor entre ventas 30 días y promedio suavizado "
            "con ritmos de 7 y 14 días."
        ),
        "items": rows,
    })


@app.get("/api/full/shipment.xlsx")
def download_full_shipment(
    search: str | None = Query(default=None),
) -> StreamingResponse:
    if SessionLocal is None:
        return StreamingResponse(
            io.BytesIO(b""),
            status_code=500,
            media_type="application/octet-stream",
        )

    search_value = (search or "").strip().upper()

    with SessionLocal() as session:
        rows = full_replenishment_rows(session, search_value)

    rows_to_send = [
        row for row in rows
        if row["suggested_shipment"] > 0
    ]

    output = io.BytesIO()

    import xlsxwriter

    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    worksheet = workbook.add_worksheet("Envio FULL sugerido")

    title_format = workbook.add_format({
        "bold": True,
        "font_size": 16,
        "font_color": "#FFFFFF",
        "bg_color": "#111827",
        "align": "left",
        "valign": "vcenter",
    })
    subtitle_format = workbook.add_format({
        "font_color": "#475467",
        "italic": True,
    })
    header_format = workbook.add_format({
        "bold": True,
        "font_color": "#FFFFFF",
        "bg_color": "#344054",
        "border": 1,
        "align": "center",
        "valign": "vcenter",
    })
    text_format = workbook.add_format({
        "border": 1,
        "valign": "top",
    })
    integer_format = workbook.add_format({
        "border": 1,
        "num_format": "0",
        "align": "right",
    })
    decimal_format = workbook.add_format({
        "border": 1,
        "num_format": "0.00",
        "align": "right",
    })
    send_format = workbook.add_format({
        "bold": True,
        "border": 1,
        "num_format": "0",
        "align": "right",
        "bg_color": "#ECFDF3",
        "font_color": "#067647",
    })

    worksheet.merge_range(
        "A1:N1",
        "GETAC — Envío sugerido a Mercado Libre FULL",
        title_format,
    )
    worksheet.write(
        "A2",
        (
            "Objetivo: cubrir 30 días usando la mayor demanda entre "
            "ventas de 30 días y tendencias suavizadas de 7 y 14 días."
        ),
        subtitle_format,
    )
    worksheet.write(
        "A3",
        f"Generado: {utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        subtitle_format,
    )

    headers = [
        "SKU",
        "Producto",
        "Inventory ID",
        "Item ID",
        "Variation ID",
        "Stock disponible FULL",
        "No disponible",
        "Ventas 7 días",
        "Ventas 14 días",
        "Ventas 30 días",
        "Proyección ritmo 7 días",
        "Proyección ritmo 14 días",
        "Objetivo stock 30 días",
        "Cantidad sugerida a enviar",
    ]

    start_row = 4
    for col, header in enumerate(headers):
        worksheet.write(start_row, col, header, header_format)

    for row_index, row in enumerate(rows_to_send, start=start_row + 1):
        worksheet.write(row_index, 0, row["sku"] or "", text_format)
        worksheet.write(row_index, 1, row["title"] or "", text_format)
        worksheet.write(row_index, 2, row["inventory_id"], text_format)
        worksheet.write(row_index, 3, row["item_id"] or "", text_format)
        worksheet.write(
            row_index, 4, row["variation_id"] or "", text_format
        )
        worksheet.write_number(
            row_index, 5, row["available_quantity"], integer_format
        )
        worksheet.write_number(
            row_index, 6, row["not_available_quantity"], integer_format
        )
        worksheet.write_number(
            row_index, 7, row["sales_7"], integer_format
        )
        worksheet.write_number(
            row_index, 8, row["sales_14"], integer_format
        )
        worksheet.write_number(
            row_index, 9, row["sales_30"], integer_format
        )
        worksheet.write_number(
            row_index, 10, row["projected_7"], decimal_format
        )
        worksheet.write_number(
            row_index, 11, row["projected_14"], decimal_format
        )
        worksheet.write_number(
            row_index, 12, row["target_30_days"], integer_format
        )
        worksheet.write_number(
            row_index, 13, row["suggested_shipment"], send_format
        )

    worksheet.freeze_panes(start_row + 1, 0)
    worksheet.autofilter(
        start_row,
        0,
        start_row + max(len(rows_to_send), 1),
        len(headers) - 1,
    )
    worksheet.set_column("A:A", 22)
    worksheet.set_column("B:B", 48)
    worksheet.set_column("C:E", 20)
    worksheet.set_column("F:J", 17)
    worksheet.set_column("K:N", 22)
    worksheet.set_row(0, 28)

    total_row = start_row + len(rows_to_send) + 2
    worksheet.write(total_row, 12, "TOTAL A ENVIAR", header_format)
    worksheet.write_formula(
        total_row,
        13,
        f"=SUM(N{start_row + 2}:N{start_row + len(rows_to_send) + 1})",
        send_format,
    )

    workbook.close()
    output.seek(0)

    filename = (
        "GETAC_envio_FULL_"
        f"{utcnow().strftime('%Y-%m-%d')}.xlsx"
    )

    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.get("/full", response_class=HTMLResponse)
def full_page() -> HTMLResponse:
    return HTMLResponse(content=r"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GETAC ERP — Inventario FULL</title>
<style>
:root{--bg:#f4f6f8;--panel:#fff;--text:#17202a;--muted:#667085;
--border:#e6eaf0;--dark:#111827;--red:#b42318;--amber:#b54708;
--green:#067647}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,-apple-system,BlinkMacSystemFont,
"Segoe UI",sans-serif;background:var(--bg);color:var(--text)}
.layout{display:grid;grid-template-columns:230px 1fr;min-height:100vh}
.sidebar{background:var(--dark);color:#fff;padding:28px 20px}
.brand{font-size:22px;font-weight:800;letter-spacing:.08em}
.brand small{display:block;font-size:11px;opacity:.55;margin-top:4px}
.nav{margin-top:32px;display:grid;gap:8px}
.nav a{color:rgba(255,255,255,.72);text-decoration:none;
padding:12px 14px;border-radius:10px;font-size:14px}
.nav a.active{background:rgba(255,255,255,.12);color:#fff;font-weight:700}
.main{padding:28px;overflow:hidden}
.top{display:flex;justify-content:space-between;align-items:center;
gap:16px;flex-wrap:wrap;margin-bottom:20px}
h1{margin:0;font-size:28px}.sub{color:var(--muted);margin-top:5px}
.controls{display:flex;gap:10px;flex-wrap:wrap}
input,select,button{border:1px solid var(--border);background:#fff;
padding:10px 12px;border-radius:10px;font-size:14px}
input{min-width:260px}button{font-weight:700;cursor:pointer}
.panel{background:#fff;border:1px solid var(--border);border-radius:16px;
padding:20px;box-shadow:0 10px 30px rgba(16,24,40,.06)}
.status{margin-bottom:16px}.bar{height:9px;border-radius:99px;
background:#eef1f5;overflow:hidden;margin-top:10px}
.bar div{height:100%;width:0;background:var(--dark)}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;
margin-bottom:16px}.card{background:#fff;border:1px solid var(--border);
border-radius:14px;padding:16px}.label{font-size:13px;color:var(--muted)}
.value{font-size:26px;font-weight:800;margin-top:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:11px 8px;border-bottom:1px solid var(--border);text-align:left}
th{color:var(--muted);position:sticky;top:0;background:#fff}
.num{text-align:right}.risk-high{color:var(--red);font-weight:800}
.risk-mid{color:var(--amber);font-weight:800}
.risk-ok{color:var(--green);font-weight:800}
.table-wrap{overflow:auto;max-height:65vh}
.error{display:none;background:#fff1f1;color:#9c2323;padding:12px;
border-radius:10px;margin-bottom:14px}
@media(max-width:900px){.layout{grid-template-columns:1fr}.sidebar{display:none}
.summary{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar">
<div class="brand">GETAC<small>ERP & ANALYTICS</small></div>
<nav class="nav">
<a href="/dashboard">Dashboard</a>
<a class="active" href="/full">Inventario FULL</a>
<a href="/automation">Automatizaciones</a>
<a href="/docs">API y sincronización</a>
</nav>
</aside>
<main class="main">
<div class="top">
<div><h1>Inventario FULL</h1>
<div class="sub">Stock FULL relacionado con SKU y ventas recientes</div></div>
<div class="controls">
<select id="days"><option value="30" selected>Ventas 30 días</option>
<option value="7">Ventas 7 días</option>
<option value="60">Ventas 60 días</option>
<option value="90">Ventas 90 días</option></select>
<input id="search" type="search" placeholder="Buscar SKU, producto o inventory ID">
<button onclick="loadInventory()">Buscar</button>
<button onclick="startSync()">Actualizar / reiniciar stock FULL</button>
<button onclick="downloadShipment()">Descargar envío sugerido</button>
</div>
</div>
<div id="error" class="error"></div>
<div class="panel status">
<strong>Actualización de FULL</strong>
<div id="syncText" class="sub">Consultando estado…</div>
<div class="bar"><div id="progress"></div></div>
</div>
<section class="summary">
<div class="card"><div class="label">SKUs FULL</div>
<div id="skuCount" class="value">0</div></div>
<div class="card"><div class="label">Stock disponible</div>
<div id="stockTotal" class="value">0</div></div>
<div class="card"><div class="label">Ventas del periodo</div>
<div id="salesTotal" class="value">0</div></div>
<div class="card"><div class="label">SKUs para enviar</div>
<div id="riskCount" class="value">0</div></div>
</section>
<div class="panel">
<div class="table-wrap">
<table>
<thead><tr>
<th>SKU</th><th>Producto</th><th>Inventory ID</th>
<th class="num">Stock FULL</th><th class="num">No disponible</th>
<th class="num">Ventas 7d</th><th class="num">Ventas 30d</th>
<th class="num">Objetivo 30d</th><th class="num">Enviar</th>
<th class="num">Días de stock</th>
</tr></thead>
<tbody id="body"></tbody>
</table>
</div>
</div>
</main>
</div>
<script>
const integer=new Intl.NumberFormat('es-MX');
function esc(v){return String(v??'').replaceAll('&','&amp;')
.replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')}
function showError(v){const e=document.getElementById('error');
e.textContent=v;e.style.display='block'}
async function loadInventory(){
document.getElementById('error').style.display='none';
const days=document.getElementById('days').value;
const search=document.getElementById('search').value.trim();
try{
const p=new URLSearchParams();
if(search)p.set('search',search);
const r=await fetch('/api/full/replenishment?'+p.toString(),{cache:'no-store'});
if(!r.ok)throw new Error('Error '+r.status);
const d=await r.json(),items=d.items||[];
document.getElementById('skuCount').textContent=integer.format(items.length);
document.getElementById('stockTotal').textContent=integer.format(
items.reduce((a,x)=>a+x.available_quantity,0));
document.getElementById('salesTotal').textContent=integer.format(
items.reduce((a,x)=>a+x.sales_30,0));
document.getElementById('riskCount').textContent=integer.format(
items.filter(x=>x.suggested_shipment>0).length);
document.getElementById('body').innerHTML=items.map(x=>{
let cls='';const daysStock=x.sales_30>0?
x.available_quantity/(x.sales_30/30):null;
if(daysStock!==null){
cls=daysStock<=15?'risk-high':daysStock<=30?'risk-mid':'risk-ok'}
return `<tr><td><strong>${esc(x.sku||'SIN SKU')}</strong></td>
<td>${esc(x.title||'')}</td><td>${esc(x.inventory_id)}</td>
<td class="num">${integer.format(x.available_quantity)}</td>
<td class="num">${integer.format(x.not_available_quantity)}</td>
<td class="num">${integer.format(x.sales_7)}</td>
<td class="num">${integer.format(x.sales_30)}</td>
<td class="num">${integer.format(x.target_30_days)}</td>
<td class="num"><strong>${integer.format(x.suggested_shipment)}</strong></td>
<td class="num ${cls}">${
x.sales_30===0?'Sin ventas':
(x.available_quantity/(x.sales_30/30)).toFixed(1)
}</td></tr>`}).join('');
}catch(e){showError('No se pudo cargar FULL: '+e.message)}
}
function downloadShipment(){
const search=document.getElementById('search').value.trim();
const p=new URLSearchParams();
if(search)p.set('search',search);
window.location.href='/api/full/shipment.xlsx?'+p.toString();
}
async function startSync(){
try{
const r=await fetch('/sync/mercadolibre/full',{method:'POST'});
const d=await r.json();
if(!r.ok&&r.status!==409)throw new Error(d.error||'Error '+r.status);
if(r.status===409){
document.getElementById('syncText').textContent=
'Ya existe una actualización activa.';
}
pollStatus();
}catch(e){showError('No se pudo iniciar: '+e.message)}
}
async function pollStatus(){
try{
const r=await fetch('/sync/mercadolibre/full/status',{cache:'no-store'});
if(!r.ok)return;
const d=await r.json();
const pct=d.progress_percent||0;
document.getElementById('progress').style.width=pct+'%';
document.getElementById('syncText').textContent=
`${d.status} · ${integer.format(d.inventories_processed||0)} de `+
`${integer.format(d.inventories_found||0)} inventarios · ${pct}%`+
(d.last_error?' · '+d.last_error:'');
if(['PENDING','RUNNING'].includes(d.status))setTimeout(pollStatus,5000);
if(d.status==='SUCCESS')loadInventory();
}catch(e){setTimeout(pollStatus,10000)}
}
document.getElementById('search').addEventListener('keydown',
e=>{if(e.key==='Enter')loadInventory()});
document.getElementById('days').addEventListener('change',loadInventory);
loadInventory();pollStatus();
</script>
</body></html>
""")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    html = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GETAC ERP — Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #667085;
      --border: #e6eaf0;
      --accent: #111827;
      --good: #16875d;
      --danger: #c73535;
      --shadow: 0 10px 30px rgba(16,24,40,.07);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }
    .layout { display: grid; grid-template-columns: 230px 1fr; min-height: 100vh; }
    .sidebar {
      background: #111827;
      color: white;
      padding: 28px 20px;
    }
    .brand { font-size: 22px; font-weight: 800; letter-spacing: .08em; }
    .brand small { display:block; font-size:11px; font-weight:600; opacity:.55; margin-top:4px; }
    .nav { margin-top: 32px; display: grid; gap: 8px; }
    .nav a {
      color: rgba(255,255,255,.72);
      text-decoration:none;
      padding:12px 14px;
      border-radius:10px;
      font-size:14px;
    }
    .nav a.active { background:rgba(255,255,255,.12); color:white; font-weight:700; }
    .main { padding: 28px; overflow: hidden; }
    .topbar {
      display:flex; justify-content:space-between; align-items:center;
      margin-bottom:24px; gap:16px;
    }
    h1 { margin:0; font-size:28px; }
    .subtitle { color:var(--muted); margin-top:5px; font-size:14px; }
    .controls { display:flex; gap:10px; }
    select, button {
      border:1px solid var(--border); background:white; padding:10px 12px;
      border-radius:10px; font-size:14px;
    }
    button { cursor:pointer; font-weight:700; }
    .cards {
      display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px;
      margin-bottom:16px;
    }
    .card, .panel {
      background:var(--panel); border:1px solid var(--border); border-radius:16px;
      box-shadow:var(--shadow);
    }
    .card { padding:18px; }
    .card .label { color:var(--muted); font-size:13px; }
    .card .value { font-size:27px; font-weight:800; margin-top:8px; }
    .card .foot { margin-top:8px; color:var(--muted); font-size:12px; }
    .grid {
      display:grid; grid-template-columns:minmax(0,2fr) minmax(300px,1fr);
      gap:16px; margin-bottom:16px;
    }
    .panel { padding:20px; min-width:0; }
    .panel h2 { font-size:16px; margin:0 0 16px; }
    .chart-wrap { height:310px; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th,td { padding:12px 8px; border-bottom:1px solid var(--border); text-align:left; }
    th { color:var(--muted); font-weight:700; }
    td.num, th.num { text-align:right; }
    .sku-title { max-width:300px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .loading {
      position:fixed; inset:0; background:rgba(244,246,248,.82); display:flex;
      align-items:center; justify-content:center; font-weight:800; z-index:20;
    }
    .error {
      display:none; background:#fff1f1; color:#9c2323; border:1px solid #ffd1d1;
      padding:12px 14px; border-radius:10px; margin-bottom:16px;
    }
    @media(max-width:1000px){
      .layout{grid-template-columns:1fr}
      .sidebar{display:none}
      .cards{grid-template-columns:repeat(2,minmax(0,1fr))}
      .grid{grid-template-columns:1fr}
    }
    @media(max-width:600px){
      .main{padding:16px}
      .cards{grid-template-columns:1fr}
      .topbar{align-items:flex-start; flex-direction:column}
    }
  </style>
</head>
<body>
<div id="loading" class="loading">Cargando dashboard…</div>
<div class="layout">
  <aside class="sidebar">
    <div class="brand">GETAC <small>ERP & ANALYTICS</small></div>
    <nav class="nav">
      <a class="active" href="/dashboard">Dashboard</a>
      <a href="/full">Inventario FULL</a>
      <a href="/automation">Automatizaciones</a>
      <a href="/docs">API y sincronización</a>
      <a href="/reports/mercadolibre/summary?days=30">Resumen JSON</a>
    </nav>
  </aside>
  <main class="main">
    <div class="topbar">
      <div>
        <h1>Dashboard de ventas</h1>
        <div class="subtitle">Mercado Libre · Cuenta GETAC</div>
      </div>
      <div class="controls" style="flex-wrap:wrap">
        <select id="days">
          <option value="7">Últimos 7 días</option>
          <option value="30" selected>Últimos 30 días</option>
          <option value="90">Últimos 90 días</option>
          <option value="365">Últimos 365 días</option>
          <option value="custom">Fechas específicas</option>
        </select>
        <input id="dateFrom" type="date" style="display:none;border:1px solid var(--border);padding:10px;border-radius:10px">
        <input id="dateTo" type="date" style="display:none;border:1px solid var(--border);padding:10px;border-radius:10px">
        <input id="searchInput" type="search" placeholder="Buscar SKU, modelo o producto"
               style="min-width:240px;border:1px solid var(--border);padding:10px;border-radius:10px">
        <select id="categoryFilter" style="min-width:200px">
          <option value="">Todas las categorías</option>
        </select>
        <button onclick="loadDashboard()">Aplicar filtros</button>
        <button onclick="clearFilters()">Limpiar</button>
      </div>
    </div>

    <div id="error" class="error"></div>

    <div class="panel" style="margin-bottom:16px">
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap">
        <div>
          <h2 style="margin-bottom:6px">Sincronización histórica</h2>
          <div id="syncStatus" class="subtitle">Sin trabajo activo</div>
        </div>
        <div style="display:flex;gap:10px">
          <button id="resumeButton" onclick="resumeHistoricalSync()" style="display:none">Reanudar</button>
          <button onclick="startHistoricalSync()">Sincronizar 365 días</button>
        </div>
      </div>
      <div style="margin-top:14px;background:#eef1f5;border-radius:999px;height:10px;overflow:hidden">
        <div id="syncProgress" style="height:100%;width:0%;background:#111827;transition:width .3s"></div>
      </div>
    </div>

    <section class="cards">
      <div class="card">
        <div class="label">Ventas del periodo</div>
        <div id="paidAmount" class="value">$0</div>
        <div id="periodLabel" class="foot">Últimos 30 días</div>
      </div>
      <div class="card">
        <div class="label">Órdenes</div>
        <div id="orders" class="value">0</div>
        <div id="averageTicket" class="foot">Ticket promedio: $0</div>
      </div>
      <div class="card">
        <div class="label">Unidades</div>
        <div id="units" class="value">0</div>
        <div id="unitsPerOrder" class="foot">0 por orden</div>
      </div>
      <div class="card">
        <div class="label">Periodo seleccionado</div>
        <div id="selectedRange" class="value" style="font-size:18px">—</div>
        <div id="filterSummary" class="foot">Sin filtros adicionales</div>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Ventas diarias</h2>
        <div class="chart-wrap"><canvas id="salesChart"></canvas></div>
      </div>
      <div class="panel">
        <h2>Estatus de las órdenes</h2>
        <div class="chart-wrap"><canvas id="statusChart"></canvas></div>
      </div>
    </section>

    <section class="panel" style="margin-bottom:16px">
      <h2>Top modelos agrupados</h2>
      <div class="subtitle" style="margin-bottom:12px">
        Ejemplo: MY2307-BLK-29 y MY2307-BLK-30 se muestran juntos como MY2307.
      </div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Modelo</th>
              <th>Producto</th>
              <th class="num">SKUs</th>
              <th class="num">Colores</th>
              <th class="num">Tallas</th>
              <th class="num">Unidades</th>
              <th class="num">Venta bruta</th>
            </tr>
          </thead>
          <tbody id="topModelBody"></tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Top 10 SKUs por unidades</h2>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>SKU</th>
              <th>Producto</th>
              <th class="num">Unidades</th>
              <th class="num">Venta bruta</th>
            </tr>
          </thead>
          <tbody id="topSkuBody"></tbody>
        </table>
      </div>
    </section>
  </main>
</div>

<script>
let salesChart;
let statusChart;

const money = new Intl.NumberFormat('es-MX', {
  style: 'currency', currency: 'MXN', maximumFractionDigits: 2
});
const integer = new Intl.NumberFormat('es-MX');

function showError(message) {
  const box = document.getElementById('error');
  box.textContent = message;
  box.style.display = 'block';
}

async function loadDashboard() {
  document.getElementById('loading').style.display = 'flex';
  document.getElementById('error').style.display = 'none';
  const daysValue = document.getElementById('days').value;
  const dateFrom = document.getElementById('dateFrom').value;
  const dateTo = document.getElementById('dateTo').value;
  const search = document.getElementById('searchInput').value.trim();
  const category = document.getElementById('categoryFilter').value;

  const params = new URLSearchParams();
  if (daysValue === 'custom') {
    if (!dateFrom || !dateTo) {
      showError('Selecciona la fecha inicial y final.');
      document.getElementById('loading').style.display = 'none';
      return;
    }
    params.set('date_from', dateFrom);
    params.set('date_to', dateTo);
  } else {
    params.set('days', daysValue);
  }
  if (search) params.set('search', search);
  if (category) params.set('category', category);

  try {
    const response = await fetch(`/api/dashboard/summary?${params.toString()}`, {cache:'no-store'});
    if (!response.ok) throw new Error(`Error ${response.status}`);
    const data = await response.json();
    const m = data.metrics;

    const categorySelect = document.getElementById('categoryFilter');
    const currentCategory = categorySelect.value;
    const knownOptions = new Set(
      Array.from(categorySelect.options).map(option => option.value)
    );
    (data.categories || []).forEach(categoryItem => {
      const value = categoryItem.id;
      if (!knownOptions.has(value)) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent =
          categoryItem.label || categoryItem.name || value;
        categorySelect.appendChild(option);
      }
    });
    categorySelect.value = currentCategory;

    document.getElementById('paidAmount').textContent = money.format(m.paid_amount);
    document.getElementById('orders').textContent = integer.format(m.orders);
    document.getElementById('units').textContent = integer.format(m.units);
    document.getElementById('averageTicket').textContent =
      `Ticket promedio: ${money.format(m.average_ticket)}`;
    document.getElementById('unitsPerOrder').textContent =
      `${m.orders ? (m.units / m.orders).toFixed(2) : '0'} por orden`;
    document.getElementById('selectedRange').textContent =
      `${data.date_from} a ${data.date_to}`;
    document.getElementById('filterSummary').textContent =
      [data.search ? `Búsqueda: ${data.search}` : '',
       data.category ? `Categoría: ${data.category}` : '']
      .filter(Boolean).join(' · ') || 'Sin filtros adicionales';
    document.getElementById('periodLabel').textContent =
      `${data.date_from} a ${data.date_to}`;

    const salesCtx = document.getElementById('salesChart');
    if (salesChart) salesChart.destroy();
    salesChart = new Chart(salesCtx, {
      type: 'line',
      data: {
        labels: data.daily_sales.map(x => x.date),
        datasets: [{
          label: 'Ventas',
          data: data.daily_sales.map(x => x.paid_amount),
          borderWidth: 2,
          tension: .28,
          fill: false
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {mode:'index', intersect:false},
        plugins: {
          legend: {display:false},
          tooltip: {callbacks:{label: ctx => money.format(ctx.parsed.y)}}
        },
        scales: {
          y: {ticks:{callback: value => money.format(value)}},
          x: {grid:{display:false}}
        }
      }
    });

    const statusCtx = document.getElementById('statusChart');
    if (statusChart) statusChart.destroy();
    statusChart = new Chart(statusCtx, {
      type: 'doughnut',
      data: {
        labels: data.order_statuses.map(x => x.status),
        datasets: [{data: data.order_statuses.map(x => x.orders)}]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins:{legend:{position:'bottom'}}
      }
    });

    const modelsResponse = await fetch(
      `/api/products/models?${params.toString()}&limit=50`,
      {cache:'no-store'}
    );
    if (!modelsResponse.ok) throw new Error(`Error modelos ${modelsResponse.status}`);
    const modelsData = await modelsResponse.json();

    document.getElementById('topModelBody').innerHTML = modelsData.models.map(row => `
      <tr>
        <td>
          <a href="/api/products/models/${encodeURIComponent(row.model)}?days=${days}"
             target="_blank"
             style="color:inherit;font-weight:800">
            ${escapeHtml(row.model)}
          </a>
        </td>
        <td class="sku-title" title="${escapeHtml(row.title || '')}">
          ${escapeHtml(row.title || '')}
        </td>
        <td class="num">${integer.format(row.sku_count)}</td>
        <td class="num">${integer.format(row.color_count)}</td>
        <td class="num">${integer.format(row.size_count)}</td>
        <td class="num">${integer.format(row.units)}</td>
        <td class="num">${money.format(row.gross_sales)}</td>
      </tr>
    `).join('');

    document.getElementById('topSkuBody').innerHTML = data.top_skus.map(row => `
      <tr>
        <td><strong>${escapeHtml(row.sku)}</strong></td>
        <td class="sku-title" title="${escapeHtml(row.title || '')}">
          ${escapeHtml(row.title || '')}
        </td>
        <td class="num">${integer.format(row.units)}</td>
        <td class="num">${money.format(row.gross_sales)}</td>
      </tr>
    `).join('');

  } catch (error) {
    showError(`No se pudo cargar el dashboard: ${error.message}`);
  } finally {
    document.getElementById('loading').style.display = 'none';
  }
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&','&amp;')
    .replaceAll('<','&lt;')
    .replaceAll('>','&gt;')
    .replaceAll('"','&quot;')
    .replaceAll("'","&#039;");
}


let currentSyncJobId = null;

async function startHistoricalSync() {
  try {
    const response = await fetch('/sync/mercadolibre/historical?days=365', {method:'POST'});
    const data = await response.json();
    if (response.status === 409 && data.job_id) {
      currentSyncJobId = data.job_id;
    } else if (!response.ok) {
      throw new Error(data.message || data.error || `Error ${response.status}`);
    } else {
      currentSyncJobId = data.job_id;
    }
    pollSyncStatus();
  } catch (error) {
    showError(`No se pudo iniciar la sincronización: ${error.message}`);
  }
}

async function discoverActiveSync() {
  try {
    const response = await fetch('/sync/jobs?limit=5', {cache:'no-store'});
    if (!response.ok) return;
    const data = await response.json();
    const latest = (data.jobs || [])[0];
    if (latest) {
      currentSyncJobId = latest.job_id;
      pollSyncStatus();
    }
  } catch (_) {}
}

async function resumeHistoricalSync() {
  if (!currentSyncJobId) return;
  try {
    const response = await fetch(`/sync/jobs/${currentSyncJobId}/resume`, {method:'POST'});
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `Error ${response.status}`);
    }
    document.getElementById('resumeButton').style.display = 'none';
    pollSyncStatus();
  } catch (error) {
    showError(`No se pudo reanudar: ${error.message}`);
  }
}

async function pollSyncStatus() {
  if (!currentSyncJobId) return;
  try {
    const response = await fetch(`/sync/jobs/${currentSyncJobId}`, {cache:'no-store'});
    if (!response.ok) return;
    const job = await response.json();
    document.getElementById('syncProgress').style.width = `${job.progress_percent || 0}%`;
    document.getElementById('syncStatus').textContent =
      `${job.status} · ${integer.format(job.orders_processed)} órdenes · ` +
      `${job.progress_percent}% (${job.chunks_completed}/${job.total_chunks} bloques)` +
      (job.last_error ? ` · ${job.last_error}` : '');

    const resumeButton = document.getElementById('resumeButton');
    resumeButton.style.display = ['ERROR','CANCELLED'].includes(job.status) ? 'inline-block' : 'none';

    if (['PENDING','RUNNING'].includes(job.status)) {
      setTimeout(pollSyncStatus, 5000);
    } else if (job.status === 'SUCCESS') {
      loadDashboard();
    }
  } catch (_) {
    setTimeout(pollSyncStatus, 10000);
  }
}


function updateDateControls() {
  const custom = document.getElementById('days').value === 'custom';
  document.getElementById('dateFrom').style.display = custom ? 'inline-block' : 'none';
  document.getElementById('dateTo').style.display = custom ? 'inline-block' : 'none';
}

function clearFilters() {
  document.getElementById('days').value = '30';
  document.getElementById('dateFrom').value = '';
  document.getElementById('dateTo').value = '';
  document.getElementById('searchInput').value = '';
  document.getElementById('categoryFilter').value = '';
  updateDateControls();
  loadDashboard();
}

document.getElementById('searchInput').addEventListener('keydown', event => {
  if (event.key === 'Enter') loadDashboard();
});

document.getElementById('days').addEventListener('change', () => {
  updateDateControls();
  if (document.getElementById('days').value !== 'custom') loadDashboard();
});

updateDateControls();
loadDashboard();
discoverActiveSync();
</script>
</body>
</html>
"""
    return HTMLResponse(content=html)
