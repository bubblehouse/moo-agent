#!/usr/bin/env python3
"""
test_ssh_bugs.py - Empirically diagnose build_from_yaml.py bugs.

Tests:
  1. ID capture: does @create output land between PREFIX/SUFFIX?
  2. Short verb: does @edit verb ... with "short_code" work?
  3. Long verb: does @edit verb ... with "long_code" work or hang?

Usage:
    cd extras/skills/game-designer/tools
    python test_ssh_bugs.py
"""

import re
import sys
import time
from pathlib import Path

import pexpect

sys.path.insert(0, str(Path(__file__).parent))
from moo_ssh import MooSSH  # pylint: disable=wrong-import-position


def test_id_capture(moo):
    """Test that @create output is captured between PREFIX/SUFFIX."""
    print("=== Test 1: ID capture ===")
    # Run three creates in a row to check if first one is affected
    refs = []
    for i in range(3):
        out = moo.run(f'@create "test widget {i}" from "$thing" in the void')
        print(f"  [{i}] raw output: {out!r}")
        m = re.search(r"Created (#\d+)", out)
        if m:
            print(f"  [{i}] PASS: captured {m.group(1)}")
            refs.append(m.group(1))
        else:
            print(f"  [{i}] FAIL: no 'Created #N' found")
            refs.append(None)
    return refs


def test_short_verb(moo, ref):
    """Test @edit verb with a short code string."""
    short_code = '#!moo verb test_short --on $thing --dspec this\nprint("hello world")'
    print(f"\n=== Test 2: Short verb ({len(short_code)} chars) ===")
    escaped = short_code.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    t0 = time.time()
    out = moo.run(f'@edit verb test_short on {ref} with "{escaped}"')
    elapsed = time.time() - t0
    print(f"  Output: {out!r}")
    print(f"  Elapsed: {elapsed:.1f}s")
    if "Set verb" in out or "Created verb" in out:
        print("  PASS")
    else:
        print("  FAIL or no confirmation in output")


def test_medium_verb(moo, ref):
    """Test @edit verb with a medium code string (~300 chars)."""
    lines = ["#!moo verb test_medium --on $thing --dspec this"]
    lines += [f'x_{i} = "this is value number {i}"' for i in range(8)]
    medium_code = "\n".join(lines)
    print(f"\n=== Test 3: Medium verb ({len(medium_code)} chars) ===")
    escaped = medium_code.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    t0 = time.time()
    out = moo.run(f'@edit verb test_medium on {ref} with "{escaped}"')
    elapsed = time.time() - t0
    print(f"  Output: {out!r}")
    print(f"  Elapsed: {elapsed:.1f}s")
    if "Set verb" in out or "Created verb" in out:
        print("  PASS")
    else:
        print("  FAIL or no confirmation in output")


def test_long_verb(moo, ref):
    """Test @edit verb with a long code string (~1000 chars, similar to the 'talk' verb)."""
    lines = ["#!moo verb test_long --on $thing --dspec this"]
    lines.append("from moo.sdk import context")
    lines += [f'line_{i} = "This is output line number {i} from the long verb test."' for i in range(25)]
    lines.append("print(line_0)")
    long_code = "\n".join(lines)
    print(f"\n=== Test 4: Long verb ({len(long_code)} chars) ===")
    escaped = long_code.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    t0 = time.time()
    out = moo.run(f'@edit verb test_long on {ref} with "{escaped}"')
    elapsed = time.time() - t0
    print(f"  Output: {out!r}")
    print(f"  Elapsed: {elapsed:.1f}s")
    if "Set verb" in out or "Created verb" in out:
        print("  PASS")
    else:
        print("  FAIL or no confirmation in output (possible timeout)")


def test_very_long_verb(moo, ref):
    """Test @edit verb with a very long code string (~2000 chars)."""
    lines = ["#!moo verb test_vlong --on $thing --dspec this"]
    lines.append("from moo.sdk import context")
    lines += [
        f'output_line_{i} = "This is a longer output line number {i} with some extra text to pad it out."'
        for i in range(40)
    ]
    lines.append("print(output_line_0)")
    vlong_code = "\n".join(lines)
    print(f"\n=== Test 5: Very long verb ({len(vlong_code)} chars) ===")
    escaped = vlong_code.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    t0 = time.time()
    out = moo.run(f'@edit verb test_vlong on {ref} with "{escaped}"')
    elapsed = time.time() - t0
    print(f"  Output: {out!r}")
    print(f"  Elapsed: {elapsed:.1f}s")
    if "Set verb" in out or "Created verb" in out:
        print("  PASS")
    else:
        print("  FAIL or no confirmation in output (possible timeout)")


def test_quit_disconnects():
    """Verify that @quit causes a clean EOF (not a 5 s TIMEOUT)."""
    print("\n=== Test: @quit disconnects ===")
    moo = MooSSH(timeout=10)
    moo.connect()
    moo.enable_automation_mode()

    t0 = time.time()
    moo.child.sendline("@quit")
    result = moo.child.expect([pexpect.EOF, pexpect.TIMEOUT], timeout=5)
    elapsed = time.time() - t0

    if moo.child.isalive():
        moo.child.close()
    moo.child = None

    assert result == 0, f"Expected EOF but got TIMEOUT after {elapsed:.2f}s — @quit did not disconnect"
    print(f"  PASS: clean EOF in {elapsed:.2f}s")


def main():
    print("[test_ssh_bugs] Connecting...")
    with MooSSH(timeout=15) as moo:
        moo.enable_automation_mode()

        refs = test_id_capture(moo)

        # Use first successful ref for verb tests
        ref = next((r for r in refs if r), None)
        if not ref:
            print("\nNo object created, skipping verb tests")
            return

        test_short_verb(moo, ref)
        test_medium_verb(moo, ref)
        test_long_verb(moo, ref)
        test_very_long_verb(moo, ref)

        # Cleanup all created objects
        print("\n=== Cleanup ===")
        for r in refs:
            if r:
                out = moo.run(f"@recycle {r}")
                print(f"  recycled {r}: {out!r}")

    test_quit_disconnects()

    print("\n[test_ssh_bugs] Done.")


if __name__ == "__main__":
    main()
