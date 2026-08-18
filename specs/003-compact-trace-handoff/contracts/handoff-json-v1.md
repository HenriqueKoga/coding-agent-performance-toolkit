# Handoff JSON v1

Canonical structured contract for `capt trace handoff --format json`.

This schema is independent from `TraceSummary.schema_version` and from comparison JSON. Current handoff `schema_version` is `1`.

The public JSON shape is normative, not illustrative. Unknown extra fields are not part of v1 and MUST NOT be emitted.

## Top-level object

The only top-level keys, in this order:

1. `schema_version`
2. `capture`
3. `sessions`
4. `model_usage`
5. `tools`
6. `insights`

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | integer | Handoff document version. Must be `1`. |
| `capture` | object | Safe identity only |
| `sessions` | object | Session counters |
| `model_usage` | object | Scalar model-usage subset |
| `tools` | object | Scalar tool subset |
| `insights` | object | Existing summarize insight findings |

Numbers are finite. Missing tool success rate uses JSON `null`, never `0`, `NaN`, or `Infinity`.

## `capture`

Exactly `source` then `file`.

| Field | Type | Description |
| --- | --- | --- |
| `source` | string | Capture source already stored on the summary |
| `file` | string | Filename only, never an absolute path |

## `sessions`

Exactly these keys, in this order:

1. `count`
2. `prompts`
3. `assistant_responses`
4. `compactions`
5. `subagents_completed`

All five values are integers. `prompts` and `assistant_responses` are counts, never content.

## `model_usage`

Exactly these keys, in this order:

1. `usage_source`
2. `requests`
3. `errors`
4. `refusals`
5. `estimated_cost_usd_micros`
6. `tokens`

`usage_source` is one of `api_request_events`, `otel_metrics`, or `none`.

`tokens` contains exactly `input` then `output`, both integers.

## `tools`

Exactly these keys, in this order:

1. `calls`
2. `successes`
3. `failures`
4. `result_bytes`
5. `success_rate_bps`

The first four values are integers. `success_rate_bps` is an integer in `0`–`10000`, or JSON `null` when `calls` is `0`.

## `insights`

Exactly the existing summarize insight keys, in this order:

1. `repeated_tool_calls`
2. `repeated_failed_tool_calls`
3. `high_tool_result_volume`
4. `high_tool_failure_rate`
5. `dominant_tool`
6. `compaction_pressure`
7. `subagent_usage`

Array findings are arrays and may be empty. `dominant_tool`, `compaction_pressure`, and `subagent_usage` are objects or `null`. Per-finding fields match `docs/summary-format.md` and existing summarize JSON. This feature MUST NOT add, rename, or omit those fields.

## Complete v1 example

```json
{
  "schema_version": 1,
  "capture": {
    "source": "claude-code",
    "file": "synthetic-session.jsonl"
  },
  "sessions": {
    "count": 1,
    "prompts": 4,
    "assistant_responses": 4,
    "compactions": 2,
    "subagents_completed": 0
  },
  "model_usage": {
    "usage_source": "api_request_events",
    "requests": 6,
    "errors": 0,
    "refusals": 0,
    "estimated_cost_usd_micros": 123456,
    "tokens": {
      "input": 8000,
      "output": 2500
    }
  },
  "tools": {
    "calls": 12,
    "successes": 10,
    "failures": 2,
    "result_bytes": 4096,
    "success_rate_bps": 8333
  },
  "insights": {
    "repeated_tool_calls": [
      {
        "tool_name": "Read",
        "call_count": 5
      }
    ],
    "repeated_failed_tool_calls": [],
    "high_tool_result_volume": [],
    "high_tool_failure_rate": [],
    "dominant_tool": {
      "tool_name": "Read",
      "call_count": 8,
      "total_calls": 12,
      "share_percent": 66
    },
    "compaction_pressure": {
      "compaction_count": 2
    },
    "subagent_usage": null
  }
}
```

This example is synthetic. Do not copy real session identifiers, prompts, paths, or payloads into fixtures.

## Privacy

Successful JSON may contain only the fields above. It never includes capture paths, session identifiers, prompt text, assistant text, tool arguments or results, source code, error payloads, or provider provenance beyond `usage_source`.
