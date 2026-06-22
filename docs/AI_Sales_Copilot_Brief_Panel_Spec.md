# AI Sales Copilot — Brief Panel Redesign

## Контекст задачи

AI Sales Copilot — Chrome Extension (React + TypeScript), сайдбар ~380px шириной. Перед звонком менеджер видит **бриф по клиенту** — подготовленную AI стратегию разговора. Текущий дизайн перегружен текстом и не сканируется за 10 секунд. Нужен редизайн: dashboard для быстрого сканирования, а не документ для чтения.

## Цель

Менеджер за **3–4 коротких взгляда** (≤10 сек) понимает:
1. С кем говорит (роль, компания, тип личности)
2. На чём фокусироваться (3 ключевых действия)
3. Главный числовой аргумент (ROI)
4. Что отвечать на возражения

При этом сохраняется возможность открыть полный бриф.

---

## Data Contract

Бэкенд отдаёт JSON следующей структуры. Компонент **не должен** хардкодить данные — всё приходит из пропсов.

```typescript
interface BriefData {
  // Блок 1: Кто
  contact: {
    role: string;             // "Коммерческий директор"
    company: string;          // 'ООО «СтройГрупп»'
    companyDetail?: string;   // "5 филиалов"
    avatarInitials: string;   // "КД"
    budgetNote?: string;      // "Согласовывает ген. директор Петров С.А."
  };

  // Теги поведенческого профиля (макс. 3 штуки)
  profileTags: Array<{
    label: string;            // "ROI-ориентирован"
    color: 'blue' | 'green' | 'amber'; // цветовая схема тега
  }>;

  // Блок 2: Что делать (строго 3 пункта)
  focusPoints: Array<{
    headline: string;         // "Экономия 2ч/день"
    detail: string;           // "CRM сам заполняет карточки после звонков"
  }>; // length === 3

  // Блок 3: Боли клиента (компактный список)
  painPoints: string[];       // ["2 часа/день на ручное заполнение CRM", ...]

  // Блок 4: ROI — главный числовой аргумент
  roi: {
    value: string;            // "42 млн ₽"
    description: string;      // "потенциальная допвыручка/год при внедрении СберCRM"
  };

  // Блок 5: Сравнение с текущим решением
  comparison: {
    current: {
      name: string;           // "Bitrix24"
      price: string;          // "~35 000 ₽/мес"
      cons: string;           // "тормозит, нет 1С"
    };
    proposed: {
      name: string;           // "СберCRM Бизнес"
      price: string;          // "23 460 ₽/мес"
      pros: string;           // "40 лицензий, –15% год"
    };
  };

  // Блок 6: Возражения с готовыми ответами (2–3 штуки)
  objections: Array<{
    question: string;         // "У нас уже есть Bitrix24"
    answer: string;           // "СберCRM дешевле на 33%..."
  }>;

  // Полный бриф (для раскрытия)
  fullBrief?: string;         // markdown-текст полного брифа
}
```

---

## Компонентная структура

```
<BriefPanel brief={BriefData}>
  ├── <BriefHeader />                    // логотип, версия, статусы сервисов
  ├── <RecordingBar />                   // кнопка REC, статус
  ├── <ContactCard contact, profileTags /> // аватар, роль, компания, теги
  ├── <Divider />
  ├── <FocusPoints focusPoints />         // 3 numbered action items
  ├── <PainPoints painPoints />           // compact pain list
  ├── <Divider />
  ├── <RoiHighlight roi />                // крупное число + описание
  ├── <ComparisonCards comparison />       // old vs new side-by-side
  ├── <Divider />
  ├── <ObjectionCards objections />        // Q&A формат
  └── <ExpandButton />                    // "Открыть полный бриф"
```

---

## Визуальные правила

### Общие

| Параметр | Значение |
|----------|----------|
| Ширина панели | 380px (фиксированная, Chrome sidebar) |
| Фон | `--background-primary` (белый / тёмный в dark mode) |
| Шрифт | System sans-serif, 13px base |
| Разделители | 0.5px solid, `--border-tertiary` |
| Радиус карточек | 12px (lg) |
| Паддинг секций | 16px горизонтальный |
| Gap между секциями | 12px |

