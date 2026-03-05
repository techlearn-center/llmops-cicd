# Module 02: Prompt Versioning and Management

| | |
|---|---|
| **Time** | 3-5 hours |
| **Difficulty** | Beginner-Intermediate |
| **Prerequisites** | Module 01 completed, PostgreSQL and Redis running |

---

## Learning Objectives

By the end of this module, you will be able to:

- Design a prompt versioning schema with semantic versioning, content hashing, and metadata
- Implement both git-based and database-backed prompt storage strategies
- Build an A/B comparison workflow that diffs two prompt versions side-by-side
- Tag and retrieve prompt versions by environment (dev, staging, prod)
- Integrate prompt versioning into a team workflow with review and approval gates

---

## Concepts

### Why Version Prompts?

In traditional software, code changes go through version control, code review, and CI before reaching production. Prompt changes deserve the same rigor because:

1. **A single word change can break output quality.** Changing "concise" to "brief" in a summarization prompt can shift output length by 40%.
2. **Rollback needs to be instant.** If a new prompt degrades user experience, you need to revert to the previous version within seconds, not minutes.
3. **Audit trails matter.** Compliance and debugging require knowing exactly which prompt version generated each output.
4. **Team collaboration.** Multiple engineers editing prompts without version control leads to conflicts and lost work.

### Storage Strategies

#### Git-Based Versioning

Store prompts as files in your repository:

```
prompts/
  summarizer/
    v1.0.txt      # "Summarize: {text}"
    v1.1.txt      # "Summarize in bullets: {text}"
    v2.0.txt      # Complete rewrite
    metadata.json  # tags, author, created_at per version
```

**Pros:** Free, works with existing code review tools, integrates with CI/CD naturally.
**Cons:** Tight coupling to deploy cycles, harder to do runtime version switching.

#### Database-Backed Versioning

Store prompts in PostgreSQL with full metadata:

```sql
CREATE TABLE prompt_versions (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(255) NOT NULL,
    version       VARCHAR(32)  NOT NULL,
    template      TEXT         NOT NULL,
    content_hash  VARCHAR(64)  NOT NULL,
    variables     JSONB        DEFAULT '[]',
    tags          JSONB        DEFAULT '[]',
    author        VARCHAR(255) DEFAULT 'system',
    description   TEXT         DEFAULT '',
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE(name, version)
);
```

**Pros:** Runtime switching, rich queries, decoupled from deploys.
**Cons:** Extra infrastructure, need migration tooling.

#### Hybrid Approach (Recommended)

Use git for prompt development and review. On merge to `main`, a CI step pushes the prompt to the database so the running application can retrieve it at runtime.

### Semantic Versioning for Prompts

```
MAJOR.MINOR

MAJOR bump: Breaking change to output format, variable names, or behavior
MINOR bump: Refinements that maintain the same output structure
```

Examples:
- `1.0` -> `1.1`: Tweaked wording for clarity (minor)
- `1.5` -> `2.0`: Changed from paragraph to bullet points (major - output format changed)
- `2.0` -> `2.1`: Added "be concise" instruction (minor)

### Content Hash Deduplication

Every prompt template is SHA-256 hashed before storage. If you try to save the same template text twice, the store recognizes the duplicate and returns the existing version instead of creating a new one. This prevents version clutter from accidental re-saves.

### Key Terminology

| Term | Definition |
|---|---|
| **Prompt template** | A parameterized string with `{variable}` placeholders |
| **Content hash** | SHA-256 digest of the template text, used for deduplication |
| **Semantic version** | `MAJOR.MINOR` format tracking breaking vs. non-breaking changes |
| **Tag** | A label like `prod`, `staging`, `experiment-42` attached to a version |
| **Prompt diff** | A comparison showing what changed between two versions |
| **Render** | Filling template variables with actual values to produce the final prompt |

---

## Hands-On Lab

### Prerequisites Check

```bash
# Verify services from Module 01
docker compose exec postgres pg_isready -U llmops
docker compose exec redis redis-cli ping

# Verify Python imports
python3 -c "from src.versioning.prompt_store import PromptStore; print('Ready')"
```

### Exercise 1: Build a Prompt Library

**Goal:** Create a library of versioned prompts for different tasks.

```python
from src.versioning.prompt_store import PromptStore

store = PromptStore("postgresql://llmops:llmops_secret@localhost:5432/llmops_db")

# --- Summarizer prompt family ---
store.save(
    "summarizer",
    "Summarize the following text in one paragraph:\n\n{text}",
    author="engineer-a",
    description="Basic single-paragraph summarizer",
    tags=["prod", "v1"],
)

store.save(
    "summarizer",
    "You are a professional editor. Summarize the following text in "
    "3 concise bullet points:\n\n{text}",
    author="engineer-a",
    description="Bullet-point format for dashboards",
    tags=["staging"],
)

store.save(
    "summarizer",
    "You are a professional editor. Summarize the following text in "
    "3 concise bullet points. Each bullet must be under 20 words:\n\n{text}",
    author="engineer-b",
    description="Added word limit per bullet",
    tags=["staging", "experiment"],
)

# --- Classifier prompt family ---
store.save(
    "classifier",
    "Classify the following support ticket into one of these categories: "
    "billing, technical, account, other.\n\nTicket: {ticket}\n\nCategory:",
    author="engineer-a",
    description="Support ticket classifier v1",
    tags=["prod"],
)

# List everything
for name in ["summarizer", "classifier"]:
    versions = store.list_versions(name)
    print(f"\n{name} ({len(versions)} versions):")
    for v in versions:
        print(f"  v{v.version} [{', '.join(v.tags)}] - {v.description}")
```

