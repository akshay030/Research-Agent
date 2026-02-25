from __future__ import annotations
import re
from fastapi.responses import StreamingResponse
import io
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
import json
import operator
from pathlib import Path
from typing import TypedDict, List, Optional, Literal, Annotated

from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_tavily import TavilySearch
from groq import RateLimitError, APIError
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
app = FastAPI(title="Blog Generator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Task(BaseModel):
    id: int
    title: str
    goal: str= Field(..., description="One sentence describing what the reader should be able to do/understand after this section.")
    bullets: List[str] = Field(
        ...,
        min_length=3,
        max_length=6,
        description="3-6 concrete, non-overlapping subpoints to cover in this section.",
    ) 
    target_words: int = Field(..., description="Target word count for this section.")
    section_type: str = Field(..., description="Use 'common_mistakes' exactly once in the plan.",)
      
    requires_code: Optional[bool] = False
    requires_research: Optional[bool] = False
    requires_citations: Optional[bool] = False 
    
class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer","tutorial","news_roundup","comparison","system_design"]="explainer" 
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]
    
    model_config = ConfigDict(
    extra="forbid",
)

class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str]=None
    snippet: Optional[str]=None
    source: Optional[str]=None
    
class RouterDecision(BaseModel):
    needs_research: bool
    mode:Literal["closed_book","hybrid","open_book"]
    queries: List[str] = Field(default_factory=list)
    
class EvidencePack(BaseModel):
    evidence: List[EvidenceItem]= Field(default_factory=list)
                         

class State(TypedDict):
    topic: str
    mode: str
    needs_research: bool
    queries: List[str]
    evidence: List[EvidenceItem]
    
    plan: Optional[Plan]
    
    sections: Annotated[List[tuple[int, str]], operator.add]
    final: str


llm = ChatGroq(
    model="qwen/qwen3-32b",
    
)

ROUTER_SYSTEM = """You are a routing module for a technical blog planner.

Decide whether web research is needed BEFORE planning.

Modes:
- closed_book (needs_research=false):
  Evergreen topics where correctness does not depend on recent facts (concepts, fundamentals).
- hybrid (needs_research=true):
  Mostly evergreen but needs up-to-date examples/tools/models to be useful.
- open_book (needs_research=true):
  Mostly volatile: weekly roundups, "this week", "latest", rankings, pricing, policy/regulation.

If needs_research=true:
- Output 3–10 high-signal queries.
- Queries should be scoped and specific (avoid generic queries like just "AI" or "LLM").
- If user asked for "last week/this week/latest", reflect that constraint IN THE QUERIES.
"""

def router_node(state: State) -> dict:
    topic = state["topic"]

    raw = llm.invoke(
        [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(
                content=f"""
Topic: {topic}

Return ONLY valid JSON. No markdown. No explanation.
"""
            )
        ]
    ).content.strip()

    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found")

        json_str = match.group(0)
        data = json.loads(json_str)

        # 🔥 Fallback logic for missing mode
        if "mode" not in data:
            if data.get("needs_research"):
                data["mode"] = "hybrid"
            else:
                data["mode"] = "closed_book"

        decision = RouterDecision.model_validate(data)

    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise RuntimeError(
            f"Router validation failed: {e}\n\nRaw output:\n{raw}"
        )

    return {
        "needs_research": decision.needs_research,
        "mode": decision.mode,
        "queries": decision.queries,
    }

    
def route_next(state: State)->str:
    return "research" if state["needs_research"] else "orchestrator"


def _tavily_search(query: str, max_results=5):
    tool = TavilySearch(max_results=max_results, include_raw_content=True)
    results = tool.invoke(query)  # ✅ STRING

    normalized = []
    for r in results:
        if isinstance(r, dict):
            normalized.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "published_at": r.get("published_at"),
                "source": r.get("source"),
            })
    return normalized

RESEARCH_SYSTEM = """You are a research synthesizer for technical writing.

Given raw web search results, produce a deduplicated list of EvidenceItem objects.

Rules:
- Only include items with a non-empty url.
- Prefer relevant + authoritative sources (company blogs, docs, reputable outlets).
- If a published date is explicitly present in the result payload, keep it as YYYY-MM-DD.
  If missing or unclear, set published_at=null. Do NOT guess.
- Keep snippets short.
- Deduplicate by URL.
"""

