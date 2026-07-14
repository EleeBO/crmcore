---
name: Prompt Engineering for Real-Time Sales Coaching
description: Design and optimize LLM system prompts for real-time sales assistants. Covers buyer psychology, objection handling (LAER), conversational intelligence, tone calibration, and structured output. Use when creating or improving prompts for sales coaching, hint generation, or real-time conversation analysis.
---

# Prompt Engineering for Real-Time Sales Coaching

## Core Principles

### 1. Role Assignment + Persona Control

Always start the system prompt with a concrete role identity:

```
Ты — [роль] с [X лет] опыта в [область].
Ты владеешь: [перечень навыков].
```

The role primes the model's behavior distribution. Be specific about expertise areas — this activates relevant knowledge clusters.

**Anti-pattern:** "Ты — ИИ-ассистент" (too generic, no behavioral grounding).

### 2. Chain-of-Thought Before Decision

Structure output so reasoning precedes conclusions:

```json
{"reasoning": "...", "relevance": "...", "hint": "...", "color": "..."}
```

The `reasoning` field forces the model to articulate its analysis before committing to a hint. This improves accuracy by 10-15% (schema-guided reasoning principle).

### 3. Brevity for Real-Time Context

Real-time hints must be:
- **1-2 sentences max** — the rep is mid-conversation, not reading a manual
- **Actionable** — what to say/do RIGHT NOW, not theory
- **Non-distracting** — augment the rep's natural flow, don't interrupt it

## Buyer Psychology Framework

Integrate these cognitive biases into prompt instructions:

### Loss Aversion
People fear losing more than they value gaining. Frame hints to address this:
- "Клиент теряет X каждый день без решения" > "Клиент получит X"
- Highlight cost of inaction, not just benefits of action

### Status Quo Bias
Buyers resist change. Counter by making change feel safe:
- Social proof ("компании вашего уровня уже используют...")
- Reversibility ("можно протестировать без обязательств")
- Incremental steps ("начните с одного отдела")

### Decision Paralysis
Too many options freeze buyers. Hints should simplify:
- Recommend one clear next step
- Remove unnecessary choices from the conversation
- Use "самый популярный вариант" framing

### Reciprocity
Giving value first creates obligation:
- Lead with insights before asking for commitment
- Share relevant industry data or benchmarks
- "Кстати, вот интересная статистика по вашей отрасли..."

## LAER Objection Handling Framework

When the client raises an objection, the hint should guide through:

| Step | Action | Prompt Instruction |
|------|--------|--------------------|
| **L**isten | Acknowledge what was said | "Сначала покажи, что услышал клиента" |
| **A**cknowledge | Validate the concern | "Подтверди, что опасение разумно" |
| **E**xplore | Ask a clarifying question | "Задай уточняющий вопрос, чтобы понять корень" |
| **R**espond | Address with facts from briefing | "Ответь фактом из брифинга, закрывающим возражение" |

### Common Objection Patterns

Encode these in the system prompt:

1. **"Дорого"** → Explore total cost of ownership, not just price. Ask what they compare with.
2. **"Нам не нужно"** → Explore current pain points. Often the need exists but isn't articulated.
3. **"Мы уже используем X"** → Don't attack competitor. Ask what they wish was different.
4. **"Нужно подумать"** → This means unresolved concerns. Ask what specific question remains.
5. **"Пришлите на почту"** → Polite rejection. Try to identify the real blocker right now.

## Conversational Intelligence

### Tone Calibration

The coaching field should suggest adjustments based on conversation dynamics:

| Signal | Coaching Response |
|--------|-------------------|
| Client is enthusiastic | "Поддержи энергию, предложи следующий шаг" |
| Client is hesitant | "Замедлись, задай открытый вопрос" |
| Client is frustrated | "Эмпатия первым делом, потом решение" |
| Client is off-topic | "Мягко верни к теме через мостик" |
| Client asks technical question | "Ответь фактом, если не знаешь — честно скажи и предложи уточнить" |

### Conversational Bridges

When the rep needs to redirect, suggest bridge phrases:
- "Это отличный вопрос, и он связан с..." (redirect to value prop)
- "Понимаю вашу точку зрения. А как сейчас у вас решается..." (redirect to pain)
- "Кстати, раз уж мы об этом..." (natural transition)

### Humor and Rapport

Appropriate use of light humor in coaching:
- **When appropriate:** To defuse tension, build rapport after formal intro, lighten heavy topics
- **When NOT appropriate:** During serious objections, pricing discussions, when client is frustrated
- **Format:** Suggest the rep use situational humor ("можно пошутить про..."), never provide canned jokes
- **Rule:** Humor must be relevant to the conversation context, never forced

## Prompt Structure Template

### System Prompt Pattern

```
1. ROLE IDENTITY (who you are, what you know)
2. CONTEXT (what's happening: real-time sales call)
3. KNOWLEDGE DOMAINS (psychology, objections, product)
4. DECISION RULES (priority-ordered if/then)
5. OUTPUT FORMAT (JSON schema with field order)
6. CONSTRAINTS (brevity, language, forbidden patterns)
```

### Decision Rules Priority

Rules should be checked in order — first match wins:

```
1. OFF-TOPIC → redirect hint
2. OBJECTION → LAER-based response
3. QUESTION → factual answer from briefing
4. POSITIVE SIGNAL → reinforce + next step
5. NEUTRAL → suggest a probing question or talking point
```

## Anti-Patterns

| Anti-Pattern | Why It Fails | Better Approach |
|--------------|-------------|-----------------|
| Generic hints ("Уточните детали") | No actionable value | Reference specific briefing content |
| Too many instructions in prompt | Cognitive overload, model ignores later rules | Prioritized rule list, first match wins |
| Telling rep what to say verbatim | Sounds robotic, rep loses authenticity | Suggest the idea, let rep phrase it naturally |
| Ignoring conversation history | Repeated hints, no progression | Use history to track what's been discussed |
| Always-positive feedback | Rep doesn't learn | Honest coaching: warn on mistakes, praise good moves |

## Quality Signals

A good hint should pass these checks:
1. **Specific** — references something from the briefing or conversation
2. **Timely** — relevant to what was JUST said, not 5 minutes ago
3. **Actionable** — the rep knows what to do RIGHT NOW
4. **Brief** — 1-2 sentences, scannable in 2 seconds
5. **Psychologically grounded** — accounts for buyer's emotional state

## Integration with SGR

This skill complements `sgr-architect`:
- Use SGR for structuring the JSON output schema
- Use this skill for the **content** of system prompts
- `reasoning` field before `hint` = SGR cascade pattern applied to sales coaching
