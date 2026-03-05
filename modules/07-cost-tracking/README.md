# Module 07: Cost Tracking and Optimization

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Intermediate-Advanced |
| **Prerequisites** | Module 06 completed |

---

## Learning Objectives

By the end of this module, you will be able to:

- Track token usage and costs per model, endpoint, and user in real time
- Calculate per-request costs using model-specific pricing tables
- Set up budget alerts and per-user spending limits
- Identify cost optimization opportunities (caching, model selection, prompt efficiency)
- Generate cost reports that inform engineering and business decisions

---

## Concepts

### Why Cost Tracking Matters

LLM costs are variable and can spike unexpectedly. Unlike traditional infrastructure with fixed monthly costs, LLM applications pay per token:

- A single GPT-4 request with a long context can cost $0.30+
- A prompt regression that doubles output length doubles your cost
- A traffic spike on an unoptimized endpoint can burn through a monthly budget in hours
- Without tracking, you will not know which endpoints or users are driving costs

### Token Pricing Model

LLM providers charge separately for input (prompt) and output (completion) tokens:

```
Cost = (prompt_tokens / 1M * input_price) + (completion_tokens / 1M * output_price)
```

Example for GPT-4o with 1,000 prompt tokens and 300 completion tokens:

```
Input:  1,000 / 1,000,000 * $2.50 = $0.0025
Output:   300 / 1,000,000 * $10.00 = $0.0030
Total:                               $0.0055
```

### Model Pricing Comparison

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Best For |
|---|---|---|---|
| gpt-4o | $2.50 | $10.00 | High-quality, complex tasks |
| gpt-4o-mini | $0.15 | $0.60 | Most production workloads |
| gpt-4-turbo | $10.00 | $30.00 | Legacy, avoid for new work |
| gpt-3.5-turbo | $0.50 | $1.50 | Simple tasks, high volume |
| claude-3.5-sonnet | $3.00 | $15.00 | Long context, complex reasoning |
| claude-3-haiku | $0.25 | $1.25 | Fast, cheap classification |

### Cost Optimization Strategies

#### 1. Model Selection (Biggest Impact)
Route simple tasks to cheap models, complex tasks to expensive ones:

```python
def select_model(task_complexity: str) -> str:
    if task_complexity == "simple":
        return "gpt-4o-mini"      # $0.15/1M input
    elif task_complexity == "complex":
        return "gpt-4o"           # $2.50/1M input
    else:
        return "gpt-4o-mini"      # Default to cheap
```

#### 2. Response Caching
Cache identical or near-identical requests in Redis:

```python
cache_key = hashlib.sha256(f"{prompt}:{model}".encode()).hexdigest()
cached = redis.get(cache_key)
if cached:
    return cached  # Free!
response = call_llm(prompt, model)
redis.setex(cache_key, 3600, response)  # Cache for 1 hour
```

#### 3. Prompt Efficiency
Shorter prompts = fewer input tokens = lower cost:

- Remove redundant instructions
- Use concise system prompts
- Set appropriate `max_tokens` limits
- Use structured output formats that are token-efficient

#### 4. Batch Processing
Group requests and process them together where possible:

- Batch classification of support tickets
- Nightly summary generation instead of real-time
- Pre-compute embeddings for known documents

### Key Terminology

| Term | Definition |
|---|---|
| **Token** | Smallest unit of text processed by an LLM (~0.75 words on average) |
| **Prompt tokens** | Input tokens (the prompt you send) |
| **Completion tokens** | Output tokens (the response you receive) |
| **Cost per request** | Total cost of one API call (input + output tokens * price) |
| **Budget alert** | Notification when spending approaches or exceeds a limit |
| **Token budget** | Maximum number of tokens a single request is allowed to use |

---

## Hands-On Lab

### Prerequisites Check

```bash
python3 -c "from src.tracking.cost_tracker import CostTracker; print('Ready')"
```

### Exercise 1: Record and Report Costs

**Goal:** Track costs across multiple models and endpoints, then generate a report.

```python
from src.tracking.cost_tracker import CostTracker, BudgetConfig

tracker = CostTracker(budget=BudgetConfig(
    daily_limit_usd=50.0,
    per_user_daily_limit_usd=5.0,
))

# Simulate a day of API usage across different endpoints
import random

endpoints = ["/api/summarize", "/api/classify", "/api/chat", "/api/analyze"]
models = ["gpt-4o-mini", "gpt-4o", "gpt-4o-mini", "gpt-4o"]
users = [f"user-{i}" for i in range(10)]

for i in range(200):
    endpoint_idx = random.randint(0, 3)
    tracker.record(
        model=models[endpoint_idx],
        prompt_tokens=random.randint(100, 2000),
        completion_tokens=random.randint(50, 500),
        endpoint=endpoints[endpoint_idx],
        user_id=random.choice(users),
    )

# Generate and print report
report = tracker.get_report("today")
print(CostTracker.format_report(report))
```

### Exercise 2: Budget Alerts

