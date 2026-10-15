"""Test helper: sign a TestClient in as a demo rider or the support agent (sets the signed session cookie)."""


def login(client, rider_id: str | None = None, support: bool = False):
    body = {"role": "support"} if support else {"rider_id": rider_id}
    r = client.post("/api/auth/login", json=body)
    assert r.status_code == 200, r.text
    return client


def logout(client):
    client.post("/api/auth/logout")
    client.cookies.clear()
    return client
