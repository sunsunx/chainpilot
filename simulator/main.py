from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import (
    DECISION_MODE_BASIC_BASELINE,
    DECISION_MODE_LLM,
    DECISION_MODE_RULE_BASED_BDI,
    SCENARIOS,
    validate_decision_mode,
)
from .runner import run_scenario, scenario_names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mesa four-node semiconductor supply-chain simulation."
    )
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS.keys()],
        default="baseline",
        help="Scenario to run.",
    )
    parser.add_argument("--days", type=int, default=365, help="Simulation horizon.")
    parser.add_argument("--seed", type=int, default=2025, help="Random seed.")
    parser.add_argument(
        "--decision_mode",
        type=validate_decision_mode,
        choices=[
            DECISION_MODE_BASIC_BASELINE,
            DECISION_MODE_RULE_BASED_BDI,
            DECISION_MODE_LLM,
        ],
        default=DECISION_MODE_RULE_BASED_BDI,
        help=("Use the basic baseline, rule-based BDI, or LLM decision mode."),
    )
    parser.add_argument(
        "--llm_model",
        type=str,
        default=os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
        help=("Local Ollama model used by the LLM decision mode."),
    )
    parser.add_argument(
        "--out_dir",
        type=Path,
        default=Path("data/mesa_semiconductor"),
        help="Output directory.",
    )
    parser.add_argument(
        "--demand_sequence_dir",
        type=Path,
        default=None,
        help=(
            "Directory containing scenario demand CSV files "
            "(baseline.csv, geopolitical.csv)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = list(scenario_names(args.scenario))
    for name in names:
        out_dir = args.out_dir / name if args.scenario == "all" else args.out_dir
        run_scenario(
            name,
            days=args.days,
            seed=args.seed,
            out_dir=out_dir,
            decision_mode=args.decision_mode,
            llm_model=args.llm_model,
            demand_sequence_dir=args.demand_sequence_dir,
        )
        print(f"wrote {name} outputs to {out_dir}")


if __name__ == "__main__":
    main()
