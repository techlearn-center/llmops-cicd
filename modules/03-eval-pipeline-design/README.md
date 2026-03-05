# Module 03: Evaluation Pipeline Design

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Intermediate |
| **Prerequisites** | Module 02 completed, prompt store operational |

---

## Learning Objectives

By the end of this module, you will be able to:

- Design an automated evaluation pipeline that scores LLM outputs across multiple dimensions
- Implement accuracy, relevance, toxicity, and coherence evaluators
- Build test case suites with expected outputs and scoring thresholds
- Detect prompt regressions by comparing evaluation results across versions
- Generate evaluation reports that block or approve prompt deployments

---

## Concepts

### Why Automated Evaluation?

Manual review does not scale. When your application serves thousands of requests per day and you update prompts weekly, you need an automated quality gate that:

- Runs on every prompt change (in CI or pre-deploy)
- Scores outputs across multiple quality dimensions
- Compares new scores against a baseline to catch regressions
- Produces a clear pass/fail signal for the deployment pipeline

### The Evaluation Pipeline Architecture

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│  Test Cases  │───▶│  LLM Call    │───▶│  Evaluators  │───▶│  Report  │
│  (inputs +   │    │  (generate   │    │  (score per  │    │  (pass/  │
│   expected)  │    │   outputs)   │    │   metric)    │    │   fail)  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────┘
                                              │
                                              ▼
                                       ┌──────────────┐
                                       │  Regression  │
                                       │  Detection   │
                                       └──────────────┘
```

### Evaluation Metrics Explained

#### Accuracy
Measures how factually correct the output is compared to an expected answer. Uses token-level F1 overlap: precision (how many output tokens match expected) multiplied by recall (how many expected tokens appear in output), combined via harmonic mean.

#### Relevance
Measures whether the output actually addresses the input query. Calculates what fraction of meaningful input terms (excluding stopwords) appear in the output.

#### Toxicity
Scans output for harmful, offensive, or inappropriate content. Uses pattern matching as a baseline; production systems integrate dedicated moderation APIs like the OpenAI Moderation endpoint.

#### Coherence
Evaluates structural quality: sentence count, average sentence length, and readability. Penalizes outputs that are too terse (under 5 words per sentence) or too verbose (over 30 words).

#### Faithfulness (Advanced)
Measures whether the output stays grounded in the provided context and does not hallucinate facts. Requires a reference context to compare against.

### Regression Detection

A regression occurs when a prompt update causes evaluation scores to drop. The pipeline detects this by comparing current scores against a baseline:

```
Baseline (v1.1):  accuracy=0.85, relevance=0.92, toxicity=0.99
Current  (v1.2):  accuracy=0.71, relevance=0.88, toxicity=0.99
                         ↑ REGRESSION (-14%)

Tolerance: 5% drop allowed
Result:    REGRESSION DETECTED -> block deployment
```

### Scoring Thresholds

| Metric | Default Threshold | Meaning |
|---|---|---|
| Accuracy | 0.70 | At least 70% token overlap with expected output |
| Relevance | 0.70 | At least 70% of input terms addressed |
| Toxicity | 0.90 | Less than 10% toxic pattern matches |
| Coherence | 0.70 | Reasonable sentence structure |

### Key Terminology

| Term | Definition |
|---|---|
| **Test case** | An input + optional expected output used to evaluate a prompt |
| **Metric evaluator** | A class that scores one quality dimension (accuracy, toxicity, etc.) |
| **Evaluation report** | Aggregated results across all test cases and metrics |
| **Regression** | A statistically significant drop in metric scores after a prompt change |
| **Baseline** | Reference scores from a known-good prompt version |
| **Quality gate** | A pass/fail check that blocks deployment if scores are too low |

---

## Hands-On Lab

### Prerequisites Check

```bash
python3 -c "from src.evaluation.eval_pipeline import EvalPipeline; print('Ready')"
```

### Exercise 1: Build a Test Case Suite

**Goal:** Create a comprehensive set of test cases for your summarizer prompt.

```python
from src.evaluation.eval_pipeline import TestCase

summarizer_test_cases = [
    TestCase(
        input_text=(
            "Machine learning is a subset of artificial intelligence that "
            "enables systems to learn from data. It uses algorithms to identify "
            "patterns and make decisions with minimal human intervention."
        ),
        expected_output=(
            "Machine learning is an AI subset that learns from data using "
            "algorithms to find patterns and make autonomous decisions."
        ),
        metadata={"category": "technical", "difficulty": "easy"},
    ),
    TestCase(
        input_text=(
            "The global economy grew by 3.2% in 2024, driven primarily by "
            "technology and services sectors. Emerging markets outperformed "
            "developed economies for the third consecutive year."
        ),
        expected_output=(
            "Global GDP grew 3.2% in 2024, led by tech and services, with "
            "emerging markets outpacing developed economies for three years."
        ),
        metadata={"category": "economics", "difficulty": "medium"},
    ),
    TestCase(
        input_text=(
            "Regular exercise has been shown to reduce the risk of heart disease, "
            "improve mental health, strengthen bones, and increase life expectancy. "
            "The WHO recommends 150 minutes of moderate activity per week."
        ),
        expected_output=(
            "Exercise reduces heart disease risk, improves mental health, "
            "strengthens bones, and extends life. WHO recommends 150 minutes weekly."
        ),
        metadata={"category": "health", "difficulty": "easy"},
    ),
]
```

### Exercise 2: Run the Full Evaluation Pipeline

**Goal:** Execute the pipeline and interpret the results.

```python
import asyncio
from src.evaluation.eval_pipeline import EvalPipeline, MetricType

