from sdc_parser import load_project, load_from_files, validate_ir
from sdc_parser.markdown import parse_blocks


def test_markdown_blocks_roundtrip():
    blocks = parse_blocks("# Title\n\n- a\n- b\n\n```\ncode\n```\n")
    kinds = [b.kind for b in blocks]
    assert kinds == ["heading", "list", "code"]
    assert blocks[1].items == ["a", "b"]
    assert blocks[2].code == "code"


def test_table_parsing():
    text = "# Data\n\n### Customer\n\n| Field | Type | Sensitive |\n|---|---|---|\n| id | string | no |\n| password | string | yes |\n"
    ir = load_from_files({"data.md": text}).ir
    ent = ir.data.entity("Customer")
    assert ent is not None
    assert "password" in ent.sensitive_fields()
    assert "id" in ent.field_names()


def test_application_meta(example_ir):
    assert example_ir.application.name == "CustomerService"
    assert example_ir.application.version == "1.0"
    assert "tenant" in example_ir.application.description.lower()


def test_endpoints(example_ir):
    keys = {e.key() for e in example_ir.api.endpoints}
    assert "GET /customers/{id}" in keys
    assert "GET /customers" in keys
    detail = next(e for e in example_ir.api.endpoints if e.path == "/customers/{id}")
    assert detail.path_params == ["id"]
    assert detail.entity == "Customer"


def test_authentication(example_ir):
    assert example_ir.authentication.scheme == "oauth2_bearer_jwt"
    assert example_ir.authentication.required is True


def test_authorization_rules(example_ir):
    az = example_ir.authorization
    assert az.model == "rbac_tenant"
    assert "cross_tenant_access" in az.forbidden
    assert az.auditable is True
    effects = {(r.subject, r.effect) for r in az.rules}
    assert ("user", "allow") in effects
    assert ("tenant_admin", "allow") in effects
    assert ("any", "deny") in effects


def test_behavior(example_ir):
    assert example_ir.behavior.status_for("unauthenticated") == 401
    assert example_ir.behavior.status_for("unauthorized") == 403
    assert example_ir.behavior.status_for("not_found") == 404
    assert example_ir.behavior.status_for("success") == 200


def test_security_and_performance(example_ir):
    ids = set(example_ir.security.check_ids())
    assert "no_secret_exposure" in ids
    assert "tenant_isolation" in ids
    assert "sql_injection" in ids
    assert example_ir.performance.p99_latency_ms == 50
    assert example_ir.performance.min_rps == 10000


def test_validation_clean(example_ir):
    assert validate_ir(example_ir) == []


def test_validation_flags_missing_tenant_field():
    text_data = "# Data\n\n### Customer\n\n| Field | Type |\n|---|---|\n| id | string |\n"
    text_authz = "# Authorization\n\nCross-tenant access is forbidden.\n"
    ir = load_from_files({"data.md": text_data, "authz.md": text_authz}).ir
    errors = validate_ir(ir)
    assert any("tenant" in e.what.lower() for e in errors)
