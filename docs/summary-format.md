# Trace summary format

Pre-alpha contract for `capt trace summarize --format json`.

This document describes the JSON object written to stdout. It is versioned by
`schema_version` inside the payload. There is no formal JSON Schema in this
release.

The summary is produced deterministically from a local CAPT JSONL capture. It
does not call a model, score quality, or emit recommendations.

## Compatibility

- Current `schema_version`: `1`
- Unknown fields in a future writer may appear; readers should ignore them
- CAPT does not migrate older summary documents automatically

## Privacy

The summary is an allowlist. It never includes session, prompt, message,
request, account, or organization identifiers. It never includes prompt text,
assistant text, tool inputs, tool parameters, commands, paths, headers, or raw
OTLP bodies.

The source capture file remains sensitive. Treat it as confidential even after
a summary has been generated.

## Top-level object

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | integer | Summary document version. Currently `1`. |
| `capture` | object | File-level metadata |
| `sessions` | object | Session and prompt counts |
| `model_usage` | object | Tokens, cost, duration, and model breakdown |
| `tools` | object | Tool call counts, capture-level success rate, and durations |
| `activity` | object | Active time, lines, commits, and edit decisions |
| `coverage` | object | Decode coverage and warnings |
| `insights` | object | Deterministic findings from analysis rules |

Numbers are finite. Missing statistics use `null`, never `NaN` or `Infinity`.
`by_model`, `by_query_source`, and `by_name` are sorted by their name field.

`capture.file` is a filename only, never an absolute path.

## `model_usage.usage_source`

| Value | Meaning |
| --- | --- |
| `api_request_events` | Tokens, cost, duration, and model totals come from `api_request` log events |
| `otel_metrics` | No `api_request` events were present; totals fall back to `claude_code.token.usage` and `claude_code.cost.usage` |
| `none` | No `api_request` events and no token or cost metric series were present |

CAPT never adds event totals and metric totals together.

## Durations

`duration_ms` objects use nearest-rank percentiles:

```text
index = ceil(percentile * count) - 1
```

- No observations: `average`, `p50`, and `p95` are `null`; `total` is `0`
- One observation: that value is used for every statistic
- Totals are integers of milliseconds
- Averages are rounded to two decimal places

## `tools.success_rate_bps`

Capture-level tool success rate in integer basis points (one hundredth of a
percent). It is derived from the existing provider-neutral aggregates
`tools.successes` and `tools.calls`:

```text
floor(successes * 10000 / calls)
```

| Value | Meaning |
| --- | --- |
| integer `0`–`10000` | Successes per 10,000 calls. `10000` is 100%. |
| `null` | No tool calls in the capture. The rate is omitted rather than `0`, `NaN`, or `Infinity`. |

This is descriptive telemetry, not a quality, performance, or health score. It
is not a finding and is not compared to a threshold. Per-tool `success_rate`
values are unchanged.

Text output shows the same integer as `DD.DD%`, or `n/a` when the rate is
`null`.

## Coverage warnings

`coverage.warnings` contains short, payload-free messages. Compatibility
warnings do not fail the command when a reliable summary can still be produced.
Unknown events and metrics are counted by name only.

`coverage.unknown_otlp_values` counts `AnyValue` fields that could not be
decoded. The original values are not included.

## Insights

`insights.repeated_tool_calls` is an array of findings. Each finding identifies a
tool whose call count met or exceeded the deterministic threshold (currently 3)
within the summarized capture.

| Field | Type | Description |
| --- | --- | --- |
| `tool_name` | string | The tool that was called repeatedly |
| `call_count` | integer | The observed number of calls |

Findings are ordered deterministically by tool name. The array is empty when no
tools meet the threshold.

`insights.repeated_failed_tool_calls` is an array of findings. Each finding
identifies a tool whose explicit failure count met or exceeded the deterministic
threshold (currently 3) within the summarized capture. Only normalized
failure/error outcomes are counted. Successful calls do not increment the count.

| Field | Type | Description |
| --- | --- | --- |
| `tool_name` | string | The tool that failed repeatedly |
| `failure_count` | integer | The observed number of explicit failures |

Findings are ordered deterministically by tool name. The array is empty when no
tools meet the threshold.

`insights.high_tool_result_volume` is an array of findings. Each finding
identifies a tool whose cumulative result bytes within the summarized capture
met or exceeded the deterministic threshold (currently 131072, which is 128 KiB).
This measures total result volume per tool, not whether any individual call was
oversized.

| Field | Type | Description |
| --- | --- | --- |
| `tool_name` | string | The tool with high cumulative result volume |
| `result_bytes` | integer | The observed cumulative result bytes for that tool |

Findings are ordered deterministically by tool name. The array is empty when no
tools meet the threshold.

`insights.high_tool_failure_rate` is an array of findings. Each finding
identifies a tool whose explicit failure rate met both deterministic
thresholds within the summarized capture: at least 3 calls, and a failure
rate of at least 1/2. Only normalized failure/error outcomes are counted.
Successful calls do not increment the failed-call count.

| Field | Type | Description |
| --- | --- | --- |
| `tool_name` | string | The tool with a high failure rate |
| `failed_calls` | integer | The observed number of explicit failures |
| `total_calls` | integer | The observed number of calls |
| `failure_rate` | object | Exact reduced ratio of failed calls to total calls |

`failure_rate` uses integers only:

| Field | Type | Description |
| --- | --- | --- |
| `numerator` | integer | Failed calls in lowest terms |
| `denominator` | integer | Total calls in lowest terms |

Threshold comparison uses integer cross-multiplication, not floating-point
division. Findings are ordered deterministically by tool name. The array is
empty when no tools meet both thresholds.

`insights.dominant_tool` is a single finding or `null`. A finding is emitted
when the capture has at least 10 total tool calls and one tool accounts for at
least 60% of those calls. This reports usage concentration only; it does not
judge efficiency or recommend another tool.

Share comparisons use integer arithmetic:
`call_count * 100 >= total_calls * 60`. `share_percent` is
`call_count * 100 // total_calls`. When multiple tools share the qualifying
maximum call count, the lexicographically first tool name is selected.

| Field | Type | Description |
| --- | --- | --- |
| `tool_name` | string | The tool with the dominant share of calls |
| `call_count` | integer | The observed number of calls for that tool |
| `total_calls` | integer | The capture-level tool call total |
| `share_percent` | integer | The integer share of total calls, floored |

The field is `null` when the sample is below 10 calls or the top tool is below
the 60% threshold.

Insight findings contain only allowlisted evidence. Tool arguments, results,
error payloads, prompts, identifiers, and absolute paths are never included.
