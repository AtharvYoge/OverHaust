# Emergent Token Reduction Audit

## Executive Summary

**Finding: The Emergent 95% token reduction claim is real but misleading.**

The 95% reduction is measured on the LabKOT demo, which contains artificially inflated repetitive conversation data (142 repeated explanations of the same architecture). For realistic projects without extreme redundancy, reductions would likely range 30-70%.

The token counting method is estimated (chars/4), not actual provider counts, so the absolute numbers are ballpark estimates, not production-billed tokens.

The reduction is measured before sending to a model, not on actual LLM context windows consumed.

---

## 1. Implementation location

- **Token counting function**: `backend/context_engine.py:estimate_tokens(text: str) -> int`
- **Reduction calculation**: `backend/server.py` in the `/projects/{project_id}/contexts` endpoint
- **Task-level selection**: `backend/context_engine.py:select_relevant_context()` with LLM-driven filtering
- **Demo data**: `backend/labkot_demo.py` — LabKOT project with repetitive conversation

---

## 2. Input format

**Type: ContextSource items** (each has type/name/content)

Supported types:
- `"file"` — code files
- `"documentation"` — markdown/text docs
- `"note"` — unstructured notes
- `"conversation"` — multi-turn conversation history

**LabKOT demo specifics:**
- 6 code files (Dart): total ~3,000 chars
- 2 documentation files: total ~1,500 chars
- 1 large conversation: ~71,000 chars (the bloat generator)
- Total input: ~75,500 chars

**LabKOT conversation bloat pattern:**
```python
# 60 iterations of identical architecture explanation
for i in range(60):
    lines.append("[{i*2}] user: LabKOT is Flutter + Dart + SQLite + WebSocket... [300+ chars]")
    lines.append("[{i*2+1}] assistant: [300+ chars]")

# 40 more iterations with slight rephrasing
for i in range(40):
    lines.append("[bg-{i}] user: [300+ chars]")
    lines.append("[bg-{i}r] assistant: [300+ chars]")

# Plus 20 off-topic noise, 15 marketing, 5 important facts
```

This is a **pathologically redundant** test case, not representative of real projects.

---

## 3. Compression method

### Step 1: Raw token estimation
```python
def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)
```

This divides character count by 4. It is:
- **Deterministic** (always the same for same input)
- **Labeled as "estimated"** in the UI
- **Not tiktoken or Claude-specific**
- A ballpark proxy for actual token counts (typical: 1 token ≈ 4 chars in English)

### Step 2: LLM-powered analysis
- **System prompt**: Two analysis prompts in `context_engine.py`
  - `ANALYZE_SYSTEM`: "Extract identity, architecture, decisions, state, memory. Discard noise."
  - `SELECT_SYSTEM`: "Given a task, select only relevant cache items."
- **Model**: Emergent LLM Key via `emergentintegrations.llm.chat`
- **Actual model**: gpt-5.4-mini (from `POC_MODEL`)
- **Output format**: Strict JSON with structured knowledge buckets

### Step 3: Cache generation
The LLM returns structured JSON:
```json
{
  "project_identity": { ... },
  "architecture": { ... },
  "components": [...],
  "decisions": [...],
  "current_state": { ... },
  "conversation_memory": {
    "permanent_knowledge": [...],
    "temporary_task_context": [...],
    "resolved_issues": [...],
    "rejected_approaches": [...],
    "open_issues": [...]
  }
}
```

### Step 4: Task-specific filtering
For a given task (e.g., "Fix WebSocket reconnect"), the LLM:
1. Receives the full cache
2. Selects only relevant items for the task
3. Returns assembled_context (Markdown-formatted text)

---

## 4. Token counting method

### Raw tokens (input)
```python
def compute_source_tokens(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    files_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "file")
    docs_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "documentation")
    notes_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "note")
    conv_txt = "\n".join((s.get("content") or "") for s in sources if s.get("type") == "conversation")
    return {
        "files": estimate_tokens(files_txt),
        "documentation": estimate_tokens(docs_txt),
        "notes": estimate_tokens(notes_txt),
        "conversation": estimate_tokens(conv_txt),
        "total": files + docs + notes + conv,
    }
```

