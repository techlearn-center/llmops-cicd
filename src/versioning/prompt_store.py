"""
Prompt Versioning System
========================
Store, retrieve, compare, and manage prompt versions with full metadata
tracking. Supports git-style versioning with diff capabilities.

Usage:
    store = PromptStore(database_url="postgresql://...")
    version = store.save("summarizer", "Summarize: {text}", tags=["prod"])
    prompt  = store.get("summarizer", version="1.2")
    diff    = store.compare("summarizer", "1.1", "1.2")
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    desc,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()


# ── SQLAlchemy Model ───────────────────────────────────────
class PromptVersionRow(Base):
    """Database row representing a single prompt version."""

    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    version = Column(String(32), nullable=False)
    template = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    variables = Column(Text, default="[]")  # JSON list of template variables
    tags = Column(Text, default="[]")  # JSON list of tags
    author = Column(String(255), default="system")
    description = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_version"),
    )


# ── Pydantic schemas ──────────────────────────────────────
class PromptVersion(BaseModel):
    """Public-facing schema for a prompt version."""

    name: str
    version: str
    template: str
    content_hash: str
    variables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    author: str = "system"
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromptDiff(BaseModel):
    """Result of comparing two prompt versions."""

    name: str
    from_version: str
    to_version: str
    template_changed: bool
    variables_added: list[str] = Field(default_factory=list)
    variables_removed: list[str] = Field(default_factory=list)
    from_template: str = ""
    to_template: str = ""


# ── Core Prompt Store ──────────────────────────────────────
class PromptStore:
    """
    Versioned prompt storage with database backing.

    Features:
    - Semantic versioning (major.minor auto-increment)
    - Content-hash deduplication (skip save if identical)
    - Tag-based retrieval (e.g., "prod", "staging", "experiment-42")
    - Side-by-side diff between any two versions
    - Full history with metadata
    """

    def __init__(self, database_url: str = "sqlite:///prompts.db") -> None:
        self.engine = create_engine(database_url, echo=False)
        Base.metadata.create_all(self.engine)
        self._Session = sessionmaker(bind=self.engine)

    # ── helpers ────────────────────────────────────────────
    @staticmethod
    def _hash(template: str) -> str:
        return hashlib.sha256(template.encode()).hexdigest()

    @staticmethod
    def _extract_variables(template: str) -> list[str]:
        """Pull {variable} names from the template string."""
        import re
        return re.findall(r"\{(\w+)\}", template)

    def _next_version(self, session: Session, name: str, *, bump_major: bool = False) -> str:
        """Auto-increment the version string."""
        latest = (
            session.query(PromptVersionRow)
            .filter_by(name=name)
            .order_by(desc(PromptVersionRow.id))
            .first()
        )
        if latest is None:
            return "1.0"
        major, minor = (int(x) for x in latest.version.split("."))
        if bump_major:
            return f"{major + 1}.0"
        return f"{major}.{minor + 1}"

    def _row_to_schema(self, row: PromptVersionRow) -> PromptVersion:
        return PromptVersion(
            name=row.name,
            version=row.version,
            template=row.template,
            content_hash=row.content_hash,
            variables=json.loads(row.variables),
            tags=json.loads(row.tags),
            author=row.author,
            description=row.description,
            created_at=row.created_at,
        )

    # ── public API ─────────────────────────────────────────
    def save(
        self,
        name: str,
        template: str,
        *,
        tags: list[str] | None = None,
        author: str = "system",
        description: str = "",
        bump_major: bool = False,
    ) -> PromptVersion:
        """
        Save a new prompt version.

        Returns the created PromptVersion. If the template is identical to the
        latest version (same content hash), the save is skipped and the existing
        version is returned instead.
        """
        content_hash = self._hash(template)
        variables = self._extract_variables(template)

        with self._Session() as session:
            # Dedup: skip if content unchanged
            latest = (
                session.query(PromptVersionRow)
                .filter_by(name=name)
                .order_by(desc(PromptVersionRow.id))
                .first()
            )
            if latest and latest.content_hash == content_hash:
                return self._row_to_schema(latest)

            version = self._next_version(session, name, bump_major=bump_major)
            row = PromptVersionRow(
                name=name,
                version=version,
                template=template,
                content_hash=content_hash,
                variables=json.dumps(variables),
                tags=json.dumps(tags or []),
                author=author,
                description=description,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._row_to_schema(row)

    def get(
        self,
        name: str,
        *,
        version: str | None = None,
        tag: str | None = None,
    ) -> Optional[PromptVersion]:
        """
        Retrieve a prompt by name.

        - If *version* is given, return that exact version.
        - If *tag* is given, return the latest version with that tag.
        - Otherwise return the latest version.
        """
        with self._Session() as session:
            query = session.query(PromptVersionRow).filter_by(name=name)

            if version:
                row = query.filter_by(version=version).first()
            elif tag:
                # Filter rows whose JSON tags list contains the tag
                rows = query.order_by(desc(PromptVersionRow.id)).all()
                row = next(
                    (r for r in rows if tag in json.loads(r.tags)),
                    None,
                )
            else:
                row = query.order_by(desc(PromptVersionRow.id)).first()

            return self._row_to_schema(row) if row else None

    def list_versions(self, name: str) -> list[PromptVersion]:
        """Return every version of a prompt, newest first."""
        with self._Session() as session:
            rows = (
                session.query(PromptVersionRow)
                .filter_by(name=name)
                .order_by(desc(PromptVersionRow.id))
                .all()
            )
            return [self._row_to_schema(r) for r in rows]

    def compare(self, name: str, from_version: str, to_version: str) -> PromptDiff:
        """Diff two versions of the same prompt."""
        v_from = self.get(name, version=from_version)
        v_to = self.get(name, version=to_version)
        if not v_from or not v_to:
            raise ValueError(
                f"Cannot compare: missing version(s) for '{name}' "
                f"({from_version} / {to_version})"
            )
        return PromptDiff(
            name=name,
            from_version=from_version,
            to_version=to_version,
            template_changed=v_from.content_hash != v_to.content_hash,
            variables_added=[v for v in v_to.variables if v not in v_from.variables],
            variables_removed=[v for v in v_from.variables if v not in v_to.variables],
            from_template=v_from.template,
            to_template=v_to.template,
        )

    def render(self, name: str, context: dict[str, Any], *, version: str | None = None) -> str:
        """Retrieve a prompt and fill in its template variables."""
        prompt = self.get(name, version=version)
        if not prompt:
            raise ValueError(f"Prompt '{name}' not found")
        return prompt.template.format(**context)

    def delete(self, name: str, version: str) -> bool:
        """Delete a specific prompt version. Returns True if deleted."""
        with self._Session() as session:
            row = (
                session.query(PromptVersionRow)
                .filter_by(name=name, version=version)
                .first()
            )
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True
