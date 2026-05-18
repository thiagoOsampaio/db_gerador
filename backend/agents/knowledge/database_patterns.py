"""Universal database design patterns shared by every modeling agent.

The string :data:`DATABASE_DESIGN_PATTERNS` is appended to every agent
system prompt via :func:`build_system_prompt`, which uses LangChain's
``ChatPromptTemplate`` so the same skill bundle can later be reused by
chat-based agents, tool-using agents, or future LangGraph nodes.
"""

from __future__ import annotations

from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    SystemMessagePromptTemplate,
)

# ---------------------------------------------------------------------------
# Universal "skill" knowledge — database design patterns.
# ---------------------------------------------------------------------------
DATABASE_DESIGN_PATTERNS = """\
Universal database design patterns (MUST follow unless the user request
contradicts a specific item, in which case explain why in the rationale):

Naming
- snake_case everywhere; table names plural for entity collections
  (``users``, ``orders``); column names singular (``user_id``).
- Join/association tables named ``<a>_<b>`` in alphabetical order with
  a composite primary key on the two FK columns.

Keys
- Primary key is always ``id UUID`` (v4) unless a natural key is clearly
  better and the rationale documents the choice.
- Foreign keys named ``<referenced_table_singular>_id``.
- Foreign keys: ``ON DELETE RESTRICT`` and ``ON UPDATE CASCADE`` by
  default. Use ``ON DELETE CASCADE`` only for strong-composition
  dependents (e.g. ``order_items`` of an ``order``).

Auditing & temporal columns
- Every table MUST have ``created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()``
  and ``updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()``.
- Use ``deleted_at TIMESTAMPTZ NULL`` for soft-delete when the domain
  needs temporal traceability of removals.
- Datetime with timezone uses ``TIMESTAMPTZ``; pure dates use ``DATE``.

Types
- Monetary values: ``NUMERIC(precision, scale)``. NEVER ``FLOAT``/
  ``DOUBLE`` for money.
- Use precise lengths: ``VARCHAR(n)`` only when ``n`` is intentional;
  otherwise ``TEXT``.
- For low-cardinality enumerations driven by application code prefer
  ``VARCHAR`` + ``CHECK`` over native ``ENUM`` (portability).

Constraints & indexes
- Declarative integrity: ``CHECK`` for simple value domains, ``UNIQUE``
  for natural keys, ``NOT NULL`` for everything that has a default or a
  business meaning.
- Index every foreign key column and every column used routinely in
  ``WHERE``, ``ORDER BY`` or ``JOIN`` clauses.
- Prefer composite/partial indexes when filters combine columns or
  filter on a known subset.

Documentation
- Every table MUST set ``description`` explaining its purpose,
  invariants and main consumers, in Brazilian Portuguese (pt-BR).
"""


# ---------------------------------------------------------------------------
# Reusable prompt builder.
# ---------------------------------------------------------------------------
def build_system_prompt(role_prompt: str) -> str:
    """Compose a system prompt from a per-agent role and shared skills.

    Using LangChain's :class:`ChatPromptTemplate` here keeps the contract
    uniform across agents and makes the prompt easy to inspect/log.

    Parameters
    ----------
    role_prompt:
        The agent-specific role and guidelines.

    Returns
    -------
    str
        The rendered system prompt (role + universal patterns + language
        directive).
    """
    template = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(
                "{role_prompt}\n\n{database_design_patterns}\n\n"
                "Language directive: all narrative fields — descriptions, "
                "notes, rationale, titles — MUST be written in Brazilian "
                "Portuguese (pt-BR). Identifiers (table/column names) stay "
                "in snake_case English unless the user explicitly requests "
                "otherwise."
            )
        ]
    )
    rendered = template.format_messages(
        role_prompt=role_prompt.strip(),
        database_design_patterns=DATABASE_DESIGN_PATTERNS.strip(),
    )
    return str(rendered[0].content)


# ---------------------------------------------------------------------------
# Reusable user-prompt skeleton (kept for agents that opt-in).
# ---------------------------------------------------------------------------
USER_PROMPT_TEMPLATE: HumanMessagePromptTemplate = (
    HumanMessagePromptTemplate.from_template("{payload}")
)