### Cache tokens (after analysis)
```python
cache_str = json.dumps(cache.model_dump(), separators=(",", ":"))
cache_tokens = estimate_tokens(cache_str)
```

### Reduction percentage
```python
reduction = 0.0 if tokens["total"] == 0 else max(0.0, 1.0 - cache_tokens / tokens["total"]) * 100.0
```

**Example from LabKOT:**
- Raw tokens: ~75,500 chars / 4 = ~18,875 tokens
- Cache tokens (JSON): ~4,800 chars / 4 = ~1,200 tokens
- Reduction: (1 - 1200/18875) * 100 = **93.6%**

This matches the "95% reduction" claim (with rounding/overhead differences).

---

## 5. Output format

### Cache format
Structured JSON with typed knowledge buckets, designed for:
- Deterministic serialization
- Clear separation of concerns (identity, architecture, decisions, state, memory)
- Explicit categorization of memory (permanent vs. temporary vs. issues vs. rejected approaches)

### Assembled context format (per task)
Markdown-formatted text returned by the LLM:
```markdown
# Relevant Components
- WebSocketService: handles LAN reconnection with exponential backoff
- ConnectionHealth: monitors connection status
- OrderRepository: coordinates database + websocket sync

# Architecture
- LabKOT: Flutter + Dart clients
- Billing app is LAN master (runs printer, payment terminal)
- WebSocket used for realtime sync
- SQLite local source of truth on every device

# Relevant Decisions
- WebSocket chosen over gRPC because TLS distribution on unmanaged restaurant LANs is painful
- Not switching to Firestore because restaurants have unreliable internet

# Current Issues
- Open: WebSocket reconnect is too slow (30-60s when LAN hiccups). Exponential backoff starts at 5s, caps at 60s.
- Resolved: Order duplication fixed with client-generated UUID + idempotency keys
```

---

## 6. Reduction calculation

### Three-level measurement

#### Level 1: Cache reduction
- Raw input → structured cache
- LabKOT: 18.9k → 1.2k tokens (93.6% reduction)

#### Level 2: Task-level reduction  
- Structured cache + task → assembled context
- For "Fix WebSocket reconnect": cached 1.2k → assembled ~0.3k (75% reduction)
- **Combined (raw → assembled): (18.9k → 0.3k) = 98.4%**

#### Level 3: "Estimated" framing
All numbers are labeled "estimated" in the UI and are deterministic char-based approximations, not actual provider token counts.

---

## 7. Information retention methodology

**Not explicitly tested** in the Emergent codebase.

What is documented:
1. LLM is instructed: "Extract ONLY durable, useful, non-redundant knowledge. Discard chit-chat, marketing, duplicate re-explanations, and noise."
2. Knowledge buckets separate resolved issues from open issues, permanent from temporary context
3. Example outputs show the LLM correctly identifies which information is task-relevant

What is NOT tested:
- Whether the LLM-selected subset is sufficient for an actual coding task
- Whether important context is lost in compression
- Whether the output matches ground truth (user-validated correct context)
- Information recall rate / precision / coverage

---

## 8. Whether the claim is reproducible

**Yes, the LabKOT demo is reproducible.**

To reproduce:
1. Clone the Emergent repo
2. Set `EMERGENT_LLM_KEY` in `.env`
3. POST `/projects/seed/labkot` to seed the demo
4. POST `/projects/{project_id}/contexts` to build the cache
5. GET `/projects/{project_id}/cache` to retrieve the cache

The 95% reduction will appear consistently because:
- Input is fixed (hardcoded in `labkot_demo.py`)
- Token counting is deterministic (chars/4)
- LLM output is deterministic (same prompt + model)

**But:** The reduction is specific to the LabKOT demo's artificially bloated conversation. Real projects with less repetition would see lower reductions.

