"""Quick verification tests for the modular semiconductor simulation."""

import unittest
from pathlib import Path

import pandas as pd

from simulator.config import DECISION_MODE_BASIC_BASELINE, DECISION_MODE_RULE_BASED_BDI
from simulator.llm import LLMDecisionEngine
from simulator.model import SemiSCM


ROOT = Path(__file__).resolve().parent.parent
DEMAND_FILE = (
    ROOT
    / "data"
    / "demo_baseline_365"
    / "daily_records.csv"
)

def load_demand(scenario: str, days: int = 3):
    values = pd.read_csv(DEMAND_FILE)["demand"]
    return values.astype(int).tolist()[:days]


class SimulationVerificationTests(unittest.TestCase):
    def run_model(self, mode=DECISION_MODE_BASIC_BASELINE):
        days = 3
        model = SemiSCM(
            scenario_name="baseline",
            days=days,
            seed=2025,
            decision_mode=mode,
            demand_sequence=load_demand("baseline", days),
        )
        model.run_model()
        return model

    def test_model_completes_and_keeps_values_valid(self):
        model = self.run_model()
        self.assertEqual(len(model.daily_records), 3)
        for record in model.daily_records:
            self.assertGreaterEqual(record["cu_backlog"], 0)
            self.assertGreaterEqual(record["dc_on_hand"], 0)
            self.assertGreaterEqual(record["fulfilment_rate_to_date"], 0.0)
            self.assertLessEqual(record["fulfilment_rate_to_date"], 1.0)

    def test_same_seed_is_reproducible(self):
        self.assertEqual(self.run_model().daily_records, self.run_model().daily_records)

    def test_rule_based_mode_runs_without_ollama(self):
        model = self.run_model(DECISION_MODE_RULE_BASED_BDI)
        self.assertEqual(len(model.daily_records), 3)

    def test_invalid_llm_action_is_rejected(self):
        engine = LLMDecisionEngine("llm_decision")
        schema = {
            "allowed": {"action": ["hold", "replenish", "nego_expedite"]},
            "numeric_bounds": {"qty": [0, 10]},
        }
        with self.assertRaises(ValueError):
            engine._validate(
                {"action": "invalid_action", "qty": 10},
                schema,
                {"action": "replenish", "qty": 10},
            )

if __name__ == "__main__":
    unittest.main()
