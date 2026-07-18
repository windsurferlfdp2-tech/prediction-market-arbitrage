from fastapi.testclient import TestClient

from app.main import app


def test_opportunities_route_returns_read_only_estimates() -> None:
    client = TestClient(app)

    response = client.get("/opportunities")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["read_only_label"].startswith("Estimate only")
