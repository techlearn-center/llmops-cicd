# Module 05: A/B Testing Prompts and Models

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Intermediate |
| **Prerequisites** | Modules 01-04 completed, canary deployment concepts understood |

---

## Learning Objectives

By the end of this module, you will be able to:

- Design an A/B testing framework for LLM prompts and model versions
- Implement traffic routing with sticky sessions for consistent user experience
- Calculate statistical significance for LLM output quality comparisons
- Build a decision framework for when to promote variant B over variant A
- Avoid common pitfalls like peeking at results too early or biased sample selection

---

## Concepts

### Why A/B Test LLMs?

Offline evaluation (Module 03) tells you how a prompt performs on test cases. A/B testing tells you how it performs with real users. The gap between these two signals is often large because:

- Test cases do not capture the full diversity of real user inputs
- User satisfaction depends on factors that metrics cannot fully capture (tone, formatting, helpfulness)
- Real-world latency and error rates differ from controlled test environments

### A/B Testing Architecture

```
                    ┌──────────────┐
  User Request ────▶│  Router      │
                    │  (hash-based │
                    │   splitting) │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼                         ▼
     ┌────────────────┐       ┌────────────────┐
     │  Variant A     │       │  Variant B     │
     │  (baseline)    │       │  (challenger)  │
     │  prompt v1.2   │       │  prompt v1.3   │
     │  gpt-4o-mini   │       │  gpt-4o-mini   │
     └────────┬───────┘       └────────┬───────┘
              │                        │
              ▼                        ▼
     ┌────────────────┐       ┌────────────────┐
     │  Metrics       │       │  Metrics       │
     │  Collector     │       │  Collector     │
     └────────┬───────┘       └────────┬───────┘
              │                        │
              └────────────┬───────────┘
                           ▼
                    ┌──────────────┐
                    │  Statistical │
                    │  Analysis    │
                    └──────────────┘
```

### Traffic Routing Strategies

#### Random Splitting
Each request is randomly assigned to A or B based on the configured weight (e.g., 50/50 or 90/10).

```python
import random
variant = "B" if random.random() < 0.5 else "A"
```

**Pro:** Simple. **Con:** Same user might get different variants on different requests.

#### Hash-Based (Sticky) Splitting
A deterministic hash of the user ID decides the variant. Same user always gets the same variant.

```python
import hashlib
hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
variant = "B" if (hash_val % 100) < 50 else "A"
```

**Pro:** Consistent user experience. **Con:** Slightly less random distribution.

### Statistical Significance

You need enough data to be confident that observed differences are real, not noise.

**Key concepts:**

| Term | Definition |
|---|---|
| **Sample size** | Number of requests per variant needed for reliable results |
| **p-value** | Probability that the observed difference is due to chance (target: < 0.05) |
| **Confidence interval** | Range within which the true metric value likely falls |
| **Effect size** | Magnitude of the difference between variants |
| **Minimum detectable effect** | Smallest improvement worth detecting |

**Rule of thumb:** For a 5% improvement detection with 95% confidence, you need approximately 1,600 samples per variant.

### Metrics to Track

| Metric | What It Measures | How to Collect |
|---|---|---|
| **User satisfaction** | Thumbs up/down, star rating | UI feedback widget |
| **Task completion** | Did the user achieve their goal? | Event tracking |
| **Response quality** | Automated eval scores | Run evaluators on sampled responses |
| **Latency** | Time to first token / total | Instrumentation |
| **Error rate** | Failed LLM calls | Error logging |
| **Cost per request** | Token usage * price | Cost tracker (Module 07) |

### Decision Framework

```
          Enough samples?
               │
         ┌─────┴─────┐
         No          Yes
         │            │
     Wait for      Significant
     more data     difference?
                      │
                ┌─────┴─────┐
                No          Yes
                │            │
           No winner.    B better?
           Keep A.          │
                      ┌─────┴─────┐
                      No          Yes
                      │            │
                 Keep A.     Promote B.
                 (A wins)    Roll out 100%.
```