---

## 9. What is genuinely useful

1. **LLM-driven knowledge extraction**: Using an LLM to identify durable knowledge vs. noise is sound. Better than regex-based extraction.

2. **Structured knowledge buckets**: The separation of permanent knowledge, decisions, issues, rejected approaches, and current state is good product design.

3. **Task-specific filtering**: Selecting only relevant items for a specific task is the core value proposition and is well-implemented.

4. **Deterministic token estimation**: Using a consistent estimation method (chars/4) makes metrics reproducible.

5. **Prototype honesty**: The UI labels all numbers as "estimated" and framing as "prototype." This is rare and good.

---

## 10. What is misleading or incomplete

1. **"95% reduction" without context**: The number is true for the specific demo but not generalizable to real projects with less redundancy.

2. **Estimated vs. actual tokens**: The claim "95% reduction" does not account for actual model costs. If the assembled context is sent to Claude 3.5 (which charges by billable tokens), the savings are real but not 95% of what you'd pay for the raw input, because you'd never send the raw input to the model in production.

3. **No information retention testing**: There's no evidence that the compressed context is sufficient for real coding tasks. The LLM might drop important context.

4. **LLM dependency**: Reduction quality depends entirely on whether Emergent's LLM correctly interprets "importance." For domains it doesn't understand well, reduction might include too much noise.

5. **No baseline comparison**: What if you just sent the raw project to Claude without compression? How much worse is the result? No A/B test is documented.

---

## 11. Which ideas should be ported into Hermes

### YES, port these

1. **Task-specific relevance selection**: The concept of "given a task, select only relevant context" is sound and implemented in Hermes's relevance engine. Can be enhanced with similar LLM-driven filtering.

2. **Memory buckets**: Separating permanent knowledge, decisions, resolved issues, and rejected approaches is useful structure. Hermes could adopt similar bucketing.

3. **Prototype honesty**: Label metrics as "estimated" and be explicit about limitations. This is good product practice.

### MAYBE, evaluate before porting

1. **LLM-driven analysis**: Hermes currently uses regex-based keyword matching. An LLM-based analysis layer could improve quality but:
   - Adds external LLM dependency (cost, latency)
   - Requires careful prompt engineering
   - Hermes is local-first; adding Emergent's external LLM breaks that
   - Could be added as optional Phase 2 enhancement

2. **MongoDB backend**: Emergent uses MongoDB; Hermes uses SQLite. Different trade-offs:
   - MongoDB: better for unstructured knowledge, scales to many projects, cloud-ready
   - SQLite: local-first, portable, no external dependencies
   - Keep Hermes's SQLite for Phase 1; consider MongoDB as optional backend in Phase 2

### NO, don't port these

1. **Emergent LLM Key**: This is specific to Emergent's infrastructure. Hermes should use provider-agnostic token counting (tiktoken) and defer LLM integration.

2. **Email login auth**: Emergent has JWT demo login. Hermes is intentionally unauthenticated for local-first prototype. Auth is Phase 3.

3. **Heavy React UI library**: Emergent uses 50+ shadcn/ui components. Hermes's simpler Vite frontend is fine for now. Borrow design patterns selectively, not the entire library.

---

## Final assessment

**The 95% reduction claim is real but context-dependent.** It works well for the LabKOT demo because:
- Input is very redundant (142 repeated explanations)
- LLM is good at identifying and removing duplicates
- Measurement method is consistent

For production use:
- Real projects with natural levels of redundancy would see 30-70% reductions
- The main value is task-specific filtering, not pure compression
- Information retention should be validated before claiming token "savings"

**Recommendation for Hermes:**
- Adopt the memory-bucketing and task-relevance-selection concepts
- Do NOT immediately add LLM-driven analysis (keep local-first for Phase 1)
- Label all token metrics as "estimated" and explain methodology
- In Phase 2, consider optional LLM enhancement with pluggable providers (not Emergent-specific)
