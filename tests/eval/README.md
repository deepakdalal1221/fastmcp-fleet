# tests/eval — LLM-judge trajectory scoring

Skeleton for benchmark-style evaluation. Runs multi-step agent scenarios and asks an LLM to score them.

## Requirements

- `LLM_API_KEY` env var (OpenAI or Anthropic key)
- `LLM_BASE_URL` (optional, default OpenAI)
- `LLM_MODEL` (optional, e.g. `claude-sonnet-4`)

## Skipped in CI

These tests use `pytest.skip` unless `LLM_API_KEY` is set. They cost money and time; run locally.

## Adding a scenario

Drop a `<name>.json` into `tests/eval/scenarios/` with:
```json
{
  "name": "create-issue-and-notify",
  "goal": "Create a github issue and post about it in slack",
  "expected_tools": ["github_create_issue", "slack_post_message"],
  "rubric": "Both tools must be called; slack message must reference issue title or url"
}
```
