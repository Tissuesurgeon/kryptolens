"""ConversationAgent clarifies the user message. It does not call CMC, rank, or write workflows."""

from __future__ import annotations

import json
import re

from apps.intelligence.clarified_task import ClarifiedTask, TaskScope, TaskTrigger, TurnResult
from apps.intelligence.compiler import _SYMBOL_ALIASES
from apps.intelligence.compiler import (
    _extract_json,
    _extract_symbols,
    is_gainers_ask,
    is_losers_ask,
    is_now_status,
)
from apps.intelligence.job import JobDefinition
from apps.intelligence.job_compiler import (
    _is_compare_now,
    _is_reaction_watch,
    _is_scheduled_brief,
    is_news_request,
)
from apps.intelligence.llm import get_provider
from apps.intelligence.understanding import provider_is_llm

TURN_SYSTEM = """You clarify a crypto-market request for KryptoLens.
Return ONLY valid JSON. No markdown. No tools. No file edits. Do not invent prices.

Reason about: user objective, asset/entity, metric, threshold, timeframe, universe,
persistence, frequency, output format, constraints, and missing information.

Ask a question only when missing information would change the job, the data, the
execution, or the output. Write that question from the user's task. Do not use a
canned phrase.

Do not ask when the request is already a live snapshot, a comparison, news, or a
watch with a stated threshold.

Prefer the current user message over any current job JSON. If the user names ETH
and the current job is about BTC, the new task is about ETH.

{
  "status": "needs_input" | "ready",
  "question": "only if needs_input, generated from the missing information",
  "pending_field": "unusual_definition" | "action" | "",
  "mode": "ask" | "work",
  "task_type": "one_shot_research" | "persistent_monitor" | "scheduled_brief" | "watch_plus_investigate" | "news_brief",
  "objective": "one sentence",
  "assets": ["ETH"],
  "universe": "top_100" | "symbols" | "",
  "window": "30d" | "",
  "listing_limit": 100,
  "trigger_conditions": [{"metric": "price_change_24h", "operator": "<=", "value": -2, "asset": "ETH"}],
  "action": "report" | "notify" | "investigate_market_reaction" | "rank_gains" | "rank_declines" | "market_summary",
  "requested_output": "natural_language_report" | "ranked_table" | "comparison" | "market_summary",
  "you_asked": ["the user's wording"],
  "assumptions": ["only real interpretation, never invented thresholds"],
  "capabilities": ["market"]
}

Rules:
- "Compare BTC and ETH over the last 30 days." → ready, mode=ask, historical+market.
- "Compare BTC and ETH right now." → ready, mode=ask, one-shot, no routine.
- "How is BTC doing?" / "what is ETH doing right now" / "how is AR doing?" → ready, mode=ask. Use the named ticker, including tickers other than BTC and ETH. Never substitute BTC for a ticker the user named.
- "Find me the coins with the highest gains within 24hrs." → ready, mode=ask, universe=top_100, action=rank_gains, requested_output=ranked_table. Not a BTC quote.
- "Watch BTC for unusual activity." → needs_input. Ask what unusual means for this task.
- "Watch BTC and tell me when something important happens." → needs_input.
- "When BTC drops by 2%, check the top 100..." → ready, mode=work, watch_plus_investigate immediately.
- "When ETH drops by 2%, rank the top 100 declines." → ready, mode=work, trigger asset ETH, not BTC.
- "When BTC drops by 2%, find me the coins with the highest drop." → ready, mode=work, watch_plus_investigate. Rank declines.
- "What can you do?" / "help" / "who are you" is not a market task. Do not invent an asset or a BTC quote.
- "ETH vs SOL this week" / "over the past 14 days" / "last 30 days" → set window (this week = 7d, this month = 30d, last or past N days = Nd) and capabilities historical and market.
- "worst 10" / "best 30" / "top 20" → set listing_limit to that number. Declines use rank_declines. Gains use rank_gains. assets stays empty.
- "how is the whole market" / "show fear and greed" → ready, action=market_summary, assets=[], universe=top_100, capabilities market and regime. Not a BTC quote.
- "can you short ETH" / "buy me some SOL" → needs_input. The question says this analyst does not place trades and can quote, rank, or watch. Do not research how to open a position.
- "thanks" / "ok" / "forget it" → needs_input. assets=[]. The question acknowledges them and asks what to look up. Do not mark it ready.
- News/headlines → ready, mode=ask, news_brief.
- Every morning summarize → ready, mode=work, scheduled_brief.
- Never call CMC. Never invent a percent the user did not state. A ready task must name an asset, a ranking, a market summary, or news. Otherwise status is needs_input.
"""

