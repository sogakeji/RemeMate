"""SessionPad B8 AI recap-summary contract."""
import pytest

from app.services import recap_summaries


def test_summary_snapshot_excludes_private_partner_notes():
    class Item:
        def __init__(self, item_id, side, kind, content):
            self.id = item_id
            self.side = side
            self.kind = kind
            self.content = content

    grouped = {
        "for_me": [
            Item(1, "for_me", "expression", "avoir hâte de"),
            Item(2, "for_me", "private_note", "Pierre 下个月准备 HSK"),
        ],
        "for_partner": [
            Item(3, "for_partner", "correction", "我很同意 → 我很赞同"),
        ],
    }

    rows, fingerprint = recap_summaries.summary_snapshot(grouped)

    assert [row["content"] for row in rows] == [
        "avoir hâte de", "我很同意 → 我很赞同",
    ]
    assert "Pierre 下个月准备 HSK" not in str(rows)
    assert all("id" not in row for row in rows)
    assert len(fingerprint) == 64


def test_summary_payload_is_bounded_and_structured():
    payload = recap_summaries.normalize_summary({
        "gains": ["表达更自然", "理解了语气差异"],
        "depth": "讨论从词义进入了真实使用语境。",
        "topics": ["旅行", "表达习惯", "旅行"],
        "next_steps": ["下次主动使用 avoir hâte de"],
    })

    assert payload == {
        "gains": ["表达更自然", "理解了语气差异"],
        "depth": "讨论从词义进入了真实使用语境。",
        "topics": ["旅行", "表达习惯"],
        "next_steps": ["下次主动使用 avoir hâte de"],
    }


def test_summary_payload_rejects_missing_sections():
    assert recap_summaries.normalize_summary({
        "gains": ["学到一个表达"],
        "topics": ["旅行"],
        "next_steps": ["复习"],
    }) is None


def test_summary_prompt_refuses_silent_truncation():
    rows = [{
        "side": "for_me",
        "kind": "natural_phrase",
        "content": "x" * recap_summaries.MAX_PROMPT_CHARS,
    }]

    with pytest.raises(ValueError, match="请先整理"):
        recap_summaries._build_messages(rows, "中文")
