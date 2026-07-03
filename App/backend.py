from __future__ import annotations
from typing import TypedDict, List, Annotated , Optional , Literal
from pydantic import BaseModel, Field
from langgraph.types import Send
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
from langgraph.graph import StateGraph,START,END
from langchain_google_genai import ChatGoogleGenerativeAI 
from dotenv import load_dotenv
load_dotenv()
import operator
from pathlib import Path
from datetime import date, datetime, timedelta
from uuid import uuid4
from langchain_community.tools.tavily_search import TavilySearchResults

# -----------------------------
# 1) Schemas
# -----------------------------
class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    goal: str = Field(...,description="One sentence describing what the reader should be able to do/understand after this section.")
    bullets: List[str] = Field(...,min_length=3,max_length=6,description="3–6 concrete, non-overlapping subpoints to cover in this section.")
    target_words: int = Field(..., description="Target word count for this section (120–550).")
    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    # NEW: tells workers what genre this is (prevents drift)
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None  # prefer ISO "YYYY-MM-DD"
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)
    max_results_per_query: int = Field(5, description="How many results to fetch per query (3–8).")


class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)

# -----------------------------
# 2) State
# -----------------------------
class State(TypedDict):
    topic: str

    # routing / research
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    plan: Optional[Plan]

    # NEW: recency control
    as_of: str           # ISO date, e.g. "2026-01-29"
    recency_days: int    # 7 for weekly news, 30 for hybrid, etc.

    # workers
    sections: Annotated[List[tuple[int, str]], operator.add]  # (task_id, section_md)
    final: str

#-----------------------------
# 3) LLM
#-----------------------------
llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite", temperature=0.5)


# -----------------------------
# 4) Router (decide upfront)
# -----------------------------
ROUTER_SYSTEM = """
You are the routing module for an AI-powered technical blog generation system.

Your ONLY responsibility is to determine whether external web research is required BEFORE blog planning.

Do NOT create an outline.
Do NOT write the blog.
Do NOT summarize information.

Return only the routing decision.

------------------------------------
Routing Modes
------------------------------------

1. closed_book
Research NOT required.

Use this when the topic is primarily educational, conceptual, or historical.

Examples:
- What is Self Attention
- Python Decorators
- Spark Transformations
- Database Normalization
- Binary Search Trees

Knowledge should come primarily from the model itself.

needs_research = false

------------------------------------

2. hybrid
Research required.

Use when the topic is mostly evergreen but benefits from current examples, recent frameworks, modern tools, updated best practices, or recent developments.

Examples:
- LangGraph tutorial
- Vector Databases
- AI Model Evaluation
- RAG Best Practices
- Databricks Delta Lake

needs_research = true

------------------------------------

3. open_book
Research required.

Use when correctness depends on recent information.

Examples:

- latest
- today
- this week
- this month
- 2026 trends
- rankings
- benchmark comparisons
- pricing
- product releases
- regulations
- AI news
- company announcements

needs_research = true

------------------------------------
Search Query Generation
------------------------------------

If research is required:

Generate between 3 and 8 high-quality search queries.

Each query should:

• be specific
• include the main topic
• include important technologies, models, companies or frameworks when appropriate
• include the year if relevant
• avoid vague terms like "AI", "ML", or "LLM" by themselves
• avoid duplicate intent
• maximize information diversity

Prefer queries that retrieve:

- official documentation
- technical blogs
- research papers
- release notes
- benchmark reports
- engineering articles

For weekly or recent topics, ensure queries explicitly target the requested time period.
"""

def router_node(state: State) -> dict:
    topic = state["topic"]
    decider = llm.with_structured_output(RouterDecision)
    decision = decider.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=f"Topic: {topic}\nAs-of date: {state['as_of']}"),
        ]
    )

    # Set default recency window based on mode
    if decision.mode == "open_book":
        recency_days = 7
    elif decision.mode == "hybrid":
        recency_days = 45
    else:
        recency_days = 3650

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": decision.queries,
        "recency_days": recency_days,
    }