**Goal:** Configure budget limits and observe alert behavior.

```python
from src.tracking.cost_tracker import CostTracker, BudgetConfig

# Tight budget for testing
tracker = CostTracker(budget=BudgetConfig(
    daily_limit_usd=0.10,
    alert_threshold_pct=0.5,  # Alert at 50% of budget
    per_user_daily_limit_usd=0.05,
))

# Simulate expensive requests that will trigger alerts
for i in range(20):
    record = tracker.record(
        model="gpt-4o",
        prompt_tokens=5000,
        completion_tokens=2000,
        endpoint="/api/analyze",
        user_id="big-spender",
    )

# Check alerts
report = tracker.get_report("today")
print(f"Total cost: ${report.total_cost_usd:.4f}")
print(f"Budget remaining: ${report.budget_remaining_usd:.4f}")
print(f"\nAlerts ({len(report.alerts)}):")
for alert in report.alerts:
    print(f"  {alert}")
```

### Exercise 3: Cost Optimization Analysis

**Goal:** Use the optimization tips feature to find savings opportunities.

```python
from src.tracking.cost_tracker import CostTracker

tracker = CostTracker()

# Simulate a pattern with optimization opportunities:
# 1. Heavy use of expensive model for simple tasks
# 2. High completion-to-prompt ratio (over-generation)
# 3. Repeated calls to the same endpoint

for i in range(200):
    tracker.record(
        model="gpt-4o",             # Expensive model for everything
        prompt_tokens=200,           # Short prompt
        completion_tokens=1500,      # Very long output (over-generation)
        endpoint="/api/classify",    # Same endpoint repeated (caching opportunity)
        user_id="automated-system",
    )

tips = tracker.get_optimization_tips()
print("Cost Optimization Tips:")
for i, tip in enumerate(tips, 1):
    print(f"  {i}. {tip}")
```

### Exercise 4: Model Cost Comparison

**Goal:** Compare the cost of serving the same workload with different models.

```python
from src.tracking.cost_tracker import CostTracker, MODEL_PRICING

# Simulate the same 100 requests with different models
workload = [
    {"prompt_tokens": random.randint(200, 1500), "completion_tokens": random.randint(100, 500)}
    for _ in range(100)
]

print(f"{'Model':<20} {'Total Cost':>12} {'Avg Cost/Req':>15} {'Savings vs GPT-4o':>18}")
print("-" * 70)

baseline_cost = None
for model_name in ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "claude-3-haiku"]:
    tracker = CostTracker()
    for w in workload:
        tracker.record(model_name, w["prompt_tokens"], w["completion_tokens"])

    report = tracker.get_report("all")
    avg_cost = report.total_cost_usd / report.total_requests
    if baseline_cost is None:
        baseline_cost = report.total_cost_usd
    savings = (1 - report.total_cost_usd / baseline_cost) * 100

    print(f"{model_name:<20} ${report.total_cost_usd:>10.4f} ${avg_cost:>13.6f} {savings:>16.1f}%")
```

---

## Starter Files

Check `lab/starter/` for:
- Skeleton CostTracker class
- Pricing data JSON
- Budget configuration templates

## Solution Files

If you get stuck, `lab/solution/` contains:
- Complete CostTracker implementation
- Working budget alert system
- Cost comparison scripts

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Not tracking completion tokens separately | Underestimating costs (output tokens cost more) | Always record both prompt and completion counts |
| Using the same model for all tasks | 10-100x overspending on simple tasks | Route by complexity: cheap models for classification, expensive for generation |
| No budget alerts | Surprise bills at end of month | Set daily and per-user limits from day one |
| Ignoring caching opportunities | Paying for identical requests | Cache responses in Redis with TTL |
| Estimating costs from local testing | Production costs are 10-100x higher | Track real production usage, not dev estimates |

---

## Self-Check Questions

1. What is the cost difference between using gpt-4o-mini and gpt-4o for 1 million input tokens?
2. Why do output tokens cost more than input tokens?
3. How would you implement response caching for an LLM endpoint?
4. What is the single most impactful cost optimization for most LLM applications?
5. How would you design a per-user rate limiting system based on cost?

---

## You Know You Have Completed This Module When...

- [ ] Tracked costs across multiple models and endpoints
- [ ] Configured budget alerts and observed them trigger
- [ ] Ran the optimization analysis and understood each recommendation
- [ ] Compared costs across different models for the same workload
- [ ] Validation script passes: `bash modules/07-cost-tracking/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: All costs showing as $0.00**
- Verify the model name matches the pricing table keys exactly (e.g., "gpt-4o" not "GPT-4o")
- Check that prompt_tokens and completion_tokens are not zero

**Issue: Budget alerts not firing**
- Verify your daily_limit_usd is low enough to be exceeded by your test data
- Check that records have timestamps within today's date range

**Issue: Optimization tips showing "No usage data"**
- Make sure you have recorded at least one request before calling `get_optimization_tips()`

---

**Next: [Module 08 - LLM Observability and Tracing -->](../08-observability/)**