def research_node(state: State)->dict:
    
    queries = (state.get("queries",[])or [])
    max_results = 6
    raw_results:List[dict] = []
    
    for q in queries:
        raw_results.extend(_tavily_search(q, max_results=max_results))
    if not raw_results:
        return {"evidence": []}
    
    extractor = llm.with_structured_output(EvidencePack)
    pack=extractor.invoke(
        [
            SystemMessage(content=RESEARCH_SYSTEM),
            HumanMessage(content=f"Raw search results: {raw_results}")
        ]
    )
    return {"evidence": pack.evidence}
    

ORCH_SYSTEM = """You are a senior technical writer and developer advocate.
Your job is to produce a highly actionable outline for a technical blog post.

Hard requirements:
- Create 5–9 sections (tasks) suitable for the topic and audience.
- Each task must include:
  1) goal (1 sentence)
  2) 3–6 bullets that are concrete, specific, and non-overlapping
  3) target word count (120–550)

Quality bar:
- Assume the reader is a developer; use correct terminology.
- Bullets must be actionable: build/compare/measure/verify/debug.
- Ensure the overall plan includes at least 2 of these somewhere:
  * minimal code sketch / MWE (set requires_code=True for that section)
  * edge cases / failure modes
  * performance/cost considerations
  * security/privacy considerations (if relevant)
  * debugging/observability tips

Grounding rules:
- Mode closed_book: keep it evergreen; do not depend on evidence.
- Mode hybrid:
  - Use evidence for up-to-date examples (models/tools/releases) in bullets.
  - Mark sections using fresh info as requires_research=True and requires_citations=True.
- Mode open_book:
  - Set blog_kind = "news_roundup".
  - Every section is about summarizing events + implications.
  - DO NOT include tutorial/how-to sections unless user explicitly asked for that.
  - If evidence is empty or insufficient, create a plan that transparently says "insufficient sources"
    and includes only what can be supported.

Output must strictly match the Plan schema.
"""

def orchestrator_node(state: State) -> dict:
    evidence = state.get("evidence", [])
    mode = state.get("mode", "closed_book")

    raw = llm.invoke(
    [
        SystemMessage(content=ORCH_SYSTEM),
        HumanMessage(
    content=(
        f"Topic: {state['topic']}\n"
        f"Mode: {mode}\n\n"
        f"Evidence (Only use for fresh claims; may be empty):\n"
        f"{[e.model_dump() for e in evidence][:16]}\n\n"
        "Return the output as valid JSON matching EXACTLY this structure:\n\n"
        "{\n"
        '  "blog_title": string,\n'
        '  "audience": string,\n'
        '  "tone": string,\n'
        '  "blog_kind": "explainer" | "tutorial" | "news_roundup" | "comparison" | "system_design",\n'
        '  "constraints": string[],\n'
        '  "tasks": [\n'
        "    {\n"
        '      "id": integer,\n'
        '      "title": string,\n'
        '      "goal": string,\n'
        '      "bullets": string[],\n'
        '      "target_words": integer,\n'
        '      "section_type": string,\n'
        '      "requires_code": boolean,\n'
        '      "requires_research": boolean,\n'
        '      "requires_citations": boolean\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Do not include any other keys."
    )
),
    ],
    response_format={"type": "json_object"}  # 🔥 FORCE JSON MODE
).content.strip()

    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found in planner output")

        json_str = match.group(0)
        data = json.loads(json_str)

        # 🔥 Auto-repair bullets to satisfy min/max constraints
        for task in data.get("tasks", []):
            bullets = task.get("bullets", [])

            # Ensure list exists
            if not isinstance(bullets, list):
                task["bullets"] = ["Expand on core implementation details.",
                                "Discuss trade-offs and practical usage.",
                                "Highlight edge cases and performance considerations."]
                continue

            # Pad if too short
            while len(bullets) < 3:
                bullets.append(
                    "Expand on implementation details and practical considerations."
                )

            # Trim if too long
            if len(bullets) > 6:
                task["bullets"] = bullets[:6]

        plan = Plan.model_validate(data)

    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        raise RuntimeError(
            f"Planner validation failed: {e}\n\nRaw output:\n{raw}"
        )

    return {"plan": plan}


def fanout(state: State):
    return [
        Send(
            "worker", 
            {
                "task": task.model_dump(), 
                "topic": state["topic"], 
                "plan": state["plan"].model_dump(),
                "evidence":[e.model_dump() for e in state.get("evidence",[])],
                "mode": state.get("mode", "closed_book"),  # 🔥 ADD THIS

            },
        )
        for task in state["plan"].tasks
    ]


