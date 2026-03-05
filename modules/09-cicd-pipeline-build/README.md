# Module 09: CI/CD Pipeline Design for LLM Applications

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Advanced |
| **Prerequisites** | Module 08 completed, familiarity with GitHub Actions |

---

## Learning Objectives

By the end of this module, you will be able to:

- Design a GitHub Actions CI/CD pipeline tailored for LLM applications
- Implement multi-stage pipelines with lint, test, evaluation, and deployment stages
- Configure tiered testing: offline checks on every commit, online evaluation on merge
- Build Docker images with prompt artifacts and model configuration baked in
- Set up quality gates that block deployment when evaluation scores regress

---

## Concepts

### How LLM CI/CD Differs from Standard CI/CD

A typical software CI/CD pipeline runs lint, unit tests, and deploys. LLM CI/CD adds several unique stages:

```
Standard CI/CD:        LLM CI/CD:
┌──────────┐           ┌──────────┐
│   Lint   │           │   Lint   │
└────┬─────┘           └────┬─────┘
     │                      │
┌────┴─────┐           ┌────┴─────┐
│  Tests   │           │  Tests   │
└────┬─────┘           └────┬─────┘
     │                      │
┌────┴─────┐           ┌────┴──────────┐
│  Build   │           │ Prompt Eval   │  <-- NEW: run evaluation pipeline
└────┬─────┘           └────┬──────────┘
     │                      │
┌────┴─────┐           ┌────┴──────────┐
│  Deploy  │           │ Regression    │  <-- NEW: compare against baseline
└──────────┘           │ Detection     │
                       └────┬──────────┘
                            │
                       ┌────┴──────────┐
                       │ Cost Estimate │  <-- NEW: predict deployment cost
                       └────┬──────────┘
                            │
                       ┌────┴──────────┐
                       │ Canary Deploy │  <-- NEW: gradual rollout
                       └────┬──────────┘
                            │
                       ┌────┴──────────┐
                       │ Health Gate   │  <-- NEW: auto-promote or rollback
                       └──────────────┘
```

### Pipeline Architecture

The pipeline in `.github/workflows/llm-ci.yml` implements five stages:

#### Stage 1: Lint and Type Check
Runs ruff (linter) and mypy (type checker) on every push. Catches syntax errors, import issues, and type mismatches before any expensive operations.

#### Stage 2: Unit Tests
Runs pytest on all test files excluding integration and e2e tests. These tests are fast, free (no API calls), and validate code logic.

#### Stage 3: Prompt Evaluation
Runs the evaluation pipeline in offline mode against a test suite. Checks that the prompt store initializes correctly, evaluators produce valid scores, canary routing works, and cost tracking records properly.

#### Stage 4: Docker Build
Builds the Docker image without pushing. Validates that the Dockerfile is correct and all dependencies install successfully.

#### Stage 5: CI Gate
A summary job that checks all previous stages and produces a single pass/fail signal for the PR.

### Workflow Triggers

```yaml
on:
  push:
    branches: [main, develop]
    paths:
      - "src/**"       # Source code changes
      - "prompts/**"   # Prompt template changes
      - "tests/**"     # Test changes
  pull_request:
    branches: [main]
```

Key design decisions:
- **Path filtering:** Only run on relevant file changes (not documentation updates)
- **Branch protection:** Run on PRs to main for quality gates
- **Push to main:** Run full pipeline on merge for deployment

### Secrets Management

```yaml
env:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Best practices:
- Never hardcode API keys in workflows or code
- Use GitHub Secrets for sensitive values
- Use different API keys for CI (with lower rate limits) vs. production
- Set spending limits on CI API keys

### Caching for Faster Builds

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.11"
    cache: pip  # Caches pip dependencies between runs
```

Additional caching opportunities:
- Docker layer caching with `cache-from: type=gha`
- Evaluation result caching (store baseline scores as artifacts)
- Model response caching for deterministic re-evaluation

### Key Terminology

| Term | Definition |
|---|---|
| **Workflow** | A YAML file defining a CI/CD pipeline in GitHub Actions |
| **Job** | A unit of work within a workflow that runs on a single runner |
| **Step** | A single command or action within a job |
| **Quality gate** | A required check that must pass before merging or deploying |
| **Artifact** | A file produced by one job and consumed by another (test results, reports) |
| **Matrix strategy** | Running the same job across multiple configurations in parallel |
| **Path filter** | Only triggering a workflow when specific files change |

---

## Hands-On Lab

### Prerequisites Check

```bash
# Verify the workflow file exists
ls .github/workflows/llm-ci.yml

# Verify you have a GitHub repo
git remote -v
```

### Exercise 1: Understand the Pipeline

**Goal:** Read and annotate the existing CI workflow.

```bash
# Open the workflow file
cat .github/workflows/llm-ci.yml
```

Answer these questions:
1. How many jobs does the pipeline have?
2. Which jobs run in parallel? Which depend on others?
3. What happens if the lint job fails?
4. Where is the OPENAI_API_KEY used, and what happens without it?

### Exercise 2: Run the Pipeline Locally

**Goal:** Execute each pipeline stage locally to verify it works before pushing.

```bash
# Stage 1: Lint
pip install ruff mypy
ruff check src/ || echo "Lint issues found"
mypy src/ --ignore-missing-imports || echo "Type issues found"

# Stage 2: Unit tests (create a minimal test first)
mkdir -p tests
```

Create `tests/test_smoke.py`:

