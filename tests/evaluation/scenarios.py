"""
Evaluation scenarios for Overhaust real-world validation.

Each scenario carries the raw conversation plus HUMAN-AUTHORED expectations
(ground truth) used to compute retention/removal metrics. Expectations are
substrings expected to appear (or NOT appear) in the extracted knowledge /
prepared context — deliberately loose so the metric measures the real engine
rather than overfitting to exact wording.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Scenario:
    id: str
    title: str
    conversation: str
    task: str                              # the task to build context for
    expected_important: List[str] = field(default_factory=list)   # must be retained
    expected_irrelevant: List[str] = field(default_factory=list)  # should be removed
    expected_decisions: List[str] = field(default_factory=list)
    expected_open_issues: List[str] = field(default_factory=list)
    expected_current_state: List[str] = field(default_factory=list)
    notes: str = ""


def _turns(*pairs) -> str:
    """Build a markdown transcript from (role, text) pairs."""
    out = []
    for role, text in pairs:
        out.append(f"## {role}\n{text}\n")
    return "\n".join(out)


SCENARIOS: List[Scenario] = []


# 1. Long coding conversation ------------------------------------------------
SCENARIOS.append(Scenario(
    id="coding",
    title="Long coding conversation",
    task="Fix the WebSocket reconnect bug in the chat backend",
    conversation=_turns(
        ("User", "Hey, I'm building a realtime chat backend."),
        ("Assistant", "Great, tell me about the stack."),
        ("User", "The architecture is React frontend, FastAPI backend, Redis pub/sub for fan-out, PostgreSQL for persistence."),
        ("Assistant", "Solid choice."),
        ("User", "We decided to use WebSockets for realtime messaging. We rejected server-sent events because corporate proxies buffer them."),
        ("Assistant", "Makes sense."),
        ("User", "Can you explain how async works in Python again?"),
        ("Assistant", "Sure, asyncio uses an event loop..."),
        ("User", "thanks"),
        ("User", "The WebSocket reconnect bug is still open: the connection drops after 60 seconds of idle and never recovers."),
        ("Assistant", "Have you added heartbeats?"),
        ("User", "We decided to use WebSocket heartbeats every 30 seconds to keep connections alive."),
        ("Assistant", "Good."),
        ("User", "Also fixed the avatar upload 500 error earlier — the fix was setting the correct multipart boundary."),
        ("Assistant", "Nice."),
        ("User", "By the way the weather is terrible today."),
        ("Assistant", "Hope it clears up."),
        ("User", "The ConnectionManager class in src/ws/manager.py owns the socket lifecycle."),
    ),
    expected_important=["WebSocket", "heartbeat", "reconnect"],
    expected_irrelevant=["weather", "async works in Python"],
    expected_decisions=["WebSocket", "heartbeat"],
    expected_open_issues=["reconnect"],
    expected_current_state=["reconnect"],
    notes="Critical WebSocket knowledge mixed with chit-chat and one resolved issue. "
          "LIMITATION: plain declarative facts without a trigger verb (e.g. "
          "'ConnectionManager owns the socket lifecycle') are not extracted — see report.",
))


# 2. Long startup / project conversation -------------------------------------
SCENARIOS.append(Scenario(
    id="startup",
    title="Long startup/project conversation",
    task="What is our go-to-market and pricing decision?",
    conversation=_turns(
        ("User", "We're founding an AI infra startup called Overhaust."),
        ("Assistant", "Exciting."),
        ("User", "The project is a persistent AI memory and efficiency layer for agents."),
        ("Assistant", "Who's the customer?"),
        ("User", "We decided to target prosumers and small teams first, not enterprise."),
        ("Assistant", "Why?"),
        ("User", "Because enterprise sales cycles are too long for a seed-stage company."),
        ("User", "good morning"),
        ("Assistant", "Morning!"),
        ("User", "We decided on usage-based pricing with a generous free tier."),
        ("Assistant", "Smart."),
        ("User", "The current task is preparing the seed pitch deck."),
        ("User", "We rejected a freemium-only model because it doesn't convert well for infra."),
        ("Assistant", "Agreed."),
        ("User", "Unrelated: what's a good pizza place nearby?"),
        ("Assistant", "Can't help with that."),
    ),
    expected_important=["usage-based pricing", "prosumers", "pitch deck"],
    expected_irrelevant=["pizza", "good morning"],
    expected_decisions=["usage-based pricing", "prosumers"],
    expected_open_issues=[],
    expected_current_state=["pitch deck"],
    notes="Business decisions buried among greetings and off-topic chatter.",
))


# 3. Research conversation ---------------------------------------------------
SCENARIOS.append(Scenario(
    id="research",
    title="Research conversation",
    task="Summarize the chosen retrieval approach and open questions",
    conversation=_turns(
        ("User", "I'm researching retrieval methods for a memory system."),
        ("Assistant", "Okay."),
        ("User", "We decided to use layered keyword retrieval first, not a vector database."),
        ("Assistant", "Reasonable for a prototype."),
        ("User", "The constraint is: everything must run locally with no external services."),
        ("User", "There is an open question about how to handle synonyms without embeddings."),
        ("Assistant", "You could add a lightweight stemmer."),
        ("User", "haha nice"),
        ("User", "Another open issue: we haven't decided how to measure retrieval quality yet."),
    ),
    expected_important=["layered keyword retrieval", "locally", "synonyms"],
    expected_irrelevant=["haha nice"],
    expected_decisions=["layered keyword retrieval"],
    expected_open_issues=["synonyms", "measure retrieval quality"],
    expected_current_state=[],
    notes="Research with explicit constraints and open questions.",
))


# 4. Repetitive AI conversation ----------------------------------------------
_rep = "We decided to use PostgreSQL as our primary database for the application."
SCENARIOS.append(Scenario(
    id="repetitive",
    title="Repetitive AI conversation",
    task="What database are we using?",
    conversation=_turns(
        ("User", _rep),
        ("Assistant", "Noted."),
        ("User", "As I mentioned, we decided to use PostgreSQL as the primary database."),
        ("Assistant", "Yes."),
        ("User", "Just to repeat: PostgreSQL is our primary database for the application."),
        ("Assistant", "Understood."),
        ("User", _rep),
        ("Assistant", "Got it."),
        ("User", "Once more: we are using PostgreSQL as the main database."),
    ),
    expected_important=["PostgreSQL"],
    expected_irrelevant=[],
    expected_decisions=["PostgreSQL"],
    expected_open_issues=[],
    expected_current_state=[],
    notes="Same fact 5x with slight rewording. Measures dedup (exact + near).",
))


# 5. Contradictory decisions -------------------------------------------------
SCENARIOS.append(Scenario(
    id="contradiction",
    title="Conversation with contradictory decisions",
    task="What database should I use for the new feature?",
    conversation=_turns(
        ("User", "We decided to use PostgreSQL for the backend."),
        ("Assistant", "Okay."),
        ("User", "Actually we switched to MongoDB for flexibility."),
        ("Assistant", "Noted."),
        ("User", "MongoDB caused problems with transactions and consistency."),
        ("Assistant", "That's a known tradeoff."),
        ("User", "We switched back to PostgreSQL and that is final."),
        ("Assistant", "Understood."),
    ),
    expected_important=["PostgreSQL"],
    expected_irrelevant=[],
    expected_decisions=["PostgreSQL"],
    expected_open_issues=[],
    expected_current_state=["PostgreSQL"],
    notes="Final decision is PostgreSQL (correctly current). LIMITATION: the older "
          "MongoDB decision is not retained as explicit history — see report.",
))


# 6. Resolved and unresolved issues ------------------------------------------
SCENARIOS.append(Scenario(
    id="resolved_unresolved",
    title="Conversation with resolved and unresolved issues",
    task="Add a new export-to-CSV feature",
    conversation=_turns(
        ("User", "Login is broken — users can't sign in with Google."),
        ("Assistant", "Let's debug."),
        ("User", "Fixed the login bug — it was an expired OAuth secret."),
        ("Assistant", "Great."),
        ("User", "The pagination on the dashboard is still broken and needs fixing."),
        ("Assistant", "Noted."),
        ("User", "We decided to use a service layer for all new features."),
    ),
    expected_important=["service layer", "pagination"],
    expected_irrelevant=[],
    expected_decisions=["service layer"],
    expected_open_issues=["pagination"],
    expected_current_state=[],
    notes="A new unrelated task must NOT surface the resolved login bug as active.",
))


# 7. Irrelevant discussion ---------------------------------------------------
SCENARIOS.append(Scenario(
    id="irrelevant",
    title="Conversation with irrelevant discussion",
    task="What is the architecture of the payment service?",
    conversation=_turns(
        ("User", "hey how's it going"),
        ("Assistant", "Good, you?"),
        ("User", "pretty good, watched a movie last night"),
        ("Assistant", "Nice."),
        ("User", "The payment service architecture: Stripe for cards, a webhook handler, and an idempotency table in Postgres."),
        ("Assistant", "Clear."),
        ("User", "anyway my coffee is cold"),
        ("Assistant", "Reheat it!"),
        ("User", "lol yeah"),
    ),
    expected_important=["Stripe", "webhook", "idempotency"],
    expected_irrelevant=["movie", "coffee", "how's it going"],
    expected_decisions=[],
    expected_open_issues=[],
    expected_current_state=[],
    notes="One dense architecture message surrounded by pure chatter.",
))


# 8. Important information buried deep ----------------------------------------
def _buried() -> str:
    parts = []
    filler = [
        ("User", "just checking in"),
        ("Assistant", "all good here"),
        ("User", "what's the weather like"),
        ("Assistant", "I can't check that"),
        ("User", "ok no worries"),
    ]
    # ~30 filler messages
    for i in range(6):
        parts.extend(filler)
    # buried critical decision
    parts.append(("User", "Important: we decided the authentication architecture uses JWT access tokens with 15-minute expiry and refresh tokens stored in httpOnly cookies."))
    for i in range(6):
        parts.extend(filler)
    return _turns(*parts)

SCENARIOS.append(Scenario(
    id="buried",
    title="Important information buried deep",
    task="How does authentication work?",
    conversation=_buried(),
    expected_important=["JWT", "refresh token", "httpOnly"],
    expected_irrelevant=["weather", "checking in"],
    expected_decisions=["JWT"],
    expected_open_issues=[],
    expected_current_state=[],
    notes="One critical decision among ~60 filler messages; tests retrieval recall.",
))


# 9. Short conversation ------------------------------------------------------
SCENARIOS.append(Scenario(
    id="short",
    title="Short conversation",
    task="What did we decide?",
    conversation=_turns(
        ("User", "We decided to use Vite for the frontend build."),
        ("Assistant", "Good choice."),
    ),
    expected_important=["Vite"],
    expected_irrelevant=[],
    expected_decisions=["Vite"],
    expected_open_issues=[],
    expected_current_state=[],
    notes="Tiny input — expected to be an 'already compact' edge case (no reduction).",
))


# 10. Almost no repetition ---------------------------------------------------
SCENARIOS.append(Scenario(
    id="no_repetition",
    title="Conversation with almost no repetition",
    task="Give me the full project context",
    conversation=_turns(
        ("User", "The project is a mobile fitness app."),
        ("Assistant", "Okay."),
        ("User", "We decided to use React Native with Expo."),
        ("Assistant", "Noted."),
        ("User", "The backend is NestJS with Prisma and PostgreSQL."),
        ("Assistant", "Clear."),
        ("User", "We use RevenueCat for subscriptions."),
        ("Assistant", "Understood."),
        ("User", "The current task is building the workout tracking screen."),
        ("Assistant", "Got it."),
        ("User", "There's an open issue with HealthKit permissions on iOS."),
    ),
    expected_important=["React Native", "NestJS", "RevenueCat", "workout tracking"],
    expected_irrelevant=[],
    expected_decisions=["React Native", "NestJS"],
    expected_open_issues=["HealthKit"],
    expected_current_state=["workout tracking"],
    notes="Dense, unique facts — little to dedupe; reduction should be modest.",
))
