# AI Sales Copilot — Live Call Screen Redesign

## Контекст задачи

AI Sales Copilot — Chrome Extension (React + TypeScript), сайдбар ~380px шириной. Этот документ описывает экран **во время звонка** — менеджер разговаривает с клиентом, Copilot в реальном времени слушает, распознаёт речь и показывает подсказки. Менеджер **не может читать** длинные тексты — у него клиент на проводе. Каждый элемент UI должен считываться периферийным зрением за 1 секунду.

Этот экран стилистически является продолжением Brief Panel (см. отдельную спецификацию). Общий визуальный язык: flat surfaces, 0.5px borders, pills/tags, цветовые акценты через border-left, минимум текста.

## Цель

Во время звонка менеджер одним взглядом (≤1 сек) понимает:
1. Что сейчас делать (AI-подсказка — одна фраза)
2. Как идёт баланс разговора (talk ratio)
3. Получил ли positive feedback (возражение отработано)
4. Что было сказано (транскрипт, фоновый поток)

---

## Data Contract

### Основные типы

```typescript
// === Состояние записи ===
interface RecordingState {
  isRecording: boolean;
  elapsedSeconds: number;       // 0..N, форматировать как MM:SS
  micLevel: number;             // 0.0..1.0 — уровень сигнала микрофона
}

// === Статусы сервисов ===
interface ServiceStatus {
  name: string;                 // "Yandex STT" | "LLM" | "Redis"
  connected: boolean;
}

// === AI-подсказка (основной блок) ===
type HintType = 'coaching' | 'success' | 'warning';

interface AIHint {
  id: string;
  type: HintType;
  headline: string;             // "Переходите к коммерческому предложению" (макс. ~50 символов)
  detail?: string;              // "Клиент подтвердил проблему с Bitrix24..." (макс. ~100 символов)
  timestamp: number;            // unix ms — для auto-dismiss
}

// === Talk Ratio ===
interface TalkRatio {
  managerPercent: number;       // 0..100
  clientPercent: number;        // 0..100 (всегда 100 - managerPercent)
  trend: 'manager_heavy' | 'balanced' | 'client_heavy';
  waveform: WaveSegment[];      // последние ~60 сегментов для визуализации
}

interface WaveSegment {
  speaker: 'manager' | 'client';
  amplitude: number;            // 0.0..1.0 — высота столбика
}

// === Транскрипт ===
type TranscriptItemType = 'message' | 'event';

interface TranscriptMessage {
  type: 'message';
  id: string;
  speaker: 'manager' | 'client';
  text: string;
  timestamp: string;            // "03:42" — уже отформатировано
  isInterim?: boolean;          // true = ещё распознаётся, курсивом
}

interface TranscriptEvent {
  type: 'event';
  id: string;
  label: string;                // "Возражение отработано: интеграция 1С"
  eventType: 'objection_handled' | 'topic_detected' | 'action_item';
}

type TranscriptItem = TranscriptMessage | TranscriptEvent;

// === Контекстные табы ===
type ContextTab = 'hints' | 'objections' | 'briefing' | 'strategy';

// === Полное состояние экрана ===
interface LiveCallState {
  recording: RecordingState;
  services: ServiceStatus[];
  currentHint: AIHint | null;
  talkRatio: TalkRatio;
  transcript: TranscriptItem[];  // reverse chronological (newest first)
  activeTab: ContextTab;
}
```

### Обновление в реальном времени

Компонент получает обновления через callback-пропсы или state management (Redux/Zustand):

```typescript
interface LiveCallCallbacks {
  onStopRecording: () => void;
  onTabChange: (tab: ContextTab) => void;
  onHintDismiss: (hintId: string) => void;
}
```

Данные приходят через WebSocket. Компонент **не управляет** подключением — только рендерит текущее состояние.

---

## Компонентная структура

```
<LiveCallPanel state={LiveCallState} callbacks={LiveCallCallbacks}>
  ├── <PanelHeader />                      // логотип, версия, settings icon
  ├── <RecordingBar                        // СТОП, микрофон visualizer, таймер
  │     recording, onStop />
  ├── <ServiceStatusRow services />         // зелёные точки STT/LLM/Redis
  ├── <AIHintCard hint, activeTab />        // подсказка / успех / предупреждение
  ├── <TalkRatioBar talkRatio />            // полоса + waveform + текстовая подсказка
  ├── <ContextTabStrip                     // горизонтальные pills
  │     activeTab, onTabChange />
  ├── <Divider />
  └── <TranscriptFeed transcript />         // живой поток сообщений + events
```

