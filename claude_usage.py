#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from run_utils import load_run_manifest


PRICING_FILE = "anthropic_model_pricing.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pricing(base_dir: Path) -> dict[str, Any]:
    return _load_json(base_dir / PRICING_FILE)


def _match_model_pricing(model: str, pricing_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    models = pricing_payload.get("models", {})
    if model in models:
        return model, dict(models[model])

    for canonical_name, item in models.items():
        aliases = list(item.get("aliases", []))
        if any(model.startswith(alias) for alias in aliases):
            return canonical_name, dict(item)

    return None, None


def _estimate_cost(
    *,
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    pricing_payload: dict[str, Any],
) -> dict[str, Any]:
    if not model:
        return {
            "pricing_available": False,
            "reason": "No model name was recorded in the Claude response.",
        }

    canonical_model, model_pricing = _match_model_pricing(model, pricing_payload)
    if not model_pricing:
        return {
            "pricing_available": False,
            "reason": f"No pricing entry is configured for model {model!r}.",
        }

    pricing = dict(model_pricing.get("pricing") or {})
    input_rate = float(pricing.get("input_per_million_usd") or 0.0)
    cached_input_rate = float(pricing.get("cached_input_per_million_usd") or 0.0)
    output_rate = float(pricing.get("output_per_million_usd") or 0.0)

    uncached_input_tokens = max(int(input_tokens) - int(cached_input_tokens), 0)

    estimated_cost = (
        (uncached_input_tokens * input_rate)
        + (int(cached_input_tokens) * cached_input_rate)
        + (int(output_tokens) * output_rate)
    ) / 1_000_000

    return {
        "pricing_available": True,
        "model": model,
        "pricing_model": canonical_model,
        "pricing_source": pricing_payload.get("source"),
        "uncached_input_tokens": uncached_input_tokens,
        "cached_input_tokens": int(cached_input_tokens),
        "output_tokens": int(output_tokens),
        "standard_rates_usd_per_million_tokens": {
            "input": input_rate,
            "cached_input": cached_input_rate,
            "output": output_rate,
        },
        "estimated_cost_usd": round(estimated_cost, 6),
    }


def _parse_agent_response(response_path: Path) -> dict[str, Any]:
    """Extract usage from a stored Claude CLI JSON response.

    The response is a stream-json 'result' event from Claude CLI which has:
    - usage.input_tokens, usage.cache_read_input_tokens, usage.output_tokens
    - modelUsage.<model-name>.{inputTokens, outputTokens, ...}
    - session_id
    """
    if not response_path.exists():
        raise FileNotFoundError(f"Claude response file not found: {response_path}")

    response = _load_json(response_path)
    usage = response.get("usage") or {}
    session_id = response.get("session_id") or None

    # Extract model name from modelUsage keys (e.g. {"claude-sonnet-4-6": {...}})
    model_usage = response.get("modelUsage") or {}
    model = response.get("model") or (list(model_usage.keys())[0] if model_usage else None)

    # Claude CLI uses cache_read_input_tokens in the result event
    cached_input = int(
        usage.get("cache_read_input_tokens")
        or usage.get("cache_read_tokens")
        or usage.get("cached_input_tokens")
        or 0
    )
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)

    return {
        "session_id": session_id,
        "model": model,
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    }


def _build_agent_summary(
    *,
    name: str,
    label: str,
    response_path: Path,
    pricing_payload: dict[str, Any],
    status: str | None = None,
) -> dict[str, Any]:
    parsed = _parse_agent_response(response_path)
    usage = dict(parsed.get("usage") or {})
    input_tokens = int(usage.get("input_tokens") or 0)
    cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

    return {
        "name": name,
        "label": label or name,
        "status": status,
        "session": {
            "session_id": parsed.get("session_id"),
            "model": parsed.get("model"),
            "response_path": str(response_path.resolve()),
        },
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "cost": _estimate_cost(
            model=parsed.get("model"),
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            pricing_payload=pricing_payload,
        ),
    }


def _summarize_agents(agent_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    pricing_available = True

    for agent in agent_summaries:
        usage = dict(agent.get("usage") or {})
        cost = dict(agent.get("cost") or {})
        totals["input_tokens"] += int(usage.get("input_tokens") or 0)
        totals["cached_input_tokens"] += int(usage.get("cached_input_tokens") or 0)
        totals["output_tokens"] += int(usage.get("output_tokens") or 0)
        totals["total_tokens"] += int(usage.get("total_tokens") or 0)

        if cost.get("pricing_available"):
            totals["estimated_cost_usd"] += float(cost.get("estimated_cost_usd") or 0.0)
        else:
            pricing_available = False

    totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 6)
    totals["pricing_available_for_all_agents"] = pricing_available
    totals["agent_count"] = len(agent_summaries)
    return totals


def build_run_usage_summary(base_dir: Path, run_dir: Path) -> dict[str, Any]:
    manifest = load_run_manifest(run_dir)
    pricing_payload = _load_pricing(base_dir)
    agent_entries = manifest.get("review_agents")

    agent_summaries: list[dict[str, Any]] = []
    missing_agents: list[dict[str, Any]] = []

    if isinstance(agent_entries, list) and agent_entries:
        for raw_entry in agent_entries:
            if not isinstance(raw_entry, dict):
                continue

            name = str(raw_entry.get("name") or "agent")
            label = str(raw_entry.get("label") or name)
            status = str(raw_entry.get("status") or "")

            response_path_value = raw_entry.get("response_path")
            if response_path_value:
                response_path = Path(str(response_path_value))
                try:
                    agent_summaries.append(
                        _build_agent_summary(
                            name=name,
                            label=label,
                            response_path=response_path,
                            pricing_payload=pricing_payload,
                            status=status,
                        )
                    )
                    continue
                except Exception as exc:  # noqa: BLE001
                    missing_agents.append(
                        {
                            "name": name,
                            "label": label,
                            "status": status,
                            "reason": str(exc),
                        }
                    )
                    continue

            # Fallback: look for claude_response.json in the runtime directory
            runtime_dir_value = raw_entry.get("runtime_dir")
            if runtime_dir_value:
                fallback_path = Path(str(runtime_dir_value)) / "claude_response.json"
                try:
                    agent_summaries.append(
                        _build_agent_summary(
                            name=name,
                            label=label,
                            response_path=fallback_path,
                            pricing_payload=pricing_payload,
                            status=status,
                        )
                    )
                    continue
                except Exception:  # noqa: BLE001
                    pass

            missing_agents.append(
                {
                    "name": name,
                    "label": label,
                    "status": status,
                    "reason": "No Claude response file found.",
                }
            )

    if not agent_summaries and not missing_agents:
        raise FileNotFoundError("No review agents found in the run manifest.")

    return {
        "agents": agent_summaries,
        "totals": _summarize_agents(agent_summaries),
        "missing_agents": missing_agents,
    }


def write_run_usage_summary(base_dir: Path, run_dir: Path) -> Path:
    summary = build_run_usage_summary(base_dir, run_dir)
    path = run_dir / "usage_summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path
