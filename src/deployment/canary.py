"""
Canary Deployment Manager for LLM Model Versions
=================================================
Gradually roll out new LLM model versions or prompt updates with
configurable traffic splitting, health monitoring, and automatic rollback.

Usage:
    manager = CanaryManager(redis_url="redis://localhost:6379")
    deployment = manager.create_deployment(
        name="summarizer-v2",
        baseline_model="gpt-4o-mini",
        canary_model="gpt-4o",
        canary_weight=0.1,
    )
    model = manager.route_request("summarizer-v2")  # returns model based on weight
    manager.record_outcome("summarizer-v2", model, success=True, latency_ms=230)
    manager.maybe_promote_or_rollback("summarizer-v2")
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────
class DeploymentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    PAUSED = "paused"


class RollbackReason(str, Enum):
    ERROR_RATE = "error_rate_exceeded"
    LATENCY = "latency_exceeded"
    QUALITY_SCORE = "quality_score_below_threshold"
    MANUAL = "manual_rollback"


# ── Data Models ────────────────────────────────────────────
class CanaryConfig(BaseModel):
    """Configuration for a canary deployment."""

    max_error_rate: float = 0.05          # 5 % errors triggers rollback
    max_latency_p99_ms: float = 5000.0    # 5 s latency ceiling
    min_quality_score: float = 0.7        # minimum eval score
    min_requests_before_decision: int = 50
    promotion_threshold: float = 0.9      # canary weight at which we auto-promote
    weight_increment: float = 0.1         # step size for gradual ramp
    ramp_interval_seconds: float = 300.0  # time between ramp steps


class CanaryMetrics(BaseModel):
    """Live metrics for one side of the deployment (baseline or canary)."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0
    latencies: list[float] = Field(default_factory=list)
    quality_scores: list[float] = Field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.failed_requests / self.total_requests if self.total_requests else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.total_requests if self.total_requests else 0.0

    @property
    def p99_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * 0.99)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    @property
    def avg_quality(self) -> float:
        return sum(self.quality_scores) / len(self.quality_scores) if self.quality_scores else 1.0


class CanaryDeployment(BaseModel):
    """Full state for a canary deployment."""

    name: str
    baseline_model: str
    canary_model: str
    canary_weight: float = 0.1
    status: DeploymentStatus = DeploymentStatus.PENDING
    config: CanaryConfig = Field(default_factory=CanaryConfig)
    baseline_metrics: CanaryMetrics = Field(default_factory=CanaryMetrics)
    canary_metrics: CanaryMetrics = Field(default_factory=CanaryMetrics)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_ramp_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rollback_reason: Optional[RollbackReason] = None
    history: list[dict[str, Any]] = Field(default_factory=list)