def route_next(state: State) -> str:
    return "research" if state["needs_research"] else "orchestrator"


# -----------------------------
# 5) Research (Tavily)
# -----------------------------
def _tavily_search(query: str, max_results: int = 5) -> List[dict]:
    """
    Uses TavilySearchResults if installed and TAVILY_API_KEY is set.
    Returns list of dict with common fields. Note: published date is often missing.
    """
    tool = TavilySearchResults(max_results=max_results)
    results = tool.invoke({"query": query})

    normalized: List[dict] = []
    for r in results or []:
        normalized.append(
            {
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "snippet": r.get("content") or r.get("snippet") or "",
                "published_at": r.get("published_date") or r.get("published_at"),
                "source": r.get("source"),
            }
        )
    return normalized


def _iso_to_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except Exception:
        return None


RESEARCH_SYSTEM = """You are a research synthesizer for technical blog generation.

Given raw web search results, produce a clean, deduplicated list of EvidenceItem objects.

Rules:
- Include only relevant sources with a valid, non-empty URL.
- Prefer authoritative sources (official documentation, company blogs, research papers, reputable news and engineering blogs).
- Remove duplicate or near-duplicate sources (deduplicate by URL).
- Keep snippets concise (1-2 sentences) while preserving key facts.
- Extract published_at in ISO format (YYYY-MM-DD) only if it can be inferred reliably; otherwise set it to null.
- Ignore advertisements, sponsored pages, forums, and low-quality content.
- Do not invent, modify, or infer facts beyond the provided search results.
"""

def research_node(state: State) -> dict:
    queries = (state.get("queries", []) or [])[:10]
    max_results = 6

    raw_results: List[dict] = []
    for q in queries:
        raw_results.extend(_tavily_search(q, max_results=max_results))

    if not raw_results:
        return {"evidence": []}

    extractor = llm.with_structured_output(EvidencePack)
    pack = extractor.invoke(
        [
            SystemMessage(content=RESEARCH_SYSTEM),
            HumanMessage(
                content=(
                    f"As-of date: {state['as_of']}\n"
                    f"Recency days: {state['recency_days']}\n\n"
                    f"Raw results:\n{raw_results}"
                )
            ),
        ]
    )

    # Deduplicate by URL
    dedup = {}
    for e in pack.evidence:
        if e.url:
            dedup[e.url] = e
    evidence = list(dedup.values())

    # HARD RECENCY FILTER for open_book weekly roundup:
    # keep only items with a parseable ISO date and within the window.
    mode = state.get("mode", "closed_book")
    if mode == "open_book":
        as_of = date.fromisoformat(state["as_of"])
        cutoff = as_of - timedelta(days=int(state["recency_days"]))
        fresh: List[EvidenceItem] = []
        for e in evidence:
            d = _iso_to_date(e.published_at)
            if d and d >= cutoff:
                fresh.append(e)
        evidence = fresh

    return {"evidence": evidence}


# -----------------------------
# 6) Orchestrator (Plan)
# -----------------------------
ORCH_SYSTEM = """You are a senior technical writer and developer advocate.

Your job is to create a comprehensive, well-structured outline for a high-quality technical blog.

Hard requirements:
- Create 5–9 sections (tasks).
- The outline should read like a complete story, not independent topics.
- Include an Introduction as the first section and a Conclusion/Key Takeaways as the final section.
- Ensure each section naturally builds upon the previous one.

Each task must include:
1. goal (1 concise sentence)
2. 3–6 concrete, specific, and non-overlapping bullets
3. target word count (120–550)

Quality requirements:
- Write for software developers and technical professionals.
- Use precise technical terminology.
- Bullets should focus on explanation, comparison, implementation, optimization, debugging, or best practices.
- Avoid duplicate concepts across sections.
- Progress from fundamentals to advanced ideas naturally.

The overall plan should include at least two of the following where appropriate:
- Minimal working code example (requires_code=True)
- Edge cases or common failure modes
- Performance or cost considerations
- Security or privacy considerations
- Debugging or observability tips
- Best practices or practical recommendations

Grounding rules:
- closed_book:
  Keep the outline evergreen and independent of current events.

- hybrid:
  Use research only for recent tools, frameworks, models, releases, or examples.
  Mark such sections as requires_research=True and requires_citations=True.

- open_book:
  Set blog_kind="news_roundup".
  Focus on recent events, their impact, trends, and future implications.
  Do not include tutorial sections unless explicitly requested.
  If evidence is insufficient, clearly indicate that only supported information will be covered.

Output must strictly follow the Plan schema.
"""

