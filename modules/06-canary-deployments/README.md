# Module 06: Canary Deployments for LLM Apps

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Intermediate-Advanced |
| **Prerequisites** | Module 05 completed, A/B testing understood |

---

## Learning Objectives

By the end of this module, you will be able to:

- Implement gradual rollout of new LLM model versions with configurable traffic weights
- Build automatic rollback logic based on error rate, latency, and quality thresholds
- Design a ramp-up schedule that balances speed with safety
- Monitor canary health in real time with structured metrics
- Differentiate canary deployments from A/B testing and know when to use each

---

## Concepts

### What is a Canary Deployment?

A canary deployment routes a small percentage of production traffic to a new version while keeping most traffic on the proven baseline. If the canary performs well, traffic is gradually increased until the new version handles 100%. If problems are detected, traffic is instantly rolled back to the baseline.

**Named after:** Coal miners who brought canaries into mines as early warning systems for toxic gases.

### Canary vs. A/B Testing

| | Canary Deployment | A/B Testing |
|---|---|---|
| **Goal** | Safe rollout of new version | Compare two alternatives |
| **Traffic split** | Starts small (5-10%), ramps up | Fixed split (often 50/50) |
| **Duration** | Until promoted or rolled back | Until statistical significance |
| **Decision** | Automated (health-based) | Data-driven (significance test) |
| **Rollback** | Automatic on failure | Manual or post-analysis |
| **Use when** | Deploying new model/prompt to prod | Comparing two prompt variants |

### The Canary Lifecycle

```
  Create         Monitor         Decision
┌────────┐    ┌──────────┐    ┌───────────┐
│  5%    │───▶│  Check   │───▶│  Healthy? │
│ canary │    │  health  │    └─────┬─────┘
└────────┘    └──────────┘          │
                                ┌───┴───┐
                               Yes     No
                                │       │
                            ┌───┴───┐   │
                            │ Ramp  │   │
                            │ to    │   │
                            │ 10%   │   │
                            └───┬───┘   │
                                │       │
                               ...      │
                                │       │
                            ┌───┴───┐   │
                            │ Ramp  │   │
                            │ to    │   │
                            │ 90%   │   │
                            └───┬───┘   │
                                │       │
                            ┌───┴───┐   ▼
                            │Promote│ ┌──────────┐
                            │ 100%  │ │ Rollback │
                            └───────┘ │   0%     │
                                      └──────────┘
```

### Rollback Triggers

The canary manager automatically rolls back when any of these conditions are met:

| Trigger | Default Threshold | What It Catches |
|---|---|---|
| **Error rate** | > 5% | API failures, timeouts, malformed responses |
| **P99 latency** | > 5,000 ms | Performance degradation, model slowness |
| **Quality score** | < 0.70 | Evaluation score drops (accuracy, relevance) |

### Ramp Schedule

A typical ramp schedule for LLM deployments:

| Step | Canary Weight | Wait Time | Min Requests |
|---|---|---|---|
| 1 | 5% | 5 minutes | 50 |
| 2 | 10% | 10 minutes | 100 |
| 3 | 25% | 15 minutes | 250 |
| 4 | 50% | 30 minutes | 500 |
| 5 | 75% | 30 minutes | 750 |
| 6 | 90% | 30 minutes | 900 |
| 7 | 100% (promoted) | - | - |

### Key Terminology

| Term | Definition |
|---|---|
| **Baseline** | The current production version serving most traffic |
| **Canary** | The new version receiving a small percentage of traffic |
| **Ramp-up** | Gradually increasing the canary's traffic percentage |
| **Rollback** | Immediately routing all traffic back to the baseline |
| **Promotion** | Making the canary the new baseline (100% traffic) |
| **Health check** | Automated evaluation of canary metrics against thresholds |
| **Bake time** | Minimum wait period between ramp steps |

---

## Hands-On Lab

### Prerequisites Check

```bash
python3 -c "from src.deployment.canary import CanaryManager; print('Ready')"
```

### Exercise 1: Create and Monitor a Canary Deployment

**Goal:** Deploy a new model version with 10% canary traffic and monitor its health.

```python
from src.deployment.canary import CanaryManager, CanaryConfig

manager = CanaryManager()

# Create deployment: gpt-4o-mini (baseline) -> gpt-4o (canary)
deployment = manager.create_deployment(
    name="model-upgrade-v2",
    baseline_model="gpt-4o-mini",
    canary_model="gpt-4o",
    canary_weight=0.1,  # Start at 10%
    config=CanaryConfig(
        max_error_rate=0.05,
        max_latency_p99_ms=3000,
        min_quality_score=0.75,
        min_requests_before_decision=50,
        weight_increment=0.1,
        ramp_interval_seconds=0,  # Instant ramp for demo
    ),
)

print(f"Created: {deployment.name}")
print(f"Status: {deployment.status.value}")
print(f"Canary weight: {deployment.canary_weight:.0%}")
```

### Exercise 2: Simulate a Successful Rollout

**Goal:** Simulate healthy traffic and watch the canary get promoted.