# ── Canary Manager ─────────────────────────────────────────
class CanaryManager:
    """
    Manages canary deployments with in-memory state.

    Production implementations would persist state to Redis or a database.
    This version keeps everything in memory for clarity and testability.

    Lifecycle:
        create  ->  route requests  ->  record outcomes  ->  ramp / rollback
    """

    def __init__(self) -> None:
        self._deployments: dict[str, CanaryDeployment] = {}

    # ── Deployment lifecycle ───────────────────────────────
    def create_deployment(
        self,
        name: str,
        baseline_model: str,
        canary_model: str,
        canary_weight: float = 0.1,
        config: CanaryConfig | None = None,
    ) -> CanaryDeployment:
        """Create a new canary deployment."""
        deployment = CanaryDeployment(
            name=name,
            baseline_model=baseline_model,
            canary_model=canary_model,
            canary_weight=canary_weight,
            config=config or CanaryConfig(),
            status=DeploymentStatus.IN_PROGRESS,
        )
        deployment.history.append({
            "event": "created",
            "canary_weight": canary_weight,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._deployments[name] = deployment
        return deployment

    def get_deployment(self, name: str) -> Optional[CanaryDeployment]:
        return self._deployments.get(name)

    def list_deployments(self) -> list[CanaryDeployment]:
        return list(self._deployments.values())

    # ── Traffic routing ────────────────────────────────────
    def route_request(self, name: str, *, sticky_key: str | None = None) -> str:
        """
        Decide which model should serve this request.

        Args:
            name: Deployment name.
            sticky_key: Optional user/session ID for consistent routing.
                        Ensures the same user always hits the same variant.

        Returns:
            The model identifier (baseline or canary).
        """
        deployment = self._deployments.get(name)
        if not deployment or deployment.status != DeploymentStatus.IN_PROGRESS:
            # Fall back to baseline if deployment is missing or inactive
            return deployment.baseline_model if deployment else ""

        if sticky_key:
            # Deterministic routing based on hash
            hash_val = int(hashlib.md5(sticky_key.encode()).hexdigest(), 16)
            use_canary = (hash_val % 100) < (deployment.canary_weight * 100)
        else:
            use_canary = random.random() < deployment.canary_weight

        return deployment.canary_model if use_canary else deployment.baseline_model

    # ── Outcome recording ──────────────────────────────────
    def record_outcome(
        self,
        name: str,
        model_used: str,
        *,
        success: bool = True,
        latency_ms: float = 0.0,
        quality_score: float | None = None,
    ) -> None:
        """Record the result of a request for metrics tracking."""
        deployment = self._deployments.get(name)
        if not deployment:
            return

        is_canary = model_used == deployment.canary_model
        metrics = deployment.canary_metrics if is_canary else deployment.baseline_metrics

        metrics.total_requests += 1
        metrics.total_latency_ms += latency_ms
        metrics.latencies.append(latency_ms)
        if success:
            metrics.successful_requests += 1
        else:
            metrics.failed_requests += 1
        if quality_score is not None:
            metrics.quality_scores.append(quality_score)

    # ── Health checks and auto-decisions ───────────────────
    def check_health(self, name: str) -> dict[str, Any]:
        """Return current health status of a canary deployment."""
        deployment = self._deployments.get(name)
        if not deployment:
            return {"error": "deployment not found"}

        cfg = deployment.config
        cm = deployment.canary_metrics

        issues = []
        if cm.total_requests >= cfg.min_requests_before_decision:
            if cm.error_rate > cfg.max_error_rate:
                issues.append(f"error_rate={cm.error_rate:.2%} > {cfg.max_error_rate:.2%}")
            if cm.p99_latency_ms > cfg.max_latency_p99_ms:
                issues.append(f"p99_latency={cm.p99_latency_ms:.0f}ms > {cfg.max_latency_p99_ms:.0f}ms")
            if cm.avg_quality < cfg.min_quality_score:
                issues.append(f"quality={cm.avg_quality:.2f} < {cfg.min_quality_score:.2f}")

        return {
            "name": name,
            "status": deployment.status.value,
            "canary_weight": deployment.canary_weight,
            "canary_requests": cm.total_requests,
            "canary_error_rate": round(cm.error_rate, 4),
            "canary_p99_latency_ms": round(cm.p99_latency_ms, 2),
            "canary_avg_quality": round(cm.avg_quality, 4),
            "healthy": len(issues) == 0,
            "issues": issues,
        }

    def maybe_promote_or_rollback(self, name: str) -> str:
        """
        Evaluate canary health and either ramp up, promote, or roll back.

        Returns a string describing the action taken.
        """
        deployment = self._deployments.get(name)
        if not deployment or deployment.status != DeploymentStatus.IN_PROGRESS:
            return "no_action"

        cfg = deployment.config
        cm = deployment.canary_metrics

        # Need minimum sample size before making decisions
        if cm.total_requests < cfg.min_requests_before_decision:
            return f"waiting (have {cm.total_requests}/{cfg.min_requests_before_decision} requests)"

        # Check for rollback conditions
        if cm.error_rate > cfg.max_error_rate:
            return self._rollback(deployment, RollbackReason.ERROR_RATE)
        if cm.p99_latency_ms > cfg.max_latency_p99_ms:
            return self._rollback(deployment, RollbackReason.LATENCY)
        if cm.avg_quality < cfg.min_quality_score:
            return self._rollback(deployment, RollbackReason.QUALITY_SCORE)

        # Canary is healthy: should we promote or ramp?
        if deployment.canary_weight >= cfg.promotion_threshold:
            return self._promote(deployment)

        # Ramp up traffic if enough time has passed
        now = datetime.now(timezone.utc)
        elapsed = (now - deployment.last_ramp_at).total_seconds()
        if elapsed >= cfg.ramp_interval_seconds:
            return self._ramp_up(deployment)

        return "healthy, waiting for next ramp interval"

    # ── Internal actions ───────────────────────────────────
    def _rollback(self, deployment: CanaryDeployment, reason: RollbackReason) -> str:
        deployment.status = DeploymentStatus.ROLLED_BACK
        deployment.rollback_reason = reason
        deployment.canary_weight = 0.0
        deployment.history.append({
            "event": "rolled_back",
            "reason": reason.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return f"ROLLED BACK: {reason.value}"

    def _promote(self, deployment: CanaryDeployment) -> str:
        deployment.status = DeploymentStatus.PROMOTED
        deployment.canary_weight = 1.0
        deployment.history.append({
            "event": "promoted",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return f"PROMOTED: {deployment.canary_model} is now primary"

    def _ramp_up(self, deployment: CanaryDeployment) -> str:
        old_weight = deployment.canary_weight
        new_weight = min(1.0, old_weight + deployment.config.weight_increment)
        deployment.canary_weight = round(new_weight, 2)
        deployment.last_ramp_at = datetime.now(timezone.utc)
        deployment.history.append({
            "event": "ramp_up",
            "from_weight": old_weight,
            "to_weight": deployment.canary_weight,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return f"RAMPED UP: {old_weight:.0%} -> {deployment.canary_weight:.0%}"

    def manual_rollback(self, name: str) -> str:
        """Operator-initiated rollback."""
        deployment = self._deployments.get(name)
        if not deployment:
            return "deployment not found"
        return self._rollback(deployment, RollbackReason.MANUAL)

    def get_summary(self, name: str) -> str:
        """Pretty-print deployment status."""
        deployment = self._deployments.get(name)
        if not deployment:
            return "Deployment not found"

        bm = deployment.baseline_metrics
        cm = deployment.canary_metrics
        lines = [
            f"{'=' * 55}",
            f"  Canary Deployment: {deployment.name}",
            f"{'=' * 55}",
            f"  Status        : {deployment.status.value}",
            f"  Baseline Model: {deployment.baseline_model}",
            f"  Canary Model  : {deployment.canary_model}",
            f"  Traffic Split : {1 - deployment.canary_weight:.0%} baseline / {deployment.canary_weight:.0%} canary",
            "",
            f"  Baseline  -  requests: {bm.total_requests}, "
            f"error_rate: {bm.error_rate:.2%}, avg_latency: {bm.avg_latency_ms:.0f}ms",
            f"  Canary    -  requests: {cm.total_requests}, "
            f"error_rate: {cm.error_rate:.2%}, avg_latency: {cm.avg_latency_ms:.0f}ms",
        ]
        if deployment.rollback_reason:
            lines.append(f"  Rollback Reason: {deployment.rollback_reason.value}")
        lines.append(f"{'=' * 55}")
        return "\n".join(lines)
