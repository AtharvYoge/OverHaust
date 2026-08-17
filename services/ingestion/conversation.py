"""
Conversation ingestion and compression for Overhaust.

Parses conversations (plain text, Markdown, JSON exports) into messages,
classifies them, extracts structured knowledge with provenance, and
deduplicates repeated information. Produces queryable structured memory,
NOT a single summary blob.
"""

import json
import re
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single parsed conversation message with provenance."""
    index: int                # message number within conversation
    role: str                 # 'user' | 'assistant' | 'system' | 'unknown'
    content: str
    conversation_id: str
    token_count: int = 0


@dataclass
class ClassifiedMemory:
    """Structured knowledge extracted from a conversation, with provenance."""
    category: str             # permanent_knowledge | current_task | decision |
                              # resolved_issue | open_issue | stale_info | irrelevant
    content: str
    conversation_id: str
    message_index: int        # provenance: which message it came from
    role: str
    confidence: float         # 0.0-1.0 heuristic confidence
    importance: float         # 0.0-1.0
    status: str               # 'active' | 'resolved' | 'stale' | 'rejected'
    source_type: str = "conversation"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def provenance(self) -> str:
        return f"Conversation {self.conversation_id}, Message #{self.message_index}"


@dataclass
class IngestionResult:
    """Result of ingesting one conversation."""
    conversation_id: str
    message_count: int
    original_tokens: int
    memories: List[ClassifiedMemory]
    stats: Dict[str, int]     # count per category
    duplicate_messages: int


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_ROLE_MARKERS = re.compile(
    r"^(?:#{1,4}\s*)?(?:\*\*)?(user|human|assistant|ai|system|chatgpt|claude|gpt|cursor|copilot)(?:\*\*)?\s*[:：]?\s*$",
    re.IGNORECASE
)
_INLINE_ROLE = re.compile(
    r"^(?:\*\*)?(user|human|assistant|ai|system|chatgpt|claude|gpt)(?:\*\*)?\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.DOTALL
)

_CANONICAL = {
    'user': 'user', 'human': 'user',
    'assistant': 'assistant', 'ai': 'assistant', 'chatgpt': 'assistant',
    'claude': 'assistant', 'gpt': 'assistant', 'cursor': 'assistant',
    'copilot': 'assistant',
    'system': 'system',
}


class ConversationParser:
    """Parses raw conversation text/JSON into Message objects."""

    def parse(self, raw: str, conversation_id: str) -> List[Message]:
        raw = raw.strip()
        if not raw:
            return []
        msgs = self._try_parse_json(raw, conversation_id)
        if msgs is not None:
            return msgs
        return self._parse_text(raw, conversation_id)

    def _try_parse_json(self, raw: str, conversation_id: str) -> Optional[List[Message]]:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
        items = None
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ('messages', 'conversation', 'turns', 'history', 'chat'):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            if items is None and 'mapping' in data:  # ChatGPT export
                return self._parse_chatgpt_export(data, conversation_id)
        if items is None:
            return None
        messages = []
        for item in items:
            if not isinstance(item, dict):
                continue
            role = str(item.get('role', item.get('author', 'unknown'))).lower()
            role = _CANONICAL.get(role, role if role in ('user', 'assistant', 'system') else 'unknown')
            content = item.get('content', item.get('text', item.get('message', '')))
            if isinstance(content, dict):  # openai-style content parts
                parts = content.get('parts', [])
                content = ' '.join(str(p) for p in parts)
            content = str(content).strip()
            if content:
                messages.append(Message(index=len(messages), role=role, content=content,
                                        conversation_id=conversation_id))
        return messages or None

    def _parse_chatgpt_export(self, data: dict, conversation_id: str) -> List[Message]:
        messages = []
        mapping = data.get('mapping', {})
        nodes = sorted(mapping.values(), key=lambda n: n.get('create_time') or 0)
        for node in nodes:
            msg = node.get('message')
            if not msg:
                continue
            role = (msg.get('author', {}) or {}).get('role', 'unknown')
            parts = (msg.get('content', {}) or {}).get('parts', [])
            content = ' '.join(str(p) for p in parts if isinstance(p, str)).strip()
            if content and role in _CANONICAL:
                messages.append(Message(index=len(messages), role=_CANONICAL[role],
                                        content=content, conversation_id=conversation_id))
        return messages

    def _parse_text(self, raw: str, conversation_id: str) -> List[Message]:
        """Parse markdown/plain-text transcripts with role markers."""
        messages: List[Message] = []
        current_role = 'user'
        current_lines: List[str] = []

        def flush():
            content = '\n'.join(current_lines).strip()
            if content:
                messages.append(Message(index=len(messages), role=current_role,
                                        content=content, conversation_id=conversation_id))

        role_line = re.compile(r"^(?:\*\*)?(user|human|assistant|ai|system)(?:\*\*)?[:：]\s*(.*)$", re.I)

        for line in raw.splitlines():
            stripped = line.strip()
            # Skip pure document/section title headers (not role markers)
            if re.match(r'^#{1,4}\s+(?!user|human|assistant|ai|system)', stripped, re.I):
                flush()
                current_lines = []
                continue
            marker = _ROLE_MARKERS.match(stripped)
            inline = role_line.match(stripped)
            if marker:
                flush()
                current_lines = []
                current_role = _CANONICAL.get(marker.group(1).lower(), 'user')
            elif inline:
                flush()
                current_lines = []
                current_role = _CANONICAL.get(inline.group(1).lower(), 'user')
                if inline.group(2):
                    current_lines.append(inline.group(2))
            else:
                current_lines.append(line)
        flush()
        return messages


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Note: use double-quoted raw strings so apostrophes in patterns are fine.
_DECISION_PATTERNS = [
    r"\bwe (?:decided|decide|chose|choose|agreed|agree) (?:to |on |that )?(.{8,300})",
    r"\bdecision[:：]\s*(.{8,300})",
    r"\bwe'?ll (?:use|go with|pick) (.{8,300})",
    r"\b(?:i|we) (?:rejected|ruled out|won'?t use|decided against) (.{8,300})",
    r"\blet'?s (?:use|go with|stick with) (.{8,300})",
]
_OPEN_ISSUE_PATTERNS = [
    r"\bthere'?s (?:an? )?(?:bug|issue|problem|error)\b.{0,200}",
    r"\b(?:still|currently) (?:broken|failing|not working|crashing)\b.{0,200}",
    r"\b(?:todo|fixme|need to fix|haven'?t fixed)\b[:：]?.{0,200}",
    r"\b(?:the )?\w[\w\s]{2,40} (?:is|keeps) (?:broken|failing|crashing|not working)\b.{0,150}",
]
_RESOLVED_PATTERNS = [
    r"\b(?:fixed|resolved|solved|closed)\b[:：]?\s*(.{8,200})",
    r"\b(?:the )?(?:fix|solution) (?:was|is)[:：]?\s*(.{8,200})",
    r"\bthat (?:fixed|solved|resolved) (?:the |it|this)?(.{8,150})",
]
_STALE_PATTERNS = [
    r"\b(?:we used to|previously|originally|at first) (?:use|had|went with)\b.{0,200}",
    r"\b(?:no longer|not anymore|deprecated|obsolete|outdated)\b[:：]?.{0,200}",
    r"\b(?:migrated|switched) (?:from|away from)\b.{0,200}",
]
_PERMANENT_PATTERNS = [
    r"\b(?:architecture|stack|tech stack)[:：]\s*(.{10,300})",
    r"\b(?:we|the project) (?:use|uses|runs on|is built (?:on|with))\b(.{10,300})",
    r"\b(?:constraint|requirement)[:：]\s*(.{10,300})",
    r"\b(?:database|backend|frontend|framework|language)[:：]\s*(.{5,200})",
    r"\b(?:the project is|this project is|we'?re building)\b(.{10,300})",
]
_CURRENT_TASK_PATTERNS = [
    r"\b(?:currently|right now|now) (?:working on|implementing|building|fixing)\b(.{0,250})",
    r"\b(?:the goal|the task|objective) (?:is|here is)[:：]?\s*(.{10,250})",
    r"\b(?:i need to|we need to|next step is to)\b(.{10,250})",
]
_IRRELEVANT_PATTERNS = [
    r"^(?:hi|hello|hey|thanks|thank you|ok|okay|great|perfect|sounds good|got it|cool|nice|awesome|yes|no|sure|bye|good morning|good evening)[\s!.]*$",
    r"^i'?ll (?:do that|look into it|check)[\s!.]*$",
    r"^(?:let me know if|hope this helps|does that make sense)[\s!.?]*",
]

_IMPORTANT_HINTS = re.compile(
    r"\b(architecture|database|schema|migration|deploy|production|auth|security|"
    r"password|secret|token|api key|endpoint|model|constraint|requirement|"
    r"decided|decision|bug|error|crash|fail|broken|performance|deadline|must|never|always)\b",
    re.IGNORECASE
)


def _match_any(patterns: List[str], text: str) -> Optional[str]:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.MULTILINE)
        if m:
            groups = [g for g in m.groups() if g]
            extracted = ' '.join(groups).strip() if groups else m.group(0).strip()
            if len(extracted) >= 8:
                return extracted[:400]
    return None


class MessageClassifier:
    """Classifies messages into structured memory categories."""

    def classify(self, msg: Message) -> List[ClassifiedMemory]:
        text = msg.content.strip()
        if not text:
            return []
        out: List[ClassifiedMemory] = []

        def make(category, content, confidence, importance, status):
            return ClassifiedMemory(
                category=category, content=content,
                conversation_id=msg.conversation_id, message_index=msg.index,
                role=msg.role, confidence=confidence, importance=importance,
                status=status)

        # Irrelevant short chatter — only skip if nothing important present
        if len(text) < 120 and not _IMPORTANT_HINTS.search(text):
            for p in _IRRELEVANT_PATTERNS:
                if re.match(p, text, re.IGNORECASE):
                    out.append(make('irrelevant', text, 0.9, 0.05, 'active'))
                    return out

        # Stale info first (it overrides earlier permanent knowledge)
        hit = _match_any(_STALE_PATTERNS, text)
        if hit:
            out.append(make('stale_info', hit, 0.7, 0.65, 'stale'))

        hit = _match_any(_DECISION_PATTERNS, text)
        if hit:
            rejected = bool(re.search(r"\b(rejected|ruled out|decided against|won'?t use)\b", text, re.I))
            out.append(make('decision', hit, 0.75, 0.9,
                            'rejected' if rejected else 'active'))

        hit = _match_any(_RESOLVED_PATTERNS, text)
        if hit:
            out.append(make('resolved_issue', hit, 0.7, 0.5, 'resolved'))

        hit = _match_any(_OPEN_ISSUE_PATTERNS, text)
        if hit:
            out.append(make('open_issue', hit, 0.65, 0.8, 'active'))

        hit = _match_any(_CURRENT_TASK_PATTERNS, text)
        if hit:
            out.append(make('current_task', hit, 0.7, 0.85, 'active'))

        hit = _match_any(_PERMANENT_PATTERNS, text)
        if hit:
            out.append(make('permanent_knowledge', hit, 0.7, 0.85, 'active'))

        return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ConversationIngestor:
    """Full pipeline: parse -> dedupe -> classify -> structured memory."""

    def __init__(self, token_estimator=None):
        from packages.tokenization.token_estimator import TokenEstimator
        self.estimator = token_estimator or TokenEstimator()
        self.parser = ConversationParser()
        self.classifier = MessageClassifier()

    def ingest_text(self, raw: str, conversation_id: Optional[str] = None) -> IngestionResult:
        conversation_id = conversation_id or hashlib.sha256(raw.encode()).hexdigest()[:12]
        messages = self.parser.parse(raw, conversation_id)
        return self._pipeline(messages, conversation_id, raw)

    def _pipeline(self, messages: List[Message], conversation_id: str, raw: str) -> IngestionResult:
        for m in messages:
            m.token_count = self.estimator.estimate_tokens(m.content)
        original_tokens = self.estimator.estimate_tokens(raw)

        # Deduplicate exact/near-identical messages (repeated information)
        seen: Dict[str, int] = {}
        unique: List[Message] = []
        duplicates = 0
        for m in messages:
            key = hashlib.sha256(re.sub(r'\s+', ' ', m.content.lower().strip()).encode()).hexdigest()
            if key in seen:
                duplicates += 1
                continue
            seen[key] = m.index
            unique.append(m)

        memories: List[ClassifiedMemory] = []
        for m in unique:
            memories.extend(self.classifier.classify(m))

        # Deduplicate extracted memories (same category + same normalized content)
        mem_seen = set()
        deduped: List[ClassifiedMemory] = []
        for mem in memories:
            key = (mem.category, re.sub(r'\s+', ' ', mem.content.lower().strip())[:200])
            if key in mem_seen:
                continue
            mem_seen.add(key)
            deduped.append(mem)

        stats: Dict[str, int] = {}
        for mem in deduped:
            stats[mem.category] = stats.get(mem.category, 0) + 1

        return IngestionResult(
            conversation_id=conversation_id,
            message_count=len(messages),
            original_tokens=original_tokens,
            memories=deduped,
            stats=stats,
            duplicate_messages=duplicates,
        )

    def store_result(self, result: IngestionResult, project_id: str, memory_store) -> List[str]:
        """Persist extracted memories with provenance. Returns memory IDs."""
        ids: List[str] = []
        category_to_type = {
            'permanent_knowledge': 'permanent',
            'decision': 'permanent',
            'current_task': 'task',
            'open_issue': 'task',
            'resolved_issue': 'resolved',
            'stale_info': 'stale',
            'irrelevant': 'temporary',
        }
        for mem in result.memories:
            if mem.category == 'irrelevant':
                continue  # don't store chatter
            metadata = {
                'knowledge_type': mem.category,
                'source_type': mem.source_type,
                'source_id': mem.conversation_id,
                'provenance': mem.provenance,
                'message_index': mem.message_index,
                'role': mem.role,
                'confidence': mem.confidence,
                'status': mem.status,
                **mem.metadata,
            }
            mem_id = memory_store.add_memory(
                project_id=project_id,
                content=mem.content,
                memory_type=category_to_type.get(mem.category, 'temporary'),
                importance_score=mem.importance,
                metadata=metadata,
            )
            ids.append(mem_id)
        return ids


def compression_report(result: IngestionResult, estimator=None) -> Dict[str, Any]:
    """Compute honest per-category token breakdown of an ingestion result."""
    from packages.tokenization.token_estimator import TokenEstimator
    est = estimator or TokenEstimator()
    breakdown: Dict[str, int] = {}
    for mem in result.memories:
        if mem.category == 'irrelevant':
            continue
        breakdown[mem.category] = breakdown.get(mem.category, 0) + est.estimate_tokens(mem.content)
    structured_total = sum(breakdown.values())
    original = result.original_tokens
    return {
        'conversation_id': result.conversation_id,
        'original_tokens': original,
        'structured_tokens': structured_total,
        'breakdown': breakdown,
        'message_count': result.message_count,
        'duplicate_messages': result.duplicate_messages,
        'reduction_percent': round((1 - structured_total / original) * 100, 2) if original else 0.0,
        'estimated': True,  # tiktoken-based estimate, not provider billing
    }
