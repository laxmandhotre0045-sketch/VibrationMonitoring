"""Session retention and the bounded self-correction limits for agent/graph modes."""

import os as _os

MAX_SESSION_TURNS = int(_os.getenv("MAX_SESSION_TURNS", "10"))
# Upper bound on retained chat sessions; oldest are evicted first so a
# long-running server does not grow without bound.
MAX_SESSIONS = int(_os.getenv("MAX_SESSIONS", "1000"))

AGENT_MAX_ITERATIONS = int(_os.getenv("AGENT_MAX_ITERATIONS", "4"))
# When the agent loop ends with a grounded text answer and no figures are in
# the result set, use that answer directly instead of making a second
# synthesis call. Set false to always run the dedicated final-answer call.
AGENT_SKIP_FINAL_CALL = _os.getenv("AGENT_SKIP_FINAL_CALL", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Bounded self-correction in mode=graph. Both are hard caps: exceeding them
# proceeds with what was found rather than looping.
GRAPH_MAX_REWRITES = int(_os.getenv("GRAPH_MAX_REWRITES", "1"))
GRAPH_MAX_REGENS = int(_os.getenv("GRAPH_MAX_REGENS", "1"))