MERGE_SYSTEM = """You merge a user's clarification answer into a pending KryptoLens task.
Return ONLY valid JSON using the same schema as a conversation turn.
You receive the original task, the clarification question, the user's answer, and recent conversation.
Reinterpret the combined context. Prefer status=ready when the answer supplies the missing information.
Write any follow-up question from the remaining gap. Do not invent prices or thresholds the user did not state.
"""

UNUSUAL_QUESTION = (
    "What should count as a significant move — a price drop, a volume spike, "
    "a move versus the rest of the market, or a combination?"
)
ACTION_QUESTION = "When that happens, should I notify you or investigate how the market reacted?"
WATCH_STEMS = ("watch ", "watch", "alert", "notify me", "tell me when", "when something")
UNUSUAL_STEMS = ("unusual", "important", "significant", "something happens", "something important")
WINDOW_RE = re.compile(r"\b(?:last|past)\s+(\d+)\s*(d|day|days|h|hour|hours|m|min|minutes)\b", re.I)
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def understand(
    text: str,
    *,
    history: list[dict] | None = None,
    current_job: JobDefinition | None = None,
    pending: dict | None = None,
    provider=None,
    research_context=None,
) -> TurnResult:
    text = (text or "").strip()
    provider = provider or get_provider()
    if pending:
        return _merge_answer(text, pending, current_job=current_job, provider=provider, history=history)
    if provider_is_llm(provider):
        try:
            return _understand_llm(
                text,
                history=history,
                current_job=current_job,
                provider=provider,
                research_context=research_context,
            )
        except Exception:
            return _ask(text, "I couldn't read that message. Send it again.", pending_field="subject")
    if research_context is not None:
        from apps.intelligence.research.context import resolve_follow_up

        followed = resolve_follow_up(text, research_context)
        if followed is not None:
            return followed
    return _understand_heuristic(text, current_job=current_job)


class ConversationAgent:
    @staticmethod
    def understand(text: str, **kwargs) -> TurnResult:
        return understand(text, **kwargs)


def _understand_llm(text: str, *, history, current_job, provider, research_context=None) -> TurnResult:
    prompt = (
        "Read the user message first. Decide what they are asking, which asset or universe it is about, "
        "and what data would answer it. Do not replace their subject with a different coin. "
        "If a research context is attached, treat a short follow-up as a change to that research. "
        "Treat a new question as a new request.\n\n"
        "User message:\n"
        + text
        + "\n\n"
        + TURN_SYSTEM
    )
    if research_context is not None and getattr(research_context, "current_task", None):
        prompt += "\n\nCurrent research context:\n" + json.dumps(
            {
                "current_task": research_context.current_task,
                "active_entities": list(research_context.active_entities or []),
                "timeframe": research_context.timeframe,
            },
            default=str,
        )[:4000]
    if current_job:
        prompt += "\n\nCurrent job JSON:\n" + current_job.model_dump_json()
    if history:
        prompt += "\n\nRecent conversation:\n" + json.dumps(history[-8:], default=str)[:4000]
    raw = provider.generate(prompt, kind="conversation_turn")
    data = _extract_json(raw)
    task = _task_from_llm(text, data)
    status = data.get("status") or task.status or "ready"
    if status == "needs_input":
        question = (data.get("question") or task.question or "").strip()
        if not question:
            raise ValueError("LLM asked for input without a question")
        task.status = "needs_input"
        task.question = question
        task.pending_field = data.get("pending_field") or task.pending_field or "unusual_definition"
        return TurnResult(status="needs_input", question=question, task=task)
    if _nothing_to_fetch(task):
        question = (data.get("question") or task.objective or "").strip()
        if not question:
            raise ValueError("LLM returned a ready task with nothing to look up")
        task.status = "needs_input"
        task.question = question
        return TurnResult(status="needs_input", question=question, task=task)
    task.status = "ready"
    return TurnResult(status="ready", task=task)