---

## Визуальные правила

### Общие (наследуются от Brief Panel)

| Параметр | Значение |
|----------|----------|
| Ширина панели | 380px (фиксированная) |
| Фон | `--background-primary` |
| Шрифт | System sans-serif, 13px base |
| Разделители | 0.5px solid `--border-tertiary` |
| Радиус карточек | 12px (lg) |
| Паддинг секций | 16px горизонтальный |

---

### RecordingBar

Верхняя строка с контролами записи.

| Элемент | Спецификация |
|---------|-------------|
| Кнопка СТОП | border: 1.5px solid `#E24B4A`, font: 12px/500, color: `#E24B4A`, bg: transparent, border-radius: `--border-radius-md`. Квадратная точка 8×8px `#E24B4A` с border-radius: 2px слева от текста. Пульсация точки: opacity 1→0.4→1, 1.2s ease-in-out infinite |
| Микрофон-визуализер | 5 вертикальных баров, width: 2px, border-radius: 1px, color: `--text-info`. Высоты [6, 10, 14, 10, 6]px в покое. Анимация: scaleY(0.4)→1→0.4, 0.6s infinite, каждый bar со сдвигом 0.1s. **В реальном продукте**: привязать scaleY к `recording.micLevel` |
| Таймер | 13px/500, `--text-primary`, font-variant-numeric: tabular-nums. Формат: `MM:SS` |
| Layout | flex, align-items: center, gap: 12px, padding: 10px 16px |

---

### ServiceStatusRow

Одна строка под RecordingBar.

- Flex centered, gap: 12px, font: 11px, color: `--text-tertiary`
- Зелёная точка: 6×6px, border-radius: 50%, background: `#5DCAA5`
- Если сервис disconnected: точка `#E24B4A`, текст с opacity: 0.5
- padding: 6px 16px, border-bottom: 0.5px solid `--border-tertiary`

---

### AIHintCard (ключевой блок)

Единственный блок, на который менеджер смотрит осознанно. Три варианта отображения по `type`:

#### Coaching (amber) — подсказка что делать

```
┌─────────────────────────────────────┐
│▎ ПОДСКАЗКА                          │
│▎ Переходите к комм. предложению     │  ← headline, 14px/500
│▎ Клиент подтвердил проблему...      │  ← detail, 12px/400
└─────────────────────────────────────┘
```

| Свойство | Значение |
|----------|----------|
| Background | `#FFF8F0` (тёплый amber-50-ish) |
| Border-left | 3px solid `#EF9F27` (amber-400) |
| Border-radius | 0 (single-sided border) |
| Label "ПОДСКАЗКА" | 11px/500, uppercase, letter-spacing: 0.5px, color: `#854F0B` (amber-800) |
| Headline | 14px/500, color: `#633806` (amber-900) |
| Detail | 12px/400, color: `#854F0B` (amber-800) |
| Padding | 14px 16px |

#### Success (green) — возражение отработано

```
┌─────────────────────────────────────┐
│▎ ✓  Возражение отработано           │  ← icon + headline
│▎    Клиент принял аргумент про...   │  ← detail
└─────────────────────────────────────┘
```

| Свойство | Значение |
|----------|----------|
| Background | `#EAF3DE` (green-50) |
| Border-left | 3px solid `#639922` (green-400) |
| Icon | Круг 24×24px, bg: `#639922`, внутри SVG галочка (path "M3 7.5l3 3 5-6") stroke: #fff, stroke-width: 2 |
| Layout | flex, align-items: center, gap: 8px (icon + text block) |
| Headline | 14px/500, color: `#27500A` (green-800) |
| Detail | 12px/400, color: `#3B6D11` (green-600) |

#### Warning (red) — предупреждение

```
┌─────────────────────────────────────┐
│▎ ВНИМАНИЕ                           │
│▎ Клиент теряет интерес              │
│▎ Задайте уточняющий вопрос          │
└─────────────────────────────────────┘
```

