from sdc_ir import canonical_json, ir_hash, specification_hash, build_id
from sdc_parser import load_from_files, load_project


def test_canonical_json_is_order_independent():
    a = {"b": 1, "a": [3, 2, 1]}
    b = {"a": [3, 2, 1], "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_ir_hash_deterministic(example_dir):
    ir1 = load_project(example_dir).ir.to_dict()
    ir2 = load_project(example_dir).ir.to_dict()
    assert ir_hash(ir1) == ir_hash(ir2)


def test_ir_hash_changes_on_semantic_change(example_dir):
    base = load_project(example_dir)
    files = dict(base.files)
    h1 = ir_hash(base.ir.to_dict())
    files["authorization.md"] = files["authorization.md"] + "\nA manager may access customers in their assigned departments.\n"
    ir2 = load_from_files(files).ir.to_dict()
    assert ir_hash(ir2) != h1


def test_spec_hash_ignores_line_endings():
    a = {"a.md": "# X\nhello\n"}
    b = {"a.md": "# X\r\nhello\r\n"}
    assert specification_hash(a) == specification_hash(b)


def test_build_id_stable():
    bid1 = build_id("sha256:aa", "sha256:bb", "0.1.0")
    bid2 = build_id("sha256:aa", "sha256:bb", "0.1.0")
    assert bid1 == bid2
    assert build_id("sha256:aa", "sha256:cc", "0.1.0") != bid1
