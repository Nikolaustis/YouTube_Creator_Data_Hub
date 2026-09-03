from creator_hub.portfolio.ai_eval import evaluate


def test_offline_ai_eval_contract_passes():
    result = evaluate()
    assert result["ok"] is True
    assert result["mode"] == "offline_fixture"
    assert result["metrics"]["structured_output_rate"] == 1.0
    assert result["metrics"]["unsupported_evidence_key_count"] == 0
