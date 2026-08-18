# Trace summary format

Pre-alpha contract for `capt trace summarize --format json`.

This document describes the JSON object written to stdout. It is versioned by
`schema_version` inside the payload. There is no formal JSON Schema in this
release.

The same file also documents `capt trace compare --format json` and
`capt trace handoff --format json`. Those contracts have their own
`schema_version` values and do not change the summary schema.

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

`insights.compaction_pressure` is a single finding or `null`. A finding is
emitted when the capture has at least one session and the capture-level
`sessions.compactions` count meets or exceeds the deterministic threshold
(currently 2). This reports observed compaction pressure only. It does not
infer root cause, quality degradation, or a next action.

| Field | Type | Description |
| --- | --- | --- |
| `compaction_count` | integer | The observed session compaction count |

The field is `null` when there are no sessions or the count is below the
threshold, including zero compactions. Compaction events without a session
identity still produce no finding.

`insights.subagent_usage` is a single finding or `null`. A finding is emitted
when the capture-level `sessions.subagents_completed` count meets or exceeds
the deterministic threshold (currently 2). This reports observed subagent
usage only. It does not classify the activity as helpful or wasteful, and it
does not recommend a next action.

| Field | Type | Description |
| --- | --- | --- |
| `completed_count` | integer | The observed completed-subagent count |

The field is `null` when the count is below the threshold, including zero
completed subagents.

Insight findings contain only allowlisted evidence. Tool arguments, results,
error payloads, prompts, identifiers, and absolute paths are never included.

## Comparison format

Pre-alpha contract for `capt trace compare --format json`.

The comparison schema version is independent from `TraceSummary.schema_version`.
Current comparison `schema_version` is `1`.

`capt trace compare BASELINE CANDIDATE` summarizes each distinct capture through
the existing bounded path. If both arguments resolve to the same filesystem
object, CAPT summarizes that object once and reuses the immutable snapshot.

Comparison is local and deterministic. It does not score quality, name a winner,
emit percentages, or recommend a next action.

### Privacy

Successful comparison output may contain only fixed metric names, availability
state, and allowlisted integer aggregates. It never includes capture paths,
session identifiers, prompts, responses, tool content, or provider provenance.

### Top-level object

The only top-level keys are `schema_version` and `metrics`, in that order.

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | integer | Comparison document version. Currently `1`. |
| `metrics` | object | Exactly eight comparison slots in fixed order |

### Metric slots

`metrics` contains exactly these keys, in this order:

1. `tool_calls`
2. `tool_failures`
3. `tool_result_bytes`
4. `model_requests`
5. `estimated_cost_usd_micros`
6. `input_tokens`
7. `output_tokens`
8. `session_compactions`

Every slot contains exactly `available`, `baseline`, `candidate`, and `delta`,
in that order.

| Field | Type | Description |
| --- | --- | --- |
| `available` | boolean | True only when both captures have observed evidence for the metric |
| `baseline` | integer or `null` | Baseline value when available |
| `candidate` | integer or `null` | Candidate value when available |
| `delta` | integer or `null` | `candidate - baseline` when available |

When `available` is `true`, the three numeric fields are integers. When
`available` is `false`, all three numeric fields are JSON `null`. CAPT never
substitutes zero for missing telemetry and never reports a percentage delta.

### Availability

Availability is tracked per metric from normalized coverage, not from
`value != 0`.

- `tool_calls` is available only when tool-event telemetry was observed.
- `tool_failures` additionally requires a valid success status on every counted
  tool event. A missing or invalid `success` attribute leaves failures
  unavailable even though existing summaries still treat that event as
  successful.
- `tool_result_bytes` requires result-size evidence for every counted tool call.
- `model_requests` is available only when at least one normalized API-request
  event exists. There is no observed-zero request count in v1.
- `estimated_cost_usd_micros`, `input_tokens`, and `output_tokens` are
  independently available only when their own API-request fields or fallback
  metric series were observed completely.
- `session_compactions` is available when log coverage exists that could have
  included compaction events. Metrics-only captures leave it unavailable.

An observed numeric zero is comparable only when that metric has affirmative
coverage proving zero. Text output uses the same eight slot names and the same
availability and integer values as JSON.

## Handoff format

Pre-alpha contract for `capt trace handoff --format json`.

The handoff schema version is independent from `TraceSummary.schema_version`
and from comparison JSON. Current handoff `schema_version` is `1`.

`capt trace handoff` summarizes one explicit local capture or `--latest`
through the existing bounded path, then copies a compact allowlist into a
`TraceHandoff`. `--latest` selects the same newest eligible capture as
`capt trace summarize --latest`. JSON is the canonical structured
representation. Text is the default CLI format and reports the same
identity, aggregate values, and insight presence or absence. Stdout is
the default. An explicit `--output` path persists the same representation
to a local file.

The handoff is an evidence extract. It does not invent goals, TODOs,
recommendations, or a next action. Insights are copied from the existing
summary findings.

### Privacy

Successful handoff output may contain only filename, allowlisted capture
`source` (`claude-code` or `unknown`), integer session/tool/model aggregates,
`usage_source`, nullable tool success-rate basis points, and existing insight
evidence fields. It never includes capture paths, session identifiers, prompt
or assistant text, tool arguments or results, source code, arbitrary envelope
`source` strings, or interpolated envelope field values.

### Top-level object

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
| `capture` | object | Safe identity only: `source` then `file` |
| `sessions` | object | Five integer session counters |
| `model_usage` | object | Scalar model-usage subset |
| `tools` | object | Scalar tool subset |
| `insights` | object | Existing summarize insight findings |

`capture.source` is `claude-code` or `unknown`. Any other summary source is
emitted as `unknown`. `capture.file` is a filename only.

`sessions` contains exactly `count`, `prompts`, `assistant_responses`,
`compactions`, and `subagents_completed`. `prompts` and `assistant_responses`
are counts, never content.

`model_usage` contains exactly `usage_source`, `requests`, `errors`,
`refusals`, `estimated_cost_usd_micros`, and `tokens`. `tokens` contains
exactly `input` then `output`. Cache-token totals, durations, and breakdowns
are omitted.

`tools` contains exactly `calls`, `successes`, `failures`, `result_bytes`,
and `success_rate_bps`. `success_rate_bps` is an integer in `0`–`10000`, or
JSON `null` when `calls` is `0`.

`insights` uses the same keys and per-finding fields as summarize JSON.
Array findings may be empty. `dominant_tool`, `compaction_pressure`, and
`subagent_usage` are objects or `null`.

Text uses the existing summarize labels for `usage_source` and the existing
insight line wording. Missing tool success rate is shown as `n/a`.
