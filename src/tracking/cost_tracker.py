"""
Token Usage and Cost Tracker
=============================
Track, aggregate, and alert on LLM token usage and costs per model,
endpoint, and user. Supports budget limits and cost-optimization
recommendations.

Usage:
    tracker = CostTracker()
    tracker.record(model="gpt-4o", prompt_tokens=500, completion_tokens=150,
                   endpoint="/api/summarize", user_id="user-42")
    report = tracker.get_report(period="today")
    print(tracker.format_report(report))
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Pricing Data (per 1 M tokens, as of early 2025) ───────
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
}


# ── Data Models ────────────────────────────────────────────
class UsageRecord(BaseModel):
    """A single LLM API call record."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int = 0
    cost_usd: float = 0.0
    endpoint: str = ""
    user_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens
        if self.cost_usd == 0.0:
            self.cost_usd = self._calculate_cost()

    def _calculate_cost(self) -> float:
        pricing = MODEL_PRICING.get(self.model)
        if not pricing:
            return 0.0
        input_cost = (self.prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.completion_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)


class CostReport(BaseModel):
    """Aggregated cost report over a time period."""

    period_start: datetime
    period_end: datetime
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    total_requests: int = 0
    cost_by_model: dict[str, float] = Field(default_factory=dict)
    tokens_by_model: dict[str, int] = Field(default_factory=dict)
    requests_by_model: dict[str, int] = Field(default_factory=dict)
    cost_by_endpoint: dict[str, float] = Field(default_factory=dict)
    cost_by_user: dict[str, float] = Field(default_factory=dict)
    top_endpoints: list[dict[str, Any]] = Field(default_factory=list)
    budget_remaining_usd: Optional[float] = None
    alerts: list[str] = Field(default_factory=list)


class BudgetConfig(BaseModel):
    """Budget limits and alert thresholds."""

    daily_limit_usd: float = 100.0
    monthly_limit_usd: float = 2000.0
    alert_threshold_pct: float = 0.8  # alert at 80 % of budget
    per_user_daily_limit_usd: float = 10.0


