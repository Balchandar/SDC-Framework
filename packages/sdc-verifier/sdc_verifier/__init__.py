"""sdc_verifier — independent verification of the generated implementation.

The verifier runs the actual generated artifact and observes its behavior over
HTTP. It never trusts the compiler's claim of correctness.
"""

from .engine import verify, VerifyResult, build_seed
from .report import VerificationReport, Check, PASS, FAIL, UNVERIFIED, WARN
from .harness import ServiceHarness

__all__ = [
    "verify",
    "VerifyResult",
    "build_seed",
    "VerificationReport",
    "Check",
    "PASS",
    "FAIL",
    "UNVERIFIED",
    "WARN",
    "ServiceHarness",
]
