# Module 04: Automated LLM Testing Frameworks

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Intermediate |
| **Prerequisites** | Module 03 completed, evaluation pipeline understood |

---

## Learning Objectives

By the end of this module, you will be able to:

- Use deepeval to write and run structured LLM test suites
- Configure promptfoo for YAML-driven prompt comparison testing
- Build custom evaluators that go beyond built-in metrics
- Integrate LLM tests into pytest for CI/CD compatibility
- Design test strategies that balance coverage, cost, and speed

---

## Concepts

### The LLM Testing Landscape

LLM testing is fundamentally different from traditional software testing:

| Traditional Testing | LLM Testing |
|---|---|
| Deterministic: same input = same output | Non-deterministic: same input can produce different outputs |
| Binary pass/fail | Scored on a spectrum (0.0 to 1.0) |
| Unit tests run in milliseconds | Each test case requires an API call (seconds, costs money) |
| Test the code | Test the prompt + model + parameters together |
| Mock dependencies | Must test against the real model (or a close proxy) |

### Testing Frameworks Compared

#### deepeval

A Python-native framework for evaluating LLM applications. Provides pre-built metrics (G-Eval, faithfulness, hallucination, toxicity) and integrates with pytest.

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric

test_case = LLMTestCase(
    input="What is the capital of France?",
    actual_output="The capital of France is Paris.",
)
metric = AnswerRelevancyMetric(threshold=0.7)
evaluate([test_case], [metric])
```

**Strengths:** Python-native, rich metrics, pytest integration, CI-ready.
**Limitations:** Requires API key for LLM-as-judge metrics.

#### promptfoo

A CLI and YAML-driven tool for comparing prompt variants across multiple models. Excellent for A/B testing prompts before deploying.

```yaml
# promptfoo.yaml
prompts:
  - "Summarize this: {{text}}"
  - "Give a brief summary: {{text}}"

providers:
  - openai:gpt-4o-mini
  - openai:gpt-4o

tests:
  - vars:
      text: "AI is changing healthcare..."
    assert:
      - type: contains
        value: "healthcare"
      - type: llm-rubric
        value: "Output should be a concise, accurate summary"
```

**Strengths:** YAML config (no code needed), multi-provider comparison, built-in web UI.
**Limitations:** Node.js based, less flexible for complex custom logic.

#### Custom Evaluators

For domain-specific needs, build your own evaluators that plug into the pipeline from Module 03.

**When to go custom:**
- Domain-specific correctness (medical accuracy, legal compliance)
- Structured output validation (JSON schema, specific formats)
- Business logic constraints (word count, brand voice, prohibited phrases)

### Test Strategy Matrix

| Test Type | When to Run | Cost | Coverage |
|---|---|---|---|
| **Syntax checks** | Every commit | Free | Low |
| **Offline eval (mocked)** | Every commit | Free | Medium |
| **Online eval (real API)** | Pre-merge, nightly | $$$ | High |
| **Human review** | Before prod release | Time | Highest |

### Cost-Conscious Testing

Each LLM test case costs money. Strategies to manage cost:

1. **Tiered testing:** Run cheap tests on every commit, expensive tests nightly
2. **Sampling:** Test 20 representative cases, not 2,000
3. **Caching:** Cache LLM responses for deterministic re-evaluation
4. **Model proxies:** Use `gpt-4o-mini` for CI, `gpt-4o` for release gate
5. **Offline metrics:** Use token-overlap and pattern matching when possible

### Key Terminology

| Term | Definition |
|---|---|
| **deepeval** | Python framework for LLM evaluation with pytest integration |
| **promptfoo** | YAML-driven CLI tool for comparing prompts across providers |
| **G-Eval** | LLM-as-judge evaluation method using chain-of-thought scoring |
| **Test harness** | The infrastructure that runs test cases and collects results |
| **Flaky test** | A test that passes and fails inconsistently due to LLM non-determinism |
| **Golden dataset** | A curated set of input-output pairs used as ground truth |

---

## Hands-On Lab

### Prerequisites Check

```bash
pip install deepeval pytest
python3 -c "import deepeval; print(f'deepeval {deepeval.__version__} ready')"
```

### Exercise 1: Write Tests with deepeval

**Goal:** Create a pytest-compatible test suite for your summarizer prompt.

Create `tests/test_summarizer.py`:

```python
import pytest
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric

# Pre-generated outputs for offline testing
SUMMARIZER_OUTPUTS = [
    {
        "input": "Machine learning enables systems to learn from data and make predictions.",
        "output": "ML allows systems to learn from data for making predictions.",
    },
    {
        "input": "Cloud computing provides on-demand access to shared computing resources.",
        "output": "Cloud computing offers scalable, on-demand computing resources.",
    },
]


class TestSummarizerQuality:
    """Test suite for the summarizer prompt."""

    @pytest.mark.parametrize("case", SUMMARIZER_OUTPUTS)
    def test_relevance(self, case):
        """Output must be relevant to the input."""
        test_case = LLMTestCase(
            input=case["input"],
            actual_output=case["output"],
        )
        assert len(case["output"]) > 0, "Output should not be empty"
        assert len(case["output"]) < len(case["input"]), "Summary should be shorter than input"

    @pytest.mark.parametrize("case", SUMMARIZER_OUTPUTS)
    def test_no_toxic_content(self, case):
        """Output must not contain harmful language."""
        toxic_terms = ["hate", "kill", "stupid", "violent"]
        output_lower = case["output"].lower()
        for term in toxic_terms:
            assert term not in output_lower, f"Output contains toxic term: {term}"

    @pytest.mark.parametrize("case", SUMMARIZER_OUTPUTS)
    def test_brevity(self, case):
        """Summary should be at most 60% the length of the input."""
        input_words = len(case["input"].split())
        output_words = len(case["output"].split())
        ratio = output_words / input_words
        assert ratio <= 0.8, f"Summary too long: {ratio:.0%} of input length"
```

Run the tests:

```bash
pytest tests/test_summarizer.py -v
```

### Exercise 2: Configure promptfoo

**Goal:** Set up a YAML-based prompt comparison test.

Create `promptfoo.yaml` in the repo root:

```yaml
description: "Summarizer prompt comparison"

prompts:
  - id: v1-paragraph
    raw: "Summarize the following text in one paragraph:\n\n{{text}}"
  - id: v2-bullets
    raw: "Summarize the following text in 3 bullet points:\n\n{{text}}"

providers:
  - id: openai:gpt-4o-mini
    config:
      temperature: 0.3
      max_tokens: 256

tests:
  - description: "Healthcare AI article"
    vars:
      text: >
        Artificial intelligence is rapidly transforming healthcare.
        New diagnostic tools can detect diseases earlier than traditional
        methods, potentially saving millions of lives annually.
    assert:
      - type: contains
        value: "healthcare"
      - type: contains
        value: "AI"
      - type: javascript
        value: "output.length < 500"

  - description: "Climate change article"
    vars:
      text: >
        Climate change poses significant risks to global food security.
        Rising temperatures and changing precipitation patterns affect
        crop yields worldwide, with developing nations most vulnerable.
    assert:
      - type: contains
        value: "climate"
      - type: javascript
        value: "output.split(' ').length < 100"
```

Run promptfoo (if installed):

```bash
npx promptfoo eval
npx promptfoo view  # Opens comparison UI in browser
```

### Exercise 3: Build a Custom Pytest Evaluator

**Goal:** Create a reusable evaluator that checks JSON output format.

```python
# tests/evaluators/test_json_output.py
import json
import pytest