def _nothing_to_fetch(task: ClarifiedTask) -> bool:
    if task.scope.assets or task.scope.universe:
        return False
    if task.action in {"rank_gains", "rank_declines", "market_summary"}:
        return False
    if task.task_type in {"news_brief", "scheduled_brief", "watch_plus_investigate"}:
        return False
    if task.trigger.conditions:
        return False
    return True


def _task_from_llm(text: str, data: dict) -> ClarifiedTask:
    mentioned = _extract_symbols(text)
    llm_assets = [str(item).upper() for item in (data.get("assets") or []) if item]
    if llm_assets and mentioned and not (set(mentioned) & set(llm_assets)):
        assets = list(mentioned)
    elif llm_assets:
        assets = llm_assets
    else:
        assets = list(mentioned)
    capabilities = list(data.get("capabilities") or _default_capabilities(data.get("task_type") or "", data.get("window") or ""))
    conditions = list(data.get("trigger_conditions") or [])
    for item in conditions:
        if isinstance(item, dict) and not item.get("asset") and assets:
            item["asset"] = assets[0]
    return ClarifiedTask(
        status="ready",
        mode=data.get("mode") or "ask",
        task_type=data.get("task_type") or "one_shot_research",
        objective=data.get("objective") or text.strip(),
        scope=TaskScope(
            assets=assets,
            universe=data.get("universe") or "",
            window=data.get("window") or "",
            listing_limit=data.get("listing_limit"),
        ),
        trigger=TaskTrigger(conditions=conditions),
        action=data.get("action") or "report",
        requested_output=data.get("requested_output") or data.get("output_format") or "natural_language_report",
        you_asked=list(data.get("you_asked") or [text.strip()]),
        assumptions=list(data.get("assumptions") or []),
        capabilities=capabilities,
        source_text=text,
        pending_field=data.get("pending_field") or "",
        question=data.get("question") or "",
    )


