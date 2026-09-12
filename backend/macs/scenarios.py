HAPPY_QUERY = ("I'm starting a podcast from a small apartment on a noisy street. Complete beginner. "
               "Sustainable brands only. Budget is 600 and I need everything by next weekend.")

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
