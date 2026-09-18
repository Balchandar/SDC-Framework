"""sdc — the SDC command-line compiler.

Commands: init, validate, compile, verify, build, run, test, diff, inspect.
The UX mirrors a modern compiler: dotted progress lines and grouped result
sections. Failures are never silent.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from sdc_ir.errors import SDCError
from sdc_compiler import COMPILER_VERSION, semantic_diff
from sdc_parser import load_project

from .pipeline import Toolchain
from . import scaffold


VERSION = "0.1.0"


# --------------------------------------------------------------------------- #
# output helpers
# --------------------------------------------------------------------------- #
def _c(text: str, code: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t): return _c(t, "32")
def red(t): return _c(t, "31")
def yellow(t): return _c(t, "33")
def bold(t): return _c(t, "1")
def dim(t): return _c(t, "2")


def step(label: str, ok: bool = True, note: str = ""):
    dots = "." * max(3, 34 - len(label))
    status = green("OK") if ok else red("FAIL")
    tail = f"  {note}" if note else ""
    print(f"  {label} {dim(dots)} {status}{tail}")


def result_line(name: str, status: str, note: str = ""):
    dots = "." * max(3, 32 - len(name))
    color = {"PASS": green, "FAIL": red, "UNVERIFIED": yellow, "WARN": yellow}.get(status, lambda x: x)
    tail = f"  {dim(note)}" if note else ""
    print(f"  {name} {dim(dots)} {color(status)}{tail}")


def header():
    print(f"\n{bold('SDC')} {VERSION}  (compiler {COMPILER_VERSION})\n")


def _fail(err: SDCError | str, exit_code: int = 1):
    print()
    print(red(bold("BUILD FAILED")))
    print()
    if isinstance(err, SDCError):
        print(f"  {bold('Error')}:   [{err.kind}] {err.what}")
        if err.why:
            print(f"  {bold('Why')}:     {err.why}")
        if err.specification:
            print(f"  {bold('Spec')}:    {err.specification}")
        if err.component:
            print(f"  {bold('Affected')}: {err.component}")
        if err.details:
            print(f"  {bold('Details')}:")
            for d in err.details:
                print(f"    - {d}")
        print(f"  {bold('Regenerable')}: {err.regenerable}")
    else:
        print(f"  {err}")
    print()
    sys.exit(exit_code)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_init(args):
    target = args.name
    if os.path.exists(target) and os.listdir(target):
        _fail(f"directory '{target}' already exists and is not empty")
    scaffold.write_project(target, name=args.app or None)
    print(green(f"Initialized SDC project in {target}/"))
    print("\nSpecification files:")
    for f in sorted(os.listdir(target)):
        print(f"  - {target}/{f}")
    print(f"\nNext: {bold(f'cd {target} && sdc build')}\n")


def cmd_validate(args):
    header()
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse()
        step("Reading specifications")
        errors = tc.validate()
        step("Building Application IR")
    except SDCError as e:
        _fail(e)
    if errors:
        step("Validating specification", ok=False)
        print()
        for e in errors:
            print(f"  {red('•')} [{e.kind}] {e.what}")
            if e.why:
                print(f"      {dim(e.why)}")
        print()
        sys.exit(1)
    step("Validating specification")
    print()
    print(green(f"Specification is valid. spec={tc.spec_hash[:23]}… ir={tc.ir_h[:23]}…"))
    print()


def cmd_compile(args):
    header()
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse(); step("Reading specifications")
        step("Building Application IR")
        errs = tc.validate()
        if any(not e.regenerable for e in errs):
            step("Validating specification", ok=False)
            _fail(errs[0])
        step("Validating specification")
        tc.compile(); step("Planning implementation")
        step("Generating implementation")
    except SDCError as e:
        _fail(e)
    print()
    print(green("Compilation complete."))
    print(f"  plan:      {tc._abs('.build/implementation-plan.json')}")
    print(f"  generated: {tc._abs('.build/generated/service.py')}")
    print()


def _print_verification(report):
    groups = report.by_category()
    label = {
        "authentication": "Authentication",
        "authorization": "Authorization",
        "tenant-isolation": "Tenant isolation",
        "api-behavior": "API behavior",
        "api-contract": "API contract",
        "error-semantics": "Error semantics",
        "security": "Security requirements",
        "performance": "Performance",
        "runtime": "Runtime",
    }
    print(bold("\nVerification\n"))
    for cat in ["authentication", "authorization", "tenant-isolation", "api-contract", "api-behavior", "error-semantics", "security", "runtime"]:
        checks = groups.get(cat)
        if not checks:
            continue
        n_pass = sum(1 for c in checks if c.status == "PASS")
        n_total = len(checks)
        worst = "PASS"
        if any(c.status == "FAIL" and c.mandatory for c in checks):
            worst = "FAIL"
        elif any(c.status == "UNVERIFIED" for c in checks) and n_pass < n_total:
            worst = "UNVERIFIED" if n_pass == 0 else "PASS"
        result_line(label.get(cat, cat), worst, f"{n_pass}/{n_total}")
    perf = groups.get("performance")
    if perf:
        print(bold("\nPerformance\n"))
        for c in perf:
            note = ""
            if c.observed and "p99_ms" in c.observed:
                note = f"{c.observed['p99_ms']}ms (target <{c.observed['target_ms']}ms)"
            result_line(c.name, c.status, note or c.detail)


def cmd_verify(args):
    header()
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse(); step("Reading specifications")
        tc.compile(); step("Generating implementation")
        report = tc.verify(); step("Running verification", ok=(report.status == "PASS"))
    except SDCError as e:
        _fail(e)
    _print_verification(report)
    print()
    if report.status == "PASS":
        print(green(bold("VERIFICATION PASSED")))
    else:
        print(red(bold("VERIFICATION FAILED")))
        for c in report.failures():
            print(f"  {red('•')} {c.name}: {c.detail}")
    print()
    sys.exit(0 if report.status == "PASS" else 1)


def cmd_test(args):
    """Run the behavioral test suite (behavior + contract) against the artifact."""
    header()
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse(); step("Reading specifications")
        tc.compile(); step("Generating implementation")
        report = tc.verify(run_performance=False)
    except SDCError as e:
        _fail(e)
    behavioral = [c for c in report.checks if c.category in ("api-behavior", "api-contract", "error-semantics", "authorization", "tenant-isolation", "authentication")]
    print(bold("\nTests\n"))
    passed = 0
    for c in behavioral:
        result_line(c.name, c.status, c.detail)
        passed += c.status == "PASS"
    print()
    print(f"  {passed}/{len(behavioral)} passed")
    print()
    sys.exit(0 if all(c.status != "FAIL" for c in behavioral) else 1)


def cmd_build(args):
    header()
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse(); step("Reading specifications")
        step("Building Application IR")
        errs = tc.validate()
        if any(not e.regenerable for e in errs):
            step("Validating specification", ok=False)
            _fail(errs[0])
        step("Validating specification")
        out = tc.build()
        report = out["report"]
        step("Planning implementation")
        step("Generating implementation")
        step("Compiling native artifact", ok=(report.status == "PASS"), note=dim(f"backend={tc.plan.backend}"))
    except SDCError as e:
        _fail(e)

    _print_verification(report)

    if report.status == "FAIL":
        print()
        print(red(bold("BUILD FAILED")))
        print()
        for c in report.failures():
            print(f"  {bold('Requirement')}: {c.name}")
            print(f"  {bold('Observed')}:    {c.detail}")
            print()
        print("  Binary generation stopped.\n")
        sys.exit(1)

    manifest = out["manifest"]
    diff = out["diff"]

    if diff:
        _print_semantic_diff_summary(diff)

    print(bold("\nArtifact\n"))
    print(f"  target:        {manifest['target']}")
    print(f"  binary:        {manifest['artifact']}")
    print(f"  specification: {manifest['specification_hash']}")
    print(f"  ir:            {manifest['ir_hash']}")
    print(f"  artifact:      {manifest['artifact_hash']}")
    print(f"  build id:      {manifest['build_id']}")
    print()
    print(green(bold("BUILD SUCCESSFUL")))
    print()


def _print_semantic_diff_summary(diff: dict):
    sd = diff.get("semantic_diff", {})
    dr = diff.get("drift", {})
    if not sd.get("changes"):
        return
    print(bold("\nSpecification changed\n"))
    for ch in sd["changes"]:
        sym = {"added": "+", "removed": "-", "changed": "~"}.get(ch["kind"], "•")
        print(f"  {sym} [{ch['category']}] {ch['description']}")
    if dr.get("affected_components"):
        print(f"\n  affected components: {', '.join(dr['affected_components'])}")
    if dr.get("unaffected_components"):
        print(f"  unaffected:          {', '.join(dr['unaffected_components'])}")
    if dr.get("affected_verification"):
        print(f"  re-verified:         {', '.join(dr['affected_verification'])}")


def cmd_run(args):
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse()
        tc.compile()
    except SDCError as e:
        _fail(e)
    env = dict(os.environ)
    env.setdefault("PORT", str(args.port))
    if not env.get("SDC_JWT_SECRET"):
        print(yellow("warning: SDC_JWT_SECRET is not set; using an ephemeral development secret"))
        env["SDC_JWT_SECRET"] = "dev-secret-change-me"
    print(green(f"Running {tc.ir.application.name} on port {env['PORT']} (Ctrl-C to stop)"))
    try:
        subprocess.run([sys.executable, tc.service_path], env=env)
    except KeyboardInterrupt:
        pass


def cmd_diff(args):
    header()
    try:
        old = load_project(args.old)
        new = load_project(args.new)
    except SDCError as e:
        _fail(e)
    sd = semantic_diff(old.ir.to_dict(), new.ir.to_dict())
    if not sd.has_changes:
        print(green("No semantic changes between specifications."))
        print()
        return
    print(bold("SEMANTIC DIFF\n"))
    by_cat: dict[str, list] = {}
    for ch in sd.changes:
        by_cat.setdefault(ch.category, []).append(ch)
    for cat, changes in by_cat.items():
        print(bold(f"{cat.capitalize()}"))
        for ch in changes:
            sym = {"added": green("+"), "removed": red("-"), "changed": yellow("~")}.get(ch.kind, "•")
            print(f"  {sym} {ch.description}")
        print()
    if sd.affected_apis:
        print(bold("Affected APIs"))
        for a in sd.affected_apis:
            print(f"  {a}")
        print()
    for title, items in [
        ("Security impact", sd.security_impact),
        ("Performance impact", sd.performance_impact),
        ("Data impact", sd.data_impact),
        ("Compatibility impact", sd.compatibility_impact),
        ("Required verification", sd.required_verification),
    ]:
        if items:
            print(bold(title))
            for it in items:
                print(f"  - {it}")
            print()


def cmd_inspect(args):
    tc = Toolchain(args.project, provider_name=args.provider)
    try:
        tc.parse()
    except SDCError as e:
        _fail(e)
    ir = tc.ir
    if args.json:
        print(json.dumps(tc.ir_dict, indent=2, sort_keys=True))
        return
    header()
    print(bold(f"{ir.application.name} v{ir.application.version}"))
    if ir.application.description:
        print(dim(f"  {ir.application.description}"))
    print(f"\n  spec hash: {tc.spec_hash}")
    print(f"  ir hash:   {tc.ir_h}")
    print(f"  build id:  {tc.build_ident}")
    print(bold("\n  API"))
    for ep in ir.api.endpoints:
        print(f"    {ep.method:6} {ep.path}  {dim('→ ' + (ep.entity or '?'))}")
    print(bold("\n  Authentication"))
    print(f"    scheme={ir.authentication.scheme} required={ir.authentication.required}")
    print(bold("\n  Authorization"))
    print(f"    model={ir.authorization.model} roles={ir.authorization.roles} forbidden={ir.authorization.forbidden}")
    for r in ir.authorization.rules:
        print(f"    {r.effect:5} {r.subject:12} {r.predicate}")
    print(bold("\n  Data"))
    for e in ir.data.entities:
        sens = ",".join(e.sensitive_fields()) or "-"
        print(f"    {e.name} (tenant_field={e.tenant_field}) sensitive=[{sens}]")
    print(bold("\n  Behavior"))
    for b in ir.behavior.rules:
        print(f"    {b.condition:16} → {b.status}")
    print(bold("\n  Security requirements"))
    for s in ir.security.requirements:
        print(f"    {s.id}")
    print()


# --------------------------------------------------------------------------- #
# argument parsing
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sdc", description="SDC — Markdown-native application compiler")
    p.add_argument("--version", action="version", version=f"SDC {VERSION} (compiler {COMPILER_VERSION})")
    sub = p.add_subparsers(dest="command", required=True)

    def add_project(sp):
        sp.add_argument("project", nargs="?", default=".", help="project directory (default: .)")
        sp.add_argument("--provider", default="local", help="AI provider (default: local deterministic)")

    sp = sub.add_parser("init", help="scaffold a new SDC project")
    sp.add_argument("name", help="new project directory")
    sp.add_argument("--app", help="application name")
    sp.set_defaults(func=cmd_init)

    for name, fn, help_ in [
        ("validate", cmd_validate, "parse and validate the specifications"),
        ("compile", cmd_compile, "generate the implementation"),
        ("verify", cmd_verify, "verify the implementation against the spec"),
        ("test", cmd_test, "run the behavioral test suite"),
        ("build", cmd_build, "validate, compile, verify and produce an artifact"),
        ("inspect", cmd_inspect, "show the Application IR"),
    ]:
        sp = sub.add_parser(name, help=help_)
        add_project(sp)
        if name == "inspect":
            sp.add_argument("--json", action="store_true", help="emit the raw IR as JSON")
        sp.set_defaults(func=fn)

    sp = sub.add_parser("run", help="run the generated service")
    add_project(sp)
    sp.add_argument("--port", type=int, default=8080)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("diff", help="semantic diff between two specification versions")
    sp.add_argument("old", help="old project directory")
    sp.add_argument("new", help="new project directory")
    sp.add_argument("--provider", default="local")
    sp.set_defaults(func=cmd_diff)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except SDCError as e:
        _fail(e)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