### Key Terminology

| Term | Definition |
|---|---|
| **Variant** | One version of the prompt/model being tested (A = control, B = challenger) |
| **Sticky routing** | Ensuring the same user always sees the same variant |
| **Statistical significance** | Confidence that observed differences are not due to random chance |
| **p-value** | The probability of seeing the observed result if there were no real difference |
| **Effect size** | How large the difference is between variants (practical significance) |
| **Guardrails** | Automatic safety checks that halt an experiment if metrics degrade |

---

## Hands-On Lab

### Exercise 1: Implement A/B Routing

**Goal:** Use the CanaryManager for A/B traffic splitting.

```python
from src.deployment.canary import CanaryManager, CanaryConfig

manager = CanaryManager()

# Create an A/B test with 50/50 split
ab_test = manager.create_deployment(
    name="summarizer-ab-test",
    baseline_model="prompt-v1.2",   # Variant A
    canary_model="prompt-v1.3",     # Variant B
    canary_weight=0.5,              # 50/50 split
    config=CanaryConfig(
        min_requests_before_decision=100,
        max_error_rate=0.05,
    ),
)

# Simulate 200 user requests with sticky routing
users = [f"user-{i}" for i in range(200)]
variant_counts = {"prompt-v1.2": 0, "prompt-v1.3": 0}

for user_id in users:
    variant = manager.route_request("summarizer-ab-test", sticky_key=user_id)
    variant_counts[variant] += 1

print(f"Variant A: {variant_counts['prompt-v1.2']} users")
print(f"Variant B: {variant_counts['prompt-v1.3']} users")

# Verify sticky routing: same user always gets same variant
v1 = manager.route_request("summarizer-ab-test", sticky_key="user-42")
v2 = manager.route_request("summarizer-ab-test", sticky_key="user-42")
assert v1 == v2, "Sticky routing broken!"
print(f"User-42 consistently routed to: {v1}")
```

### Exercise 2: Collect and Analyze Metrics

**Goal:** Simulate an A/B test with quality metrics and determine a winner.

```python
import random

# Simulate outcomes for both variants
for i in range(200):
    user_id = f"user-{i}"
    variant = manager.route_request("summarizer-ab-test", sticky_key=user_id)

    # Simulate: Variant B (v1.3) is slightly better
    if variant == "prompt-v1.3":
        success = random.random() < 0.95      # 95% success rate
        latency = random.gauss(200, 30)        # 200ms avg
        quality = random.gauss(0.88, 0.05)     # 0.88 avg quality
    else:
        success = random.random() < 0.92       # 92% success rate
        latency = random.gauss(220, 35)        # 220ms avg
        quality = random.gauss(0.82, 0.06)     # 0.82 avg quality

    manager.record_outcome(
        "summarizer-ab-test",
        variant,
        success=success,
        latency_ms=max(50, latency),
        quality_score=max(0, min(1, quality)),
    )

# Check results
health = manager.check_health("summarizer-ab-test")
print(f"Healthy: {health['healthy']}")
print(manager.get_summary("summarizer-ab-test"))
```

### Exercise 3: Calculate Statistical Significance

**Goal:** Determine whether the quality difference between variants is statistically significant.

