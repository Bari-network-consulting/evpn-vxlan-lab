#!/usr/bin/env python3
"""
fabric_test.py
==============
BGP EVPN/VXLAN Fabric — Automated End-to-End Test Suite
Runs the full 16-test ping matrix across all servers and PCs,
evaluates pass/fail, prints a colour-coded report, saves JSON,
and exits with code 0 (all pass) or 1 (any fail).

Usage:
    python fabric_test.py
    python fabric_test.py --output results.json
    python fabric_test.py --repeat 3        # ping count per test
    python fabric_test.py --workers 8       # parallel SSH sessions
    python fabric_test.py --device SRV1-TEN-A   # single device only

Requirements:
    pip install netmiko rich
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

try:
    from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
    from rich import box
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("Missing dependencies. Install with:  pip install netmiko rich")
    sys.exit(1)

# ─── Configuration ────────────────────────────────────────────────────────────

SSH_DEFAULTS = {
    "device_type": "cisco_ios",
    "username":    "admin",
    "password":    "Admin1234!",
    "timeout":     15,
    "global_delay_factor": 1,
}

# IOS legacy SSH settings for older IOL images
SSH_EXTRA_OPTIONS = (
    "-o KexAlgorithms=+diffie-hellman-group-exchange-sha1,"
    "diffie-hellman-group14-sha1 "
    "-o HostKeyAlgorithms=+ssh-rsa "
    "-o PubkeyAcceptedKeyTypes=+ssh-rsa "
    "-o StrictHostKeyChecking=no"
)

# ─── Test matrix ──────────────────────────────────────────────────────────────
# (device_name, mgmt_ip, destination, expected_result, description)
# expected_result: "pass" = connectivity expected
#                  "fail" = connectivity must NOT exist (isolation check)

TEST_MATRIX = [
    # ── TENANT-A east-west (servers) ──────────────────────────────────────────
    ("SRV1-TEN-A", "192.168.1.19", "10.10.10.21",  "pass", "SRV1-TEN-A → SRV2-TEN-A  [same tenant L2]"),
    ("SRV2-TEN-A", "192.168.1.21", "10.10.10.11",  "pass", "SRV2-TEN-A → SRV1-TEN-A  [same tenant L2]"),

    # ── TENANT-A server → PC (L3 via border leaf) ─────────────────────────────
    ("SRV1-TEN-A", "192.168.1.19", "192.168.10.3", "pass", "SRV1-TEN-A → PC1-TEN-A   [L3 border leaf]"),
    ("SRV2-TEN-A", "192.168.1.21", "192.168.10.3", "pass", "SRV2-TEN-A → PC1-TEN-A   [L3 border leaf]"),

    # ── TENANT-B east-west (servers) ──────────────────────────────────────────
    ("SRV1-TEN-B", "192.168.1.20", "10.20.20.21",  "pass", "SRV1-TEN-B → SRV2-TEN-B  [same tenant L2]"),
    ("SRV2-TEN-B", "192.168.1.22", "10.20.20.11",  "pass", "SRV2-TEN-B → SRV1-TEN-B  [same tenant L2]"),

    # ── TENANT-B server → PC (L3 via border leaf) ─────────────────────────────
    ("SRV1-TEN-B", "192.168.1.20", "192.168.20.3", "pass", "SRV1-TEN-B → PC2-TEN-B   [L3 border leaf]"),
    ("SRV2-TEN-B", "192.168.1.22", "192.168.20.3", "pass", "SRV2-TEN-B → PC2-TEN-B   [L3 border leaf]"),

    # ── PC → servers (L3 inbound) ─────────────────────────────────────────────
    ("PC1-TEN-A",  "192.168.1.23", "10.10.10.11",  "pass", "PC1-TEN-A  → SRV1-TEN-A  [L3 inbound]"),
    ("PC1-TEN-A",  "192.168.1.23", "10.10.10.21",  "pass", "PC1-TEN-A  → SRV2-TEN-A  [L3 inbound]"),
    ("PC2-TEN-B",  "192.168.1.24", "10.20.20.11",  "pass", "PC2-TEN-B  → SRV1-TEN-B  [L3 inbound]"),
    ("PC2-TEN-B",  "192.168.1.24", "10.20.20.21",  "pass", "PC2-TEN-B  → SRV2-TEN-B  [L3 inbound]"),

    # ── Cross-tenant isolation (must FAIL) ────────────────────────────────────
    ("SRV1-TEN-A", "192.168.1.19", "10.20.20.11",  "fail", "SRV1-TEN-A → SRV1-TEN-B  [ISOLATION ✗]"),
    ("SRV1-TEN-B", "192.168.1.20", "10.10.10.11",  "fail", "SRV1-TEN-B → SRV1-TEN-A  [ISOLATION ✗]"),
    ("PC1-TEN-A",  "192.168.1.23", "10.20.20.11",  "fail", "PC1-TEN-A  → SRV1-TEN-B  [ISOLATION ✗]"),
    ("PC2-TEN-B",  "192.168.1.24", "10.10.10.11",  "fail", "PC2-TEN-B  → SRV1-TEN-A  [ISOLATION ✗]"),
]

# ─── Data structures ──────────────────────────────────────────────────────────

@dataclass
class TestResult:
    test_id:      int
    device:       str
    mgmt_ip:      str
    destination:  str
    description:  str
    expected:     str          # "pass" or "fail"
    actual:       str          # "pass", "fail", or "error"
    success_rate: Optional[int] = None   # 0-100
    raw_output:   str = ""
    error_msg:    str = ""
    duration_ms:  int = 0

    @property
    def verdict(self) -> str:
        """PASS if actual matches expected, FAIL otherwise."""
        return "PASS" if self.actual == self.expected else "FAIL"

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"


# ─── SSH + ping logic ─────────────────────────────────────────────────────────

def run_ping(device: str, mgmt_ip: str, destination: str,
             repeat: int = 5) -> tuple[str, int, str]:
    """
    SSH into device, run ping, return (actual_result, success_rate, raw_output).
    actual_result = "pass" | "fail" | "error"
    """
    conn_params = {**SSH_DEFAULTS, "host": mgmt_ip}

    try:
        conn = ConnectHandler(**conn_params)
        cmd = f"ping {destination} repeat {repeat}"
        output = conn.send_command(cmd, read_timeout=30)
        conn.disconnect()

        # Parse success rate from IOS output
        # "Success rate is 100 percent (5/5)"
        # "Success rate is 0 percent (0/5)"
        match = re.search(r"Success rate is (\d+) percent", output)
        if match:
            rate = int(match.group(1))
            actual = "pass" if rate > 0 else "fail"
            return actual, rate, output

        # Fallback: count ! and .
        bangs = output.count("!")
        dots  = output.count(".")
        if bangs > 0:
            rate = int(bangs / (bangs + dots) * 100)
            return "pass", rate, output
        elif dots > 0:
            return "fail", 0, output
        else:
            return "error", -1, output

    except NetmikoTimeoutException:
        return "error", -1, "SSH timeout"
    except NetmikoAuthenticationException:
        return "error", -1, "Authentication failed"
    except Exception as e:
        return "error", -1, str(e)


def run_test(test_id: int, row: tuple, repeat: int) -> TestResult:
    device, mgmt_ip, destination, expected, description = row
    t0 = time.time()
    actual, rate, raw = run_ping(device, mgmt_ip, destination, repeat)
    elapsed = int((time.time() - t0) * 1000)

    return TestResult(
        test_id     = test_id,
        device      = device,
        mgmt_ip     = mgmt_ip,
        destination = destination,
        description = description,
        expected    = expected,
        actual      = actual,
        success_rate= rate if rate >= 0 else None,
        raw_output  = raw,
        error_msg   = raw if actual == "error" else "",
        duration_ms = elapsed,
    )


# ─── Report rendering ─────────────────────────────────────────────────────────

console = Console()

VERDICT_STYLE = {
    "PASS": "bold green",
    "FAIL": "bold red",
}
ACTUAL_STYLE = {
    "pass":  "green",
    "fail":  "yellow",
    "error": "red",
}
EXPECTED_STYLE = {
    "pass": "cyan",
    "fail": "magenta",
}


def render_results(results: list[TestResult], elapsed: float) -> Table:
    table = Table(
        title=f"BGP EVPN/VXLAN — End-to-End Test Results",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold white on dark_blue",
    )
    table.add_column("#",           justify="right",  width=3)
    table.add_column("Device",      width=14)
    table.add_column("Destination", width=16)
    table.add_column("Description", width=46)
    table.add_column("Expected",    justify="center", width=10)
    table.add_column("Actual",      justify="center", width=8)
    table.add_column("Rate",        justify="center", width=6)
    table.add_column("ms",          justify="right",  width=6)
    table.add_column("Verdict",     justify="center", width=8)

    for r in results:
        rate_str = f"{r.success_rate}%" if r.success_rate is not None else "—"
        table.add_row(
            str(r.test_id),
            r.device,
            r.destination,
            r.description,
            Text(r.expected.upper(), style=EXPECTED_STYLE[r.expected]),
            Text(r.actual.upper(),   style=ACTUAL_STYLE.get(r.actual, "white")),
            rate_str,
            str(r.duration_ms),
            Text(r.verdict, style=VERDICT_STYLE.get(r.verdict, "white")),
        )

    return table


def render_summary(results: list[TestResult], elapsed: float) -> Panel:
    total   = len(results)
    passed  = sum(1 for r in results if r.passed)
    failed  = total - passed
    errors  = sum(1 for r in results if r.actual == "error")

    # breakdown
    isolation_tests = [r for r in results if r.expected == "fail"]
    connectivity_tests = [r for r in results if r.expected == "pass"]
    iso_pass  = sum(1 for r in isolation_tests  if r.passed)
    conn_pass = sum(1 for r in connectivity_tests if r.passed)

    overall = "ALL TESTS PASSED ✓" if failed == 0 else f"{failed} TEST(S) FAILED ✗"
    overall_style = "bold green" if failed == 0 else "bold red"

    lines = [
        Text(overall, style=overall_style),
        Text(""),
        Text(f"Total tests:          {total}"),
        Text(f"Passed:               {passed}", style="green" if passed == total else "yellow"),
        Text(f"Failed:               {failed}", style="red" if failed > 0 else "green"),
        Text(f"Errors (SSH/timeout): {errors}", style="red" if errors > 0 else "green"),
        Text(""),
        Text(f"Connectivity tests:   {conn_pass}/{len(connectivity_tests)} passed",
             style="green" if conn_pass == len(connectivity_tests) else "red"),
        Text(f"Isolation tests:      {iso_pass}/{len(isolation_tests)} passed",
             style="green" if iso_pass == len(isolation_tests) else "red"),
        Text(""),
        Text(f"Total elapsed:        {elapsed:.1f}s"),
    ]

    group = Text()
    for line in lines:
        group.append_text(line)
        group.append("\n")

    return Panel(group, title="[bold]Summary[/bold]",
                 border_style="green" if failed == 0 else "red")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="BGP EVPN/VXLAN fabric automated test suite"
    )
    parser.add_argument("--output",  help="Save JSON report to file")
    parser.add_argument("--repeat",  type=int, default=5,
                        help="Ping repeat count per test (default: 5)")
    parser.add_argument("--workers", type=int, default=6,
                        help="Parallel SSH workers (default: 6)")
    parser.add_argument("--device",  help="Run tests for this device only")
    args = parser.parse_args()

    # Filter matrix if --device specified
    matrix = TEST_MATRIX
    if args.device:
        matrix = [row for row in TEST_MATRIX if row[0] == args.device]
        if not matrix:
            console.print(f"[red]Device '{args.device}' not found in test matrix[/]")
            sys.exit(1)

    console.print(Panel(
        f"[bold]BGP EVPN/VXLAN — Fabric Test Suite[/bold]\n"
        f"Tests: {len(matrix)}  |  "
        f"Ping repeat: {args.repeat}  |  "
        f"Workers: {args.workers}  |  "
        f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="blue"
    ))

    results: list[TestResult] = [None] * len(matrix)
    t_start = time.time()

    # Progress bar
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console,
    )

    with progress:
        task = progress.add_task("Running tests...", total=len(matrix))

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(run_test, i + 1, row, args.repeat): i
                for i, row in enumerate(matrix)
            }
            for future in as_completed(futures):
                idx = futures[future]
                result = future.result()
                results[idx] = result
                verdict_icon = "✓" if result.passed else "✗"
                verdict_color = "green" if result.passed else "red"
                progress.console.print(
                    f"  [{verdict_color}]{verdict_icon}[/] "
                    f"[dim]{result.device:14s}[/] → "
                    f"[cyan]{result.destination:16s}[/] "
                    f"[{verdict_color}]{result.verdict}[/] "
                    f"[dim]({result.duration_ms}ms)[/]"
                )
                progress.advance(task)

    elapsed = time.time() - t_start

    # Print results table
    console.print()
    console.print(render_results(results, elapsed))
    console.print()
    console.print(render_summary(results, elapsed))

    # Save JSON report
    if args.output:
        report = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [asdict(r) for r in results],
        }
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
        console.print(f"\n[dim]JSON report saved to {args.output}[/]")

    # Exit code
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()