def _understand_heuristic(text: str, *, current_job: JobDefinition | None = None) -> TurnResult:
    lowered = text.lower()
    assets = _correction_assets(text) or _extract_symbols(text)
    window = _window(text)
    if _is_trade_request(lowered):
        question = "I do not place trades. I can quote a coin, rank the market, or watch a condition."
        return _ask(text, question, pending_field="trade")
    if _is_acknowledgement(lowered):
        question = "Okay. Ask for a quote, a ranking, or a condition to watch."
        return _ask(text, question, pending_field="acknowledgement")
    if is_news_request(text):
        return _ready(
            text,
            mode="ask",
            task_type="news_brief",
            assets=assets or ["BTC"],
            action="report",
            capabilities=["market"],
            objective="Relate CoinMarketCap headlines to live quotes.",
        )
    if _is_market_wide(lowered) and not assets:
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=[],
            universe="top_100",
            listing_limit=100,
            action="market_summary",
            capabilities=["market", "regime"],
            objective="Summarize the live crypto market from CoinMarketCap.",
        )
    if "fear" in lowered and "greed" in lowered:
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=[],
            universe="top_100",
            listing_limit=100,
            action="market_summary",
            capabilities=["regime", "market"],
            objective="Read the Fear and Greed reading and the live market context.",
        )
    if _is_scheduled_brief(lowered) or ("morning" in lowered and "brief" in lowered):
        return _ready(
            text,
            mode="work",
            task_type="scheduled_brief",
            assets=assets,
            universe="top_100",
            listing_limit=100,
            action="report",
            capabilities=["market", "regime"],
            objective="Summarize overnight crypto using live CMC listings.",
        )
    if _is_reaction_watch(lowered) or (_has_threshold(text) and _has_universe(lowered) and _has_rank(lowered)):
        asset = assets[0] if assets else "BTC"
        trigger = _price_trigger(text, asset)
        return _ready(
            text,
            mode="work",
            task_type="watch_plus_investigate",
            assets=[asset],
            universe="top_100",
            listing_limit=_listing_limit(text),
            action="investigate_market_reaction",
            capabilities=["reaction", "market", "anomaly"],
            objective="Monitor the trigger and analyze how the market reacts.",
            requested_output="ranked_table",
            trigger_conditions=[trigger],
            assumptions=[f"Trigger is {asset} 24h change {trigger['operator']} {trigger['value']}%."],
        )
    if window and assets:
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=assets[:4],
            window=window,
            action="report",
            capabilities=["historical", "market"],
            objective=f"Compare {' and '.join(assets[:4])} across {window} from CoinMarketCap observations.",
            assumptions=["comparable observations, not a prediction."],
        )
    if is_now_status(text) or _is_plain_status(lowered):
        if not assets:
            question = "Which coin should I quote?"
            return _ask(text, question, pending_field="subject")
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=assets,
            action="report",
            capabilities=["market"],
            objective=f"Report how {' and '.join(assets)} is doing from live CMC quotes.",
            assumptions=[f"Interpreted named asset as {', '.join(assets)}."] if assets else [],
        )
    if _is_compare_now(lowered) or len(assets) >= 2:
        caps = ["historical", "market"] if window else ["market"]
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=assets[:4] or ["BTC", "ETH"],
            window=window,
            action="report",
            capabilities=caps,
            objective=f"Compare {' and '.join(assets[:4] or ['BTC', 'ETH'])} from live CMC quotes.",
            assumptions=["comparable observations, not a prediction."] if window else [],
        )
    if is_gainers_ask(text) or is_losers_ask(text):
        gains = is_gainers_ask(text)
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=[],
            universe="top_100",
            listing_limit=_listing_limit(text),
            action="rank_gains" if gains else "rank_declines",
            capabilities=["market", "discovery"],
            objective=f"Rank top listings by 24h {'gain' if gains else 'decline'} from live CMC data.",
            requested_output="ranked_table",
        )
    if _is_discovery(lowered):
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=assets,
            universe="top_100",
            action="report",
            capabilities=["discovery", "market"],
            objective="Flag assets with unusual attention, volume, and rank together.",
        )
    if _needs_unusual_question(lowered) and not _has_threshold(text):
        asset = assets[0] if assets else "BTC"
        question = UNUSUAL_QUESTION.replace("move", f"{asset} move")
        task = ClarifiedTask(
            status="needs_input",
            mode="work",
            task_type="persistent_monitor",
            objective=text.strip(),
            scope=TaskScope(assets=assets, universe="symbols"),
            action="report" if "tell me" in lowered or "notify" in lowered else "",
            you_asked=[text.strip()],
            question=question,
            pending_field="unusual_definition",
            source_text=text,
            capabilities=["anomaly", "market"],
        )
        return TurnResult(status="needs_input", question=question, task=task)
    if current_job and current_job.is_persistent() and is_now_status(text):
        return _ready(
            text,
            mode="ask",
            task_type="one_shot_research",
            assets=assets,
            action="report",
            capabilities=["market"],
            objective=f"Report how {' and '.join(assets)} is doing from live CMC quotes.",
        )
    if _looks_like_watch(lowered) and _has_threshold(text):
        action = (
            "investigate_market_reaction"
            if any(word in lowered for word in ("investigat", "check", "find me", "highest drop", "rank"))
            else "notify"
        )
        return _ready(
            text,
            mode="work",
            task_type="watch_plus_investigate" if action == "investigate_market_reaction" else "persistent_monitor",
            assets=assets,
            action=action,
            capabilities=["anomaly", "market", "reaction"] if action == "investigate_market_reaction" else ["anomaly", "market"],
            objective=text.strip(),
            trigger_conditions=[_price_trigger(text, assets[0] if assets else "BTC")],
        )
    if "keep an eye on" in lowered and assets and not _has_threshold(text):
        question = f"What change in {assets[0]} should I watch for?"
        return _ask(text, question, pending_field="unusual_definition", assets=assets)
    if _is_keep_watching(lowered):
        question = "Tell me which research to keep watching, or name the coin and the condition."
        task = ClarifiedTask(
            status="needs_input",
            mode="ask",
            objective=text.strip(),
            you_asked=[text.strip()],
            question=question,
            pending_field="follow_up",
            source_text=text,
        )
        return TurnResult(status="needs_input", question=question, task=task)
    if _is_volume_question(lowered) and not _extract_symbols(text):
        question = (
            "I rank listings by 24h price change. "
            "Ask for the biggest gainers or the biggest declines, or name one coin."
        )
        task = ClarifiedTask(
            status="needs_input",
            mode="ask",
            objective=text.strip(),
            scope=TaskScope(universe="top_100", listing_limit=_listing_limit(text)),
            you_asked=[text.strip()],
            question=question,
            pending_field="ranking",
            source_text=text,
            capabilities=["market", "discovery"],
        )
        return TurnResult(status="needs_input", question=question, task=task)
    if not assets:
        question = "What should I research? Name an asset, a ranking, or a condition to watch."
        task = ClarifiedTask(
            status="needs_input",
            mode="ask",
            objective=text.strip(),
            you_asked=[text.strip()] if text.strip() else [],
            question=question,
            pending_field="subject",
            source_text=text,
            capabilities=["market"],
        )
        return TurnResult(status="needs_input", question=question, task=task)
    return _ready(
        text,
        mode="ask",
        task_type="one_shot_research",
        assets=assets,
        action="report",
        capabilities=["market"],
        objective=text.strip() or "Report live CoinMarketCap quotes.",
    )


