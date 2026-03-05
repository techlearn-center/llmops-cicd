# Module 10: Production LLMOps Architecture

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Advanced |
| **Prerequisites** | All modules 01-09 completed |

---

## Learning Objectives

By the end of this module, you will be able to:

- Design an end-to-end production LLMOps architecture that integrates all components
- Implement the complete flow from prompt authoring to production deployment
- Build resilience patterns: circuit breakers, retries, fallback models
- Architect for scale with connection pooling, rate limiting, and horizontal scaling
- Create runbooks for common operational scenarios (model outage, cost spike, quality drop)

---

## Concepts

### The Complete LLMOps Architecture

This module ties everything together. Here is the full architecture:

```
┌──────────────────────────────────────────────────────────────────┐
│                         DEVELOPMENT                               │
│                                                                   │
│  Engineer ──▶ Write Prompt ──▶ Git Commit ──▶ Pull Request        │
│                                                    │              │
│                                              ┌─────┴─────┐       │
│                                              │  CI/CD    │       │
│                                              │ Pipeline  │       │
│                                              │ (Mod 09)  │       │
│                                              └─────┬─────┘       │
│                                                    │              │
│                    ┌───────────────┬────────────────┤              │
│                    ▼               ▼                ▼              │
│              ┌──────────┐  ┌──────────────┐  ┌──────────┐        │
│              │   Lint   │  │  Eval Gate   │  │  Docker  │        │
│              │ (Mod 09) │  │  (Mod 03)    │  │  Build   │        │
│              └──────────┘  └──────────────┘  └──────────┘        │
└──────────────────────────────────────────────────────────────────┘
                                    │
                              All gates pass
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                        DEPLOYMENT                                 │
│                                                                   │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────┐      │
│  │ Prompt Store │───▶│ Canary Deploy │───▶│ Health Monitor  │     │
│  │  (Mod 02)   │    │  (Mod 06)    │    │  (Mod 08)       │     │
│  └─────────────┘    └──────────────┘    └────────┬────────┘     │
│                                                   │              │
│                                        ┌──────────┴──────────┐   │
│                                       Pass              Fail    │
│                                        │                  │      │
│                                   ┌────┴─────┐    ┌──────┴───┐  │
│                                   │ Promote  │    │ Rollback │  │
│                                   │  100%    │    │  to 0%   │  │
│                                   └──────────┘    └──────────┘  │
└──────────────────────────────────────────────────────────────────┘
                                    │
┌──────────────────────────────────────────────────────────────────┐
│                       PRODUCTION                                  │
│                                                                   │
│  ┌────────┐    ┌──────────────┐    ┌──────────────┐              │
│  │ Users  │───▶│  API Gateway │───▶│  LLM Service │              │
│  └────────┘    │  + Rate Limit│    │  + Caching   │              │
│                └──────────────┘    └──────┬───────┘              │
│                                           │                      │
│              ┌────────────────────────────┬┴──────────────┐      │
│              ▼                            ▼                ▼      │
│       ┌──────────────┐         ┌──────────────┐   ┌──────────┐  │
│       │ Cost Tracker │         │  Quality     │   │  Alerts  │  │
│       │  (Mod 07)    │         │  Monitor     │   │ (Mod 08) │  │
│       └──────────────┘         │  (Mod 08)    │   └──────────┘  │
│                                └──────────────┘                  │
│                                       │                          │
│                                  ┌────┴────┐                     │
│                                  │ A/B Test│                     │
│                                  │ (Mod 05)│                     │
│                                  └─────────┘                     │
└──────────────────────────────────────────────────────────────────┘
```

### Resilience Patterns

#### Circuit Breaker
When the LLM provider experiences an outage, stop sending requests and serve a fallback response:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, CircuitBreaker

class LLMCircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = "closed"  # closed = normal, open = failing, half-open = testing
        self.last_failure_time = None

    def call(self, func, *args, **kwargs):
        if self.state == "open":
            if self._should_attempt_recovery():
                self.state = "half-open"
            else:
                return self._fallback(*args, **kwargs)

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            if self.state == "open":
                return self._fallback(*args, **kwargs)
            raise

    def _fallback(self, *args, **kwargs):
        return "Service temporarily unavailable. Please try again shortly."
```

#### Retry with Exponential Backoff

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def call_llm_with_retry(prompt: str, model: str):
    # Retries up to 3 times with 1s, 2s, 4s waits
    return await openai_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
```

#### Fallback Model Chain
If the primary model fails, fall back to a cheaper/faster alternative:

```python
MODEL_CHAIN = ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]

async def call_with_fallback(prompt: str):
    for model in MODEL_CHAIN:
        try:
            return await call_llm(prompt, model)
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}, trying next")
    raise Exception("All models failed")
```

### Scaling Patterns

#### Connection Pooling
Reuse HTTP connections to the LLM provider:

```python
from httpx import AsyncClient

# Create a single client with connection pooling
llm_client = AsyncClient(
    base_url="https://api.openai.com/v1",
    headers={"Authorization": f"Bearer {api_key}"},
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    timeout=30.0,
)
```

