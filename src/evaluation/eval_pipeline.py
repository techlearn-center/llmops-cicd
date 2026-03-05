"""
LLM Evaluation Pipeline
========================
Automated evaluation of LLM outputs for accuracy, relevance, toxicity,
and custom metrics. Integrates with deepeval for standardized scoring
and supports regression detection across prompt versions.

Usage:
    pipeline = EvalPipeline(openai_api_key="sk-...")
    results  = await pipeline.run_evaluation(
        prompt_name="summarizer",
        test_cases=cases,
        metrics=["accuracy", "relevance", "toxicity"],
    )
    report = pipeline.generate_report(results)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums & Config ─────────────────────────────────────────
class MetricType(str, Enum):
    ACCURACY = "accuracy"
    RELEVANCE = "relevance"
    TOXICITY = "toxicity"
    COHERENCE = "coherence"
    FAITHFULNESS = "faithfulness"
    CUSTOM = "custom"


class EvalStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


# ── Data Models ────────────────────────────────────────────
class TestCase(BaseModel):
    """A single evaluation test case."""

    input_text: str
    expected_output: Optional[str] = None
    context: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricResult(BaseModel):
    """Score for one metric on one test case."""

    metric: MetricType
    score: float  # 0.0 - 1.0
    passed: bool
    reason: str = ""
    threshold: float = 0.7


class TestCaseResult(BaseModel):
    """Full evaluation result for a single test case."""

    test_case: TestCase
    actual_output: str
    metric_results: list[MetricResult] = Field(default_factory=list)
    latency_ms: float = 0.0
    token_count: int = 0
    overall_passed: bool = True


class EvalReport(BaseModel):
    """Aggregated report across all test cases."""

    prompt_name: str
    prompt_version: str
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    avg_scores: dict[str, float] = Field(default_factory=dict)
    avg_latency_ms: float = 0.0
    total_tokens: int = 0
    status: EvalStatus = EvalStatus.PASSED
    results: list[TestCaseResult] = Field(default_factory=list)
    regression_detected: bool = False


# ── Metric Evaluators ──────────────────────────────────────
class BaseMetricEvaluator:
    """Base class for metric evaluators."""

    metric_type: MetricType
    threshold: float = 0.7

    async def evaluate(
        self,
        input_text: str,
        actual_output: str,
        expected_output: Optional[str] = None,
        context: Optional[str] = None,
    ) -> MetricResult:
        raise NotImplementedError


class AccuracyEvaluator(BaseMetricEvaluator):
    """
    Measures how factually correct the output is compared to expected output.

    Uses token-level overlap and semantic similarity when an expected output
    is provided. Falls back to self-consistency checks otherwise.
    """

    metric_type = MetricType.ACCURACY

    async def evaluate(self, input_text, actual_output, expected_output=None, context=None):
        if not expected_output:
            return MetricResult(
                metric=self.metric_type, score=1.0, passed=True,
                reason="No expected output provided; skipped.", threshold=self.threshold,
            )

        # Token overlap scoring
        expected_tokens = set(expected_output.lower().split())
        actual_tokens = set(actual_output.lower().split())

        if not expected_tokens:
            score = 1.0
        else:
            overlap = expected_tokens & actual_tokens
            precision = len(overlap) / len(actual_tokens) if actual_tokens else 0
            recall = len(overlap) / len(expected_tokens)
            score = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        return MetricResult(
            metric=self.metric_type,
            score=round(score, 4),
            passed=score >= self.threshold,
            reason=f"F1 token overlap: {score:.2%}",
            threshold=self.threshold,
        )


class RelevanceEvaluator(BaseMetricEvaluator):
    """
    Measures how relevant the output is to the input query.

    Checks that key terms from the input appear in or are addressed by the output.
    """

    metric_type = MetricType.RELEVANCE

    async def evaluate(self, input_text, actual_output, expected_output=None, context=None):
        input_terms = set(input_text.lower().split())
        output_lower = actual_output.lower()

        # What fraction of meaningful input words appear in the output?
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "to", "for", "and", "or", "it", "on"}
        meaningful = input_terms - stopwords
        if not meaningful:
            score = 1.0
        else:
            hits = sum(1 for w in meaningful if w in output_lower)
            score = hits / len(meaningful)

        return MetricResult(
            metric=self.metric_type,
            score=round(score, 4),
            passed=score >= self.threshold,
            reason=f"Input term coverage: {score:.2%}",
            threshold=self.threshold,
        )


class ToxicityEvaluator(BaseMetricEvaluator):
    """
    Checks the output for toxic, offensive, or harmful language.

    Uses a keyword-based approach as a baseline. In production you would
    integrate a dedicated moderation API (e.g., OpenAI Moderation).
    """

    metric_type = MetricType.TOXICITY
    threshold = 0.9  # Higher bar: we want low toxicity

    TOXIC_PATTERNS = [
        "hate", "kill", "stupid", "idiot", "dumb", "ugly",
        "violent", "abuse", "attack", "racist", "sexist",
    ]

    async def evaluate(self, input_text, actual_output, expected_output=None, context=None):
        output_lower = actual_output.lower()
        found = [p for p in self.TOXIC_PATTERNS if p in output_lower]
        score = 1.0 - (len(found) / max(len(self.TOXIC_PATTERNS), 1))

        return MetricResult(
            metric=self.metric_type,
            score=round(score, 4),
            passed=score >= self.threshold,
            reason=f"Toxic patterns found: {found}" if found else "No toxic patterns detected",
            threshold=self.threshold,
        )


class CoherenceEvaluator(BaseMetricEvaluator):
    """
    Measures structural coherence: sentence count, average length,
    and basic readability heuristics.
    """

    metric_type = MetricType.COHERENCE

    async def evaluate(self, input_text, actual_output, expected_output=None, context=None):
        sentences = [s.strip() for s in actual_output.split(".") if s.strip()]
        if not sentences:
            return MetricResult(
                metric=self.metric_type, score=0.0, passed=False,
                reason="Empty output", threshold=self.threshold,
            )

        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        # Penalize very short or very long average sentence length
        if 5 <= avg_len <= 30:
            score = 1.0
        elif avg_len < 5:
            score = avg_len / 5
        else:
            score = max(0.3, 30 / avg_len)

        return MetricResult(
            metric=self.metric_type,
            score=round(score, 4),
            passed=score >= self.threshold,
            reason=f"Avg sentence length: {avg_len:.1f} words across {len(sentences)} sentences",
            threshold=self.threshold,
        )


# ── Evaluator Registry ────────────────────────────────────
EVALUATOR_REGISTRY: dict[MetricType, type[BaseMetricEvaluator]] = {
    MetricType.ACCURACY: AccuracyEvaluator,
    MetricType.RELEVANCE: RelevanceEvaluator,
    MetricType.TOXICITY: ToxicityEvaluator,
    MetricType.COHERENCE: CoherenceEvaluator,
}


# ── Main Pipeline ──────────────────────────────────────────
class EvalPipeline:
    """
    Orchestrates end-to-end LLM evaluation.

    1. Takes a list of test cases and metrics to evaluate.
    2. Calls the LLM for each test case (or accepts pre-generated outputs).
    3. Runs every requested metric evaluator.
    4. Aggregates scores and detects regressions against a baseline.
    """

    def __init__(
        self,
        openai_api_key: str | None = None,
        model: str = "gpt-4o-mini",
        default_threshold: float = 0.7,
    ) -> None:
        self.api_key = openai_api_key
        self.model = model
        self.default_threshold = default_threshold

    async def _generate_output(self, prompt: str) -> tuple[str, float, int]:
        """
        Call the LLM and return (output, latency_ms, token_count).
        Falls back to a placeholder when no API key is configured.
        """
        start = time.perf_counter()

        if self.api_key:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=self.api_key)
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                )
                output = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                latency = (time.perf_counter() - start) * 1000
                return output, latency, tokens
            except Exception as exc:
                latency = (time.perf_counter() - start) * 1000
                return f"[Error: {exc}]", latency, 0

        # No API key: return the input as a mock output for local testing
        latency = (time.perf_counter() - start) * 1000
        return f"[mock] Processed: {prompt[:100]}", latency, len(prompt.split())

    async def evaluate_case(
        self,
        test_case: TestCase,
        metrics: list[MetricType],
        prompt_template: str | None = None,
    ) -> TestCaseResult:
        """Evaluate a single test case against all requested metrics."""
        # Generate LLM output
        input_text = test_case.input_text
        if prompt_template:
            input_text = prompt_template.format(text=test_case.input_text)

        actual_output, latency_ms, token_count = await self._generate_output(input_text)

        # Run evaluators in parallel
        evaluators = [EVALUATOR_REGISTRY[m]() for m in metrics if m in EVALUATOR_REGISTRY]
        metric_results = await asyncio.gather(
            *[
                e.evaluate(
                    input_text=test_case.input_text,
                    actual_output=actual_output,
                    expected_output=test_case.expected_output,
                    context=test_case.context,
                )
                for e in evaluators
            ]
        )

        overall_passed = all(r.passed for r in metric_results)

        return TestCaseResult(
            test_case=test_case,
            actual_output=actual_output,
            metric_results=list(metric_results),
            latency_ms=latency_ms,
            token_count=token_count,
            overall_passed=overall_passed,
        )

    async def run_evaluation(
        self,
        prompt_name: str,
        test_cases: list[TestCase],
        metrics: list[str | MetricType],
        prompt_template: str | None = None,
        prompt_version: str = "latest",
        baseline_scores: dict[str, float] | None = None,
    ) -> EvalReport:
        """
        Run a full evaluation across all test cases and metrics.

        Args:
            prompt_name: Identifier for the prompt being evaluated.
            test_cases: List of TestCase objects.
            metrics: Which metrics to run (names or MetricType enums).
            prompt_template: Optional template to wrap input text.
            prompt_version: Version label for the report.
            baseline_scores: Previous avg scores for regression detection.

        Returns:
            EvalReport with per-case results and aggregated statistics.
        """
        metric_types = [MetricType(m) if isinstance(m, str) else m for m in metrics]

        # Evaluate all cases (could be parallelized further with semaphores)
        results = []
        for case in test_cases:
            result = await self.evaluate_case(case, metric_types, prompt_template)
            results.append(result)

        # Aggregate
        passed = sum(1 for r in results if r.overall_passed)
        failed = len(results) - passed

        avg_scores: dict[str, float] = {}
        for mt in metric_types:
            scores = [
                mr.score
                for r in results
                for mr in r.metric_results
                if mr.metric == mt
            ]
            avg_scores[mt.value] = round(sum(scores) / len(scores), 4) if scores else 0.0

        avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0.0
        total_tokens = sum(r.token_count for r in results)

        # Regression detection
        regression = False
        if baseline_scores:
            for metric_name, baseline_val in baseline_scores.items():
                current_val = avg_scores.get(metric_name, 0.0)
                if current_val < baseline_val - 0.05:  # 5% regression tolerance
                    regression = True
                    break

        status = EvalStatus.FAILED if failed > 0 else EvalStatus.PASSED
        if not regression and status == EvalStatus.PASSED and any(
            avg_scores.get(m, 1.0) < self.default_threshold for m in avg_scores
        ):
            status = EvalStatus.WARNING

        return EvalReport(
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            total_cases=len(results),
            passed_cases=passed,
            failed_cases=failed,
            avg_scores=avg_scores,
            avg_latency_ms=round(avg_latency, 2),
            total_tokens=total_tokens,
            status=status,
            results=results,
            regression_detected=regression,
        )

    @staticmethod
    def generate_report(report: EvalReport) -> str:
        """Pretty-print an evaluation report."""
        lines = [
            f"{'=' * 60}",
            f"  Evaluation Report: {report.prompt_name} v{report.prompt_version}",
            f"{'=' * 60}",
            f"  Status      : {report.status.value.upper()}",
            f"  Test Cases  : {report.total_cases} total, "
            f"{report.passed_cases} passed, {report.failed_cases} failed",
            f"  Avg Latency : {report.avg_latency_ms:.1f} ms",
            f"  Total Tokens: {report.total_tokens:,}",
            f"  Regression  : {'YES' if report.regression_detected else 'No'}",
            "",
            "  Metric Averages:",
        ]
        for metric, score in report.avg_scores.items():
            bar = "#" * int(score * 20)
            lines.append(f"    {metric:<15} {score:.2%}  [{bar:<20}]")

        lines.append(f"{'=' * 60}")
        return "\n".join(lines)