pipeline = EvalPipeline()  # offline mode (no API key)

report = asyncio.run(
    pipeline.run_evaluation(
        prompt_name="summarizer",
        prompt_version="1.2",
        test_cases=summarizer_test_cases,
        metrics=["accuracy", "relevance", "toxicity", "coherence"],
    )
)

# Print the formatted report
print(EvalPipeline.generate_report(report))

# Inspect individual results
for result in report.results:
    print(f"\nInput: {result.test_case.input_text[:60]}...")
    print(f"  Passed: {result.overall_passed}")
    for mr in result.metric_results:
        status = "PASS" if mr.passed else "FAIL"
        print(f"  {mr.metric.value:<15} {mr.score:.2%}  [{status}]  {mr.reason}")
```

### Exercise 3: Detect a Regression

**Goal:** Simulate a prompt regression and verify the pipeline catches it.

```python
# Baseline scores from v1.1 (the "known good" version)
baseline_scores = {
    "accuracy": 0.85,
    "relevance": 0.90,
    "toxicity": 0.99,
}

# Run evaluation for v1.2 with regression detection
report_with_baseline = asyncio.run(
    pipeline.run_evaluation(
        prompt_name="summarizer",
        prompt_version="1.2",
        test_cases=summarizer_test_cases,
        metrics=["accuracy", "relevance", "toxicity"],
        baseline_scores=baseline_scores,
    )
)

print(f"Regression detected: {report_with_baseline.regression_detected}")
print(f"Status: {report_with_baseline.status.value}")
```

### Exercise 4: Build a Custom Evaluator

**Goal:** Extend the pipeline with a domain-specific metric.

```python
from src.evaluation.eval_pipeline import BaseMetricEvaluator, MetricResult, MetricType

class BrevityEvaluator(BaseMetricEvaluator):
    """Checks that the summary is shorter than the input."""

    metric_type = MetricType.CUSTOM
    threshold = 0.5

    async def evaluate(self, input_text, actual_output, expected_output=None, context=None):
        input_len = len(input_text.split())
        output_len = len(actual_output.split())
        ratio = output_len / input_len if input_len > 0 else 1.0

        # Score is 1.0 when output is very short, 0.0 when same length as input
        score = max(0.0, 1.0 - ratio)

        return MetricResult(
            metric=self.metric_type,
            score=round(score, 4),
            passed=ratio < self.threshold,
            reason=f"Output is {ratio:.0%} the length of input ({output_len}/{input_len} words)",
            threshold=self.threshold,
        )
```

---

## Starter Files

Check `lab/starter/` for:
- Test case templates to fill in
- Skeleton evaluator classes
- Sample baseline scores for regression testing

## Solution Files

If you get stuck, `lab/solution/` contains:
- Complete test suite with 10+ test cases
- Custom evaluator implementations
- Expected evaluation report output

> **Important:** Try to complete the exercises yourself first!

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Setting thresholds too high | Every test case fails | Start with 0.5 thresholds and tighten gradually |
| No expected outputs | Accuracy evaluator skips all cases | Provide expected outputs for meaningful accuracy scores |
| Ignoring metric reasons | Cannot debug failures | Always read the `reason` field on MetricResult |
| Running with API key in CI | Expensive and slow | Use offline mode for CI; API-backed eval for nightly runs |

---

## Self-Check Questions

1. Why do we need multiple evaluation metrics instead of a single "quality" score?
2. What is the difference between accuracy and relevance in the context of LLM evaluation?
3. How does regression detection work, and what is the tolerance threshold?
4. When would you use LLM-as-judge instead of rule-based evaluators?
5. How would you handle evaluation for creative tasks where there is no single correct answer?

---

## You Know You Have Completed This Module When...

- [ ] Created a test suite with at least 3 test cases
- [ ] Ran the evaluation pipeline and can interpret the report
- [ ] Successfully detected a simulated regression
- [ ] Built or outlined a custom evaluator
- [ ] Validation script passes: `bash modules/03-eval-pipeline-design/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: All scores are 0.0**
- Check that your test cases have non-empty `input_text` and `expected_output` fields
- Verify the evaluators are being run (check `metric_results` list is not empty)

**Issue: "No module named deepeval"**
```bash
pip install deepeval
# deepeval is optional; the built-in evaluators work without it
```

**Issue: Regression detection not triggering**
- The tolerance is 5% by default. Your scores must drop by more than 5% below baseline.
- Verify your baseline scores are realistic (not 0.0).

---

**Next: [Module 04 - Automated LLM Testing -->](../04-automated-testing/)**