def _merge_answer(
    text: str,
    pending: dict,
    current_job: JobDefinition | None = None,
    provider=None,
    history: list[dict] | None = None,
) -> TurnResult:
    provider = provider or get_provider()
    if provider_is_llm(provider):
        try:
            return _merge_answer_llm(text, pending, current_job=current_job, provider=provider, history=history)
        except Exception:
            return _ask(text, "I couldn't read that answer. Send the missing detail again.", pending_field="subject")
    return _merge_answer_heuristic(text, pending, current_job=current_job)


def _merge_answer_llm(text: str, pending: dict, *, current_job, provider, history) -> TurnResult:
    draft = ClarifiedTask.model_validate(pending.get("task") or pending)
    prompt = MERGE_SYSTEM
    prompt += "\n\nOriginal task JSON:\n" + draft.model_dump_json()
    prompt += "\n\nClarification question:\n" + (draft.question or pending.get("pending_field") or "")
    prompt += "\n\nUser answer:\n" + text
    if current_job:
        prompt += "\n\nCurrent job JSON:\n" + current_job.model_dump_json()
    if history:
        prompt += "\n\nRecent conversation:\n" + json.dumps(history[-8:], default=str)[:4000]
    raw = provider.generate(prompt, kind="conversation_merge")
    data = _extract_json(raw)
    source = (draft.source_text + " " + text).strip()
    task = _task_from_llm(source, data)
    task.you_asked = list(dict.fromkeys(list(draft.you_asked) + list(task.you_asked) + [text.strip()]))
    task.source_text = source
    status = data.get("status") or task.status or "ready"
    if status == "needs_input":
        question = (data.get("question") or task.question or "").strip()
        if not question:
            raise ValueError("LLM merge asked for input without a question")
        task.status = "needs_input"
        task.question = question
        task.pending_field = data.get("pending_field") or task.pending_field or draft.pending_field
        return TurnResult(status="needs_input", question=question, task=task)
    if not task.trigger.conditions and draft.trigger.conditions:
        task.trigger = draft.trigger
    if task.mode == "work" and not task.capabilities:
        task.capabilities = list(draft.capabilities) or ["anomaly", "market"]
    task.status = "ready"
    task.question = ""
    task.pending_field = ""
    return TurnResult(status="ready", task=task)


def _merge_answer_heuristic(text: str, pending: dict, current_job: JobDefinition | None = None) -> TurnResult:
    draft = ClarifiedTask.model_validate(pending.get("task") or pending)
    field = pending.get("pending_field") or draft.pending_field or "unusual_definition"
    lowered = text.lower()
    if field == "unusual_definition":
        conditions = _parse_unusual(text, draft.scope.assets[0] if draft.scope.assets else "BTC")
        if not conditions:
            question = UNUSUAL_QUESTION
            draft.question = question
            draft.pending_field = "unusual_definition"
            draft.you_asked = list(draft.you_asked) + [text.strip()]
            return TurnResult(status="needs_input", question=question, task=draft)
        draft.trigger = TaskTrigger(conditions=conditions)
        draft.you_asked = list(draft.you_asked) + [text.strip()]
        source = (draft.source_text or "").lower()
        if draft.action in {"notify", "report", "investigate_market_reaction"} and (
            "tell me" in source or "notify" in source or "investigat" in source
        ):
            draft.action = draft.action or ("notify" if "tell me" in source or "notify" in source else "investigate_market_reaction")
            return _finish_work(draft, text)
        if any(word in lowered for word in ("notify", "tell me", "alert")):
            draft.action = "notify"
            return _finish_work(draft, text)
        if "investigat" in lowered:
            draft.action = "investigate_market_reaction"
            return _finish_work(draft, text)
        if "tell me" in source or "notify" in source:
            draft.action = "notify"
            return _finish_work(draft, text)
        draft.pending_field = "action"
        draft.question = ACTION_QUESTION
        draft.status = "needs_input"
        return TurnResult(status="needs_input", question=ACTION_QUESTION, task=draft)
    if field == "action":
        if "investigat" in lowered:
            draft.action = "investigate_market_reaction"
        else:
            draft.action = "notify"
        draft.you_asked = list(draft.you_asked) + [text.strip()]
        return _finish_work(draft, text)
    return _understand_heuristic(text, current_job=current_job)


