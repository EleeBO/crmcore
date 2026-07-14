"""Tests for scenario prompt formatter (FEAT: concise briefing-aware hints)."""

from __future__ import annotations

from backend.pipeline.scenario import (
    BuyerPortrait,
    KeyFact,
    Objection,
    Scenario,
    Strategy,
)


def test_format_scenario_includes_portrait() -> None:
    """Formatted scenario should include portrait section."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        portrait=BuyerPortrait(
            role="CTO",
            pain_points=["high costs", "slow deployment"],
            motivators=["automation", "cost savings"],
            budget="$50k",
            communication_style="direct",
        ),
    )
    result = format_scenario_for_hints(scenario)
    assert "ПОРТРЕТ КЛИЕНТА" in result
    assert "CTO" in result
    assert "high costs" in result
    assert "slow deployment" in result
    assert "automation" in result
    assert "$50k" in result
    assert "direct" in result


def test_format_scenario_includes_strategy() -> None:
    """Formatted scenario should include strategy section."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        strategy=Strategy(
            approach="consultative selling",
            key_messages=["ROI in 3 months", "24/7 support"],
            avoid=["price pressure", "competitor bashing"],
        ),
    )
    result = format_scenario_for_hints(scenario)
    assert "СТРАТЕГИЯ" in result
    assert "consultative selling" in result
    assert "ROI in 3 months" in result
    assert "24/7 support" in result
    assert "price pressure" in result


def test_format_scenario_includes_objections() -> None:
    """Formatted scenario should include objections section."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        objections=[
            Objection(trigger="Too expensive", response="ROI covers cost in 3 months"),
            Objection(trigger="We have a vendor", response="Easy migration path"),
        ],
    )
    result = format_scenario_for_hints(scenario)
    assert "ВОЗРАЖЕНИЯ" in result
    assert "Too expensive" in result
    assert "ROI covers cost in 3 months" in result
    assert "We have a vendor" in result


def test_format_scenario_includes_key_facts() -> None:
    """Formatted scenario should include key facts section."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        key_facts=[
            KeyFact(fact="RTO 15 minutes", source_file="sla.pdf", source_page=3),
            KeyFact(fact="99.9% uptime", source_file="brochure.pdf"),
        ],
    )
    result = format_scenario_for_hints(scenario)
    assert "КЛЮЧЕВЫЕ ФАКТЫ" in result
    assert "RTO 15 minutes" in result
    assert "sla.pdf" in result
    assert "стр. 3" in result
    assert "99.9% uptime" in result


def test_format_scenario_includes_talking_points() -> None:
    """Formatted scenario should include talking points section."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        talking_points=["Mention case study", "Ask about timeline"],
    )
    result = format_scenario_for_hints(scenario)
    assert "ТЕЗИСЫ" in result
    assert "Mention case study" in result
    assert "Ask about timeline" in result


def test_format_scenario_includes_topic_perimeter() -> None:
    """Formatted scenario should include ТЕМА РАЗГОВОРА section first."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        portrait=BuyerPortrait(
            role="Коммерческий директор",
            pain_points=["ручной ввод данных", "Bitrix24 тормозит"],
        ),
        strategy=Strategy(
            approach="консультативная продажа CRM-системы",
            key_messages=["ROI за 3 месяца", "интеграция с 1С"],
        ),
    )
    result = format_scenario_for_hints(scenario)
    assert "ТЕМА РАЗГОВОРА" in result
    assert "ОТКЛОНЕНИЕ" in result
    assert "консультативная продажа CRM-системы" in result
    assert "ручной ввод данных" in result
    # Topic perimeter must come BEFORE portrait
    assert result.index("ТЕМА РАЗГОВОРА") < result.index("ПОРТРЕТ КЛИЕНТА")


def test_format_scenario_no_perimeter_without_data() -> None:
    """No ТЕМА РАЗГОВОРА section when strategy and portrait are empty."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        talking_points=["Mention case study"],
    )
    result = format_scenario_for_hints(scenario)
    assert "ТЕМА РАЗГОВОРА" not in result
    assert "ТЕЗИСЫ" in result


def test_format_scenario_empty() -> None:
    """Empty scenario should return fallback text."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    result = format_scenario_for_hints(Scenario())
    assert isinstance(result, str)
    assert len(result) > 0


def test_format_scenario_full() -> None:
    """Full scenario with all sections produces structured output."""
    from backend.pipeline.prompt_formatter import format_scenario_for_hints

    scenario = Scenario(
        portrait=BuyerPortrait(role="VP Sales"),
        strategy=Strategy(approach="challenger sale"),
        objections=[Objection(trigger="No budget", response="Flexible pricing")],
        key_facts=[KeyFact(fact="SLA Gold", source_file="doc.pdf")],
        talking_points=["Start with ROI"],
    )
    result = format_scenario_for_hints(scenario)
    assert "ПОРТРЕТ КЛИЕНТА" in result
    assert "СТРАТЕГИЯ" in result
    assert "ВОЗРАЖЕНИЯ" in result
    assert "КЛЮЧЕВЫЕ ФАКТЫ" in result
    assert "ТЕЗИСЫ" in result
    # Should NOT be JSON
    assert "{" not in result or "##" in result