WORKER_SYSTEM = """You are a senior technical writer and developer advocate.
Write ONE section of a technical blog post in Markdown.

Hard constraints:
- Follow the provided Goal and cover ALL Bullets in order (do not skip or merge bullets).
- Stay close to Target words (±15%).
- Output ONLY the section content in Markdown (no blog title H1, no extra commentary).
- Start with a '## <Section Title>' heading.

Scope guard:
- If blog_kind == "news_roundup": do NOT turn this into a tutorial/how-to guide.
  Do NOT teach web scraping, RSS, automation, or "how to fetch news" unless bullets explicitly ask for it.
  Focus on summarizing events and implications.

Grounding policy:
- If mode == open_book:
  - Do NOT introduce any specific event/company/model/funding/policy claim unless it is supported by provided Evidence URLs.
  - For each event claim, attach a source as a Markdown link: ([Source](URL)).
  - Only use URLs provided in Evidence. If not supported, write: "Not found in provided sources."
- If requires_citations == true:
  - For outside-world claims, cite Evidence URLs the same way.
- Evergreen reasoning is OK without citations unless requires_citations is true.

Code:
- If requires_code == true, include at least one minimal, correct code snippet relevant to the bullets.

Style:
- Short paragraphs, bullets where helpful, code fences for code.
- Avoid fluff/marketing. Be precise and implementation-oriented.
"""


def worker_node(payload: dict) -> dict:
    task = Task(**payload["task"])
    plan =Plan(**payload["plan"])
    evidence = [EvidenceItem(**e) for e in payload.get("evidence",[])]
    topic= payload["topic"]
    mode = payload.get("mode","closed_book")
    bullets_text = "\n-" + "\n-".join(task.bullets)
    
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
                    f"Mode: {mode}\n\n"
                    f"Section title: {task.title}\n"
                    f"Goal: {task.goal}\n"
                    f"Target words: {task.target_words}\n"
                    f"requires_research: {task.requires_research}\n"
                    f"requires_citations: {task.requires_citations}\n"
                    f"requires_code: {task.requires_code}\n"
                    f"Bullets:{bullets_text}\n\n"
                    f"Evidence (ONLY use these URLs when citing):\n{evidence_text}\n"
          )
          
        )
          
      ]
    ).content.strip()
    return {"sections": [(task.id, section_md)]}
    


def reducer_node(state: State) -> dict:
    plan = state.get("plan")
    evidence = state.get("evidence", [])
    queries = state.get("queries", [])
    mode = state.get("mode")

    ordered_sections = [
        md for _, md in sorted(state["sections"], key=lambda x: x[0])
    ]

    body = "\n\n".join(ordered_sections).strip()
    final_md = f"# {plan.blog_title}\n\n{body}\n"

    return {
        "final": final_md,
        "plan": plan,
        "evidence": evidence,
        "queries": queries,
        "mode": mode,
    }



g = StateGraph(State)

g.add_node("router", router_node)
g.add_node("research", research_node)
g.add_node("orchestrator", orchestrator_node)
g.add_node("worker", worker_node)
g.add_node("reducer", reducer_node)

g.add_edge(START, "router")

g.add_conditional_edges(
    "router",
    route_next,
    {"research": "research", "orchestrator": "orchestrator"},
)

g.add_edge("research", "orchestrator")

g.add_conditional_edges("orchestrator", fanout, ["worker"])

g.add_edge("worker", "reducer")

# 🔥 IMPORTANT
g.set_finish_point("reducer")

workflow = g.compile()


# =========================
# ===== API ROUTES ========
# =========================

class BlogRequest(BaseModel):
    topic: str


class BlogResponse(BaseModel):
    blog_title: str
    content: str
    plan: Optional[dict] = None
    evidence: Optional[list] = None


@app.post("/generate", response_model=BlogResponse)
def generate_blog(req: BlogRequest):
    try:
        result = workflow.invoke({
            "topic": req.topic,
            "sections": [],
        })

        plan = result.get("plan")
        evidence = result.get("evidence", [])

        return BlogResponse(
            blog_title=plan.blog_title if plan else "Untitled",
            content=result.get("final", ""),
            plan=plan.model_dump() if plan else None,
            evidence=[e.model_dump() for e in evidence] if evidence else [],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@app.post("/generate/download")
def generate_and_download(req: BlogRequest):
    try:
        result = workflow.invoke({
            "topic": req.topic,
            "sections": [],
        })

        plan = result.get("plan")
        content = result.get("final", "")

        if not content:
            raise HTTPException(status_code=500, detail="Blog generation failed")

        filename = (
            plan.blog_title.strip().replace(" ", "_")
            if plan else "generated_blog"
        ) + ".md"

        file_stream = io.BytesIO(content.encode("utf-8"))

        return StreamingResponse(
            file_stream,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))