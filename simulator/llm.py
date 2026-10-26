from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from .config import (
    DECISION_MODE_LLM,
    DECISION_MODE_RULE_BASED_BDI,
    validate_decision_mode,
)


# LLM decision engine using Ollama and constrained action.
class LLMDecisionEngine:
    def __init__(
        self,
        decision_mode: str = DECISION_MODE_RULE_BASED_BDI,
        model_name: str = "llama3.2:3b",
    ) -> None:
        self.decision_mode = validate_decision_mode(decision_mode)
        self.model_name = model_name
        self.ollama_base_url = os.environ.get(
            "OLLAMA_BASE_URL",
            "http://localhost:11434",
        ).rstrip("/")
        self.last_source = DECISION_MODE_RULE_BASED_BDI
        self.last_reason = ""

    def choose_intention(
        self,
        agent_name: str,
        beliefs: Dict[str, Any],
        desires: Dict[str, Any],
        rule_intention: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self.decision_mode == DECISION_MODE_LLM:
            self.last_source = DECISION_MODE_RULE_BASED_BDI
        else:
            self.last_source = self.decision_mode
        self.last_reason = "rule_based_decision"
        if self.decision_mode != DECISION_MODE_LLM:
            return rule_intention
        try:
            candidate = self._request_json(
                agent_name, beliefs, desires, schema,
            )
            validated = self._validate(candidate, schema, rule_intention)
        except urllib.error.HTTPError as exc:
            detail = self._read_http_error(exc)
            self.last_reason = (f"fallback_HTTPError_{exc.code}_{detail}")[:240]
            return rule_intention
        except urllib.error.URLError as exc:
            self.last_reason = f"fallback_URLError_{exc.reason}"[:240]
            return rule_intention
        except Exception as exc:
            self.last_reason = f"fallback_{type(exc).__name__}_{exc}"[:240]
            return rule_intention

        self.last_source = DECISION_MODE_LLM
        self.last_reason = str(validated.get("reason", "llm_decision"))[:240]
        validated.pop("reason", None)
        return validated

    def _read_http_error(self, exc: urllib.error.HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
        raw = raw.replace("\n", " ").strip()
        return raw[:180]

    def _request_json(
        self,
        agent_name: str,
        beliefs: Dict[str, Any],
        desires: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        system = (
            "You are an intention selector in a semiconductor supply chain BDI simulation. "
            "Return only valid JSON. "
            "Choose only allowed options. "
            "Do not invent inv, capacity, or actions outside the schema. "
        )
        user = {
            "agent": agent_name,
            "beliefs": beliefs,
            "desires": desires,
            "required_schema": schema,
            "instruction": (
                "Select the next valid intention. "
                "Balance cu service and operational cost. "
                "When backlog is high, consider actions that reduce it, "
                "while respecting inv, capacity, cost, and lead-time constraints. "
                "When on-hand and pipeline inv are sufficient and backlog "
                "pressure is low, avoid excessive or repeated replenishment. "
                "Provide a short reason. "
            ),
        }
        return self._request_ollama_json(system, user)

    def _extract_json_object(self, content: str) -> Dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`").strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start : end + 1])
            raise

    def _request_ollama_json(
        self,
        system: str,
        user: Dict[str, Any],
    ) -> Dict[str, Any]:
        model_name = self.model_name or "llama3.2:3b"
        payload = {
            "model": model_name,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
        }
        req = urllib.request.Request(
            f"{self.ollama_base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["message"]["content"]
        return self._extract_json_object(content)

    # Check LLM output constraints
    def _validate(
        self,
        candidate: Dict[str, Any],
        schema: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        output = dict(fallback)
        allowed = schema.get("allowed", {})
        numeric_bounds = schema.get("numeric_bounds", {})
        # constraint check
        for key, allowed_values in allowed.items():
            value = candidate.get(key, output.get(key))
            if value not in allowed_values:
                raise ValueError(f"invalid {key}: {value}")
            output[key] = value

        for key, bounds in numeric_bounds.items():
            value = candidate.get(key, output.get(key, 0))
            value = float(value)
            lo, hi = float(bounds[0]), float(bounds[1])
            value = max(lo, min(hi, value))
            if key.endswith("qty"):
                value = int(round(value))
            output[key] = value

        if "reason" in candidate:
            output["reason"] = str(candidate["reason"])
        return output
