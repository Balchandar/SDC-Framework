from sdc_compiler import (
    AICompiler,
    get_provider,
    LocalDeterministicProvider,
    validate_plan,
    ImplementationPlan,
    semantic_diff,
    analyze_drift,
)
from sdc_parser import load_project, load_from_files


def test_local_provider_default():
    assert isinstance(get_provider("local"), LocalDeterministicProvider)


def test_unknown_provider_falls_back():
    # unknown non-registered name raises; unavailable model provider falls back
    p = get_provider("anthropic")  # no key -> falls back to local
    assert isinstance(p, LocalDeterministicProvider)


def test_plan_is_valid(example_dir):
    ir = load_project(example_dir).ir
    plan = AICompiler(get_provider("local")).plan_only(ir, target="linux-x86_64")
    assert validate_plan(plan) == []
    names = {c.name for c in plan.components}
    assert {"http-server", "authentication", "authorization", "database"} <= names
    assert plan.backend == "python-stdlib-http"


def test_plan_validation_catches_bad_backend():
    plan = ImplementationPlan(target="x", language="y", framework="z", backend="nope")
    errors = validate_plan(plan)
    assert any("backend" in e.what.lower() for e in errors)


def test_semantic_diff_detects_added_rule(example_dir):
    base = load_project(example_dir)
    files = dict(base.files)
    files["authorization.md"] += "\nA manager may access customers in their assigned departments.\n"
    new_ir = load_from_files(files).ir
    sd = semantic_diff(base.ir.to_dict(), new_ir.to_dict())
    assert sd.has_changes
    descs = " ".join(c.description for c in sd.changes)
    assert "manager" in descs
    assert "GET /customers/{id}" in sd.affected_apis


def test_drift_maps_change_to_components(example_dir):
    base = load_project(example_dir)
    ir = base.ir
    plan = AICompiler(get_provider("local")).plan_only(ir)
    files = dict(base.files)
    files["authorization.md"] += "\nA manager may access customers in their assigned departments.\n"
    new_ir = load_from_files(files).ir
    drift = analyze_drift(ir.to_dict(), new_ir.to_dict(), plan)
    assert "authorization" in drift.changed_sections
    assert "authorization" in drift.affected_components
    assert "authentication" in drift.unaffected_components


def test_no_diff_when_identical(example_dir):
    ir = load_project(example_dir).ir.to_dict()
    assert not semantic_diff(ir, ir).has_changes