def orchestrator_node(state: State) -> dict:
    planner = llm.with_structured_output(Plan)
    evidence = state.get("evidence", [])
    mode = state.get("mode", "closed_book")

    # Force blog_kind for open_book
    forced_kind = "news_roundup" if mode == "open_book" else None

    plan = planner.invoke(
        [
            SystemMessage(content=ORCH_SYSTEM),
            HumanMessage(
                content=(
                    f"Topic: {state['topic']}\n"
                    f"Mode: {mode}\n"
                    f"As-of: {state['as_of']} (recency_days={state['recency_days']})\n"
                    f"{'Force blog_kind=news_roundup' if forced_kind else ''}\n\n"
                    f"Evidence (ONLY use for fresh claims; may be empty):\n"
                    f"{[e.model_dump() for e in evidence][:16]}\n\n"
                    f"Instruction: If mode=open_book, your plan must NOT drift into a tutorial."
                )
            ),
        ]
    )

    # Ensure open_book forces the kind even if model forgets
    if forced_kind:
        plan.blog_kind = "news_roundup"

    return {"plan": plan}


# -----------------------------
# 7) Fanout
# -----------------------------
def fanout(state: State):
    assert state["plan"] is not None
    return [
        Send(
            "worker",
            {
                "task": task.model_dump(),
                "topic": state["topic"],
                "mode": state["mode"],
                "as_of": state["as_of"],
                "recency_days": state["recency_days"],
                "plan": state["plan"].model_dump(),
                "evidence": [e.model_dump() for e in state.get("evidence", [])],
            },
        )
        for task in state["plan"].tasks
    ]


# -----------------------------
# 8) Worker (write one section)
# -----------------------------
WORKER_SYSTEM = """You are a senior technical writer and developer advocate.

Write ONE section of a professional technical blog in Markdown.

Hard constraints:
- Follow the provided Goal and cover ALL Bullets in order (do not skip, merge, or invent new bullets).
- Stay within the Target word count (±15%).
- Output ONLY the section in Markdown.
- Start with '## <Section Title>'.
- Do not generate the blog title or conclusion unless this task explicitly requests it.

Writing style:
- Write like an experienced engineer explaining concepts to fellow developers.
- Keep the tone engaging, practical, and conversational without becoming informal.
- Prefer short paragraphs and use bullet lists where appropriate.
- Explain WHY before HOW whenever possible.
- Use practical examples, analogies, comparisons, or real-world scenarios whenever they improve understanding.
- Avoid repeating concepts that are likely covered in previous sections.
- End the section with a natural transition into the next topic when appropriate.

Grounding:
- If blog_kind == "news_roundup", summarize events and their implications only.
- Do not turn news sections into tutorials unless explicitly requested.

Citation policy:
- If mode == open_book:
    - Every factual claim about recent events must be supported by the provided Evidence.
    - Cite using Markdown links: ([Source](URL)).
    - Never invent sources or facts.
    - If evidence is unavailable, write "Not found in provided sources."

- If requires_citations == true:
    - Cite all external factual claims using the provided Evidence URLs.

- Evergreen explanations may be written without citations unless citations are required.

Code:
- If requires_code == true:
    - Include at least one minimal, correct, and relevant code example.
    - Keep code concise and explain its purpose briefly after the snippet.

Quality:
- Avoid fluff and marketing language.
- Prefer actionable insights over generic descriptions.
- Be technically accurate, implementation-oriented, and easy to follow.
"""

