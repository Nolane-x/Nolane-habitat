from __future__ import annotations

import re


def _int_match(pattern: str, text: str) -> int:
    m = re.search(pattern, text, re.I)
    return int(m.group(1)) if m else 0


def normalize_test_output(capability: str, stdout: str, stderr: str, exit_code: int | None, timed_out: bool) -> dict | None:
    text = (stdout or "") + "\n" + (stderr or "")
    if "pytest" in capability:
        failed_tests = re.findall(r"(?m)^FAILED\s+([^\s]+)", text)
        passed = _int_match(r"(\d+)\s+passed", text)
        failed = _int_match(r"(\d+)\s+failed", text)
        skipped = _int_match(r"(\d+)\s+skipped", text)
        errors = _int_match(r"(\d+)\s+errors?", text)
        total = passed + failed + skipped + errors
        return {"kind": "test", "framework": "pytest", "status": "timeout" if timed_out else ("passed" if exit_code == 0 else "failed"),
                "total": total, "passed": passed, "failed": failed, "errors": errors, "skipped": skipped,
                "failed_tests": failed_tests[:100], "failed_tests_total": len(failed_tests),
                "failed_tests_truncated": len(failed_tests) > 100}
    if "unittest" in capability:
        ran = _int_match(r"Ran\s+(\d+)\s+tests?", text)
        failures = _int_match(r"failures=(\d+)", text)
        errors = _int_match(r"errors=(\d+)", text)
        skipped = _int_match(r"skipped=(\d+)", text)
        failed_names = re.findall(r"(?m)^(?:FAIL|ERROR):\s+([^\s(]+)", text)
        passed = max(0, ran - failures - errors - skipped)
        return {"kind": "test", "framework": "unittest", "status": "timeout" if timed_out else ("passed" if exit_code == 0 else "failed"),
                "total": ran, "passed": passed, "failed": failures, "errors": errors, "skipped": skipped,
                "failed_tests": failed_names[:100], "failed_tests_total": len(failed_names),
                "failed_tests_truncated": len(failed_names) > 100}
    if any(x in capability for x in ("jest", "vitest")):
        passed = _int_match(r"Tests:\s+.*?(\d+)\s+passed", text)
        failed = _int_match(r"Tests:\s+.*?(\d+)\s+failed", text)
        total = _int_match(r"Tests:\s+.*?(\d+)\s+total", text)
        return {"kind": "test", "framework": "jest/vitest", "status": "timeout" if timed_out else ("passed" if exit_code == 0 else "failed"),
                "total": total, "passed": passed, "failed": failed, "errors": 0, "skipped": max(0, total-passed-failed), "failed_tests": [],
                "failed_tests_total": failed, "failed_tests_truncated": False}
    return None
