HAPPY_QUERY = ("I'm starting a podcast from a small apartment on a noisy street. Complete beginner. "
               "Sustainable brands only. Budget is 600 and I need everything by next weekend.")

# Agent identities the console can simulate. Mandate ids follow the seed data in data/mandates.json;
# buyer-999 has no credential and no mandate on purpose.
# negotiation policy: "counter_then_accept" counters once and always accepts in round 2;
# "accept_first" accepts the first proposal without countering.
AGENTS = [
    {"agent_id": "buyer-001", "mandate_id": "mandate-001", "label": "Registered, negotiates once", "negotiation": "counter_then_accept"},
    {"agent_id": "buyer-002", "mandate_id": "mandate-002", "label": "Registered, accepts first offer", "negotiation": "accept_first"},
    {"agent_id": "buyer-999", "mandate_id": "mandate-999", "label": "Unregistered, will be refused", "negotiation": "counter_then_accept"},
]
AGENT_BY_ID = {a["agent_id"]: a for a in AGENTS}

SCENARIOS = {
    "happy_path": {
        "protocol": "acp", "agent_id": "buyer-001", "mandate_id": "mandate-001",
        "messages": [{"role": "user", "content": HAPPY_QUERY}],
    },
    "rejected_agent": {
        "protocol": "acp", "agent_id": "buyer-999", "mandate_id": "mandate-999",
        "messages": [{"role": "user", "content": "Looking for a podcast microphone under 200."}],
    },
}


def build_input(agent_id: str, query: str) -> dict:
    """ACP-shaped inbound message for a typed query from a chosen agent identity."""
    agent = AGENT_BY_ID[agent_id]
    return {
        "protocol": "acp", "agent_id": agent_id, "mandate_id": agent["mandate_id"],
        "messages": [{"role": "user", "content": query}],
    }