# ── Main Tracker ───────────────────────────────────────────
class CostTracker:
    """
    In-memory cost tracker with aggregation and alerting.

    In production, records would be persisted to PostgreSQL or a
    time-series database. This implementation keeps everything in
    memory for clarity and ease of testing.
    """

    def __init__(self, budget: BudgetConfig | None = None) -> None:
        self.budget = budget or BudgetConfig()
        self._records: list[UsageRecord] = []
        self._alerts: list[str] = []

    # ── Recording ──────────────────────────────────────────
    def record(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        endpoint: str = "",
        user_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> UsageRecord:
        """Record a single LLM API call and check budget alerts."""
        entry = UsageRecord(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            endpoint=endpoint,
            user_id=user_id,
            metadata=metadata or {},
        )
        self._records.append(entry)
        self._check_alerts(entry)
        return entry

    # ── Querying ───────────────────────────────────────────
    def _records_in_range(
        self, start: datetime, end: datetime
    ) -> list[UsageRecord]:
        return [r for r in self._records if start <= r.timestamp <= end]

    def get_report(
        self,
        period: str = "today",
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> CostReport:
        """
        Generate an aggregated cost report.

        Args:
            period: "today", "week", "month", or "all"
            start/end: Override the period with explicit timestamps.
        """
        now = datetime.now(timezone.utc)
        if start and end:
            period_start, period_end = start, end
        elif period == "today":
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period_end = now
        elif period == "week":
            period_start = now - timedelta(days=7)
            period_end = now
        elif period == "month":
            period_start = now - timedelta(days=30)
            period_end = now
        else:  # "all"
            period_start = datetime.min.replace(tzinfo=timezone.utc)
            period_end = now

        records = self._records_in_range(period_start, period_end)

        # Aggregate
        cost_by_model: dict[str, float] = defaultdict(float)
        tokens_by_model: dict[str, int] = defaultdict(int)
        requests_by_model: dict[str, int] = defaultdict(int)
        cost_by_endpoint: dict[str, float] = defaultdict(float)
        cost_by_user: dict[str, float] = defaultdict(float)

        total_cost = 0.0
        total_tokens = 0

        for r in records:
            cost_by_model[r.model] += r.cost_usd
            tokens_by_model[r.model] += r.total_tokens
            requests_by_model[r.model] += 1
            if r.endpoint:
                cost_by_endpoint[r.endpoint] += r.cost_usd
            if r.user_id:
                cost_by_user[r.user_id] += r.cost_usd
            total_cost += r.cost_usd
            total_tokens += r.total_tokens

        # Top endpoints by cost
        top_endpoints = sorted(
            [{"endpoint": k, "cost_usd": round(v, 4)} for k, v in cost_by_endpoint.items()],
            key=lambda x: x["cost_usd"],
            reverse=True,
        )[:10]

        # Budget remaining
        budget_remaining = None
        if period in ("today", "all"):
            budget_remaining = round(self.budget.daily_limit_usd - total_cost, 4)

        return CostReport(
            period_start=period_start,
            period_end=period_end,
            total_cost_usd=round(total_cost, 4),
            total_tokens=total_tokens,
            total_requests=len(records),
            cost_by_model=dict(cost_by_model),
            tokens_by_model=dict(tokens_by_model),
            requests_by_model=dict(requests_by_model),
            cost_by_endpoint=dict(cost_by_endpoint),
            cost_by_user=dict(cost_by_user),
            top_endpoints=top_endpoints,
            budget_remaining_usd=budget_remaining,
            alerts=list(self._alerts),
        )

    # ── Alerts ─────────────────────────────────────────────
    def _check_alerts(self, record: UsageRecord) -> None:
        """Check budget limits after each record."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_records = self._records_in_range(today_start, now)
        daily_spend = sum(r.cost_usd for r in today_records)

        threshold_amount = self.budget.daily_limit_usd * self.budget.alert_threshold_pct
        if daily_spend >= self.budget.daily_limit_usd:
            msg = f"CRITICAL: Daily budget exceeded (${daily_spend:.2f} / ${self.budget.daily_limit_usd:.2f})"
            if msg not in self._alerts:
                self._alerts.append(msg)
        elif daily_spend >= threshold_amount:
            msg = f"WARNING: Approaching daily budget (${daily_spend:.2f} / ${self.budget.daily_limit_usd:.2f})"
            if msg not in self._alerts:
                self._alerts.append(msg)

        # Per-user check
        if record.user_id:
            user_records = [r for r in today_records if r.user_id == record.user_id]
            user_spend = sum(r.cost_usd for r in user_records)
            if user_spend >= self.budget.per_user_daily_limit_usd:
                msg = f"ALERT: User '{record.user_id}' exceeded daily limit (${user_spend:.2f})"
                if msg not in self._alerts:
                    self._alerts.append(msg)

    def get_optimization_tips(self) -> list[str]:
        """Analyze usage patterns and suggest cost optimizations."""
        tips: list[str] = []
        if not self._records:
            return ["No usage data yet. Start recording to get optimization tips."]

        # Check for expensive model overuse
        model_counts: dict[str, int] = defaultdict(int)
        for r in self._records:
            model_counts[r.model] += 1

        total = sum(model_counts.values())
        for model, count in model_counts.items():
            pct = count / total
            pricing = MODEL_PRICING.get(model, {})
            input_price = pricing.get("input", 0)
            if input_price >= 10.0 and pct > 0.5:
                tips.append(
                    f"Consider using a cheaper model for some requests. "
                    f"{model} ({pct:.0%} of traffic) costs ${input_price}/1M input tokens. "
                    f"Try gpt-4o-mini for simpler tasks."
                )

        # Check for high completion-to-prompt ratio (over-generation)
        total_prompt = sum(r.prompt_tokens for r in self._records)
        total_completion = sum(r.completion_tokens for r in self._records)
        if total_prompt > 0 and total_completion / total_prompt > 3:
            tips.append(
                "Completion tokens are 3x+ prompt tokens. Consider setting lower "
                "max_tokens or using more concise system prompts."
            )

        # Caching opportunity
        endpoints = defaultdict(int)
        for r in self._records:
            if r.endpoint:
                endpoints[r.endpoint] += 1
        for ep, count in endpoints.items():
            if count > 100:
                tips.append(
                    f"Endpoint '{ep}' has {count} calls. Consider implementing "
                    f"response caching with Redis to reduce redundant API calls."
                )

        if not tips:
            tips.append("Usage patterns look efficient. No optimizations suggested.")

        return tips

    # ── Formatting ─────────────────────────────────────────
    @staticmethod
    def format_report(report: CostReport) -> str:
        """Pretty-print a cost report."""
        lines = [
            f"{'=' * 55}",
            f"  Cost Report",
            f"  {report.period_start:%Y-%m-%d %H:%M} to {report.period_end:%Y-%m-%d %H:%M}",
            f"{'=' * 55}",
            f"  Total Cost     : ${report.total_cost_usd:.4f}",
            f"  Total Tokens   : {report.total_tokens:,}",
            f"  Total Requests : {report.total_requests:,}",
            "",
            "  Cost by Model:",
        ]
        for model, cost in sorted(report.cost_by_model.items(), key=lambda x: -x[1]):
            reqs = report.requests_by_model.get(model, 0)
            lines.append(f"    {model:<20} ${cost:.4f}  ({reqs} requests)")

        if report.top_endpoints:
            lines.append("")
            lines.append("  Top Endpoints:")
            for ep in report.top_endpoints[:5]:
                lines.append(f"    {ep['endpoint']:<30} ${ep['cost_usd']:.4f}")

        if report.budget_remaining_usd is not None:
            lines.append("")
            lines.append(f"  Budget Remaining: ${report.budget_remaining_usd:.4f}")

        if report.alerts:
            lines.append("")
            lines.append("  Alerts:")
            for alert in report.alerts:
                lines.append(f"    - {alert}")

        lines.append(f"{'=' * 55}")
        return "\n".join(lines)