#### Rate Limiting
Protect against traffic spikes and stay within provider limits:

```python
from fastapi import Request
import redis

async def rate_limit_middleware(request: Request):
    user_id = request.headers.get("X-User-ID", "anonymous")
    key = f"rate_limit:{user_id}:{int(time.time()) // 60}"
    count = redis_client.incr(key)
    redis_client.expire(key, 120)
    if count > 60:  # 60 requests per minute
        raise HTTPException(429, "Rate limit exceeded")
```

#### Horizontal Scaling
Scale the application layer independently from the LLM provider:

```yaml
# docker-compose.prod.yml
services:
  app:
    deploy:
      replicas: 3
    environment:
      - REDIS_URL=redis://redis:6379

  nginx:
    image: nginx:alpine
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    ports:
      - "80:80"
    depends_on:
      - app
```

### Operational Runbooks

#### Runbook: Model Provider Outage
```
1. Detection: Error rate alert fires (>5% for 5 min)
2. Verify: Check provider status page (status.openai.com)
3. Mitigate: Circuit breaker should auto-engage fallback
4. Monitor: Watch error rate and fallback usage metrics
5. Recover: Circuit breaker auto-recovers when provider returns
6. Post-mortem: Document incident, review circuit breaker settings
```

#### Runbook: Cost Spike
```
1. Detection: Cost alert fires (daily spend > 2x average)
2. Investigate: Check cost tracker for top endpoints and users
3. Identify: Is it traffic spike, prompt regression, or abuse?
4. Mitigate:
   - Traffic spike: Scale up, enable rate limiting
   - Prompt regression: Rollback to previous prompt version
   - Abuse: Block offending user, tighten per-user limits
5. Resolve: Fix root cause, update budget alerts
```

#### Runbook: Quality Degradation
```
1. Detection: Quality score drops below 0.6 for >1 hour
2. Investigate: Check recent prompt/model changes (deployment history)
3. Correlate: Was there a new deployment? Model update? Traffic shift?
4. Mitigate:
   - Bad prompt: Rollback to previous version
   - Model regression: Switch to alternative model
   - Data drift: Update test cases, retune prompts
5. Verify: Run evaluation pipeline, confirm scores recover
```

### Key Terminology

| Term | Definition |
|---|---|
| **Circuit breaker** | Pattern that stops calling a failing service and serves fallback responses |
| **Fallback chain** | Ordered list of models to try if the primary fails |
| **Connection pooling** | Reusing HTTP connections to reduce overhead |
| **Rate limiting** | Restricting the number of requests per user/time period |
| **Horizontal scaling** | Adding more application instances behind a load balancer |
| **Runbook** | Step-by-step guide for handling specific operational incidents |
| **SLO** | Service Level Objective: target reliability/performance commitment |
| **Error budget** | Allowed downtime/errors before violating the SLO |

---

## Hands-On Lab

### Exercise 1: Build the Full Pipeline End-to-End

**Goal:** Connect prompt versioning, evaluation, canary deployment, and cost tracking in a single flow.

```python
import asyncio
from src.versioning.prompt_store import PromptStore
from src.evaluation.eval_pipeline import EvalPipeline, TestCase
from src.deployment.canary import CanaryManager, CanaryConfig
from src.tracking.cost_tracker import CostTracker
import random

# Step 1: Version a new prompt
store = PromptStore()
new_version = store.save(
    "production-summarizer",
    "You are a professional editor. Provide a clear, concise summary "
    "of the following text in 2-3 sentences:\n\n{text}",
    author="engineer",
    description="Production v2 - improved clarity",
    tags=["staging"],
)
print(f"1. Saved prompt v{new_version.version}")

# Step 2: Evaluate the prompt
pipeline = EvalPipeline()
test_cases = [
    TestCase(
        input_text="AI is transforming healthcare with faster, more accurate diagnostics.",
        expected_output="AI improves healthcare through faster and more accurate diagnostics.",
    ),
    TestCase(
        input_text="Renewable energy adoption is accelerating globally.",
        expected_output="Global renewable energy adoption is increasing rapidly.",
    ),
]

report = asyncio.run(pipeline.run_evaluation(
    prompt_name="production-summarizer",
    prompt_version=new_version.version,
    test_cases=test_cases,
    metrics=["accuracy", "relevance", "toxicity"],
))
print(f"2. Evaluation: {report.status.value} (accuracy={report.avg_scores.get('accuracy', 0):.2%})")

# Step 3: Deploy as canary
manager = CanaryManager()
deployment = manager.create_deployment(
    name="summarizer-prod-deploy",
    baseline_model="gpt-4o-mini",
    canary_model="gpt-4o",
    canary_weight=0.1,
    config=CanaryConfig(min_requests_before_decision=30, ramp_interval_seconds=0),
)
print(f"3. Canary deployment created: {deployment.canary_weight:.0%} traffic")

# Step 4: Simulate production traffic with cost tracking
tracker = CostTracker()
for i in range(100):
    model = manager.route_request("summarizer-prod-deploy")
    success = random.random() < 0.97
    latency = random.gauss(250, 40)
    prompt_tokens = random.randint(200, 800)
    completion_tokens = random.randint(50, 200)

    manager.record_outcome(
        "summarizer-prod-deploy", model,
        success=success, latency_ms=latency,
        quality_score=random.gauss(0.85, 0.05),
    )
    tracker.record(model, prompt_tokens, completion_tokens, endpoint="/api/summarize")

# Step 5: Check health and decide
decision = manager.maybe_promote_or_rollback("summarizer-prod-deploy")
cost_report = tracker.get_report("all")
print(f"4. Canary decision: {decision}")
print(f"5. Total cost: ${cost_report.total_cost_usd:.4f} ({cost_report.total_requests} requests)")
```

