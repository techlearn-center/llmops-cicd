# Module 01: LLMOps Fundamentals

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Beginner |
| **Prerequisites** | Docker installed, basic Python knowledge, familiarity with REST APIs |

---

## Learning Objectives

By the end of this module, you will be able to:

- Explain how LLM CI/CD differs from traditional ML pipelines and classical software CI/CD
- Identify the unique challenges of deploying and maintaining LLM-powered applications
- Set up a local development environment with Docker, PostgreSQL, and Redis
- Describe the end-to-end lifecycle of a prompt from authoring to production
- Map LLMOps concepts to the tools and workflows used in the rest of this course

---

## Concepts

### What is LLMOps?

LLMOps (Large Language Model Operations) is the set of practices, tools, and workflows for deploying, monitoring, and maintaining LLM-based applications in production. It extends traditional MLOps with concerns that are unique to large language models:

- **Prompts are code.** Unlike traditional ML where the model artifact is the primary deliverable, LLM applications are driven by prompt templates that change frequently and need version control, testing, and review just like source code.
- **Evaluation is subjective.** Classification models have accuracy and F1 scores. LLM outputs require multi-dimensional evaluation: relevance, coherence, toxicity, faithfulness, and domain-specific correctness.
- **Costs scale with usage.** Every API call costs real money. A poorly-optimized prompt or a missing cache can turn a $50/day service into a $5,000/day one overnight.
- **Non-determinism is the norm.** The same prompt can produce different outputs on successive calls. Testing must account for variance rather than expecting exact matches.

**Real-world analogy:** Traditional CI/CD is like a factory assembly line: same inputs, same outputs, predictable quality. LLMOps is like managing a team of expert consultants: each response is unique, quality varies, you need clear evaluation criteria, and you pay per consultation.

### How LLM CI/CD Differs from Traditional ML

| Dimension | Traditional ML CI/CD | LLM CI/CD |
|---|---|---|
| **Primary artifact** | Trained model (.pkl, .pt) | Prompt templates + model config |
| **Training** | Hours/days of GPU compute | No training; prompt engineering |
| **Testing** | Deterministic assertions | Fuzzy matching, LLM-as-judge |
| **Versioning** | Model weights + features | Prompt text + parameters + model version |
| **Cost model** | Fixed infra cost | Pay-per-token, variable |
| **Rollback** | Swap model artifact | Swap prompt version + model routing |
| **Evaluation** | Accuracy, precision, recall | Relevance, coherence, toxicity, faithfulness |
| **Data drift** | Feature distribution shifts | User query distribution shifts |

### The LLMOps Lifecycle

```
 1. Author       2. Version       3. Test          4. Deploy
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │  Write   │──▶│  Store   │──▶│ Evaluate │──▶│  Canary  │
 │  prompt  │   │  in DB   │   │  offline  │   │  deploy  │
 └──────────┘   └──────────┘   └──────────┘   └──────────┘
                                                     │
 8. Iterate      7. Optimize     6. Monitor      5. Serve
 ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
 │  Update  │◀──│  Reduce  │◀──│  Track   │◀──│  Route   │
 │  prompt  │   │  costs   │   │  quality │   │  traffic │
 └──────────┘   └──────────┘   └──────────┘   └──────────┘
```

### Key Terminology

| Term | Definition |
|---|---|
| **Prompt template** | A parameterized string sent to the LLM, e.g., `Summarize this article: {text}` |
| **Prompt version** | A specific revision of a prompt template, identified by a semantic version string |
| **Evaluation metric** | A quantitative measure of output quality (accuracy, relevance, toxicity, etc.) |
| **Canary deployment** | Routing a small percentage of traffic to a new version while monitoring for regressions |
| **Token** | The atomic unit of text processed by an LLM; both input and output tokens cost money |
| **LLM-as-judge** | Using one LLM to evaluate the output of another, with structured scoring criteria |
| **Prompt regression** | When a prompt change degrades output quality on existing test cases |
| **Traffic splitting** | Dividing user requests between multiple model/prompt versions for comparison |

---

## Hands-On Lab

### Prerequisites Check

Before starting, verify your environment:

```bash
# Check Docker is running
docker --version
docker compose version

# Check Python
python3 --version   # Should be 3.11+

# Check you have the project cloned
ls modules/01-llmops-fundamentals/
```

### Exercise 1: Set Up the LLMOps Development Environment

**Goal:** Get the Docker-based development stack running locally.

**Step 1:** Copy the environment configuration

```bash
# From the repo root
cp .env.example .env

# Edit .env and add your OpenAI API key (optional for Module 01)
# OPENAI_API_KEY=sk-your-key-here
```

**Step 2:** Start the infrastructure services

```bash
docker compose up -d postgres redis
```

**Step 3:** Verify the services are healthy