| Свойство | Значение |
|----------|----------|
| Background | `#FEF5F5` (чуть теплее red-50) |
| Border-left | 3px solid `#E24B4A` (red-400) |
| Label "ВНИМАНИЕ" | 11px/500, color: `#791F1F` (red-800) |
| Headline | 14px/500, color: `#501313` (red-900) |
| Detail | 12px/400, color: `#791F1F` (red-800) |

#### Поведение смены подсказок

- **Coaching → Coaching**: плавная замена текста, без анимации контейнера
- **Coaching → Success**: карточка меняет цвет amber→green за 200ms (CSS transition на background + border-color)
- **Success auto-dismiss**: через 4 секунды success карточка возвращается к последнему coaching hint. Таймер хранится в `hint.timestamp`, компонент считает разницу
- **Warning**: остаётся пока бэкенд не пришлёт новый hint

---

### TalkRatioBar

Визуализация баланса разговора.

#### Основная полоса

| Свойство | Значение |
|----------|----------|
| Track | height: 6px, border-radius: 3px, background: `#EAF3DE` (green-50, означает "территория клиента") |
| Fill (менеджер) | height: 100%, border-radius: 3px, background: `--text-info` (синий). Width = `{managerPercent}%`, transition: width 0.8s ease |

#### Лейблы

- Flex space-between над полосой
- Левый: "Вы **68%**" — "Вы" в 11px tertiary, процент в 12px/500 primary
- Правый: "**32%** Клиент" — аналогично
- Числа обновляются в реальном времени через пропсы

#### Waveform (история за ~2 мин)

- Под основной полосой, flex row, gap: 1px, height: 16px, centered
- ~60 вертикальных баров, width: 2px, border-radius: 1px
- Цвет: `--text-info` для manager, `#5DCAA5` для client
- Высота: `3 + amplitude * 13` px (min 3px, max 16px)
- Opacity: 0.4 — не должен отвлекать, фоновый паттерн
- Данные: из `talkRatio.waveform[]`

#### Текстовая подсказка

- Под waveform, text-align: center, 11px
- Логика:
  - `managerPercent > 65` → "Дайте клиенту больше говорить", color: `#854F0B` (amber-800)
  - `managerPercent < 35` → "Перехватите инициативу", color: `#854F0B`
  - `35 ≤ managerPercent ≤ 65` → "Отличный баланс", color: `#3B6D11` (green-600)

---

### ContextTabStrip

Горизонтальная навигация, заменяющая аккордеоны из предыдущего дизайна.

| Свойство | Значение |
|----------|----------|
| Layout | flex, gap: 6px, padding: 0 16px 12px, overflow-x: auto |
| Pill (inactive) | 11px, padding: 4px 10px, border-radius: 20px, border: 0.5px solid `--border-tertiary`, bg: `--background-primary`, color: `--text-secondary`, white-space: nowrap, cursor: pointer |
| Pill (active) | bg: `--background-info`, color: `--text-info`, border-color: transparent |
| Hover (inactive) | bg: `--background-secondary` |
| Transition | all 0.15s |

Табы: `Подсказки` | `Возражения` | `Брифинг` | `Стратегия`

При переключении таба меняется содержимое AIHintCard:
- **Подсказки** → текущий coaching/warning hint
- **Возражения** → последний success hint или список готовых ответов (из BriefData.objections)
- **Брифинг** → компактная версия ContactCard + FocusPoints из Brief Panel
- **Стратегия** → top-3 стратегических пунктов из Brief Panel

**Контент табов "Брифинг" и "Стратегия"** отображается в той же зоне, где AIHintCard, с тем же padding. Стилизация — как в Brief Panel spec (те же компоненты, но в compact режиме).

---

### TranscriptFeed

Живой поток распознанной речи.

#### Header

- Flex space-between, padding: 12px 16px 0
- "Транскрипт" — 12px/500, `--text-primary`
- LIVE badge: flex, gap: 4px, 11px/500, color: `#E24B4A`. Точка 6×6px с пульсацией (как в RecordingBar)

#### Сообщения (TranscriptMessage)

