import os

from sdc_parser import load_project
from sdc_compiler import AICompiler, get_provider
from sdc_codegen import generate_implementation
from sdc_verifier import verify, ServiceHarness, build_seed


def _build_service(example_dir, tmp_path):
    ir = load_project(example_dir).ir
    plan = AICompiler(get_provider("local")).plan_only(ir)
    generate_implementation(ir, plan.to_dict(), str(tmp_path))
    return ir, str(tmp_path / "service.py")


def test_full_verification_passes(example_dir, tmp_path):
    ir, service = _build_service(example_dir, tmp_path)
    report = verify(ir, service).report
    assert report.status == "PASS", [c.to_dict() for c in report.failures()]
    names = {c.name for c in report.checks}
    assert "tenant_isolation" in names
    assert "no_secret_exposure" in names
    assert "authentication_enforced" in names


def test_harness_live_behaviors(example_dir, tmp_path):
    ir, service = _build_service(example_dir, tmp_path)
    with ServiceHarness(service, seed=build_seed(ir)) as h:
        assert h.get("/customers/c1").status == 401
        tok_t1 = h.token(tenant_id="t1", role="user")
        assert h.get("/customers/c1", token=tok_t1).status == 200
        tok_t2 = h.token(tenant_id="t2", role="user")
        assert h.get("/customers/c1", token=tok_t2).status == 403
        assert h.get("/customers/does-not-exist", token=tok_t1).status == 404


def test_no_sensitive_data_in_response(example_dir, tmp_path):
    ir, service = _build_service(example_dir, tmp_path)
    with ServiceHarness(service, seed=build_seed(ir)) as h:
        r = h.get("/customers/c1", token=h.token(tenant_id="t1", role="user"))
        assert "password" not in r.body
        assert "auth_token" not in r.body
        assert "secret-" not in r.body


def test_verification_fails_on_contradictory_test(example_dir, tmp_path, monkeypatch):
    ir, service = _build_service(example_dir, tmp_path)
    # Inject a spec test that contradicts the enforced policy.
    from sdc_ir import TestCase

    ir.testing.cases.append(
        TestCase(
            name="impossible",
            request={"endpoint": "GET /customers/c1", "principal": {"role": "user", "tenant_id": "t2"}},
            expect_status=200,
        )
    )
    report = verify(ir, service, run_performance=False).report
    assert report.status == "FAIL"
    assert any(c.name == "impossible" for c in report.failures())