### Exercise 2: Compare and Diff Versions

**Goal:** Build a side-by-side comparison workflow.

```python
# Compare summarizer v1.0 vs v1.1
diff = store.compare("summarizer", "1.0", "1.1")
print(f"Template changed: {diff.template_changed}")
print(f"Variables added:   {diff.variables_added}")
print(f"Variables removed:  {diff.variables_removed}")
print(f"\n--- v{diff.from_version} ---")
print(diff.from_template)
print(f"\n--- v{diff.to_version} ---")
print(diff.to_template)

# Compare v1.1 vs v1.2 (added word limit)
diff2 = store.compare("summarizer", "1.1", "1.2")
print(f"\nv1.1 -> v1.2 changed: {diff2.template_changed}")
```

### Exercise 3: Tag-Based Retrieval and Rendering

**Goal:** Retrieve prompts by tag and render them with actual data.

```python
# Get the current production version
prod_prompt = store.get("summarizer", tag="prod")
print(f"Production: v{prod_prompt.version}")

# Get the latest staging version
staging_prompt = store.get("summarizer", tag="staging")
print(f"Staging: v{staging_prompt.version}")

# Render with actual data
article = (
    "Artificial intelligence is rapidly changing the healthcare industry. "
    "New diagnostic tools powered by deep learning can detect diseases earlier "
    "than traditional methods, potentially saving millions of lives each year."
)

rendered = store.render("summarizer", {"text": article}, version="1.0")
print(f"\nRendered prompt:\n{rendered}")
```

### Exercise 4: Build a Git-Based Prompt Workflow

**Goal:** Store prompts as files and auto-sync to the database on commit.

```bash
# Create prompt files
mkdir -p prompts/summarizer
```

```python
# prompts/summarizer/v1.0.txt
"""Summarize the following text in one paragraph:

{text}"""

# prompts/sync_to_db.py - Run this in CI after merging to main
import os
import glob
from src.versioning.prompt_store import PromptStore

store = PromptStore(os.environ["DATABASE_URL"])

for prompt_dir in glob.glob("prompts/*/"):
    name = os.path.basename(prompt_dir.rstrip("/"))
    for filepath in sorted(glob.glob(f"{prompt_dir}*.txt")):
        version = os.path.basename(filepath).replace(".txt", "").lstrip("v")
        with open(filepath) as f:
            template = f.read().strip()
        store.save(name, template, description=f"Synced from git ({filepath})")
        print(f"Synced {name} v{version}")
```

---

## Starter Files

Check `lab/starter/` for:
- Skeleton `PromptStore` class to complete
- SQL migration scripts for the prompt_versions table
- Sample prompt templates in `prompts/`

## Solution Files

If you get stuck, `lab/solution/` contains:
- Fully implemented PromptStore with all methods
- Working sync script for git-to-database workflow
- Expected output from each exercise

> **Important:** Try to complete the exercises yourself first! Looking at solutions too early reduces learning.

---

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Saving identical templates | No new version created | This is correct behavior -- content hash deduplication prevents duplicates |
| Forgetting `{variable}` syntax | `KeyError` on render | Use `{text}` not `{{text}}` or `$text` |
| Not bumping major version on format changes | Downstream consumers break | Bump major when output structure changes |
| Hardcoding database URL | Works locally, fails in CI | Use `DATABASE_URL` environment variable |

---

## Self-Check Questions

1. Why is content-hash deduplication important for prompt versioning?
2. When should you bump the major version vs. the minor version?
3. What are the trade-offs between git-based and database-backed prompt storage?
4. How would you implement a prompt approval workflow in a team of 5 engineers?
5. What happens if two team members save different prompts at the same time?

---

## You Know You Have Completed This Module When...

- [ ] Created at least 3 versioned prompts in the prompt store
- [ ] Compared two versions and understood the diff output
- [ ] Retrieved a prompt by tag and rendered it with variables
- [ ] Validation script passes: `bash modules/02-prompt-versioning/validation/validate.sh`
- [ ] You can explain the hybrid git + database approach to a colleague

---

## Troubleshooting

### Common Issues

**Issue: PostgreSQL connection refused**
```bash
# Verify the container is running
docker compose ps postgres
# Restart if needed
docker compose restart postgres
```

**Issue: "relation prompt_versions does not exist"**
```python
# The PromptStore auto-creates tables on init.
# Make sure you are passing the correct database URL.
store = PromptStore("postgresql://llmops:llmops_secret@localhost:5432/llmops_db")
```

**Issue: Version not incrementing**
```python
# Content hash dedup: if the template text is identical to the last version,
# no new version is created. Change the template to get a new version.
```

---

**Next: [Module 03 - Evaluation Pipeline Design -->](../03-eval-pipeline-design/)**