def worker_node(payload: dict) -> dict:

    task = Task(**payload["task"])
    plan = Plan(**payload["plan"])
    evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]
    topic = payload["topic"]
    mode = payload.get("mode", "closed_book")
    as_of = payload.get("as_of")
    recency_days = payload.get("recency_days")

    bullets_text = "\n- " + "\n- ".join(task.bullets)

    # Provide a compact evidence list for citation use
    evidence_text = ""
    if evidence:
        evidence_text = "\n".join(
            f"- {e.title} | {e.url} | {e.published_at or 'date:unknown'}".strip()
            for e in evidence[:20]
        )

    section_md = llm.invoke(
        [
            SystemMessage(content=WORKER_SYSTEM),
            HumanMessage(
                content=(
                    f"Blog title: {plan.blog_title}\n"
                    f"Audience: {plan.audience}\n"
                    f"Tone: {plan.tone}\n"
                    f"Blog kind: {plan.blog_kind}\n"
                    f"Constraints: {plan.constraints}\n"
                    f"Topic: {topic}\n"
                    f"Mode: {mode}\n"
                    f"As-of: {as_of} (recency_days={recency_days})\n\n"
                    f"Section title: {task.title}\n"
                    f"Goal: {task.goal}\n"
                    f"Target words: {task.target_words}\n"
                    f"Tags: {task.tags}\n"
                    f"requires_research: {task.requires_research}\n"
                    f"requires_citations: {task.requires_citations}\n"
                    f"requires_code: {task.requires_code}\n"
                    f"Bullets:{bullets_text}\n\n"
                    f"Evidence (ONLY use these URLs when citing):\n{evidence_text}\n"
                )
            ),
        ]
    ).content.strip()

    # deterministic ordering
    return {"sections": [(task.id, section_md)]}



# -----------------------------
# 9) Reducer (merge + save)
# -----------------------------
from turtle import title


def reducer_node(state: State) -> dict:
    plan = state["plan"]
    if plan is None:
        raise ValueError("Reducer called without a plan.")

    title = state["plan"].blog_title
    ordered_sections = sorted(state["sections"], key=lambda x: x[0])
    body = "\n\n".join(section for _, section in ordered_sections).strip()

    final_md = f"# {title}\n\n{body}\n"
    filename = "".join(c if c.isalnum() or c in (" ", "_", "-") else "" for c in title)
    filename = filename.strip().lower().replace(" ", "_") + ".md"
    Path(filename).write_text(final_md, encoding="utf-8")

    return {"final": final_md}


# -----------------------------
# 10) Build graph
# -----------------------------
g = StateGraph(State)
g.add_node("router", router_node)
g.add_node("research", research_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("reducer", reducer_node)

g.add_edge(START, "router")
g.add_conditional_edges("router", route_next, {"research": "research", "orchestrator": "orchestrator"})
g.add_edge("research", "orchestrator")

g.add_conditional_edges("orchestrator", fanout, ["worker"])
g.add_edge("worker", "reducer")
g.add_edge("reducer", END)

app = g.compile()

# # -----------------------------
# # 11) Helper functions
# # -----------------------------
def create_initial_state(topic: str,as_of: Optional[str] = None,):
    """Creates the initial LangGraph state."""
    if as_of is None:
        as_of = date.today().isoformat()

    return {
        "topic": topic,
        "mode": "",
        "needs_research": False,
        "queries": [],
        "evidence": [],
        "plan": None,
        "as_of": as_of,
        "recency_days": 7,
        "sections": [],
        "final": "",
    }


def run(topic: str,as_of: Optional[str] = None):
    """
    Executes the complete LangGraph workflow and returns the final state.
    """
    initial_state = create_initial_state(
        topic=topic,
        as_of=as_of,
    )
    return app.invoke(initial_state)


def generate_blog(topic: str,as_of: Optional[str] = None):
    """
    Returns only the generated markdown blog.
    """
    result = run(
        topic=topic,
        as_of=as_of,
    )
    return result["final"]