```python
"""Smoke tests that verify core modules import and initialize correctly."""

def test_prompt_store_init():
    from src.versioning.prompt_store import PromptStore
    store = PromptStore()
    assert store is not None

def test_eval_pipeline_init():
    from src.evaluation.eval_pipeline import EvalPipeline
    pipeline = EvalPipeline()
    assert pipeline is not None

def test_canary_manager_init():
    from src.deployment.canary import CanaryManager
    manager = CanaryManager()
    assert manager is not None

def test_cost_tracker_init():
    from src.tracking.cost_tracker import CostTracker
    tracker = CostTracker()
    assert tracker is not None

def test_prompt_store_save_and_retrieve():
    from src.versioning.prompt_store import PromptStore
    store = PromptStore()
    version = store.save("ci-test", "Hello {name}", author="ci")
    assert version.version == "1.0"
    retrieved = store.get("ci-test")
    assert retrieved is not None
    assert retrieved.template == "Hello {name}"

def test_cost_tracker_record():
    from src.tracking.cost_tracker import CostTracker
    tracker = CostTracker()
    record = tracker.record("gpt-4o-mini", 500, 150)
    assert record.total_tokens == 650
    assert record.cost_usd > 0
```

Run the tests:

```bash
pytest tests/test_smoke.py -v
```

### Exercise 3: Add a Prompt Evaluation Stage

**Goal:** Add a CI step that evaluates prompts and fails on regression.

Create `scripts/ci_eval.py`:

```python
"""CI script: run prompt evaluation and exit with non-zero on failure."""
import asyncio
import sys
from src.evaluation.eval_pipeline import EvalPipeline, TestCase

REQUIRED_SCORE = 0.6  # Minimum average score to pass CI

TEST_CASES = [
    TestCase(
        input_text="Summarize: AI is transforming healthcare with faster diagnostics.",
        expected_output="AI transforms healthcare through faster diagnostics.",
    ),
    TestCase(
        input_text="Summarize: Climate change affects global food production.",
        expected_output="Climate change impacts global food production.",
    ),
    TestCase(
        input_text="Summarize: Remote work has become standard since 2020.",
        expected_output="Remote work became standard after 2020.",
    ),
]

async def main():
    pipeline = EvalPipeline()
    report = await pipeline.run_evaluation(
        prompt_name="ci-summarizer",
        test_cases=TEST_CASES,
        metrics=["accuracy", "relevance", "toxicity"],
    )

    print(EvalPipeline.generate_report(report))

    # Check quality gate
    for metric, score in report.avg_scores.items():
        if score < REQUIRED_SCORE:
            print(f"\nFAILED: {metric} score {score:.2%} < {REQUIRED_SCORE:.2%}")
            sys.exit(1)

    if report.regression_detected:
        print("\nFAILED: Regression detected")
        sys.exit(1)

    print("\nPASSED: All quality gates met")
    sys.exit(0)

asyncio.run(main())
```

### Exercise 4: Configure Branch Protection

**Goal:** Set up GitHub branch protection that requires the CI to pass.

Steps (in GitHub UI):
1. Go to Settings > Branches > Add rule
2. Branch name pattern: `main`
3. Check "Require status checks to pass before merging"
4. Add these required checks:
   - `Lint & Type Check`
   - `Unit Tests`
   - `Prompt Evaluation`
   - `CI Gate`
5. Check "Require branches to be up to date before merging"
6. Save

Now PRs to main cannot be merged unless all CI stages pass.

---

## Starter Files

Check `lab/starter/` for:
- Skeleton GitHub Actions workflow
- Minimal test files
- CI evaluation script template

## Solution Files

If you get stuck, `lab/solution/` contains:
- Complete workflow with all stages
- Full test suite
- Working CI evaluation script

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Running expensive LLM tests on every commit | Slow CI, high costs | Use offline mode on commits, online on merge |
| No path filtering | CI runs on README changes | Add `paths:` filter to workflow triggers |
| Hardcoded API keys in workflow | Security vulnerability | Use GitHub Secrets (`secrets.OPENAI_API_KEY`) |
| No CI gate job | Individual job failures are easy to miss | Add a summary job that checks all dependencies |
| Not caching pip dependencies | Slow installs on every run | Use `cache: pip` in setup-python action |

---

## Self-Check Questions

1. What are the five stages of an LLM CI/CD pipeline?
2. Why do we need path filtering in workflow triggers?
3. How do you prevent expensive LLM API calls from running on every commit?
4. What is a quality gate and how does it block bad deployments?
5. How would you add a cost estimation stage to the pipeline?

---

## You Know You Have Completed This Module When...

- [ ] Read and understood the `.github/workflows/llm-ci.yml` workflow
- [ ] Ran all pipeline stages locally (lint, test, eval)
- [ ] Created smoke tests that verify module initialization
- [ ] Written a CI evaluation script with quality gates
- [ ] Validation script passes: `bash modules/09-cicd-pipeline-build/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: GitHub Actions workflow not triggering**
- Check that the file is at exactly `.github/workflows/llm-ci.yml`
- Verify the branch name matches the `on.push.branches` list
- Check that changed files match the `paths` filter

**Issue: "Module not found" errors in CI**
- The repo root needs to be in `PYTHONPATH`
- Add `PYTHONPATH: .` to the env section, or install the package

**Issue: CI passes locally but fails on GitHub**
- Check Python version matches (3.11)
- Verify all dependencies are in `requirements.txt`
- Check that no tests depend on local files or environment variables

---

**Next: [Module 10 - Production LLMOps Platform -->](../10-production-llmops/)**