```python
import numpy as np

# Extract quality scores for each variant
dep = manager.get_deployment("summarizer-ab-test")
a_scores = dep.baseline_metrics.quality_scores
b_scores = dep.canary_metrics.quality_scores

# Manual two-sample t-test (no scipy required)
a_mean, b_mean = np.mean(a_scores), np.mean(b_scores)
a_std, b_std = np.std(a_scores, ddof=1), np.std(b_scores, ddof=1)
n_a, n_b = len(a_scores), len(b_scores)

# Pooled standard error
se = np.sqrt(a_std**2 / n_a + b_std**2 / n_b)
t_stat = (b_mean - a_mean) / se

print(f"Variant A: mean={a_mean:.4f}, std={a_std:.4f}, n={n_a}")
print(f"Variant B: mean={b_mean:.4f}, std={b_std:.4f}, n={n_b}")
print(f"t-statistic: {t_stat:.4f}")
print(f"Improvement: {b_mean - a_mean:.4f} ({(b_mean - a_mean) / a_mean:.1%})")

# Rule of thumb: |t| > 2 is roughly p < 0.05 for large samples
if abs(t_stat) > 2:
    winner = "B" if b_mean > a_mean else "A"
    print(f"Result: SIGNIFICANT - Variant {winner} wins")
else:
    print(f"Result: NOT SIGNIFICANT - No clear winner")
```

### Exercise 4: Automate the Decision

**Goal:** Build an automated promotion/rollback based on A/B test results.

```python
def make_ab_decision(manager, name, min_samples=50):
    """Automated decision engine for A/B tests."""
    dep = manager.get_deployment(name)
    if not dep:
        return "no deployment found"

    a_scores = dep.baseline_metrics.quality_scores
    b_scores = dep.canary_metrics.quality_scores

    if len(a_scores) < min_samples or len(b_scores) < min_samples:
        return f"need more data ({len(a_scores)}/{len(b_scores)} vs {min_samples} min)"

    a_mean = sum(a_scores) / len(a_scores)
    b_mean = sum(b_scores) / len(b_scores)

    # Check error rates
    a_err = dep.baseline_metrics.error_rate
    b_err = dep.canary_metrics.error_rate

    if b_err > dep.config.max_error_rate:
        manager.manual_rollback(name)
        return f"ROLLBACK: Variant B error rate too high ({b_err:.2%})"

    if b_mean > a_mean + 0.02:  # B must be 2+ points better
        return f"PROMOTE B: quality {b_mean:.4f} vs {a_mean:.4f} (+{b_mean - a_mean:.4f})"
    elif a_mean > b_mean + 0.02:
        return f"KEEP A: quality {a_mean:.4f} vs {b_mean:.4f} (B is worse)"
    else:
        return f"NO WINNER: quality too close ({a_mean:.4f} vs {b_mean:.4f})"

result = make_ab_decision(manager, "summarizer-ab-test")
print(f"Automated decision: {result}")
```

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Peeking at results too early | False positives, premature decisions | Set minimum sample size before analyzing |
| Not using sticky routing | Same user sees different variants | Use hash-based routing with user ID |
| Testing too many variants | Diluted traffic, slow results | Test at most 2-3 variants simultaneously |
| Ignoring segment effects | Overall result hides per-segment differences | Analyze by user segment and query type |
| No guardrails | Bad variant degrades experience | Set error rate and latency limits with auto-rollback |

---

## Self-Check Questions

1. Why is sticky routing important for A/B testing LLMs?
2. How many samples do you need per variant for a statistically significant result?
3. What is the difference between A/B testing and canary deployment?
4. How would you handle an A/B test where neither variant is clearly better?
5. What metrics beyond quality scores should you track during an A/B test?

---

## You Know You Have Completed This Module When...

- [ ] Implemented traffic routing with sticky sessions
- [ ] Ran a simulated A/B test with quality metrics
- [ ] Calculated statistical significance of the results
- [ ] Built an automated decision function
- [ ] Validation script passes: `bash modules/05-ab-testing-prompts/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: Uneven traffic split**
- Hash-based routing is not perfectly 50/50; expect 45-55% splits with small samples
- Increase sample size for better balance

**Issue: Statistical test always says "not significant"**
- Increase sample size (need 100+ per variant minimum)
- Check that the simulated quality difference is large enough to detect

**Issue: Both variants have identical metrics**
- Verify you are recording metrics for the correct variant
- Check that the simulation uses different parameters for each variant

---

**Next: [Module 06 - Canary Deployments for LLM Apps -->](../06-canary-deployments/)**