```
┌──────────────────────────────────────┐
│ Клиент  03:38                        │  ← meta row
│ ▎ Ну а как с 1С-то у вас? У нас     │  ← bar + text
│ ▎ бухгалтерия очень чувствительна... │
└──────────────────────────────────────┘
```

| Элемент | Спецификация |
|---------|-------------|
| Container | padding: 8px 0, border-bottom: 0.5px solid `--border-tertiary` |
| Meta row | flex, gap: 6px, margin-bottom: 3px |
| Speaker label | 11px/500. "Вы" → color: `--text-info` (синий). "Клиент" → color: `#1D9E75` (teal-400) |
| Timestamp | 11px, `--text-tertiary` |
| Content row | flex, gap: 8px |
| Vertical bar | width: 3px, border-radius: 1.5px, min-height: 12px, self-stretch. "Вы" → `--text-info`. "Клиент" → `#1D9E75` |
| Text | 13px/400, `--text-primary`, line-height: 1.45 |
| Interim text | Когда `isInterim: true` → color: `--text-tertiary`, font-style: italic. Обновляется по мере распознавания |

#### Events (TranscriptEvent)

Вставляются между сообщениями в хронологическом порядке.

```
         ┌───────────────────────────────────┐
         │ ✓ Возражение отработано: 1С       │
         └───────────────────────────────────┘
```

| Элемент | Спецификация |
|---------|-------------|
| Container | padding: 6px 0, text-align: center |
| Pill | inline-flex, align-items: center, gap: 4px |
| Style | 11px, color: `#3B6D11`, background: `#EAF3DE`, padding: 3px 10px, border-radius: 20px |
| Icon | SVG "+" 12×12px для `topic_detected`, галочка для `objection_handled`, точка для `action_item`. Stroke: `#3B6D11`, stroke-width: 1.5 |

#### Event types → icon mapping

| eventType | Icon | Color scheme |
|-----------|------|-------------|
| `objection_handled` | Галочка (check) | Green (bg: `#EAF3DE`, text: `#3B6D11`) |
| `topic_detected` | Плюс (+) | Blue (bg: `#E6F1FB`, text: `#185FA5`) |
| `action_item` | Стрелка вправо (→) | Amber (bg: `#FAEEDA`, text: `#854F0B`) |

#### Скролл и производительность

- Контейнер: `overflow-y: auto`, `max-height: calc(100vh - [header + ratio + tabs height])`
- Автоскролл к новому сообщению, **кроме** случая когда пользователь вручную скроллнул вверх (стандартный паттерн "sticky to bottom")
- Виртуализация: при >100 сообщений использовать `react-window` или аналог
- Interim-сообщение всегда одно (последнее) — оно обновляется на месте, не добавляется новое

---

## Анимации и переходы

Все анимации обёрнуты в `@media (prefers-reduced-motion: no-preference)`.

| Элемент | Анимация | Параметры |
|---------|---------|-----------|
| СТОП-точка | Пульсация opacity | 1→0.4→1, 1.2s ease-in-out infinite |
| Mic bars | Bounce scaleY | 0.4→1→0.4, 0.6s infinite, stagger 0.1s |
| LIVE-точка | Пульсация opacity | Та же, что СТОП |
| Talk ratio fill | Ширина | transition: width 0.8s ease |
| Hint card смена типа | Background + border | transition: background 200ms, border-color 200ms |
| Context pill switch | Background + color | transition: all 150ms |
| Success auto-dismiss | Нет анимации | Просто замена на coaching hint через 4 сек |

---

## Состояния и edge cases

### Нет подсказки (currentHint === null)

AIHintCard показывает нейтральное состояние:
```
┌─────────────────────────────────────┐
│ Слушаю разговор...                  │
│ Подсказки появятся автоматически    │
└─────────────────────────────────────┘
```
Background: `--background-secondary`, text: `--text-tertiary`, 12px. Без border-left.

### Сервис отключён

- Точка в ServiceStatusRow становится красной
- Если STT disconnected → транскрипт перестаёт обновляться, показать banner:
  ```
  ⚠ Распознавание речи недоступно. Проверьте подключение.
  ```
  Background: `#FEF5F5`, color: `#791F1F`, 12px, padding: 8px 16px.

### Пустой транскрипт (начало записи)

