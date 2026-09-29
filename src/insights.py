from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Protocol
from dataclasses import dataclass


class LLMClient(Protocol):
    def complete(self, prompt: str, timeout_seconds: float) -> str:
        ...


class InvalidEvent(ValueError):
    pass


class InvalidLLMResponse(ValueError):
    pass


@dataclass
class PR:
    opened_at: datetime | None
    merged_at: datetime | None

    @property
    def cycle_time(self) -> float | None:
        if self.merged_at is None or self.opened_at is None:
            return None

        return (self.merged_at - self.opened_at).total_seconds() / 3600


SUPPORTED_TYPES = {
    "pr_opened",
    "pr_merged",
    "deployment",
    "incident",
}


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise InvalidEvent("timestamp must be a string")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidEvent(f"invalid timestamp: {value}") from exc

    if parsed.tzinfo is None:
        raise InvalidEvent("timestamp must include a timezone")

    return parsed.astimezone(timezone.utc)


def validate_event(event: Any) -> tuple[str, datetime, str | None]:
    if not isinstance(event, dict):
        raise InvalidEvent("each event must be an object")

    event_type = event.get("type")
    if event_type not in SUPPORTED_TYPES:
        raise InvalidEvent(f"unsupported event type: {event_type}")

    timestamp = parse_timestamp(event.get("timestamp"))

    event_id = event.get("id")
    requires_id = event_type in {"pr_opened", "pr_merged"}

    if requires_id and not isinstance(event_id, str):
        raise InvalidEvent(f"{event_type} requires a string id")

    if event_id is not None and not isinstance(event_id, str):
        raise InvalidEvent("id must be a string when provided")

    return event_type, timestamp, event_id


def calculate_metrics(events: list[dict[str, Any]]) -> dict[str, int | float]:
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    
    prs: dict[str, PR] = {}
    merged_prs: int = 0
    deployments = 0
    incidents = 0

    for event in events:
        event_type, timestamp, event_id = validate_event(event)

        if event_id is not None:
            pr = prs.get(event_id)
            if pr is None:
                pr = PR(opened_at=None, merged_at=None)

            if event_type == "pr_opened":
                pr.opened_at = timestamp
            else:
                pr.merged_at = timestamp
                merged_prs += 1

            prs[event_id] = pr

        elif event_type == "deployment":
            deployments += 1
        elif event_type == "incident":
            incidents += 1

    cycle_times = []

    for pr in prs.values():
        cycle_time = pr.cycle_time
        if cycle_time is None:
            continue

        cycle_times.append(cycle_time)

    average_cycle_time = (
        round(sum(cycle_times) / len(cycle_times), 2)
        if cycle_times
        else None
    )

    return {
        "merged_prs": merged_prs,
        "average_pr_cycle_time_hours": average_cycle_time,
        "deployments": deployments,
        "incidents": incidents,
    }


def build_prompt(team_id: str, metrics: dict[str, int | float]) -> str:
    metrics_json = json.dumps(metrics, sort_keys=True)

    return (
        "You are assisting with team-level engineering productivity insights. "
        "Do not evaluate individuals, infer personal performance, or invent data. "
        "Use only the following aggregated metrics. Return JSON with exactly "
        "a string field named summary and an array of string recommendations.\n\n"
        f"Team: {team_id}\n"
        f"Aggregated metrics: {metrics_json}"
    )


def parse_llm_response(response: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as exc:
        raise InvalidLLMResponse("LLM response was not valid JSON") from exc

    if not isinstance(parsed, dict):
        raise InvalidLLMResponse("LLM response must be a JSON object")

    summary = parsed.get("summary")
    recommendations = parsed.get("recommendations")

    if not isinstance(summary, str):
        raise InvalidLLMResponse("summary must be a string")

    if (
        not isinstance(recommendations, list)
        or not all(isinstance(item, str) for item in recommendations)
    ):
        raise InvalidLLMResponse(
            "recommendations must be a list of strings"
        )

    return {
        "summary": summary,
        "recommendations": recommendations,
    }


def call_llm(llm_client: LLMClient, prompt: str) -> dict[str, Any]:
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            raw_response = llm_client.complete(
                prompt,
                timeout_seconds=5.0,
            )
            insight = parse_llm_response(raw_response)
            break
        except (TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt == 1:
                raise RuntimeError("LLM request failed after retry") from exc
        except InvalidLLMResponse:
            raise
    else:
        raise RuntimeError("LLM request failed") from last_error

    return insight

    
def generate_team_insight(
    team_id: str,
    events: list[dict[str, Any]],
    llm_client: LLMClient,
) -> dict[str, Any]:
    if not isinstance(team_id, str) or not team_id.strip():
        raise ValueError("team_id must be a non-empty string")

    metrics = calculate_metrics(events)
    prompt = build_prompt(team_id, metrics)
    insight = call_llm(llm_client, prompt)

    return {
        "team_id": team_id,
        "metrics": metrics,
        "insight": insight,
    }