```bash
# PostgreSQL
docker compose exec postgres pg_isready -U llmops
# Expected: /var/run/postgresql:5432 - accepting connections

# Redis
docker compose exec redis redis-cli ping
# Expected: PONG
```

**What you should see:** Both services report healthy status. PostgreSQL accepts connections and Redis responds with PONG.

### Exercise 2: Explore the Prompt Store

**Goal:** Understand how prompts are versioned by interacting with the prompt store directly.

**Step 1:** Open a Python shell and create your first versioned prompt

```python
from src.versioning.prompt_store import PromptStore

store = PromptStore()

# Save version 1.0
v1 = store.save(
    "summarizer",
    "Summarize the following text in one paragraph:\n\n{text}",
    author="your-name",
    description="Initial summarizer prompt",
    tags=["dev"],
)
print(f"Created: {v1.name} v{v1.version}")
```

**Step 2:** Create a second version and compare

```python
# Save version 1.1 with an improved template
v2 = store.save(
    "summarizer",
    "You are a professional editor. Summarize the following text in exactly "
    "3 bullet points, focusing on the key takeaways:\n\n{text}",
    author="your-name",
    description="Switched to bullet-point format",
    tags=["dev", "experiment"],
)
print(f"Created: {v2.name} v{v2.version}")

# Compare the two versions
diff = store.compare("summarizer", "1.0", "1.1")
print(f"Template changed: {diff.template_changed}")
print(f"Variables added: {diff.variables_added}")
print(f"Variables removed: {diff.variables_removed}")
```

**Step 3:** List all versions

```python
versions = store.list_versions("summarizer")
for v in versions:
    print(f"  v{v.version} by {v.author} - {v.description} (tags: {v.tags})")
```

### Exercise 3: Run a Basic Evaluation

**Goal:** Execute the evaluation pipeline in offline mode to understand how prompt testing works.

```python
import asyncio
from src.evaluation.eval_pipeline import EvalPipeline, TestCase

pipeline = EvalPipeline()  # No API key = offline mock mode

cases = [
    TestCase(
        input_text="AI is transforming healthcare with faster diagnostics.",
        expected_output="AI improves healthcare through faster diagnostics.",
    ),
    TestCase(
        input_text="Explain the benefits of renewable energy.",
        expected_output="Renewable energy reduces emissions and is sustainable.",
    ),
]

report = asyncio.run(
    pipeline.run_evaluation(
        prompt_name="summarizer",
        test_cases=cases,
        metrics=["accuracy", "relevance", "toxicity"],
    )
)
print(EvalPipeline.generate_report(report))
```

---

## Starter Files

Check `lab/starter/` for:
- Environment configuration template
- Python script skeletons for the exercises above
- Docker Compose override for development

## Solution Files

If you get stuck, `lab/solution/` contains:
- Complete working scripts for all three exercises
- Expected output examples
- Notes on common variations

> **Important:** Try to complete the exercises yourself first! Looking at solutions too early reduces learning.

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Forgetting to start Docker services | Connection refused errors | Run `docker compose up -d postgres redis` |
| Using Python 3.9 or earlier | Import errors with `list[str]` syntax | Upgrade to Python 3.11+ |
| Not copying `.env.example` to `.env` | Missing environment variables | Run `cp .env.example .env` |
| Trying to run evaluation with API key in offline mode | Mock outputs instead of real ones | This is expected for Module 01; real API calls come later |

---

## Self-Check Questions

Test your understanding before moving on:

1. Name three ways LLM CI/CD differs from traditional software CI/CD.
2. Why do prompts need version control if they are just text strings?
3. What is a prompt regression and why is it harder to detect than a software bug?
4. What are the main cost drivers in an LLM application?
5. Explain the LLMOps lifecycle in your own words. Which stage is most error-prone and why?

---

## You Know You Have Completed This Module When...

- [ ] Docker services (PostgreSQL + Redis) are running locally
- [ ] You can create, retrieve, and compare prompt versions using the PromptStore
- [ ] You have run the evaluation pipeline in offline mode and can read the report
- [ ] Validation script passes: `bash modules/01-llmops-fundamentals/validation/validate.sh`
- [ ] You can explain how LLMOps differs from traditional MLOps to a colleague

---

## Troubleshooting

### Common Issues

**Issue: Docker Compose version mismatch**
```bash
# If you see errors about "version" in docker-compose.yml
docker compose version  # Must be v2+
# If using older Docker, install Docker Compose V2
```

**Issue: Port 5432 already in use**
```bash
# Find and stop the conflicting service
lsof -i :5432
# Or change the port in docker-compose.yml
```

**Issue: Python import errors**
```bash
# Make sure you are running from the repo root
cd llmops-cicd
python -c "from src.versioning.prompt_store import PromptStore; print('OK')"
```

---

**Next: [Module 02 - Prompt Versioning and Management -->](../02-prompt-versioning/)**
