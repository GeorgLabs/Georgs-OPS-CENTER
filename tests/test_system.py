def test_health_needs_no_login(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_processes_limit_is_validated(auth_client):
    assert auth_client.get("/api/system/processes", params={"limit": 0}).status_code == 422
    assert auth_client.get("/api/system/processes", params={"limit": 26}).status_code == 422
    assert len(auth_client.get("/api/system/processes", params={"limit": 3}).json()) <= 3
