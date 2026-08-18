# Data Model: Export compact trace handoff

**Feature**: `003-compact-trace-handoff`

Handoff types are immutable extracts. They do not replace `TraceSummary`.

## TraceHandoff

Finished compact artifact for one capture.

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | `int` | Handoff document version. V1 is `1`. Independent from `TraceSummary.schema_version`. |
| `capture` | `HandoffCapture` | Safe identity only |
| `sessions` | existing `SessionStats` | Five integer counters already on the summary |
| `model_usage` | `HandoffModelUsage` | Scalar subset of summary model usage |
| `tools` | `HandoffTools` | Scalar subset of summary tool stats |
| `insights` | existing `Insights` | Copied unchanged from the summary |

Validation:

- Construction copies values from one `TraceSummary`. It does not recompute aggregates or insight thresholds.
- `capture.source` is allowlisted while copying identity; it is not a new telemetry mapping.
- No path, identifier, payload, activity, coverage, or narrative field is present.
- Field order in the public JSON contract is fixed; see `contracts/handoff-json-v1.md`.

## HandoffCapture

| Field | Type | Notes |
| --- | --- | --- |
| `source` | `str` | Closed allowlist: `claude-code`, else `unknown`. Never a raw arbitrary envelope source. |
| `file` | `str` | Filename only, never an absolute path |

## HandoffModelUsage

| Field | Type | Notes |
| --- | --- | --- |
| `usage_source` | existing `UsageSource` | `api_request_events`, `otel_metrics`, or `none` |
| `requests` | `int` | Observed request count from the summary |
| `errors` | `int` | Observed error count |
| `refusals` | `int` | Observed refusal count |
| `estimated_cost_usd_micros` | `int` | Integer USD micros |
| `tokens` | `HandoffTokens` | `input` and `output` integers only |

`HandoffTokens` excludes cache-read and cache-creation totals.

## HandoffTools

| Field | Type | Notes |
| --- | --- | --- |
| `calls` | `int` | Capture-level tool calls |
| `successes` | `int` | Capture-level successes |
| `failures` | `int` | Capture-level failures |
| `result_bytes` | `int` | Cumulative result bytes |
| `success_rate_bps` | `int \| None` | Existing basis-point rate, or `None` when `calls == 0` |

Do not include `input_bytes`, durations, or `by_name`.

## HandoffInsights

Reuse the existing `Insights` value. Empty arrays stay empty arrays. Singleton findings stay `None` when absent. Do not add a parallel insight type.

## Relationships

```text
TraceSummary
    -> handoff_from_summary()
    -> TraceHandoff
           ├─ HandoffCapture
           ├─ SessionStats (reused)
           ├─ HandoffModelUsage
           │     └─ HandoffTokens
           ├─ HandoffTools
           └─ Insights (reused)
```

No persistence. No state transitions. The object exists only for rendering after summarization.
