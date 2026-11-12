r"""M5 - YOUR tests. `conftest.py` gives you `client` (not logged in) and `auth_client` (logged in).

Run them with:   .venv\Scripts\python -m pytest        (Linux: .venv/bin/python -m pytest)

Write at least one test for each of these. Make a test FAIL first (break your code on purpose),
then fix the code - a test you have never seen fail proves nothing.
"""


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


# TODO: a user cannot read another user's host (IDOR)  - hint: two users, one host, expect 404
# TODO: the 6th wrong password in a row is answered with 429
# TODO: registering with "is_admin": true does NOT make you an admin
# TODO: your own idea - what else could go wrong?
