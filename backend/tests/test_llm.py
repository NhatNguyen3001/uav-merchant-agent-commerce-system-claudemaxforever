from pathlib import Path

import pytest

from macs.llm import LLM, LLMOutputError
from macs.models import BuyerDecision, Intent, Proposal

FIX = Path(__file__).resolve().parents[1] / "macs" / "fixtures"


async def test_fake_intent_loads_and_validates():
    llm = LLM(fake=True)
    intent = await llm.structured(Intent, "sys", "user", fixture="record_intent_happy_path")
    assert intent.constraint_count == 6


async def test_fake_proposal_substitutes_tool_result_id():
    llm = LLM(fake=True)
    p = await llm.structured(Proposal, "sys", "user", fixture="record_proposal_happy_path_1",
                             tool_result_id="tool-7")
    assert all(ref.tool_result_id == "tool-7" for it in p.items for ref in it.grounded_on)
    assert p.discount_pct == 22


async def test_fake_buyer_rounds():
    llm = LLM(fake=True)
    d1 = await llm.structured(BuyerDecision, "sys", "user", fixture="buyer_decision_happy_path_1")
    d2 = await llm.structured(BuyerDecision, "sys", "user", fixture="buyer_decision_happy_path_2")
    assert (d1.action, d2.action) == ("counter", "accept")


async def test_malformed_fixture_raises(tmp_path):
    (tmp_path / "bad.json").write_text('{"goal": 1}', encoding="utf-8")
    llm = LLM(fake=True, fixtures_dir=tmp_path)
    with pytest.raises(LLMOutputError):
        await llm.structured(Intent, "sys", "user", fixture="bad")


def test_from_env_reads_flag(monkeypatch):
    monkeypatch.setenv("FAKE_LLM", "1")
    assert LLM.from_env().fake is True
    monkeypatch.setenv("FAKE_LLM", "0")
    assert LLM.from_env().fake is False
