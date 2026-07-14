"""Tests for TalkRatioTracker."""

import pytest


def test_initial_state_is_zero() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    state = tracker.get_state()
    assert state["managerPercent"] == 0
    assert state["clientPercent"] == 0
    assert state["waveform"] == []


def test_single_manager_utterance() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    tracker.on_utterance("rep", "hello world how are you", is_final=True)
    state = tracker.get_state()
    assert state["managerPercent"] == 100
    assert state["clientPercent"] == 0
    assert len(state["waveform"]) == 1
    assert state["waveform"][0]["speaker"] == "manager"


def test_balanced_conversation() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    tracker.on_utterance("rep", "one two three", is_final=True)
    tracker.on_utterance("client", "four five six", is_final=True)
    state = tracker.get_state()
    assert state["managerPercent"] == 50
    assert state["clientPercent"] == 50


def test_interim_utterances_ignored_for_waveform() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    tracker.on_utterance("rep", "interim text", is_final=False)
    state = tracker.get_state()
    assert state["waveform"] == []


def test_waveform_ring_buffer_caps_at_60() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    for i in range(70):
        speaker = "rep" if i % 2 == 0 else "client"
        tracker.on_utterance(speaker, f"word{i} extra", is_final=True)
    state = tracker.get_state()
    assert len(state["waveform"]) == 60


def test_amplitude_caps_at_1() -> None:
    from backend.pipeline.talk_ratio import TalkRatioTracker

    tracker = TalkRatioTracker()
    # 40 words > NORMALIZATION_MAX of 30 → amplitude capped at 1.0
    long_text = " ".join(f"word{i}" for i in range(40))
    tracker.on_utterance("rep", long_text, is_final=True)
    state = tracker.get_state()
    assert state["waveform"][0]["amplitude"] == 1.0


def test_wave_segment_is_pydantic_model() -> None:
    from backend.pipeline.talk_ratio import WaveSegment

    seg = WaveSegment(speaker="manager", amplitude=0.5)
    assert seg.model_dump() == {"speaker": "manager", "amplitude": 0.5}


def test_wave_segment_rejects_invalid_speaker() -> None:
    from pydantic import ValidationError

    from backend.pipeline.talk_ratio import WaveSegment

    with pytest.raises(ValidationError):
        WaveSegment(speaker="unknown", amplitude=0.5)
