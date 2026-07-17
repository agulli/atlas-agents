"""
enterprise_ceiling_calculator.py — Model the automation ceiling for a process portfolio.

Chapter 21 introduces the 27% problem: only ~27% of enterprise processes are
fully automatable today. This tool lets you input your process portfolio and
model what happens to that ceiling as agentic capabilities improve.

Outputs:
  - Current automation coverage (Zone I + partial Zone II)
  - Projected coverage with guardrails, self-improvement
  - Which processes are in each zone and why
  - Token/cost estimate for the automatable subset

Usage:
    python enterprise_ceiling_calculator.py --demo
    python enterprise_ceiling_calculator.py --processes processes.json

Requires: pip install anthropic
"""

import argparse
import json
from dataclasses import dataclass
from typing import Literal

import anthropic

client = anthropic.Anthropic()

Zone = Literal["I", "II", "III", "IV"]

# ── Process definition ────────────────────────────────────────────────

@dataclass
class BusinessProcess:
    name:               str
    description:        str
    volume_per_month:   int          # Number of instances per month
    avg_handling_time:  float        # Minutes per instance (human)
    exception_rate:     float        # Fraction that require judgment (0–1)
    compliance_level:   str          # "none", "moderate", "strict"
    data_quality:       str          # "clean", "messy", "mixed"

    def zone(self) -> Zone:
        """Classify this process into the four automation zones."""
        if self.exception_rate < 0.05 and self.data_quality == "clean" and self.compliance_level == "none":
            return "I"
        elif self.exception_rate < 0.25 and self.data_quality in ("clean", "mixed"):
            return "II"
        elif self.exception_rate < 0.50 or self.compliance_level == "strict":
            return "III"
        else:
            return "IV"

    def automatable_fraction(self) -> float:
        """Estimate what fraction is automatable today."""
        z = self.zone()
        if z == "I":  return 0.95
        if z == "II": return 0.40
        if z == "III": return 0.10
        return 0.0

    def projected_fraction(
        self,
        with_guardrails: bool = False,
        with_self_improvement: bool = False,
    ) -> float:
        """Project automation fraction with capability improvements."""
        base = self.automatable_fraction()
        if with_guardrails and self.compliance_level == "strict":
            base = min(base + 0.15, 0.70)   # Guardrails unlock Zone III
        if with_self_improvement:
            # Self-improvement reduces effective exception rate over time
            adjusted_exception = self.exception_rate * 0.6
            if adjusted_exception < 0.25 and self.zone() in ("II", "III"):
                base = min(base + 0.20, 0.85)
        return base


# ── Sample process portfolio ──────────────────────────────────────────

SAMPLE_PROCESSES = [
    BusinessProcess(
        name="Invoice matching",
        description="Match vendor invoices to POs automatically",
        volume_per_month=5000, avg_handling_time=3,
        exception_rate=0.03, compliance_level="none", data_quality="clean",
    ),
    BusinessProcess(
        name="Invoice exception handling",
        description="Handle invoices that don't match POs exactly",
        volume_per_month=150, avg_handling_time=25,
        exception_rate=0.22, compliance_level="none", data_quality="mixed",
    ),
    BusinessProcess(
        name="New vendor onboarding",
        description="Validate and onboard new suppliers",
        volume_per_month=40, avg_handling_time=90,
        exception_rate=0.35, compliance_level="moderate", data_quality="mixed",
    ),
    BusinessProcess(
        name="Customer order confirmation",
        description="Confirm standard product orders",
        volume_per_month=10000, avg_handling_time=2,
        exception_rate=0.01, compliance_level="none", data_quality="clean",
    ),
    BusinessProcess(
        name="Contract review",
        description="Review and redline vendor contracts",
        volume_per_month=20, avg_handling_time=180,
        exception_rate=0.80, compliance_level="strict", data_quality="clean",
    ),
    BusinessProcess(
        name="Compliance document classification",
        description="Classify incoming regulatory filings",
        volume_per_month=200, avg_handling_time=15,
        exception_rate=0.08, compliance_level="strict", data_quality="clean",
    ),
    BusinessProcess(
        name="Support ticket triage",
        description="Classify and route customer support tickets",
        volume_per_month=8000, avg_handling_time=5,
        exception_rate=0.04, compliance_level="none", data_quality="clean",
    ),
    BusinessProcess(
        name="Expense report approval",
        description="Review and approve employee expense reports",
        volume_per_month=1500, avg_handling_time=8,
        exception_rate=0.18, compliance_level="moderate", data_quality="clean",
    ),
    BusinessProcess(
        name="M&A due diligence",
        description="Analyze target company financials and risks",
        volume_per_month=2, avg_handling_time=4800,
        exception_rate=0.95, compliance_level="strict", data_quality="mixed",
    ),
    BusinessProcess(
        name="Regulatory filing",
        description="Prepare and submit quarterly regulatory reports",
        volume_per_month=4, avg_handling_time=480,
        exception_rate=0.45, compliance_level="strict", data_quality="mixed",
    ),
]


