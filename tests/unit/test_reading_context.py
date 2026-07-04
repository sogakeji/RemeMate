from app.services.reading.context import extract_context_sentence


def test_extracts_english_sentence():
    text = "First sentence. Target term appears here! Last sentence."
    start = text.index("Target")

    result = extract_context_sentence(text, start, start + len("Target"), "en", expected_term="Target")

    assert result.sentence == "Target term appears here!"
    assert result.start == text.index("Target")
    assert result.end == text.index("!") + 1
    assert result.offset_matched is True


def test_extracts_french_sentence():
    text = "Avant. Le mot café est ici? Après."
    start = text.index("café")

    result = extract_context_sentence(text, start, start + len("café"), "fr", expected_term="café")

    assert result.sentence == "Le mot café est ici?"
    assert result.start == text.index("Le")
    assert result.end == text.index("?") + 1
    assert result.offset_matched is True


def test_extracts_chinese_sentence():
    text = "第一句。目标词在这里！最后一句。"
    start = text.index("目标词")

    result = extract_context_sentence(text, start, start + len("目标词"), "zh", expected_term="目标词")

    assert result.sentence == "目标词在这里！"
    assert result.start == text.index("目标词")
    assert result.end == text.index("！") + 1
    assert result.offset_matched is True


def test_extracts_japanese_sentence():
    text = "最初の文。対象語はここです？最後の文。"
    start = text.index("対象語")

    result = extract_context_sentence(text, start, start + len("対象語"), "ja", expected_term="対象語")

    assert result.sentence == "対象語はここです？"
    assert result.start == text.index("対象語")
    assert result.end == text.index("？") + 1
    assert result.offset_matched is True


def test_searches_nearby_window_when_offsets_do_not_match_expected_term():
    text = "Opening sentence. The desired term appears in this sentence. Closing sentence."
    wrong_start = text.index("Opening")

    result = extract_context_sentence(
        text,
        wrong_start,
        wrong_start + len("Opening"),
        "en",
        expected_term="desired term",
    )

    assert result.sentence == "The desired term appears in this sentence."
    assert result.start == text.index("The")
    assert result.end == text.index(".", text.index("desired term")) + 1
    assert result.offset_matched is False


def test_truncates_long_sentence_while_keeping_expected_term():
    prefix = "a" * 260
    term = "target-term"
    suffix = "b" * 260
    text = f"Intro. {prefix}{term}{suffix}. Outro."
    start = text.index(term)

    result = extract_context_sentence(text, start, start + len(term), "en", expected_term=term, max_chars=80)

    assert len(result.sentence) == 80
    assert term in result.sentence
    assert result.start <= start
    assert result.end >= start + len(term)
    assert result.offset_matched is True