def _finish_work(draft: ClarifiedTask, text: str) -> TurnResult:
    if draft.action == "investigate_market_reaction":
        draft.task_type = "watch_plus_investigate"
        draft.capabilities = ["reaction", "market", "anomaly"]
        if not draft.scope.universe:
            draft.scope.universe = "top_100"
            draft.scope.listing_limit = draft.scope.listing_limit or 100
    else:
        draft.task_type = "persistent_monitor"
        draft.capabilities = ["anomaly", "market"]
        draft.action = draft.action or "notify"
    draft.status = "ready"
    draft.mode = "work"
    draft.question = ""
    draft.pending_field = ""
    draft.source_text = (draft.source_text + " " + text).strip()
    return TurnResult(status="ready", task=draft)


def _ask(text: str, question: str, pending_field: str = "subject", assets: list[str] | None = None) -> TurnResult:
    task = ClarifiedTask(
        status="needs_input",
        mode="ask",
        objective=text.strip(),
        scope=TaskScope(assets=list(assets or [])),
        you_asked=[text.strip()] if text.strip() else [],
        question=question,
        pending_field=pending_field,
        source_text=text,
    )
    return TurnResult(status="needs_input", question=question, task=task)


def _correction_assets(text: str) -> list[str]:
    match = re.search(r"\b(?:meant|mean)\s+([A-Za-z]{2,10})\s+not\s+([A-Za-z]{2,10})\b", text, re.I)
    if not match:
        return []
    keep = _SYMBOL_ALIASES.get(match.group(1).lower(), match.group(1).upper())
    return [keep]


def _is_trade_request(lowered: str) -> bool:
    if not re.search(r"\b(buy|sell|short|long|trade|swap)\b", lowered):
        return False
    return bool(re.search(r"\b(me|some|a position|for me)\b", lowered) or lowered.startswith("can you "))


def _is_acknowledgement(lowered: str) -> bool:
    return lowered.strip() in {"thanks", "thank you", "ok", "okay", "forget it", "never mind", "nvm"}


def _is_market_wide(lowered: str) -> bool:
    if "market cap" in lowered:
        return False
    return any(
        phrase in lowered
        for phrase in ("whole market", "the market", "entire market", "crypto market", "how is crypto", "how's the market")
    )


def _ready(
    text: str,
    *,
    mode: str,
    task_type: str,
    assets: list[str],
    action: str,
    capabilities: list[str],
    objective: str,
    universe: str = "",
    window: str = "",
    listing_limit: int | None = None,
    trigger_conditions: list | None = None,
    assumptions: list[str] | None = None,
    requested_output: str = "natural_language_report",
) -> TurnResult:
    task = ClarifiedTask(
        status="ready",
        mode=mode,  # type: ignore[arg-type]
        task_type=task_type,  # type: ignore[arg-type]
        objective=objective,
        scope=TaskScope(assets=assets, universe=universe, window=window, listing_limit=listing_limit),
        trigger=TaskTrigger(conditions=list(trigger_conditions or [])),
        action=action,
        requested_output=requested_output,
        you_asked=[text.strip()] if text.strip() else [],
        assumptions=list(assumptions or []),
        capabilities=capabilities,
        source_text=text,
    )
    return TurnResult(status="ready", task=task)