# ── Analysis ──────────────────────────────────────────────────────────

@dataclass
class PortfolioAnalysis:
    total_monthly_hours:     float
    automatable_hours:       float
    projected_hours_guardrails: float
    projected_hours_self_improvement: float
    coverage_today:          float
    coverage_guardrails:     float
    coverage_self_improvement: float
    zone_breakdown:          dict[str, list[str]]
    highest_value_targets:   list[str]


def analyze_portfolio(processes: list[BusinessProcess]) -> PortfolioAnalysis:
    total_hours   = sum(p.volume_per_month * p.avg_handling_time / 60 for p in processes)
    auto_hours    = sum(p.volume_per_month * p.avg_handling_time / 60 * p.automatable_fraction()
                        for p in processes)
    guard_hours   = sum(p.volume_per_month * p.avg_handling_time / 60
                        * p.projected_fraction(with_guardrails=True)
                        for p in processes)
    self_imp_hours = sum(p.volume_per_month * p.avg_handling_time / 60
                         * p.projected_fraction(with_guardrails=True, with_self_improvement=True)
                         for p in processes)

    zone_breakdown: dict[str, list[str]] = {"I": [], "II": [], "III": [], "IV": []}
    for p in processes:
        zone_breakdown[p.zone()].append(p.name)

    # Highest-value targets: Zone II with high volume
    zone_ii = [p for p in processes if p.zone() == "II"]
    zone_ii.sort(key=lambda p: p.volume_per_month * p.avg_handling_time, reverse=True)

    return PortfolioAnalysis(
        total_monthly_hours=total_hours,
        automatable_hours=auto_hours,
        projected_hours_guardrails=guard_hours,
        projected_hours_self_improvement=self_imp_hours,
        coverage_today=auto_hours / total_hours,
        coverage_guardrails=guard_hours / total_hours,
        coverage_self_improvement=self_imp_hours / total_hours,
        zone_breakdown=zone_breakdown,
        highest_value_targets=[p.name for p in zone_ii[:3]],
    )


def print_report(analysis: PortfolioAnalysis, processes: list[BusinessProcess]):
    print("\n" + "="*60)
    print("ENTERPRISE AUTOMATION CEILING ANALYSIS")
    print("="*60)
    print(f"\nTotal monthly workload: {analysis.total_monthly_hours:.0f} person-hours\n")

    print("COVERAGE BY SCENARIO")
    print(f"  {'Today (agents):':<35} {analysis.coverage_today:>6.0%}  "
          f"({analysis.automatable_hours:.0f}h saved/mo)")
    print(f"  {'+ Compliance guardrails:':<35} {analysis.coverage_guardrails:>6.0%}  "
          f"({analysis.projected_hours_guardrails:.0f}h saved/mo)")
    print(f"  {'+ Self-improving scaffolding:':<35} {analysis.coverage_self_improvement:>6.0%}  "
          f"({analysis.projected_hours_self_improvement:.0f}h saved/mo)")

    print("\nZONE BREAKDOWN")
    zone_labels = {"I": "Automatable now", "II": "Needs checkpoints",
                   "III": "High stakes", "IV": "Not yet"}
    for zone, label in zone_labels.items():
        names = analysis.zone_breakdown[zone]
        print(f"  Zone {zone} ({label}): {len(names)} processes")
        for n in names:
            print(f"    - {n}")

    if analysis.highest_value_targets:
        print("\nHIGHEST-VALUE ZONE II TARGETS (best ROI for agentic investment)")
        for name in analysis.highest_value_targets:
            p = next(proc for proc in processes if proc.name == name)
            monthly_hours = p.volume_per_month * p.avg_handling_time / 60
            print(f"  - {p.name}: {monthly_hours:.0f}h/mo, "
                  f"{p.exception_rate:.0%} exception rate → "
                  f"~{p.projected_fraction(with_self_improvement=True):.0%} automatable with self-improvement")

    additional = (analysis.coverage_self_improvement - analysis.coverage_today)
    print(f"\nSelf-improvement adds {additional:.0%} coverage — the difference between "
          f"\"pilot project\" and \"operational system.\"")


def main():
    parser = argparse.ArgumentParser(description="Enterprise Automation Ceiling Calculator")
    parser.add_argument("--demo",      action="store_true")
    parser.add_argument("--processes", default=None, help="Path to processes JSON")
    args = parser.parse_args()

    if args.processes:
        with open(args.processes) as f:
            raw      = json.load(f)
            processes = [BusinessProcess(**p) for p in raw]
    else:
        processes = SAMPLE_PROCESSES

    analysis = analyze_portfolio(processes)
    print_report(analysis, processes)


if __name__ == "__main__":
    main()
