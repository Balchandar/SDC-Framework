import pytest

from sdc_runtime import (
    jwt_encode,
    jwt_verify,
    JWTError,
    Policy,
    Principal,
    Router,
    InMemoryStore,
    project_fields,
    Metrics,
    StructuredLogger,
)
import io


def test_jwt_roundtrip():
    tok = jwt_encode({"sub": "u", "tenant_id": "t1", "role": "user"}, "s")
    claims = jwt_verify(tok, "s")
    assert claims["tenant_id"] == "t1"


def test_jwt_bad_signature():
    tok = jwt_encode({"sub": "u"}, "s")
    with pytest.raises(JWTError):
        jwt_verify(tok, "other-secret")


def test_jwt_expired():
    tok = jwt_encode({"sub": "u", "exp": 1}, "s")
    with pytest.raises(JWTError):
        jwt_verify(tok, "s")


def test_policy_same_tenant_allow():
    rules = [
        {"effect": "deny", "subject": "any", "predicate": {"op": "cross_tenant"}},
        {"effect": "allow", "subject": "user", "predicate": {"op": "same_tenant"}},
    ]
    pol = Policy(rules)
    p = Principal("u", "t1", "user")
    allowed, reason = pol.decide(p, {"tenant_id": "t1"})
    assert allowed and reason.startswith("allow")


def test_policy_cross_tenant_deny():
    rules = [
        {"effect": "deny", "subject": "any", "predicate": {"op": "cross_tenant"}},
        {"effect": "allow", "subject": "user", "predicate": {"op": "same_tenant"}},
    ]
    pol = Policy(rules)
    p = Principal("u", "t2", "user")
    allowed, reason = pol.decide(p, {"tenant_id": "t1"})
    assert not allowed and reason.startswith("deny")


def test_policy_manager_department():
    rules = [{"effect": "allow", "subject": "manager", "predicate": {"op": "assigned_department"}}]
    pol = Policy(rules)
    p = Principal("m", "t1", "manager", claims={"departments": ["sales"]})
    assert pol.decide(p, {"tenant_id": "t1", "department": "sales"})[0]
    assert not pol.decide(p, {"tenant_id": "t1", "department": "eng"})[0]


def test_router_match_and_405():
    r = Router()
    r.add("GET", "/customers/{id}", lambda req: None)
    route, params = r.match("GET", "/customers/c1")
    assert route is not None and params == {"id": "c1"}
    route, params = r.match("POST", "/customers/c1")
    assert route is None and params.get("__method_not_allowed__")


def test_store_tenant_scope():
    store = InMemoryStore({"Customer": [{"id": "c1", "tenant_id": "t1"}, {"id": "c3", "tenant_id": "t2"}]})
    assert store.get("Customer", "c1")["tenant_id"] == "t1"
    scoped = store.list("Customer", tenant_id="t1")
    assert [r["id"] for r in scoped] == ["c1"]


def test_project_fields_strips_sensitive():
    row = {"id": "c1", "password": "secret", "name": "x"}
    out = project_fields(row, ["password"])
    assert "password" not in out and out["name"] == "x"


def test_logger_redacts():
    buf = io.StringIO()
    log = StructuredLogger(stream=buf, sensitive_keys=["password"])
    log.info("test", password="hunter2", tenant_id="t1")
    line = buf.getvalue()
    assert "hunter2" not in line and "t1" in line


def test_metrics_prometheus():
    m = Metrics()
    m.inc_request("GET /x", 200)
    m.observe_latency(0.01)
    out = m.prometheus()
    assert "sdc_requests_total 1" in out