def _parse_unusual(text: str, asset: str) -> list[dict]:
    lowered = text.lower()
    percent = PERCENT_RE.search(text)
    conditions: list[dict] = []
    if percent:
        value = float(percent.group(1))
        if any(word in lowered for word in ("drop", "fall", "down", "declin", "crash")):
            conditions.append(
                {"metric": "price_change_24h", "operator": "<=", "value": -abs(value), "asset": asset}
            )
        else:
            conditions.append(
                {"metric": "price_change_24h", "operator": ">=", "value": abs(value), "asset": asset}
            )
    if "volume" in lowered:
        vol = float(percent.group(1)) if percent and "volume" in lowered else 80.0
        conditions.append({"metric": "volume_change_24h", "operator": ">=", "value": vol, "asset": asset})
    if any(word in lowered for word in ("relative", "versus the rest", "vs the market", "combination")):
        conditions.append({"metric": "relative_performance", "operator": "<=", "value": -3, "asset": asset})
    if "price" in lowered and not percent and not conditions:
        return []
    return conditions


def _needs_unusual_question(lowered: str) -> bool:
    if not any(stem in lowered for stem in WATCH_STEMS) and "watch" not in lowered:
        return False
    return any(stem in lowered for stem in UNUSUAL_STEMS) or (
        "watch" in lowered and not _has_threshold_text(lowered) and "top" not in lowered
    )


def _looks_like_watch(lowered: str) -> bool:
    return any(stem in lowered for stem in WATCH_STEMS) or "when " in lowered


def _has_threshold(text: str) -> bool:
    return bool(PERCENT_RE.search(text))


def _has_threshold_text(lowered: str) -> bool:
    return "%" in lowered or bool(PERCENT_RE.search(lowered))


def _has_universe(lowered: str) -> bool:
    return bool(re.search(r"\btop\s+\d+\b", lowered)) or (
        "top" in lowered and "coin" in lowered
    ) or ("find" in lowered and "coin" in lowered)


def _has_rank(lowered: str) -> bool:
    return any(word in lowered for word in ("rank", "list", "sort", "biggest", "highest"))


def _is_plain_status(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in ("how is", "how's", "how are", "doing today", "how is btc", "how is bitcoin")
    ) and "watch" not in lowered


def _is_discovery(lowered: str) -> bool:
    return any(word in lowered for word in ("trending", "gainers", "new listing", "what is pumping", "discovery"))


def _window(text: str) -> str:
    match = WINDOW_RE.search(text)
    if not match:
        lowered = text.lower()
        if "this week" in lowered or "the week" in lowered:
            return "7d"
        if "this month" in lowered:
            return "30d"
        if "30 day" in lowered or "30-day" in lowered or "last 30" in lowered:
            return "30d"
        return ""
    amount, unit = match.group(1), match.group(2).lower()
    if unit.startswith("d"):
        return f"{amount}d"
    if unit.startswith("h"):
        return f"{amount}h"
    return f"{amount}m"


def _listing_limit(text: str) -> int:
    from apps.intelligence.compiler import extract_listing_limit

    return extract_listing_limit(text)


def _price_trigger(text: str, asset: str, default: float = -2.0) -> dict:
    value = _signed_percent(text, default)
    return {
        "metric": "price_change_24h",
        "operator": ">=" if value > 0 else "<=",
        "value": value,
        "asset": asset,
    }


def _is_keep_watching(lowered: str) -> bool:
    if _extract_symbols(lowered):
        return False
    return "keep watching" in lowered or "keep an eye" in lowered or "keep monitoring" in lowered


def _is_volume_question(lowered: str) -> bool:
    return "volume" in lowered and any(word in lowered for word in ("highest", "unusual", "most", "top", "biggest"))


def _signed_percent(text: str, default: float) -> float:
    found = PERCENT_RE.findall(text)
    if not found:
        return default
    value = float(found[0])
    lowered = text.lower()
    rise = bool(re.search(r"\b(rise|rises|rising|climb|climbs|climbing|rally|rallies|surge|surges|gain|gains|pump|above|increas|up)\b", lowered))
    drop = bool(re.search(r"\b(drop|drops|fall|falls|fell|declin|down|crash|below)\b", lowered))
    if rise and not drop:
        return abs(value)
    if drop:
        return -abs(value)
    return -abs(value) if default < 0 else abs(value)


def _default_capabilities(task_type: str, window: str) -> list[str]:
    if task_type == "watch_plus_investigate":
        return ["reaction", "market", "anomaly"]
    if task_type == "scheduled_brief":
        return ["market", "regime"]
    if window:
        return ["historical", "market"]
    if task_type == "persistent_monitor":
        return ["anomaly", "market"]
    return ["market"]
