from fastapi.testclient import TestClient

from app.main import app


def test_local_cors_preflight_allows_frontend_origins() -> None:
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]

    with TestClient(app) as client:
        for origin in allowed_origins:
            response = client.options(
                "/market-matches/generate?data_mode=live",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert "POST" in response.headers["access-control-allow-methods"]
            assert "content-type" in response.headers["access-control-allow-headers"]


def test_local_cors_preflight_allows_paper_trade_endpoint() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/model-paper-trades/run?data_mode=test",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_opportunities_route_returns_read_only_estimates() -> None:
    with TestClient(app) as client:
        response = client.get("/opportunities")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert len(payload) >= 3
    assert all(item["title"].startswith("TEST:") for item in payload)
    assert all(str(item["same_market_key"]).startswith("TEST:") for item in payload)
    assert payload[0]["read_only_label"].startswith("Estimate only")


def test_health_route_labels_test_mode() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "test"
    assert payload["test_mode"] is True
    assert payload["read_only"] is True
    assert payload["exchanges"] == []


def test_query_param_can_switch_health_to_live_mode() -> None:
    with TestClient(app) as client:
        response = client.get("/health?data_mode=live")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "live"
    assert payload["test_mode"] is False
    assert payload["read_only"] is True
    assert {item["exchange"] for item in payload["exchanges"]} == {"polymarket", "kalshi"}


def test_query_param_can_switch_markets_to_test_mode() -> None:
    with TestClient(app) as client:
        response = client.get("/markets?data_mode=test")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 6
    assert all(item["title"].startswith("TEST:") for item in payload)
    assert all(item["same_market_key"].startswith("TEST:") for item in payload)


def test_analytics_route_returns_research_metrics() -> None:
    with TestClient(app) as client:
        client.get("/opportunities?data_mode=test")
        response = client.get("/analytics/opportunities?data_mode=test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_candidates_recorded"] >= 3
    assert "opportunities_detected_per_day" in payload
    assert "median_opportunity_duration_seconds" in payload
    assert "median_net_roi" in payload
    assert "maximum_theoretical_profit" in payload
    assert "percentage_lasting_over_1_seconds" in payload
    assert "percentage_lasting_over_3_seconds" in payload
    assert "percentage_lasting_over_5_seconds" in payload
    assert "percentage_lasting_over_10_seconds" in payload
    assert payload["paper_label"] == "TEST PAPER TRADE"
    assert payload["simulated_trade_count"] >= 3


def test_phase_2_paper_trades_and_order_book_status_routes() -> None:
    with TestClient(app) as client:
        client.get("/opportunities?data_mode=test")
        trades = client.get("/paper-trades?limit=5")
        statuses = client.get("/order-books/status")

    assert trades.status_code == 200
    assert trades.json()
    assert trades.json()[0]["label"] == "TEST PAPER TRADE"
    assert statuses.status_code == 200
    assert statuses.json()
    assert {item["transport"] for item in statuses.json()} == {"test"}


def test_market_match_routes_require_manual_review() -> None:
    with TestClient(app) as client:
        response = client.post("/market-matches/generate?data_mode=test")
        assert response.status_code == 200
        generated = response.json()

        assert generated
        assert all(item["status"] == "pending_review" for item in generated)
        assert all("polymarket_title" in item and "kalshi_title" in item for item in generated)
        assert all("polymarket_resolution_criteria" in item for item in generated)
        assert all("similarity_score" in item for item in generated)
        assert all("mismatches" in item for item in generated)

        review_id = generated[0]["id"]
        update = client.patch(
            f"/market-matches/{review_id}",
            json={"status": "verified_equivalent"},
        )
        assert update.status_code == 200
        assert update.json()["status"] == "verified_equivalent"

        listed = client.get("/market-matches?status=verified_equivalent&data_mode=test")
        assert listed.status_code == 200
        assert any(item["id"] == review_id for item in listed.json())


def test_model_paper_trade_run_route_is_paused_by_default() -> None:
    with TestClient(app) as client:
        for existing_model in client.get("/models").json():
            client.post(f"/models/{existing_model['id']}/retire")

        client.post("/models/dataset")
        model = client.post(
            "/models/train",
            json={"category": "general", "data_mode": "test", "model_type": "ensemble"},
        )
        assert model.status_code == 200
        approve = client.post(f"/models/{model.json()['id']}/approve-paper")
        assert approve.status_code == 400
        assert "approval thresholds" in approve.json()["detail"]
        predictions = client.post("/predictions/generate?data_mode=test")
        assert predictions.status_code == 200
        opportunities = client.post("/model-opportunities/generate?data_mode=test")
        assert opportunities.status_code == 200

        response = client.post("/model-paper-trades/run?data_mode=test")
        persisted = client.get("/model-paper-trades?data_mode=test")
        client.post(f"/models/{model.json()['id']}/retire")

    assert response.status_code == 400
    assert "MODEL PAPER TRADING PAUSED" in response.json()["detail"]
    assert persisted.status_code == 200
