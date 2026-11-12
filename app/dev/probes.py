"""The contract, written as code. Read it - it is the spec.

Each probe makes real HTTP requests against your app (in memory, with its own empty database)
and checks the answers. Three outcomes:

  pass   your code does this right
  todo   your endpoint still answers 501 "not built yet" - nothing wrong, just not done
  fail   it answers, but not what the contract says (the message tells you what it got)

M4 probes are *attacks*. "pass" means the attack is blocked, "fail" means it works against you.
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from app.models import Host, Metric, User


class Todo(Exception):  # noqa: N818 - reads better in the probes
    """The endpoint answered 501: not built yet."""


@dataclass
class Probe:
    id: str
    milestone: str
    title: str
    kind: str
    fn: Callable[[Ctx], None]


PROBES: list[Probe] = []


def probe(milestone: str, title: str, kind: str = "check"):
    def register(fn: Callable[[Ctx], None]):
        number = sum(1 for p in PROBES if p.milestone == milestone) + 1
        PROBES.append(Probe(f"{milestone}.{number}", milestone, title, kind, fn))
        return fn

    return register


# ------------------------------------------------------------------ helpers
@dataclass
class Actor:
    """A (pretend) person talking to the API."""

    client: TestClient
    username: str | None = None
    password: str | None = None
    token: str | None = None
    id: int | None = None


class Ctx:
    PASSWORD = "correct-horse-battery"

    def __init__(self, app, engine, settings) -> None:
        self.app = app
        self.engine = engine
        self.settings = settings
        self.run = secrets.token_hex(3)
        self._actors: dict[str, Actor] = {}
        self._failed: dict[str, Exception] = {}

    def client(self, token: str | None = None) -> TestClient:
        headers = {"x-mission-probe": "1"}  # keeps these requests out of the Traffic panel
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return TestClient(self.app, headers=headers)

    def db(self) -> Session:
        return Session(self.engine)

    def secret(self) -> str:
        return self.settings.secret_key.get_secret_value()

    def actor(self, name: str = "alice", *, required: bool = False) -> Actor:
        """A registered, logged-in user. Before M3 exists this quietly returns an anonymous
        client, so the M1/M2 probes can run without any login. required=True insists on a login."""
        if name in self._actors:
            return self._actors[name]
        if name in self._failed:
            if required:
                raise self._failed[name]
            return Actor(self.client())
        username = f"{name}_{self.run}"
        anon = self.client()
        try:
            reg = expect(
                anon.post("/api/auth/register", json={"username": username, "password": self.PASSWORD}),
                201,
                "register",
            )
            login = expect(
                anon.post("/api/auth/token", data={"username": username, "password": self.PASSWORD}),
                200,
                "login",
            )
            token = login.json()["access_token"]
            actor = Actor(self.client(token), username, self.PASSWORD, token, reg.json()["id"])
        except (Todo, AssertionError, KeyError, ValueError) as exc:
            self._failed[name] = exc  # remember it: do not hammer a broken endpoint again and again
            if required:
                raise
            return Actor(anon)
        self._actors[name] = actor
        return actor


def _detail(resp) -> str:
    try:
        return str(resp.json().get("detail", "not built yet"))
    except Exception:  # noqa: BLE001
        return "not built yet"


def _snippet(resp) -> str:
    try:
        return json.dumps(resp.json())[:220]
    except Exception:  # noqa: BLE001
        return resp.text[:220]


def expect(resp, code: int | tuple[int, ...], what: str):
    codes = (code,) if isinstance(code, int) else code
    if resp.status_code == 501 and 501 not in codes:
        raise Todo(_detail(resp))
    if resp.status_code not in codes:
        wanted = " or ".join(str(c) for c in codes)
        raise AssertionError(f"{what}: expected HTTP {wanted}, got {resp.status_code}: {_snippet(resp)}")
    return resp


def eq(got, wanted, what: str) -> None:
    if got != wanted:
        raise AssertionError(f"{what}: expected {wanted!r}, got {got!r}")


def new_host(actor: Actor, name: str | None = None, description: str = "") -> dict:
    name = name or f"host-{secrets.token_hex(3)}"
    resp = actor.client.post("/api/hosts", json={"name": name, "description": description})
    return expect(resp, 201, "POST /api/hosts").json()


def send_metric(client: TestClient, key: str, cpu=10.0, mem=20.0, disk=30.0):
    return client.post(
        "/api/ingest",
        headers={"X-API-Key": key},
        json={"cpu_percent": cpu, "memory_percent": mem, "disk_percent": disk},
    )


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_keys(item)


SECRET_KEYS = {"hashed_password", "password", "api_key_hash", "secret_key"}


# ================================================================== M1 - Hello, data
SYSTEM_TYPES = {
    "hostname": str,
    "os": str,
    "cpu_count": int,
    "cpu_percent": (int, float),
    "memory_percent": (int, float),
    "disk_percent": (int, float),
    "uptime_seconds": (int, float),
}


@probe("M1", "GET /api/health answers {'status': 'ok'} - without any login")
def m1_health(ctx: Ctx) -> None:
    resp = expect(ctx.client().get("/api/health"), 200, "GET /api/health")
    eq(resp.json(), {"status": "ok"}, "body of GET /api/health")


@probe("M1", "GET /api/system returns the machine's hostname, os, cpu/memory/disk and uptime")
def m1_system(ctx: Ctx) -> None:
    resp = expect(ctx.actor().client.get("/api/system"), 200, "GET /api/system")
    data = resp.json()
    missing = sorted(set(SYSTEM_TYPES) - set(data))
    assert not missing, f"missing fields in the answer: {missing}"
    for field, types in SYSTEM_TYPES.items():
        assert isinstance(data[field], types), f"{field} should be {types}, got {data[field]!r}"
    for field in ("cpu_percent", "memory_percent", "disk_percent"):
        assert 0 <= data[field] <= 100, f"{field} should be between 0 and 100, got {data[field]}"
    assert data["cpu_count"] >= 1, "cpu_count should be at least 1"


@probe("M1", "SystemInfo is a real Pydantic model with limits (visible in /docs as the response schema)")
def m1_system_schema(ctx: Ctx) -> None:
    spec = ctx.app.openapi()
    op = spec["paths"].get("/api/system", {}).get("get", {})
    ref = op.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
    assert "$ref" in ref, "GET /api/system has no response_model - add response_model=SystemInfo"
    props = spec["components"]["schemas"][ref["$ref"].split("/")[-1]].get("properties", {})
    if not props:
        raise Todo("SystemInfo has no fields yet")
    missing = sorted(set(SYSTEM_TYPES) - set(props))
    assert not missing, f"SystemInfo is missing fields: {missing}"
    for field in ("cpu_percent", "memory_percent", "disk_percent"):
        limits = (props[field].get("minimum"), props[field].get("maximum"))
        assert limits == (0, 100), f"{field} should be limited to 0..100 with Field(ge=0, le=100), has {limits}"
    assert props["cpu_count"].get("minimum") == 1, "cpu_count should have ge=1"


@probe("M1", "GET /api/system/processes returns the 5 busiest processes by default")
def m1_processes_default(ctx: Ctx) -> None:
    resp = expect(ctx.actor().client.get("/api/system/processes"), 200, "GET /api/system/processes")
    data = resp.json()
    assert isinstance(data, list) and 1 <= len(data) <= 5, f"expected 1-5 processes, got {len(data) if isinstance(data, list) else data!r}"
    for item in data:
        missing = {"pid", "name", "cpu_percent", "memory_percent"} - set(item)
        assert not missing, f"a process is missing {sorted(missing)}: {item}"
        assert isinstance(item["pid"], int) and isinstance(item["name"], str)


@probe("M1", "?limit= works and is limited to 1..25 (422 outside)")
def m1_processes_limit(ctx: Ctx) -> None:
    client = ctx.actor().client
    resp = expect(client.get("/api/system/processes", params={"limit": 3}), 200, "limit=3")
    assert len(resp.json()) <= 3, f"limit=3 returned {len(resp.json())} processes"
    for bad in (0, 26, -1, "many"):
        expect(client.get("/api/system/processes", params={"limit": bad}), 422, f"limit={bad}")
    expect(client.get("/api/system/processes", params={"limit": 25}), 200, "limit=25")


@probe("M1", "?sort_by=cpu|memory|name sorts correctly; anything else is 422")
def m1_processes_sort(ctx: Ctx) -> None:
    client = ctx.actor().client
    for key in ("cpu", "memory"):
        data = expect(client.get("/api/system/processes", params={"sort_by": key, "limit": 25}), 200, f"sort_by={key}").json()
        values = [p[f"{key}_percent"] for p in data]
        assert values == sorted(values, reverse=True), f"sort_by={key}: highest first expected, got {values}"
    data = expect(client.get("/api/system/processes", params={"sort_by": "name", "limit": 25}), 200, "sort_by=name").json()
    names = [p["name"].lower() for p in data]
    assert names == sorted(names), f"sort_by=name: A-Z (ignoring capitals) expected, got {names}"
    expect(client.get("/api/system/processes", params={"sort_by": "banana"}), 422, "sort_by=banana")


# ================================================================== M2 - Hosts & database
@probe("M2", "POST /api/hosts creates a host: 201 + id + a one-time API key (ops_...)")
def m2_create(ctx: Ctx) -> None:
    host = new_host(ctx.actor(), "web-1", "front door")
    missing = {"id", "name", "description", "created_at", "api_key"} - set(host)
    assert not missing, f"the answer is missing {sorted(missing)}"
    eq(host["name"], "web-1", "name")
    eq(host["description"], "front door", "description")
    assert isinstance(host["api_key"], str) and host["api_key"].startswith("ops_") and len(host["api_key"]) >= 30, (
        f"api_key should look like ops_<long random text>, got {host['api_key']!r}"
    )


@probe("M2", "invalid host data is rejected with 422 (empty/blank/too long name, missing body)")
def m2_create_validation(ctx: Ctx) -> None:
    new_host(ctx.actor())  # a valid host must work first - rejecting everything is not an implementation
    client = ctx.actor().client
    bad_bodies = [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 51},
        {"name": "ok", "description": "x" * 201},
        {"name": "ok", "owner_id": 1},
    ]
    for body in bad_bodies:
        expect(client.post("/api/hosts", json=body), 422, f"POST /api/hosts {json.dumps(body)[:60]}")


@probe("M2", "GET /api/hosts lists hosts; a host that never reported is 'unknown' and shows no key")
def m2_list(ctx: Ctx) -> None:
    actor = ctx.actor()
    created = new_host(actor, "list-me")
    resp = expect(actor.client.get("/api/hosts"), 200, "GET /api/hosts")
    items = resp.json()
    mine = [h for h in items if h["id"] == created["id"]]
    assert mine, "the host I just created is not in the list"
    host = mine[0]
    eq(host["status"], "unknown", "status of a host without measurements")
    eq(host["last_seen"], None, "last_seen of a host without measurements")
    assert "api_key" not in host, "the list must never contain api_key (it is shown only once, at creation)"


@probe("M2", "?skip= and ?limit= paginate (limit 1..100, skip >= 0)")
def m2_pagination(ctx: Ctx) -> None:
    actor = ctx.actor()
    for i in range(3):
        new_host(actor, f"page-{i}")
    everything = expect(actor.client.get("/api/hosts", params={"limit": 100}), 200, "limit=100").json()
    assert len(everything) >= 3, "expected at least 3 hosts"
    ids = [h["id"] for h in everything]
    assert ids == sorted(ids), "hosts should be listed oldest first (by id)"
    two = expect(actor.client.get("/api/hosts", params={"limit": 2}), 200, "limit=2").json()
    eq([h["id"] for h in two], ids[:2], "ids with limit=2")
    skipped = expect(actor.client.get("/api/hosts", params={"skip": 1, "limit": 100}), 200, "skip=1").json()
    eq([h["id"] for h in skipped], ids[1:], "ids with skip=1")
    for bad in ({"limit": 0}, {"limit": 101}, {"skip": -1}):
        expect(actor.client.get("/api/hosts", params=bad), 422, f"GET /api/hosts?{bad}")


@probe("M2", "GET /api/hosts/{id}: the host, 404 'Host not found' for unknown ids, 422 for non-numbers")
def m2_get(ctx: Ctx) -> None:
    actor = ctx.actor()
    created = new_host(actor, "single")
    resp = expect(actor.client.get(f"/api/hosts/{created['id']}"), 200, "GET /api/hosts/{id}")
    eq(resp.json()["name"], "single", "name")
    missing = expect(actor.client.get("/api/hosts/987654"), 404, "GET /api/hosts/987654")
    eq(missing.json(), {"detail": "Host not found"}, "body of the 404")
    expect(actor.client.get("/api/hosts/abc"), 422, "GET /api/hosts/abc")


@probe("M2", "?q= searches host names (contains, ignoring capitals)")
def m2_search(ctx: Ctx) -> None:
    actor = ctx.actor()
    a, b = new_host(actor, f"Alpha-DB-{ctx.run}"), new_host(actor, f"beta-web-{ctx.run}")
    found = expect(actor.client.get("/api/hosts", params={"q": "alpha-db"}), 200, "q=alpha-db").json()
    ids = {h["id"] for h in found}
    assert a["id"] in ids and b["id"] not in ids, f"q=alpha-db should find only the first host, found ids {sorted(ids)}"
    nothing = expect(actor.client.get("/api/hosts", params={"q": "zzzqqq"}), 200, "q=zzzqqq").json()
    eq(nothing, [], "result for a search without matches")


@probe("M2", "POST /api/ingest with a valid X-API-Key stores a measurement (201)")
def m2_ingest_ok(ctx: Ctx) -> None:
    host = new_host(ctx.actor())
    resp = expect(send_metric(ctx.client(), host["api_key"], 12.5, 40.0, 70.25), 201, "POST /api/ingest")
    data = resp.json()
    eq((data["cpu_percent"], data["memory_percent"], data["disk_percent"]), (12.5, 40.0, 70.25), "stored values")
    assert "ts" in data, "the answer should contain the timestamp `ts`"


@probe("M2", "/api/ingest: missing or wrong API key -> 401")
def m2_ingest_auth(ctx: Ctx) -> None:
    host = new_host(ctx.actor())
    client = ctx.client()
    body = {"cpu_percent": 1, "memory_percent": 1, "disk_percent": 1}
    expect(client.post("/api/ingest", json=body), 401, "no X-API-Key header")
    expect(send_metric(client, "ops_wrong"), 401, "wrong key")
    expect(send_metric(client, host["api_key"][:-1] + "x"), 401, "key with one changed character")


@probe("M2", "/api/ingest validates: percentages must be numbers from 0 to 100, all three required")
def m2_ingest_validation(ctx: Ctx) -> None:
    host = new_host(ctx.actor())
    client, headers = ctx.client(), {"X-API-Key": host["api_key"]}
    good = {"cpu_percent": 1, "memory_percent": 1, "disk_percent": 1}
    for label, patch in [("cpu 101", {"cpu_percent": 101}), ("memory -1", {"memory_percent": -1}),
                         ("disk 'full'", {"disk_percent": "full"}), ("extra field", {"host_id": 7})]:
        expect(client.post("/api/ingest", headers=headers, json={**good, **patch}), 422, label)
    expect(client.post("/api/ingest", headers=headers, json={"cpu_percent": 1}), 422, "missing fields")


@probe("M2", "after a measurement the host is 'online' and shows the latest values")
def m2_status(ctx: Ctx) -> None:
    actor = ctx.actor()
    host = new_host(actor)
    send_metric(ctx.client(), host["api_key"], 5.0, 6.0, 7.0)
    send_metric(ctx.client(), host["api_key"], 12.5, 40.0, 70.25)
    got = expect(actor.client.get(f"/api/hosts/{host['id']}"), 200, "GET /api/hosts/{id}").json()
    eq(got["status"], "online", "status")
    assert got["last_seen"], "last_seen should be set"
    eq((got["cpu_percent"], got["memory_percent"], got["disk_percent"]), (12.5, 40.0, 70.25), "latest values")


@probe("M2", "GET /api/hosts/{id}/metrics: oldest first, ?limit keeps the NEWEST, ?minutes 1..1440, 404 if unknown")
def m2_metrics(ctx: Ctx) -> None:
    actor = ctx.actor()
    host = new_host(actor)
    for cpu in (10, 20, 30):
        expect(send_metric(ctx.client(), host["api_key"], cpu), 201, "POST /api/ingest")
    url = f"/api/hosts/{host['id']}/metrics"
    rows = expect(actor.client.get(url), 200, "GET metrics").json()
    eq([r["cpu_percent"] for r in rows], [10, 20, 30], "cpu values, oldest first")
    assert {"ts", "cpu_percent", "memory_percent", "disk_percent"} <= set(rows[0]), f"fields: {sorted(rows[0])}"
    newest = expect(actor.client.get(url, params={"limit": 2}), 200, "limit=2").json()
    eq([r["cpu_percent"] for r in newest], [20, 30], "cpu values with limit=2 (the newest two, oldest first)")
    for bad in ({"minutes": 0}, {"minutes": 1441}, {"limit": 0}):
        expect(actor.client.get(url, params=bad), 422, f"metrics?{bad}")
    expect(actor.client.get("/api/hosts/987654/metrics"), 404, "metrics of an unknown host")


@probe("M2", "DELETE /api/hosts/{id}: 204 without body, metrics deleted too, the old key stops working")
def m2_delete(ctx: Ctx) -> None:
    actor = ctx.actor()
    host = new_host(actor)
    send_metric(ctx.client(), host["api_key"])
    resp = expect(actor.client.delete(f"/api/hosts/{host['id']}"), 204, "DELETE /api/hosts/{id}")
    eq(resp.content, b"", "body of a 204 answer")
    expect(actor.client.get(f"/api/hosts/{host['id']}"), 404, "GET after DELETE")
    expect(actor.client.delete(f"/api/hosts/{host['id']}"), 404, "second DELETE")
    with ctx.db() as db:
        left = db.exec(select(Metric).where(Metric.host_id == host["id"])).all()
    eq(len(left), 0, "metrics left in the database after deleting the host")
    expect(send_metric(ctx.client(), host["api_key"]), 401, "ingest with the deleted host's key")


@probe("M2", "the data really lives in the database (not in a Python variable)")
def m2_persistence(ctx: Ctx) -> None:
    host = new_host(ctx.actor(), "in-the-db")
    with ctx.db() as db:
        row = db.get(Host, host["id"])
    assert row is not None, "no row with that id in the Host table - did you save with session.add + commit?"
    eq(row.name, "in-the-db", "name stored in the database")


# ================================================================== M3 - Who are you?
@probe("M3", "POST /api/auth/register creates a user: 201, no password in the answer, not an admin")
def m3_register(ctx: Ctx) -> None:
    name = f"newbie_{ctx.run}"
    resp = expect(ctx.client().post("/api/auth/register", json={"username": name, "password": "hunter2hunter2"}), 201, "register")
    data = resp.json()
    assert {"id", "username", "is_admin"} <= set(data), f"answer should contain id, username, is_admin - got {sorted(data)}"
    eq(data["username"], name, "username")
    eq(data["is_admin"], False, "is_admin of a new user")
    leaked = SECRET_KEYS & set(_all_keys(data))
    assert not leaked, f"the answer leaks {sorted(leaked)}"


@probe("M3", "registration validates: username 3-32 characters (letters, digits, _ . -), password at least 8")
def m3_register_validation(ctx: Ctx) -> None:
    client = ctx.client()
    expect(client.post("/api/auth/register", json={"username": f"valid_{ctx.run}", "password": "longenough1"}), 201, "a valid register")
    for body in ({"username": "ab", "password": "longenough1"}, {"username": "bad name!", "password": "longenough1"},
                 {"username": "fine_name", "password": "short"}, {"username": "fine_name"}, {}):
        expect(client.post("/api/auth/register", json=body), 422, f"register {json.dumps(body)}")


@probe("M3", "a taken username -> 409 (usernames ignore capitals)")
def m3_duplicate(ctx: Ctx) -> None:
    client, name = ctx.client(), f"dupe_{ctx.run}"
    expect(client.post("/api/auth/register", json={"username": name, "password": "longenough1"}), 201, "first register")
    expect(client.post("/api/auth/register", json={"username": name, "password": "longenough1"}), 409, "same name again")
    expect(client.post("/api/auth/register", json={"username": name.upper(), "password": "longenough1"}), 409, "same name in CAPITALS")


@probe("M3", "POST /api/auth/token (form data) returns a bearer token; wrong credentials -> 401 + WWW-Authenticate")
def m3_login(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    client = ctx.client()
    ok = expect(client.post("/api/auth/token", data={"username": alice.username, "password": alice.password}), 200, "login").json()
    eq(ok.get("token_type", "").lower(), "bearer", "token_type")
    assert isinstance(ok.get("access_token"), str) and ok["access_token"].count(".") == 2, "access_token should be a JWT (three parts separated by dots)"
    wrong = expect(client.post("/api/auth/token", data={"username": alice.username, "password": "not-the-password"}), 401, "wrong password")
    assert "bearer" in wrong.headers.get("www-authenticate", "").lower(), "a 401 should carry the header `WWW-Authenticate: Bearer`"
    expect(client.post("/api/auth/token", data={"username": "nobody_" + ctx.run, "password": "whatever123"}), 401, "unknown user")


@probe("M3", "the token carries `sub` and `exp`, and expires within 24 hours")
def m3_token_claims(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    claims = jwt.decode(alice.token, options={"verify_signature": False})
    assert "sub" in claims and "exp" in claims, f"claims should contain sub and exp, got {sorted(claims)}"
    eq(str(claims["sub"]), str(alice.id), "sub (the user id)")
    remaining = claims["exp"] - time.time()
    assert 60 < remaining <= 24 * 3600, f"token should be valid for minutes, not {remaining:.0f} seconds / days"


@probe("M3", "GET /api/auth/me: your user with a token; 401 without or with garbage")
def m3_me(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    me = expect(alice.client.get("/api/auth/me"), 200, "GET /api/auth/me").json()
    eq(me["username"], alice.username, "username")
    expect(ctx.client().get("/api/auth/me"), 401, "no token")
    expect(ctx.client("this.is.garbage").get("/api/auth/me"), 401, "garbage token")


@probe("M3", "passwords are stored as Argon2 hashes, never as text")
def m3_hashing(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    with ctx.db() as db:
        user = db.get(User, alice.id)
    assert user is not None, "user is not in the database"
    assert user.hashed_password != alice.password and alice.password not in user.hashed_password, "the password is stored in plain text!"
    assert user.hashed_password.startswith("$argon2"), f"expected an Argon2 hash ($argon2...), got {user.hashed_password[:12]}..."


@probe("M3", "hosts and system routes need a login (401), /api/health does not, agents still use their key")
def m3_protected(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    anon = ctx.client()
    host = new_host(alice)
    for method, path in [("get", "/api/hosts"), ("post", "/api/hosts"), ("get", f"/api/hosts/{host['id']}"),
                         ("get", f"/api/hosts/{host['id']}/metrics"), ("delete", f"/api/hosts/{host['id']}"),
                         ("get", "/api/system"), ("get", "/api/system/processes")]:
        kwargs = {"json": {"name": "x"}} if method == "post" else {}
        expect(getattr(anon, method)(path, **kwargs), 401, f"{method.upper()} {path} without login")
    expect(anon.get("/api/health"), 200, "GET /api/health without login")
    expect(send_metric(anon, host["api_key"]), 201, "agent ingest with an API key and no login")
    expect(alice.client.get("/api/hosts"), 200, "GET /api/hosts with login")


@probe("M3", "GET /api/admin/users: 401 anonymous, 403 for normal users, 200 for admins")
def m3_admin(ctx: Ctx) -> None:
    alice, root = ctx.actor(required=True), ctx.actor("root", required=True)
    expect(ctx.client().get("/api/admin/users"), 401, "admin area without login")
    expect(alice.client.get("/api/admin/users"), 403, "admin area as a normal user")
    with ctx.db() as db:
        user = db.get(User, root.id)
        user.is_admin = True  # type: ignore[union-attr]
        db.add(user)
        db.commit()
    resp = expect(root.client.get("/api/admin/users"), 200, "admin area as an admin")
    assert any(u["username"] == alice.username for u in resp.json()), "the admin list should contain all users"


# ================================================================== M4 - Red team (attacks)
@probe("M4", "IDOR: bob reads alice's host by guessing its id", "attack")
def m4_idor_read(ctx: Ctx) -> None:
    alice, bob = ctx.actor(required=True), ctx.actor("bob", required=True)
    host = new_host(alice, "alices-secret-server")
    got = bob.client.get(f"/api/hosts/{host['id']}")
    expect(got, 404, f"bob GET /api/hosts/{host['id']} (alice's host) - it was readable")
    ids = [h["id"] for h in expect(bob.client.get("/api/hosts", params={"limit": 100}), 200, "bob lists hosts").json()]
    assert host["id"] not in ids, "bob's host list contains alice's host"


@probe("M4", "IDOR: bob deletes alice's host", "attack")
def m4_idor_delete(ctx: Ctx) -> None:
    alice, bob = ctx.actor(required=True), ctx.actor("bob", required=True)
    host = new_host(alice, "do-not-delete-me")
    resp = bob.client.delete(f"/api/hosts/{host['id']}")
    still_there = alice.client.get(f"/api/hosts/{host['id']}").status_code == 200
    assert still_there, f"bob DELETED alice's host (answer was {resp.status_code}) - gone!"
    expect(resp, 404, "bob DELETE alice's host")


@probe("M4", "IDOR: bob reads alice's measurements", "attack")
def m4_idor_metrics(ctx: Ctx) -> None:
    alice, bob = ctx.actor(required=True), ctx.actor("bob", required=True)
    host = new_host(alice)
    send_metric(ctx.client(), host["api_key"], 99.0)
    expect(bob.client.get(f"/api/hosts/{host['id']}/metrics"), 404, "bob GET alice's metrics - they were readable")


@probe("M4", "mass assignment: registering with \"is_admin\": true", "attack")
def m4_mass_assignment(ctx: Ctx) -> None:
    client, name = ctx.client(), f"sneaky_{ctx.run}"
    resp = client.post("/api/auth/register", json={"username": name, "password": "longenough1", "is_admin": True})
    if resp.status_code == 422:  # rejecting unknown fields is fine, too
        return
    expect(resp, 201, "register")
    assert resp.json().get("is_admin") is False, "registered with is_admin=true and became an ADMIN"
    token = client.post("/api/auth/token", data={"username": name, "password": "longenough1"}).json()["access_token"]
    expect(ctx.client(token).get("/api/admin/users"), 403, "the new user opens the admin area")


@probe("M4", "brute force: guessing a password over and over", "attack")
def m4_bruteforce(ctx: Ctx) -> None:
    victim = ctx.actor("victim", required=True)
    client = ctx.client()
    codes, last = [], None
    for i in range(8):
        last = client.post("/api/auth/token", data={"username": victim.username, "password": f"guess-{i}-wrong"})
        codes.append(last.status_code)
    assert 429 in codes, f"8 wrong passwords in a row and no lock-out. Status codes were {codes}"
    blocked = client.post("/api/auth/token", data={"username": victim.username, "password": victim.password})
    eq(blocked.status_code, 429, "even the CORRECT password must wait while locked")
    retry = blocked.headers.get("retry-after", "")
    assert retry.isdigit() and int(retry) > 0, f"a 429 should carry `Retry-After: <seconds>`, got {retry!r}"
    other = ctx.actor(required=True)
    expect(client.post("/api/auth/token", data={"username": other.username, "password": other.password}), 200, "another user logs in meanwhile")


@probe("M4", "user enumeration: 'no such user' vs 'wrong password' must look identical", "attack")
def m4_enumeration(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    client = ctx.client()
    known = client.post("/api/auth/token", data={"username": alice.username, "password": "wrong-wrong-1"})
    unknown = client.post("/api/auth/token", data={"username": f"ghost_{ctx.run}", "password": "wrong-wrong-1"})
    eq(known.status_code, unknown.status_code, "status code (existing user vs unknown user)")
    eq(known.json(), unknown.json(), "body (existing user vs unknown user) - it tells the attacker which names exist")


@probe("M4", "secret leaks: hashes, passwords or keys showing up in responses", "attack")
def m4_leaks(ctx: Ctx) -> None:
    alice, root = ctx.actor(required=True), ctx.actor("root", required=True)
    host = new_host(alice)
    with ctx.db() as db:
        user = db.get(User, root.id)
        user.is_admin = True  # type: ignore[union-attr]
        db.add(user)
        db.commit()
    responses = {
        "GET /api/auth/me": alice.client.get("/api/auth/me"),
        "GET /api/hosts": alice.client.get("/api/hosts"),
        f"GET /api/hosts/{host['id']}": alice.client.get(f"/api/hosts/{host['id']}"),
        "GET /api/admin/users": root.client.get("/api/admin/users"),
        "POST /api/auth/register": ctx.client().post("/api/auth/register", json={"username": f"leak_{ctx.run}", "password": "longenough1"}),
    }
    for what, resp in responses.items():
        expect(resp, (200, 201), what)
        leaked = SECRET_KEYS & set(_all_keys(resp.json()))
        assert not leaked, f"{what} leaks {sorted(leaked)}"
        if what != "POST /api/hosts":
            assert "api_key" not in set(_all_keys(resp.json())), f"{what} contains an api_key - it may only be shown once, at creation"


@probe("M4", "stolen database: are API keys stored hashed?", "attack")
def m4_keys_at_rest(ctx: Ctx) -> None:
    host = new_host(ctx.actor(required=True))
    with ctx.db() as db:
        row = db.get(Host, host["id"])
    assert row is not None
    assert host["api_key"] not in row.api_key_hash and row.api_key_hash != host["api_key"], (
        "the API key is stored in the database as it is - anyone who copies the database gets working keys"
    )
    assert len(row.api_key_hash) >= 40, f"api_key_hash should be a real hash, got {row.api_key_hash!r}"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()


@probe("M4", "forged tokens: wrong secret, alg=none, edited payload, damaged signature", "attack")
def m4_jwt_forged(ctx: Ctx) -> None:
    alice, bob = ctx.actor(required=True), ctx.actor("bob", required=True)
    soon = int(time.time()) + 3600
    head, payload, sig = alice.token.split(".")
    forged = {
        "signed with another secret": jwt.encode({"sub": str(alice.id), "exp": soon}, "not-the-servers-secret-0123456789abcdef", algorithm="HS256"),
        'alg "none" (no signature at all)': _b64({"alg": "none", "typ": "JWT"}) + "." + _b64({"sub": str(alice.id), "exp": soon}) + ".",
        "payload edited to bob's id": head + "." + _b64({"sub": str(bob.id), "exp": soon}) + "." + sig,
        "damaged signature": head + "." + payload + "." + ("A" if sig[0] != "A" else "B") + sig[1:],
    }
    for what, token in forged.items():
        resp = ctx.client(token).get("/api/auth/me")
        assert resp.status_code == 401, f"token {what} was ACCEPTED (HTTP {resp.status_code})"


@probe("M4", "bad tokens: expired, no expiry, unknown user, non-numeric subject", "attack")
def m4_jwt_invalid(ctx: Ctx) -> None:
    alice = ctx.actor(required=True)
    secret, algorithm = ctx.secret(), ctx.settings.jwt_algorithm
    now = int(time.time())
    cases = {
        "expired a minute ago": {"sub": str(alice.id), "exp": now - 60},
        "no expiry at all": {"sub": str(alice.id)},
        "user does not exist": {"sub": "987654", "exp": now + 3600},
        "subject is not a number": {"sub": "abc", "exp": now + 3600},
        "no subject": {"exp": now + 3600},
    }
    for what, claims in cases.items():
        resp = ctx.client(jwt.encode(claims, secret, algorithm=algorithm)).get("/api/auth/me")
        assert resp.status_code == 401, f"token ({what}) answered HTTP {resp.status_code} instead of 401"


@probe("M4", "browser attacks: security headers (nosniff, no framing, no referrer, CSP, no-store)", "attack")
def m4_headers(ctx: Ctx) -> None:
    client = ctx.client()
    api = expect(client.get("/api/health"), 200, "GET /api/health")
    page = expect(client.get("/"), 200, "GET /")
    wanted = {"x-content-type-options": "nosniff", "x-frame-options": "deny", "referrer-policy": "no-referrer"}
    for header, value in wanted.items():
        got = api.headers.get(header, "").lower()
        assert got == value, f"header {header}: expected {value!r}, got {got!r}"
    assert "no-store" in api.headers.get("cache-control", ""), "API answers need `Cache-Control: no-store`"
    csp = page.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp, f"Content-Security-Policy missing or too weak: {csp!r}"


@probe("M4", "injection: SQL tricks and LIKE wildcards in the search box", "attack")
def m4_injection(ctx: Ctx) -> None:
    actor = ctx.actor(required=True)
    new_host(actor, f"plain-one-{ctx.run}")
    new_host(actor, f"plain-two-{ctx.run}")
    for text in ("' OR '1'='1", "'; DROP TABLE host; --", "%", "_", "%%"):
        resp = actor.client.get("/api/hosts", params={"q": text})
        expect(resp, 200, f"search for {text!r}")
        assert resp.json() == [], f"searching for {text!r} returned {len(resp.json())} host(s) - the text must be matched literally"
    with ctx.db() as db:
        assert db.exec(select(Host).order_by(col(Host.id))).first() is not None, "the host table is gone!"