class TestClassifierOutput:
    """Verify that classifier outputs valid JSON with required fields."""

    CLASSIFIER_CASES = [
        {
            "input": "My credit card was charged twice",
            "output": '{"category": "billing", "confidence": 0.92}',
        },
        {
            "input": "I cannot log into my account",
            "output": '{"category": "account", "confidence": 0.88}',
        },
    ]

    @pytest.mark.parametrize("case", CLASSIFIER_CASES)
    def test_valid_json(self, case):
        """Output must be valid JSON."""
        parsed = json.loads(case["output"])
        assert isinstance(parsed, dict)

    @pytest.mark.parametrize("case", CLASSIFIER_CASES)
    def test_required_fields(self, case):
        """Output must contain category and confidence."""
        parsed = json.loads(case["output"])
        assert "category" in parsed, "Missing 'category' field"
        assert "confidence" in parsed, "Missing 'confidence' field"

    @pytest.mark.parametrize("case", CLASSIFIER_CASES)
    def test_valid_category(self, case):
        """Category must be one of the allowed values."""
        parsed = json.loads(case["output"])
        allowed = {"billing", "technical", "account", "other"}
        assert parsed["category"] in allowed, f"Invalid category: {parsed['category']}"

    @pytest.mark.parametrize("case", CLASSIFIER_CASES)
    def test_confidence_range(self, case):
        """Confidence must be between 0 and 1."""
        parsed = json.loads(case["output"])
        assert 0 <= parsed["confidence"] <= 1, f"Confidence out of range: {parsed['confidence']}"
```

### Exercise 4: Tiered Test Configuration for CI

**Goal:** Create a pytest marker system for running different test tiers.

```python
# conftest.py
import pytest

def pytest_addoption(parser):
    parser.addoption("--tier", default="offline", choices=["offline", "online", "full"])

def pytest_configure(config):
    config.addinivalue_line("markers", "offline: runs without API calls")
    config.addinivalue_line("markers", "online: requires API key")
    config.addinivalue_line("markers", "slow: takes more than 30 seconds")

def pytest_collection_modifyitems(config, items):
    tier = config.getoption("--tier")
    if tier == "offline":
        skip = pytest.mark.skip(reason="skipped in offline tier")
        for item in items:
            if "online" in item.keywords:
                item.add_marker(skip)
```

Usage:

```bash
# CI: fast offline tests only
pytest tests/ --tier=offline -v

# Nightly: include API-backed tests
pytest tests/ --tier=online -v

# Release gate: everything
pytest tests/ --tier=full -v
```

---

## Starter Files

Check `lab/starter/` for:
- Test file skeletons for summarizer and classifier
- promptfoo.yaml template
- Pytest configuration (conftest.py)

## Solution Files

If you get stuck, `lab/solution/` contains:
- Complete test suites with all assertions
- Working promptfoo configuration
- Custom evaluator examples

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Testing with temperature=1.0 | Flaky tests due to high variance | Use temperature=0.0-0.3 for deterministic testing |
| Running all tests on every commit | Slow CI, high API costs | Tier tests: offline on commit, online nightly |
| No baseline for comparison | Cannot detect regressions | Establish baseline scores before changing prompts |
| Testing exact string matches | Failures on semantically correct outputs | Use fuzzy matching, token overlap, or LLM-as-judge |

---

## Self-Check Questions

1. What are the key differences between deepeval and promptfoo? When would you use each?
2. How do you manage the cost of LLM test suites that require real API calls?
3. What is the difference between offline evaluation and online evaluation?
4. How would you test a creative writing prompt where there is no single correct answer?
5. Why is temperature=0.0 important for reproducible test results?

---

## You Know You Have Completed This Module When...

- [ ] Written at least 5 pytest-compatible LLM test cases
- [ ] Created a promptfoo.yaml configuration
- [ ] Built a custom evaluator for domain-specific validation
- [ ] Configured tiered test execution with pytest markers
- [ ] Validation script passes: `bash modules/04-automated-testing/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: deepeval requires OPENAI_API_KEY for LLM-as-judge metrics**
- Use offline evaluators (token overlap, pattern matching) for CI
- Set the API key only for nightly or pre-release evaluation runs

**Issue: promptfoo not found**
```bash
# promptfoo is a Node.js tool
npx promptfoo --version
# Or install globally: npm install -g promptfoo
```

**Issue: Flaky tests**
- Set `temperature=0.0` in your LLM calls
- Use `seed` parameter if the provider supports it
- Increase tolerance thresholds for non-deterministic metrics

---

**Next: [Module 05 - A/B Testing Prompts and Models -->](../05-ab-testing-prompts/)**
