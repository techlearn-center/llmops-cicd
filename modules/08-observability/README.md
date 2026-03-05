# Module 08: Monitoring LLM Quality (Observability and Tracing)

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Advanced |
| **Prerequisites** | Module 07 completed |

---

## Learning Objectives

By the end of this module, you will be able to:

- Instrument LLM applications with structured logging and metrics collection
- Track latency, error rates, token usage, and user feedback in real time
- Build dashboards and alerts for LLM-specific quality signals
- Implement distributed tracing for multi-step LLM chains (RAG, agents)
- Design an observability strategy that catches quality degradation before users notice

---

## Concepts

### Why LLM Observability is Different

Traditional application monitoring tracks uptime, latency, and error rates. LLM applications need all of that plus quality monitoring, because:

- **An LLM can return a 200 OK with a terrible answer.** HTTP status codes do not tell you if the response was accurate, relevant, or helpful.
- **Quality degrades gradually.** Model updates, prompt drift, and data distribution shifts cause slow quality erosion that latency/error monitors miss entirely.
- **User feedback is sparse and delayed.** Only 5-10% of users provide explicit feedback, and it arrives hours or days after the response.
- **Cost and quality are correlated.** A model that starts generating longer responses costs more and may actually be less helpful.

### The LLM Observability Stack

```
┌─────────────────────────────────────────────────────┐
│                    Dashboards                        │
│  (Grafana / Datadog / custom)                       │
├─────────────────────────────────────────────────────┤
│                     Alerts                           │
│  (PagerDuty / Slack / email)                        │
├──────────┬──────────┬──────────┬───────────────────┤
│  Metrics │  Logs    │  Traces  │  Evaluations      │
│  (Prom)  │ (struct) │  (OTel)  │  (offline eval)   │
├──────────┴──────────┴──────────┴───────────────────┤
│              Instrumentation Layer                   │
│  (middleware, decorators, callbacks)                 │
├─────────────────────────────────────────────────────┤
│              LLM Application                         │
│  (FastAPI + LLM calls + chains)                     │
└─────────────────────────────────────────────────────┘
```

### Metrics to Monitor

#### Request-Level Metrics

| Metric | Type | Why It Matters |
|---|---|---|
| **Request latency** | Histogram | Directly impacts user experience |
| **Time to first token (TTFT)** | Histogram | Perceived responsiveness for streaming |
| **Total tokens** | Counter | Cost tracking and anomaly detection |
| **Error rate** | Gauge | Service reliability |
| **Model version** | Label | Correlate quality changes with deploys |

#### Quality Metrics

| Metric | Type | How to Collect |
|---|---|---|
| **User feedback score** | Gauge | Thumbs up/down, star ratings |
| **Automated eval score** | Gauge | Run eval pipeline on sampled responses |
| **Hallucination rate** | Gauge | Faithfulness evaluator on responses with source docs |
| **Refusal rate** | Counter | Count "I cannot help with that" responses |
| **Output length** | Histogram | Detect over-generation or truncation |

#### System-Level Metrics

| Metric | Type | Why It Matters |
|---|---|---|
| **API rate limit hits** | Counter | Capacity planning |
| **Cache hit ratio** | Gauge | Cost optimization effectiveness |
| **Queue depth** | Gauge | Backpressure and scaling needs |
| **Concurrent requests** | Gauge | Resource utilization |

### Structured Logging for LLMs