### ContactCard

- Аватар: 40×40px, `border-radius: 10px`, градиент синий, белые инициалы 16px/500
- Имя: 15px/500
- Компания + детали: 12px, secondary color
- Бюджет: 11px, tertiary color
- Теги: pills с `border-radius: 20px`, 11px, фон + текст одного цветового семейства:
  - `blue`: bg `#E6F1FB`, text `#185FA5`
  - `green`: bg `#EAF3DE`, text `#3B6D11`
  - `amber`: bg `#FAEEDA`, text `#854F0B`

### FocusPoints (ключевой блок)

- Фон карточки: `--background-secondary`
- Лейбл "ФОКУС РАЗГОВОРА": 11px, uppercase, letter-spacing 0.5px, tertiary
- Нумерация: круг 20×20px, `--text-info` фон, белый текст 11px
- Headline: 13px/500 (жирный)
- Detail: 13px/400, secondary — через тире после headline
- Максимум 3 пункта. Если бэк отдаёт больше — обрезать.

### PainPoints

- Compact список, без карточки
- Красный `!` слева (16px, `#E24B4A`), текст 12px secondary
- Без bullets, без нумерации

### RoiHighlight

- Отдельная полоса с фоном `#EAF3DE` (green-50), `border-radius: 12px`
- Число: 22px/500, цвет `#3B6D11`
- Описание: 12px, `#3B6D11`, до 2 строк

### ComparisonCards

- Два блока в ряд (`flex`, `gap: 8px`)
- Левый (текущее решение): фон `#FCEBEB`, текст `#791F1F`
- Правый (наше предложение): фон `#EAF3DE`, текст `#27500A`
- Название: 11px/500, цена: 14px/500, доп. инфо: 12px/400

### ObjectionCards

- Лейбл секции: "ГОТОВЫЕ ОТВЕТЫ НА ВОЗРАЖЕНИЯ", 11px uppercase
- Вопрос: 12px/500
- Ответ: 12px/400, secondary, начинается с "→ "
- Разделитель между Q&A: 0.5px border-bottom
- Максимум 3 возражения

### ExpandButton

- На всю ширину, 12px, secondary text
- Border: 0.5px `--border-tertiary`
- Hover: `--background-secondary`
- Текст: "Открыть полный бриф →"
- Действие: раскрывает markdown-контент `fullBrief` или переключает на полноэкранный view

---

## Порядок визуального сканирования

Дизайн оптимизирован под Z-паттерн сканирования:

```
Взгляд 1 (0–2 сек):  ContactCard → теги
                       "А, это КД из СтройГрупп, любит цифры и ROI"

Взгляд 2 (2–5 сек):  FocusPoints (3 пункта)
                       "Говорю про экономию 2ч, единую воронку, нативную 1С"

Взгляд 3 (5–7 сек):  ROI число + Comparison
                       "42 млн допвыручки, мы дешевле на 33%"

Взгляд 4 (7–10 сек): Objections (по необходимости)
                       "Если скажет про Bitrix — вот ответ"
```

---

## Что НЕ делать

- ❌ Аккордеоны / collapsed секции на главном экране — всё видно сразу
- ❌ Больше 3 пунктов в FocusPoints
- ❌ Стены текста — максимум 2 строки на любой элемент
- ❌ Одинаковый визуальный вес у всех элементов — иерархия обязательна
- ❌ Числа внутри текстовых абзацев — числа всегда выделены крупно
- ❌ Маркетинговая "вода" — только конкретика и цифры

---

## Dark Mode

Все цвета должны работать в обоих режимах. Правила:
- Фоны карточек: использовать CSS-переменные `--background-*`
- Текст: `--text-primary`, `--text-secondary`, `--text-tertiary`
- Цветные блоки (ROI, Comparison, Tags): в dark mode инвертировать на тёмные оттенки того же семейства
  - Green `#EAF3DE` → `#173404` (green-900), текст `#C0DD97` (green-200)
  - Red `#FCEBEB` → `#501313` (red-900), текст `#F09595` (red-200)
  - Amber `#FAEEDA` → `#412402` (amber-900), текст `#FAC775` (amber-100)
  - Blue `#E6F1FB` → `#042C53` (blue-900), текст `#85B7EB` (blue-200)

