# Capstone Project: Production LLMOps Platform

## Overview

This capstone project combines everything you learned across all 10 modules into a single, production-grade LLMOps platform. You will build a complete system that versions prompts, evaluates quality, deploys with canary routing, tracks costs, and monitors health -- all orchestrated through a CI/CD pipeline. This is the project you will showcase to hiring managers.

## The Challenge

Build a production-ready LLMOps platform for a hypothetical company that serves AI-powered customer support through multiple LLM-backed endpoints (summarization, classification, and chat). Your platform must handle:

- Multiple prompt families with version history
- Automated quality gates that block bad deployments
- Gradual rollout of new models/prompts with automatic rollback
- Real-time cost tracking with budget alerts
- End-to-end observability from request to response

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  CI/CD Pipeline (GitHub Actions)                              │
│  ┌────────┐ ┌────────┐ ┌──────────┐ ┌────────┐ ┌─────────┐ │
│  │  Lint  │▶│  Test  │▶│ Eval Gate│▶│ Docker │▶│  Deploy │ │
│  └────────┘ └────────┘ └──────────┘ └────────┘ └─────────┘ │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Application Layer                                            │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐ │
│  │ Prompt Store  │  │ Canary Router │  │ Cost Tracker     │ │
│  │ (PostgreSQL)  │  │ (Redis flags) │  │ (per-request)    │ │
│  └───────────────┘  └───────────────┘  └──────────────────┘ │
│                                                               │
│  ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐ │
│  │ /summarize    │  │ /classify     │  │ /chat            │ │
│  │  endpoint     │  │  endpoint     │  │  endpoint        │ │
│  └───────────────┘  └───────────────┘  └──────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                              │
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure                                               │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ PostgreSQL │  │   Redis    │  │ Prometheus + Grafana   │ │
│  └────────────┘  └────────────┘  └────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

## Requirements

### Must Have

- [ ] **Prompt Versioning** (Module 02): At least 3 prompt families (summarizer, classifier, chat), each with 2+ versions stored in the PromptStore
- [ ] **Evaluation Pipeline** (Module 03): Test suite with 5+ test cases per prompt family. Regression detection against baseline scores
- [ ] **Automated Testing** (Module 04): pytest test suite that runs in CI. At least 10 passing tests covering all core modules
- [ ] **A/B Testing** (Module 05): Hash-based traffic routing between two prompt variants with metrics collection
- [ ] **Canary Deployment** (Module 06): Gradual rollout configuration with auto-rollback on error rate > 5% or quality score < 0.7
- [ ] **Cost Tracking** (Module 07): Per-model, per-endpoint cost tracking with budget alerts. Model cost comparison report
- [ ] **Observability** (Module 08): Structured logging on all endpoints. At least 3 Prometheus metrics defined. Alert rules for error rate, latency, and cost
- [ ] **CI/CD Pipeline** (Module 09): GitHub Actions workflow that runs lint, test, and evaluation stages. Quality gate that blocks on regression
- [ ] **Production Patterns** (Module 10): Circuit breaker with fallback model chain. Rate limiting configuration. Operational runbook for at least one scenario
- [ ] **Docker** (All): `docker compose up` starts the full platform (app + PostgreSQL + Redis)

### Nice to Have

- [ ] Interactive dashboard showing cost and quality metrics
- [ ] Webhook notifications for deployment events (Slack, Discord)
- [ ] Pre-computed cost projections based on traffic forecasts
- [ ] Custom evaluation metric for domain-specific quality
- [ ] Load testing results with p50/p95/p99 latency numbers

## Getting Started

```bash
# 1. Review the requirements
cat capstone/requirements.md

# 2. Set up your environment
cp .env.example .env
# Edit .env with your API key (optional for offline mode)

# 3. Start infrastructure
docker compose up -d postgres redis

# 4. Run the platform
python -m uvicorn src.main:app --reload

# 5. Run tests
pytest tests/ -v

# 6. When done, validate your work
bash capstone/validation/validate.sh
```

## Evaluation Criteria

| Criteria | Weight | Description |
|---|---|---|
| **Functionality** | 25% | All components work together end-to-end |
| **Architecture** | 20% | Clean separation of concerns, modular design |
| **Testing** | 20% | Comprehensive test suite, evaluation pipeline, regression detection |
| **Resilience** | 15% | Error handling, fallbacks, circuit breakers |
| **Observability** | 10% | Logging, metrics, alerting, cost tracking |
| **Documentation** | 10% | Architecture decisions documented, runbooks written |

## Deliverables

1. **Working platform**: `docker compose up` starts everything
2. **Test suite**: `pytest tests/ -v` passes all tests
3. **CI/CD pipeline**: `.github/workflows/llm-ci.yml` runs on push
4. **Architecture document**: Explains design decisions and trade-offs
5. **Runbook**: At least one operational runbook (e.g., model outage response)
6. **Cost report**: Model cost comparison for a simulated workload

## Implementation Guide

### Phase 1: Foundation (2-3 hours)
1. Set up the prompt store with 3 prompt families
2. Create the evaluation test suite
3. Implement cost tracking for all endpoints
4. Write smoke tests for every module

### Phase 2: Deployment (1-2 hours)
1. Configure canary deployment for one prompt family
2. Implement A/B testing for prompt variant comparison
3. Add circuit breaker with fallback model chain
4. Set up structured logging on all endpoints

### Phase 3: Operations (1-2 hours)
1. Define Prometheus metrics and alert rules
2. Write operational runbook for model outage
3. Configure budget alerts and per-user limits
4. Run the full pipeline end-to-end and capture results

## Solution

The `solution/` directory contains a reference implementation. Try to complete the capstone yourself first -- that is what builds real skills and interview confidence.

## Showcasing to Hiring Managers

When you complete this capstone:

1. **Fork this repo** to your personal GitHub
2. **Add your solution** with clear, descriptive commit messages
3. **Update the README** with your architecture diagram and design decisions
4. **Record a 5-minute demo video** walking through the platform (optional but impressive)
5. **Reference it on your resume** as "Production LLMOps CI/CD Platform"
6. **Be ready to discuss** design trade-offs, cost optimization strategies, and failure scenarios in interviews

### Interview Talking Points

- "I built a prompt versioning system with content-hash deduplication and semantic versioning"
- "The evaluation pipeline runs multi-metric assessment with automatic regression detection"
- "Canary deployments use health-based auto-rollback with configurable error rate and latency thresholds"
- "Cost tracking identifies optimization opportunities: model selection, caching, prompt efficiency"
- "The CI/CD pipeline has tiered testing -- offline on every commit, online for release gates"

See [docs/portfolio-guide.md](../docs/portfolio-guide.md) for more guidance.