Показать placeholder:
```
Начните говорить — транскрипт появится здесь
```
12px, `--text-tertiary`, text-align: center, padding: 24px 0.

### Очень длинный hint headline

Обрезать через `text-overflow: ellipsis` на 2 строки (line-clamp: 2). Detail — на 2 строки.

---

## Dark Mode

Все цвета семантические через CSS-переменные, кроме цветных карточек:

| Элемент | Light | Dark |
|---------|-------|------|
| Coaching card bg | `#FFF8F0` | `#412402` (amber-900) |
| Coaching card border | `#EF9F27` | `#EF9F27` (без изменений) |
| Coaching label | `#854F0B` | `#FAC775` (amber-100) |
| Coaching headline | `#633806` | `#FAEEDA` (amber-50) |
| Coaching detail | `#854F0B` | `#FAC775` |
| Success card bg | `#EAF3DE` | `#173404` (green-900) |
| Success card border | `#639922` | `#639922` |
| Success headline | `#27500A` | `#EAF3DE` (green-50) |
| Success detail | `#3B6D11` | `#C0DD97` (green-200) |
| Success icon bg | `#639922` | `#639922` |
| Warning card bg | `#FEF5F5` | `#501313` (red-900) |
| Warning card border | `#E24B4A` | `#E24B4A` |
| Warning label | `#791F1F` | `#F7C1C1` (red-100) |
| Warning headline | `#501313` | `#FCEBEB` (red-50) |
| Talk ratio track | `#EAF3DE` | `#173404` |
| Waveform bars | opacity 0.4 | opacity 0.5 (чуть ярче) |
| Event pill bg | `#EAF3DE` | `#173404` |
| Event pill text | `#3B6D11` | `#C0DD97` |
| Transcript bar (you) | `--text-info` | `--text-info` |
| Transcript bar (client) | `#1D9E75` | `#5DCAA5` (teal-200, ярче) |

Реализация: CSS media query `@media (prefers-color-scheme: dark)` или класс `.dark` на root, в зависимости от архитектуры приложения.

---

## Accessibility

- Все интерактивные элементы: `tabIndex`, `role="button"`, `aria-label`
- Кнопка СТОП: `aria-label="Остановить запись"`
- Context pills: `role="tablist"` + `role="tab"` + `aria-selected`
- LIVE-индикатор: `aria-live="polite"` на новых сообщениях транскрипта
- Анимации: `@media (prefers-reduced-motion: reduce)` → отключить все keyframe-анимации
- Talk ratio: `aria-label="Баланс разговора: менеджер 68%, клиент 32%"`
- Контраст: минимум 4.5:1 по WCAG AA для всех текстов

---

## Acceptance Criteria

1. [ ] Компонент `LiveCallPanel` принимает `LiveCallState` через пропсы, без хардкода данных
2. [ ] RecordingBar показывает таймер в формате MM:SS с tabular-nums
3. [ ] Mic visualizer анимирован в idle, в реальном продукте привязывается к micLevel
4. [ ] AIHintCard корректно рендерит три варианта: coaching (amber), success (green), warning (red)
5. [ ] Success hint автоматически dismissится через 4 секунды и возвращается к coaching
6. [ ] Talk ratio обновляется плавно (transition 0.8s), waveform рендерит ~60 баров
7. [ ] Текстовая подсказка talk ratio динамически меняется по порогам (35% / 65%)
8. [ ] ContextTabStrip переключает контент в зоне hint-карточки
9. [ ] TranscriptFeed авто-скроллится к новым сообщениям (sticky to bottom)
10. [ ] Interim-сообщение обновляется на месте (не добавляется новый элемент)
11. [ ] TranscriptEvent корректно маппит eventType → icon + color
12. [ ] Dark mode работает для всех цветных элементов
13. [ ] Состояние "нет подсказки" (null hint) показывает placeholder
14. [ ] Состояние "сервис отключён" показывает warning banner
15. [ ] Ширина строго 380px, нет горизонтального overflow
16. [ ] Все анимации обёрнуты в prefers-reduced-motion

---

## Файловая структура

