import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exchanges.kalshi import KalshiAdapter
from app.exchanges.polymarket import PolymarketAdapter
from app.logging import configure_logging
from app.models.domain import ArbitrageOpportunity, ExchangeHealth, Market
from app.services.scanner import ScannerService

configure_logging(settings.log_level)

scanner = ScannerService(settings, [PolymarketAdapter(settings), KalshiAdapter(settings)])

app = FastAPI(title="Prediction Market Arbitrage Scanner", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, object]:
    exchanges: list[ExchangeHealth] = await scanner.health()
    return {
        "ok": all(item.ok for item in exchanges),
        "mode": "fixtures" if settings.use_fixtures else "live",
        "read_only": True,
        "exchanges": exchanges,
    }


@app.get("/markets", response_model=list[Market])
async def markets() -> list[Market]:
    return await scanner.markets()


@app.get("/opportunities", response_model=list[ArbitrageOpportunity])
async def opportunities() -> list[ArbitrageOpportunity]:
    return await scanner.opportunities()


@app.get("/opportunities/{opportunity_id}", response_model=ArbitrageOpportunity)
async def opportunity(opportunity_id: str) -> ArbitrageOpportunity:
    result = await scanner.opportunity(opportunity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return result


@app.websocket("/ws/opportunities")
async def ws_opportunities(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(
                [item.model_dump(mode="json") for item in await scanner.opportunities()]
            )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