Traditional logging is unstructured and hard to query. Use structured (JSON) logging to capture LLM-specific fields:

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "llm_request_completed",
    model="gpt-4o-mini",
    prompt_name="summarizer",
    prompt_version="1.2",
    prompt_tokens=450,
    completion_tokens=120,
    latency_ms=340,
    cost_usd=0.0001,
    user_id="user-42",
    endpoint="/api/summarize",
    status="success",
)
```

This enables queries like:
- "Show me all requests to the summarizer prompt that took > 2 seconds"
- "What is the average cost per request for user-42 this week?"
- "Which prompt version has the highest error rate?"

### Distributed Tracing for LLM Chains

A single user request may trigger multiple LLM calls (RAG retrieval, chain-of-thought, tool use). Distributed tracing connects these into a single trace:

```
Trace: user-request-abc123
├── Span: api_handler (12ms)
│   ├── Span: retrieve_context (45ms)
│   │   ├── Span: embed_query (20ms)
│   │   └── Span: vector_search (25ms)
│   ├── Span: llm_call (890ms)
│   │   ├── model: gpt-4o
│   │   ├── prompt_tokens: 1200
│   │   └── completion_tokens: 350
│   └── Span: post_process (5ms)
└── Total: 952ms
```

### Alert Design

| Alert | Condition | Severity | Action |
|---|---|---|---|
| High error rate | error_rate > 5% for 5 min | Critical | Page on-call, check model status |
| High latency | p99 > 5s for 10 min | Warning | Check rate limits, consider scaling |
| Quality drop | eval_score < 0.6 for 1 hour | Warning | Check recent prompt changes |
| Cost spike | daily_cost > 2x average | Warning | Check for traffic spike or prompt regression |
| Cache miss rate | cache_hit_ratio < 50% | Info | Review cache TTL and key strategy |

### Key Terminology

| Term | Definition |
|---|---|
| **Observability** | Ability to understand system behavior from its outputs (metrics, logs, traces) |
| **Structured logging** | Logging with key-value fields instead of free-text messages |
| **Distributed tracing** | Connecting related operations across services into a single trace |
| **Span** | A single unit of work within a trace (e.g., one LLM call) |
| **OpenTelemetry (OTel)** | Open-source framework for collecting metrics, logs, and traces |
| **SLO** | Service Level Objective - target for reliability (e.g., 99.9% availability) |
| **TTFT** | Time to First Token - how quickly the user sees the first response token |

---

## Hands-On Lab

### Exercise 1: Instrument an LLM Endpoint with Structured Logging

**Goal:** Add structured logging to an LLM API endpoint.

```python
import structlog
import time
from fastapi import FastAPI

app = FastAPI()
logger = structlog.get_logger()

@app.post("/api/summarize")
async def summarize(text: str, user_id: str = "anonymous"):
    start = time.perf_counter()

    # Simulate LLM call
    prompt_tokens = len(text.split())
    completion_tokens = prompt_tokens // 3
    result = f"Summary of: {text[:50]}..."

    latency_ms = (time.perf_counter() - start) * 1000

    # Structured log entry
    logger.info(
        "llm_request",
        endpoint="/api/summarize",
        model="gpt-4o-mini",
        prompt_name="summarizer",
        prompt_version="1.2",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=round(latency_ms, 2),
        user_id=user_id,
        status="success",
    )

    return {"summary": result, "tokens": prompt_tokens + completion_tokens}
```

### Exercise 2: Build a Prometheus Metrics Collector

**Goal:** Export LLM-specific metrics for Prometheus/Grafana dashboards.

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Define metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["model", "endpoint", "status"],
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM request latency in seconds",
    ["model", "endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens processed",
    ["model", "token_type"],  # token_type: prompt or completion
)

llm_cost_usd = Counter(
    "llm_cost_usd_total",
    "Total cost in USD",
    ["model", "endpoint"],
)

llm_quality_score = Gauge(
    "llm_quality_score",
    "Rolling average quality score",
    ["prompt_name"],
)

# Record metrics after each LLM call
def record_llm_metrics(model, endpoint, status, latency, prompt_tokens, completion_tokens, cost):
    llm_requests_total.labels(model=model, endpoint=endpoint, status=status).inc()
    llm_latency_seconds.labels(model=model, endpoint=endpoint).observe(latency)
    llm_tokens_total.labels(model=model, token_type="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(model=model, token_type="completion").inc(completion_tokens)
    llm_cost_usd.labels(model=model, endpoint=endpoint).inc(cost)
```