---

## Accessibility

- Все интерактивные элементы: `tabIndex`, `role="button"`, `aria-label`
- Контраст текста: минимум 4.5:1 по WCAG AA
- Фокус-кольца на кнопках
- `prefers-reduced-motion` — отключить анимации

---

## Acceptance Criteria

1. [ ] Компонент `BriefPanel` принимает `BriefData` через пропсы, не содержит захардкоженных данных
2. [ ] Все 6 блоков рендерятся в правильном порядке при полных данных
3. [ ] Опциональные поля (`budgetNote`, `companyDetail`, `fullBrief`) gracefully скрываются при отсутствии
4. [ ] `focusPoints` обрезается до 3 элементов
5. [ ] `objections` обрезается до 3 элементов
6. [ ] Dark mode корректно работает для всех цветных блоков
7. [ ] Кнопка "Открыть полный бриф" раскрывает `fullBrief` markdown-контент
8. [ ] Панель не скроллится при типичных данных (всё помещается в ~800px высоты)
9. [ ] Ширина строго 380px, нет горизонтального overflow
10. [ ] Все текстовые блоки — максимум 2 строки с `text-overflow: ellipsis` при переполнении

---

## Файловая структура

```
src/components/brief/
├── BriefPanel.tsx            // главный контейнер
├── BriefPanel.module.css     // стили (CSS Modules)
├── ContactCard.tsx
├── FocusPoints.tsx
├── PainPoints.tsx
├── RoiHighlight.tsx
├── ComparisonCards.tsx
├── ObjectionCards.tsx
├── ExpandButton.tsx
├── Divider.tsx
├── types.ts                  // BriefData interface
└── __tests__/
    └── BriefPanel.test.tsx
```

---

## Пример использования

```tsx
import { BriefPanel } from './components/brief/BriefPanel';
import type { BriefData } from './components/brief/types';

const briefData: BriefData = {
  contact: {
    role: 'Коммерческий директор',
    company: 'ООО «СтройГрупп»',
    companyDetail: '5 филиалов',
    avatarInitials: 'КД',
    budgetNote: 'Согласовывает ген. директор Петров С.А.',
  },
  profileTags: [
    { label: 'ROI-ориентирован', color: 'blue' },
    { label: 'Любит цифры', color: 'green' },
    { label: 'Нужна интеграция 1С', color: 'amber' },
  ],
  focusPoints: [
    { headline: 'Экономия 2ч/день', detail: 'CRM сам заполняет карточки после звонков' },
    { headline: 'Единая воронка', detail: 'Все 5 филиалов в одном дашборде, прогноз выручки live' },
    { headline: 'Нативная 1С', detail: 'Без костылей, данные синхронизируются автоматически' },
  ],
  painPoints: [
    '2 часа/день на ручное заполнение CRM',
    'Нет единой воронки — филиалы ведут свои таблицы',
    'Bitrix24 тормозит при >10 000 сделок',
    'Интеграция с 1С через костыли',
  ],
  roi: {
    value: '42 млн ₽',
    description: 'потенциальная допвыручка/год при внедрении СберCRM',
  },
  comparison: {
    current: { name: 'Bitrix24', price: '~35 000 ₽/мес', cons: 'тормозит, нет 1С' },
    proposed: { name: 'СберCRM Бизнес', price: '23 460 ₽/мес', pros: '40 лицензий, –15% год' },
  },
  objections: [
    { question: '«У нас уже есть Bitrix24»', answer: 'СберCRM дешевле на 33%, нативная 1С, без тормозов. Пилот 30 дней бесплатно.' },
    { question: '«Сложно переезжать»', answer: 'Миграция за 2 недели нашей командой. Параллельная работа, ноль простоя.' },
    { question: '«Нужно согласовать с ген. директором»', answer: 'Подготовим ROI-презентацию для Петрова С.А. с расчётом окупаемости за 3 мес.' },
  ],
};

<BriefPanel brief={briefData} />
```
