#!/usr/bin/env python
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.config import settings  # noqa: E402
from app.models.domain import MarketCategory, ModelTrainingRequest  # noqa: E402
from app.persistence.database import AsyncSessionLocal, PredictionModelRecord, init_db  # noqa: E402
from app.services.prediction import PredictionService  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reproduce a Phase 3 model from registry metadata."
    )
    parser.add_argument("model_id", help="Existing prediction_models.id to reproduce")
    args = parser.parse_args()

    await init_db()
    async with AsyncSessionLocal() as session:
        record = await session.get(PredictionModelRecord, args.model_id)
    if record is None:
        raise SystemExit(f"model not found: {args.model_id}")

    metadata = record.metadata_payload
    seed = int(metadata.get("seed", settings.model_training_seed))
    service = PredictionService(settings, AsyncSessionLocal)
    reproduced = await service.train_model(
        ModelTrainingRequest(
            category=MarketCategory(record.category),
            data_mode="test",
            model_type="ensemble",
            seed=seed,
        )
    )
    print(f"reproduced_from={record.id}")
    print(f"new_model_id={reproduced.id}")
    print(f"status={reproduced.status.value}")
    print(f"seed={seed}")


if __name__ == "__main__":
    asyncio.run(main())