```
src/components/live-call/
├── LiveCallPanel.tsx              // главный контейнер
├── LiveCallPanel.module.css       // стили (CSS Modules)
├── RecordingBar.tsx
├── ServiceStatusRow.tsx
├── AIHintCard.tsx                 // coaching | success | warning
├── TalkRatioBar.tsx               // полоса + waveform + hint text
├── ContextTabStrip.tsx
├── TranscriptFeed.tsx             // scroll container
├── TranscriptMessage.tsx
├── TranscriptEvent.tsx
├── Divider.tsx                    // shared with brief/
├── types.ts                       // LiveCallState, AIHint, etc.
├── constants.ts                   // пороги talk ratio, auto-dismiss timing
├── hooks/
│   ├── useAutoScroll.ts           // sticky-to-bottom логика
│   └── useHintAutoDismiss.ts      // 4-sec success dismiss
└── __tests__/
    ├── LiveCallPanel.test.tsx
    ├── AIHintCard.test.tsx
    └── TalkRatioBar.test.tsx
```

---

## Пример использования

```tsx
import { LiveCallPanel } from './components/live-call/LiveCallPanel';
import type { LiveCallState } from './components/live-call/types';

const state: LiveCallState = {
  recording: {
    isRecording: true,
    elapsedSeconds: 222, // 03:42
    micLevel: 0.65,
  },
  services: [
    { name: 'Yandex STT', connected: true },
    { name: 'LLM', connected: true },
    { name: 'Redis', connected: true },
  ],
  currentHint: {
    id: 'hint-1',
    type: 'coaching',
    headline: 'Переходите к коммерческому предложению',
    detail: 'Клиент подтвердил проблему с Bitrix24. Самое время предложить пилот СберCRM.',
    timestamp: Date.now(),
  },
  talkRatio: {
    managerPercent: 68,
    clientPercent: 32,
    trend: 'manager_heavy',
    waveform: Array.from({ length: 60 }, () => ({
      speaker: Math.random() > 0.35 ? 'manager' as const : 'client' as const,
      amplitude: 0.2 + Math.random() * 0.8,
    })),
  },
  transcript: [
    {
      type: 'event',
      id: 'evt-1',
      label: 'Возражение отработано: интеграция 1С',
      eventType: 'objection_handled',
    },
    {
      type: 'message',
      id: 'msg-1',
      speaker: 'client',
      text: 'Ну а как с 1С-то у вас? У нас бухгалтерия очень чувствительна к этому вопросу.',
      timestamp: '03:38',
    },
    {
      type: 'message',
      id: 'msg-2',
      speaker: 'manager',
      text: 'Алексей Владимирович, у СберCRM нативная интеграция — никаких костылей, данные синхронизируются автоматически в обе стороны.',
      timestamp: '03:25',
    },
    {
      type: 'message',
      id: 'msg-3',
      speaker: 'client',
      text: 'Мы пробовали Bitrix, но он начал тормозить, когда сделок стало больше десяти тысяч.',
      timestamp: '03:12',
    },
    {
      type: 'message',
      id: 'msg-4',
      speaker: 'manager',
      text: 'Да, это частая проблема у компаний с такими объёмами...',
      timestamp: '02:58',
      isInterim: true,
    },
  ],
  activeTab: 'hints',
};

const callbacks = {
  onStopRecording: () => console.log('stop'),
  onTabChange: (tab) => console.log('tab:', tab),
  onHintDismiss: (id) => console.log('dismiss:', id),
};

<LiveCallPanel state={state} callbacks={callbacks} />
```

---

## Связь с Brief Panel

Оба экрана — часть одного Chrome Extension. Общие элементы:

| Компонент | Shared |
|-----------|--------|
| `<PanelHeader />` | Идентичный (логотип + версия) |
| `<Divider />` | Идентичный |
| `<ServiceStatusRow />` | Идентичный |
| Цветовая палитра | Полностью совпадает |
| Типографика | Полностью совпадает |
| Радиусы, border-width | Полностью совпадает |

Переход между экранами: нажатие REC на Brief Panel → переход на Live Call Panel. Нажатие СТОП → возврат на Brief Panel (или экран результатов — отдельная спецификация).

Табы "Брифинг" и "Стратегия" в ContextTabStrip переиспользуют компоненты `ContactCard`, `FocusPoints`, `ObjectionCards` из Brief Panel spec, но в compact-режиме (меньше padding, без expand button).
