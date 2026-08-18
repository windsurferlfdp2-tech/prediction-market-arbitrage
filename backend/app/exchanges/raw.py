from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class RawEnvelope(BaseModel):
    exchange: str
    endpoint: str
    payload: dict[str, Any]


class PolymarketRawMarket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    condition_id: str = Field(validation_alias=AliasChoices("condition_id", "conditionId"))
    question: str
    active: bool
    closed: bool
    enable_order_book: bool = Field(
        default=False,
        validation_alias=AliasChoices("enable_order_book", "enableOrderBook"),
    )
    tokens: list[dict[str, Any]] = Field(default_factory=list)
    clob_token_ids: str | list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("clob_token_ids", "clobTokenIds"),
    )
    outcomes: str | list[str] | None = None
    market_slug: str | None = Field(
        default=None,
        validation_alias=AliasChoices("market_slug", "slug"),
    )


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
    title: str | None = None
    subtitle: str | None = None
    yes_sub_title: str | None = None
    no_sub_title: str | None = None
    event_ticker: str | None = None


class KalshiRawOrderBook(BaseModel):
    ticker: str
    orderbook_fp: dict[str, list[list[str]]]
