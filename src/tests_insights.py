from .insights import generate_team_insight


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def complete(self, prompt: str, timeout_seconds: float) -> str:
        self.calls += 1
        assert "pr-1" not in prompt
        return self.response


client = FakeLLMClient(
    '{"summary": "Healthy delivery flow.", '
    '"recommendations": ["Monitor cycle time."]}'
)

result = generate_team_insight(
    "platform",
    [
        {
            "type": "pr_opened",
            "id": "pr-1",
            "timestamp": "2026-01-01T09:00:00Z",
        },
        {
            "type": "pr_merged",
            "id": "pr-1",
            "timestamp": "2026-01-02T09:00:00Z",
        },
        {
            "type": "pr_merged",
            "id": "pr-2",
            "timestamp": "2026-01-02T09:00:00Z",
        },
        {
            "type": "deployment",
            "timestamp": "2026-01-03T12:00:00Z",
        },
        {
            "type": "incident",
            "timestamp": "2026-01-04T12:00:00Z",
        },
        {
            "type": "deployment",
            "timestamp": "2026-01-04T12:00:00Z",
        },
        {
            "type": "incident",
            "timestamp": "2026-01-05T12:00:00Z",
        },
        {
            "type": "pr_opened",
            "id": "pr-3",
            "timestamp": "2026-01-06T09:00:00Z",
        },
        {
            "type": "pr_merged",
            "id": "pr-3",
            "timestamp": "2026-01-08T09:00:00Z",
        },
    ],
    client,
)

assert result["metrics"]["merged_prs"] == 3
assert result["metrics"]["average_pr_cycle_time_hours"] == 36.0
assert result["metrics"]["deployments"] == 2
assert result["metrics"]["incidents"] == 2
assert result["insight"]["summary"] == "Healthy delivery flow."