import os
import shutil

import pytest

from sdc_cli.main import build_parser, main


def _run(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def test_cli_validate(example_dir, capsys):
    _run(["validate", example_dir])
    out = capsys.readouterr().out
    assert "valid" in out.lower()


def test_cli_inspect_json(example_dir, capsys):
    _run(["inspect", example_dir, "--json"])
    import json

    data = json.loads(capsys.readouterr().out)
    assert data["application"]["name"] == "CustomerService"


def test_cli_init_and_build(tmp_path, capsys):
    proj = str(tmp_path / "svc")
    _run(["init", proj])
    assert os.path.exists(os.path.join(proj, "project.md"))
    assert os.path.exists(os.path.join(proj, "authorization.md"))
    # a scaffolded project should build successfully (no SystemExit on success)
    _run(["build", proj])
    out = capsys.readouterr().out
    assert "BUILD SUCCESSFUL" in out
    assert os.path.exists(os.path.join(proj, "dist", "svc"))


def test_cli_diff(example_dir, tmp_path, capsys):
    new = str(tmp_path / "new")
    shutil.copytree(example_dir, new)
    for d in (".build", "dist"):
        p = os.path.join(new, d)
        if os.path.exists(p):
            shutil.rmtree(p)
    with open(os.path.join(new, "authorization.md"), "a") as fh:
        fh.write("\nA manager may access customers in their assigned departments.\n")
    _run(["diff", example_dir, new])
    out = capsys.readouterr().out
    assert "SEMANTIC DIFF" in out
    assert "manager" in out
