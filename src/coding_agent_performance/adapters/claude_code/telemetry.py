"""Claude Code OpenTelemetry export settings.

This adapter only knows how to configure Claude Code's official OTLP export.
It does not start Claude Code or change local settings.
"""

from dataclasses import dataclass
from typing import Final

SOURCE: Final = "claude-code"
LOGS_EXPORT_INTERVAL_MS: Final = 1000
METRICS_EXPORT_INTERVAL_MS: Final = 5000


@dataclass(frozen=True, slots=True)
class ClaudeCodeExportConfig:
    logs_endpoint: str
    metrics_endpoint: str

    def environment(self) -> dict[str, str]:
        return {
            "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
            "OTEL_LOGS_EXPORTER": "otlp",
            "OTEL_METRICS_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_LOGS_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_METRICS_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": self.logs_endpoint,
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": self.metrics_endpoint,
            "OTEL_LOGS_EXPORT_INTERVAL": str(LOGS_EXPORT_INTERVAL_MS),
            "OTEL_METRIC_EXPORT_INTERVAL": str(METRICS_EXPORT_INTERVAL_MS),
            "OTEL_LOG_USER_PROMPTS": "0",
            "OTEL_LOG_ASSISTANT_RESPONSES": "0",
            "OTEL_LOG_TOOL_DETAILS": "0",
            "OTEL_LOG_TOOL_CONTENT": "0",
        }

    def shell_snippet(self) -> str:
        lines = [f"export {name}={value}" for name, value in self.environment().items()]
        lines.append("claude")
        return "\n".join(lines)