```python
import random

# Simulate 500 requests with good canary performance
for i in range(500):
    model = manager.route_request("model-upgrade-v2")
    manager.record_outcome(
        "model-upgrade-v2",
        model,
        success=random.random() < 0.98,       # 98% success
        latency_ms=random.gauss(250, 50),      # 250ms avg
        quality_score=random.gauss(0.88, 0.04),  # 0.88 avg quality
    )

    # Check and ramp every 50 requests
    if (i + 1) % 50 == 0:
        decision = manager.maybe_promote_or_rollback("model-upgrade-v2")
        dep = manager.get_deployment("model-upgrade-v2")
        print(f"  Request {i + 1}: weight={dep.canary_weight:.0%}, decision={decision}")

# Final status
print("\n" + manager.get_summary("model-upgrade-v2"))
```

### Exercise 3: Simulate a Rollback

**Goal:** Simulate a failing canary that triggers automatic rollback.

```python
# Create a new deployment
manager.create_deployment(
    name="bad-model-test",
    baseline_model="gpt-4o-mini",
    canary_model="bad-model-v1",
    canary_weight=0.1,
    config=CanaryConfig(
        max_error_rate=0.05,
        min_requests_before_decision=30,
        ramp_interval_seconds=0,
    ),
)

# Simulate traffic with bad canary performance
for i in range(100):
    model = manager.route_request("bad-model-test")
    is_canary = model == "bad-model-v1"

    if is_canary:
        # Canary has high error rate and slow latency
        manager.record_outcome(
            "bad-model-test", model,
            success=random.random() < 0.80,        # Only 80% success (bad!)
            latency_ms=random.gauss(2000, 500),     # Very slow
            quality_score=random.gauss(0.55, 0.1),  # Low quality
        )
    else:
        manager.record_outcome(
            "bad-model-test", model,
            success=random.random() < 0.98,
            latency_ms=random.gauss(200, 30),
            quality_score=random.gauss(0.88, 0.04),
        )

    if (i + 1) % 30 == 0:
        decision = manager.maybe_promote_or_rollback("bad-model-test")
        print(f"  Request {i + 1}: decision={decision}")

print("\n" + manager.get_summary("bad-model-test"))
```

### Exercise 4: Review Deployment History

**Goal:** Inspect the audit trail of canary deployment decisions.

```python
import json

# Check history for both deployments
for name in ["model-upgrade-v2", "bad-model-test"]:
    dep = manager.get_deployment(name)
    print(f"\n--- {name} ({dep.status.value}) ---")
    for event in dep.history:
        print(f"  {event['event']}: {json.dumps({k: v for k, v in event.items() if k != 'event'})}")

# Health check
for name in ["model-upgrade-v2", "bad-model-test"]:
    health = manager.check_health(name)
    print(f"\n{name} health: {'HEALTHY' if health['healthy'] else 'UNHEALTHY'}")
    if health.get("issues"):
        for issue in health["issues"]:
            print(f"  Issue: {issue}")
```

---

## Starter Files

Check `lab/starter/` for:
- Skeleton CanaryManager class to complete
- Configuration templates for different ramp schedules
- Simulation scripts

## Solution Files

If you get stuck, `lab/solution/` contains:
- Fully implemented CanaryManager with all features
- Working simulation for both success and rollback scenarios
- Expected output from each exercise

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Starting canary at too high weight | Large blast radius on failure | Start at 5-10% and ramp gradually |
| No minimum request threshold | Decisions made on insufficient data | Set `min_requests_before_decision` to 50+ |
| Forgetting to monitor baseline | Cannot compare relative performance | Track metrics for both baseline and canary |
| Ramp interval too short | Insufficient observation time | Set bake time to at least 5 minutes between ramps |
| No manual rollback path | Cannot override automation | Always expose a manual rollback endpoint |

---

## Self-Check Questions

1. Why start a canary at 5-10% instead of 50%?
2. What three metrics should trigger an automatic rollback?
3. How does a canary deployment differ from an A/B test in terms of decision-making?
4. What is "bake time" and why is it important?
5. Describe a scenario where the canary is healthy on all metrics but you still should not promote it.

---

## You Know You Have Completed This Module When...

- [ ] Created a canary deployment with configurable thresholds
- [ ] Simulated a successful rollout with gradual ramp-up
- [ ] Triggered and observed an automatic rollback
- [ ] Reviewed the deployment history audit trail
- [ ] Validation script passes: `bash modules/06-canary-deployments/validation/validate.sh`

---

## Troubleshooting

### Common Issues

**Issue: Canary never ramps up**
- Check that `ramp_interval_seconds` has elapsed since the last ramp
- Verify `min_requests_before_decision` is met
- For testing, set `ramp_interval_seconds=0`

**Issue: Rollback not triggering**
- Verify canary metrics exceed the threshold (not baseline metrics)
- Check `min_requests_before_decision` is met before rollback logic runs

**Issue: All traffic going to baseline**
- Check deployment status is `IN_PROGRESS` (not `ROLLED_BACK` or `PROMOTED`)
- Verify `canary_weight` is greater than 0

---

**Next: [Module 07 - Cost Tracking and Optimization -->](../07-cost-tracking/)**