### Exercise 3: Implement OpenTelemetry Tracing

**Goal:** Add distributed tracing to a multi-step LLM chain.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Setup tracing
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("llmops.tracer")

async def rag_pipeline(query: str):
    """A multi-step RAG pipeline with full tracing."""

    with tracer.start_as_current_span("rag_pipeline") as root_span:
        root_span.set_attribute("query", query[:100])

        # Step 1: Embed the query
        with tracer.start_as_current_span("embed_query") as embed_span:
            # Simulate embedding
            embedding = [0.1] * 1536
            embed_span.set_attribute("model", "text-embedding-3-small")
            embed_span.set_attribute("dimensions", 1536)

        # Step 2: Vector search
        with tracer.start_as_current_span("vector_search") as search_span:
            # Simulate search
            results = ["doc1", "doc2", "doc3"]
            search_span.set_attribute("results_count", len(results))

        # Step 3: LLM generation
        with tracer.start_as_current_span("llm_generation") as llm_span:
            # Simulate LLM call
            response = f"Answer to: {query[:50]}..."
            llm_span.set_attribute("model", "gpt-4o-mini")
            llm_span.set_attribute("prompt_tokens", 800)
            llm_span.set_attribute("completion_tokens", 200)
            llm_span.set_attribute("cost_usd", 0.0002)

        return response
```

### Exercise 4: Design Alerting Rules

**Goal:** Define alerting rules for an LLM application.

```yaml
# alerts.yml - Prometheus alerting rules
groups:
  - name: llm_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(llm_requests_total{status="error"}[5m]) / rate(llm_requests_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "LLM error rate exceeds 5%"

      - alert: HighLatency
        expr: histogram_quantile(0.99, rate(llm_latency_seconds_bucket[5m])) > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "LLM p99 latency exceeds 5 seconds"

      - alert: CostSpike
        expr: increase(llm_cost_usd_total[1h]) > 10
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "LLM cost exceeded $10 in the last hour"

      - alert: QualityDrop
        expr: llm_quality_score < 0.6
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "LLM quality score below 0.6 for over 1 hour"
```

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Only monitoring HTTP status codes | Missing quality degradation | Add quality-specific metrics and evaluators |
| Too many alerts | Alert fatigue, ignoring real issues | Tier alerts: critical for outages, warning for quality |
| No correlation between deploys and metrics | Cannot identify root cause | Tag metrics with prompt version and model |
| Logging PII in traces | Compliance violations | Scrub user data from log fields, hash user IDs |
| Monitoring in aggregate only | Missing per-endpoint issues | Break down metrics by endpoint, model, and prompt |

---

## Self-Check Questions

1. Why is HTTP status code monitoring insufficient for LLM applications?
2. What five metrics would you put on a single-pane LLM dashboard?
3. How does distributed tracing help debug a slow RAG pipeline?
4. What is the difference between a metric, a log, and a trace?
5. How would you detect gradual quality degradation that happens over weeks?

---

## You Know You Have Completed This Module When...

- [ ] Added structured logging to at least one endpoint
- [ ] Defined Prometheus metrics for latency, tokens, cost, and quality
- [ ] Implemented or outlined OpenTelemetry tracing for a multi-step chain
- [ ] Designed at least 3 alerting rules
- [ ] Validation script passes: `bash modules/08-observability/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: "No module named prometheus_client"**
```bash
pip install prometheus-client
```

**Issue: "No module named opentelemetry"**
```bash
pip install opentelemetry-api opentelemetry-sdk
```

**Issue: Traces not showing up**
- Verify the TracerProvider is set before any spans are created
- Check that the exporter is correctly configured (ConsoleSpanExporter for local testing)

---

**Next: [Module 09 - Building the CI/CD Pipeline -->](../09-cicd-pipeline-build/)**