### Exercise 2: Implement Circuit Breaker with Fallback

**Goal:** Build a circuit breaker that falls back to a cheaper model.

```python
import time

class SimpleCircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = "closed"
        self.opened_at = None

    def execute(self, func, fallback_func, *args, **kwargs):
        if self.state == "open":
            if time.time() - self.opened_at > self.recovery_timeout:
                self.state = "half-open"
            else:
                print(f"  Circuit OPEN: using fallback")
                return fallback_func(*args, **kwargs)

        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
                print(f"  Circuit recovered: back to CLOSED")
            return result
        except Exception as e:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = "open"
                self.opened_at = time.time()
                print(f"  Circuit OPENED after {self.failures} failures")
            return fallback_func(*args, **kwargs)


# Simulate usage
cb = SimpleCircuitBreaker(failure_threshold=3, recovery_timeout=5)

def primary_model(text):
    if random.random() < 0.7:  # 70% failure rate (simulating outage)
        raise Exception("Model unavailable")
    return f"[gpt-4o] Summary: {text[:30]}..."

def fallback_model(text):
    return f"[gpt-4o-mini] Summary: {text[:30]}..."

for i in range(15):
    result = cb.execute(primary_model, fallback_model, "Sample text for summarization")
    print(f"  Request {i + 1}: {result} (state={cb.state})")
    time.sleep(0.5)
```

### Exercise 3: Design Your Production Architecture

**Goal:** Create an architecture document for a production LLMOps system.

Document the following:
1. Which modules' components are used at each stage
2. Infrastructure requirements (Docker services, databases, caches)
3. Monitoring and alerting configuration
4. Scaling strategy (when to add replicas, rate limits)
5. Disaster recovery plan (what if OpenAI goes down for 4 hours?)

### Exercise 4: Production Readiness Checklist

**Goal:** Validate that your system meets production standards.

```python
checklist = {
    "Prompt versioning": "PromptStore with database backing",
    "Evaluation pipeline": "Automated scoring with regression detection",
    "Testing framework": "pytest + deepeval with tiered execution",
    "A/B testing": "Hash-based routing with statistical significance",
    "Canary deployments": "Gradual rollout with auto-rollback",
    "Cost tracking": "Per-model, per-endpoint, per-user with alerts",
    "Observability": "Structured logging + metrics + tracing",
    "CI/CD pipeline": "GitHub Actions with quality gates",
    "Resilience": "Circuit breaker + retry + fallback chain",
    "Security": "Secrets management, rate limiting, input validation",
}

print("Production Readiness Checklist:")
for item, description in checklist.items():
    print(f"  [x] {item}: {description}")
```

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| No fallback model | Complete outage when primary model fails | Implement fallback chain with cheaper models |
| No rate limiting | Single user can exhaust budget | Add per-user and global rate limits |
| Testing only happy paths | Failures in production reveal bugs | Test error handling, timeouts, and edge cases |
| No runbooks | Slow incident response, repeated mistakes | Document procedures for common scenarios |
| Monolithic deployment | Cannot scale or update components independently | Separate prompt store, API, and evaluation services |

---

## Self-Check Questions

1. Draw the complete flow from prompt authoring to production serving.
2. What is a circuit breaker and when does it engage?
3. How would you handle a scenario where OpenAI is down for 2 hours?
4. What are the three runbooks every LLMOps team needs?
5. How do you decide between horizontal scaling and model downgrading during a traffic spike?

---

## You Know You Have Completed This Module When...

- [ ] Connected all components in an end-to-end pipeline
- [ ] Implemented circuit breaker with fallback model chain
- [ ] Documented production architecture with all module components
- [ ] Completed the production readiness checklist
- [ ] Validation script passes: `bash modules/10-production-llmops/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: Components not connecting**
- Verify all `__init__.py` files exist in `src/` subdirectories
- Run `python -c "from src.versioning.prompt_store import PromptStore"` to test imports

**Issue: Database conflicts between modules**
- Each PromptStore instance can use a different database URL
- Use SQLite for local development, PostgreSQL for Docker/production

**Issue: Canary not ramping**
- Set `ramp_interval_seconds=0` for testing
- Verify `min_requests_before_decision` threshold is met

---

**Next: [Capstone Project -->](../../capstone/)**
