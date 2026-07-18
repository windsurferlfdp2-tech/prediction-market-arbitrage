from typing import Any

from pydantic import BaseModel, Field


class RawEnvelope(BaseModel):
    exchange: str
    endpoint: str
    payload: dict[str, Any]


class PolymarketRawMarket(BaseModel):
    condition_id: str
    question: str
    active: bool
    closed: bool
    enable_order_book: bool
    tokens: list[dict[str, Any]] = Field(default_factory=list)
    market_slug: str | None = None


class PolymarketRawOrderBook(BaseModel):
    market: str
    asset_id: str
    timestamp: str
    bids: list[dict[str, str]]
    asks: list[dict[str, str]]
    min_order_size: str
    tick_size: str
    neg_risk: bool
    hash: str | None = None
    last_trade_price: str | None = None


class KalshiRawMarket(BaseModel):
    ticker: str
    market_type: str
    status: str
    title: str
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    event_ticker: str | None = None


class KalshiRawOrderBook(BaseModel):
    ticker: str
    orderbook_fp: dict[str, list[list[str]]]
