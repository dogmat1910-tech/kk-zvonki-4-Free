"""
prompt_builder.py — формирует промпт для Gemini на основе чеклиста из БД.

Промпт строится динамически: берёт активные правила чеклиста,
веса этапов для конкретного типа звонка и инструктирует модель
вернуть строго валидный JSON по заданной схеме.
"""

from core.database import get_checklist_rules, get_stage_weights
import pandas as pd


CALL_TYPE_LABELS = {
    "primary_inbound":  "Первичный входящий звонок",
    "primary_outbound": "Первичный исходящий звонок",
    "confirmation":     "Звонок-подтверждение явки на БК",
    "repeat":           "Повторный звонок после отказа или без результата",
    "inactive":         "Нецелевой / короткий звонок",
    "unknown":          "Тип не определён",
}

STAGE_LABELS = {
    "contact":         "Установление контакта",
    "needs":           "Выявление потребностей",
    "qualification":   "Квалификация",
    "presentation":    "Презентация БК",
    "objections":      "Работа с возражениями",
    "closing":         "Закрытие",
    "summary":         "Резюмирование",
    "commitment":      "Фиксация явки",
    "speech":          "Стройность речи",
    "control":         "Управление диалогом",
    "salesmanship":    "Продажность",
    "tone":            "Тон менеджера",
    "client_state":    "Психосостояние клиента",
    "client_reaction": "Реакция клиента на аргументы",
    "reminder":        "Напоминание о консультации",
    "confirm_datetime":"Подтверждение даты и времени",
    "confirm_address": "Подтверждение адреса",
    "what_to_bring":   "Что взять с собой",
    "motivation":      "Усиление мотивации прийти",
    "risk_detection":  "Выявление риска неявки",
    "doubts":          "Отработка сомнений",
    "final_confirm":   "Финальное подтверждение явки",
    "past_call_link":  "Привязка к прошлому разговору",
    "past_refusal":    "Выявление причины прошлого отказа",
    "problem_update":  "Актуализация проблемы",
    "new_value":       "Новая ценность консультации",
}

SALES_TOOLS = [
    "Выявление боли",
    "Усиление боли без запугивания",
    "Выявление срочности",
    "Формирование ценности очной консультации",
    "Объяснение следующего логичного шага",
    "Альтернативный выбор",
    "Микро-согласия",
    "Резюмирование",
    "Фиксация обязательства",
    "Предотвращение неявки",
    "Уточнение скрытого возражения",
    "Переформулирование сомнения клиента",
    "Мягкое ведение диалога",
    "Возврат к цели звонка",
    "Создание доверия",
    "Подстройка под психосостояние клиента",
    "Снятие тревоги",
    "Усиление мотивации",
    "Конкретизация следующего действия",
    "Контроль договорённости",
]

WEAK_AGREEMENT_PHRASES = [
    "постараюсь", "если получится", "возможно", "может быть",
    "посмотрим", "я подумаю", "если успею", "ну давайте",
    "ладно, запишите", "я не обещаю", "если что, перезвоню",
]

JSON_SCHEMA = """
{
  "call_type": "primary_inbound | primary_outbound | confirmation | repeat | inactive",
  "is_active_call": true,
  "client_name": "имя клиента или null",
  "qa_score": 0-100,
  "regulation_score": 0-100,
  "sales_quality_score": 0-100,
  "speech_structure_score": 0-100,
  "manager_control_score": 0-100,
  "tone_score": 0-100,
  "client_reflection_score": 0-100,
  "show_up_probability_score": 0-100,
  "objection_handling_score": 0-100,
  "closing_score": 0-100,
  "summary": "краткое резюме звонка 2-3 предложения",
  "main_problem": "главная проблема звонка",
  "main_risk": "главный риск для РОПа",
  "goal_achieved": true/false,
  "sales_stage_scores": [
    {
      "stage_code": "код этапа",
      "stage_name": "название этапа",
      "score": 0-100,
      "weight": вес,
      "evidence_quote": "цитата из звонка",
      "timestamp": "MM:SS",
      "explanation": "что хорошо и что плохо",
      "recommendation": "конкретная рекомендация с примером фразы"
    }
  ],
  "detected_errors": [
    {
      "checklist_rule_title": "название пункта чеклиста",
      "description": "описание нарушения",
      "criticality": "low | medium | high | critical",
      "evidence_quote": "точная цитата из звонка",
      "timestamp": "MM:SS",
      "confidence": 0.0-1.0,
      "status": "detected_by_ai | needs_review"
    }
  ],
  "sales_tools": [
    {
      "tool_name": "название инструмента из списка",
      "was_used": true/false,
      "quality_score": 0-100,
      "evidence_quote": "цитата или null",
      "timestamp": "MM:SS или null",
      "recommendation": "как использовать лучше или null"
    }
  ],
  "objections": [
    {
      "type": "тип возражения",
      "is_hidden": false,
      "client_phrase": "точная фраза клиента",
      "timestamp": "MM:SS",
      "manager_response": "ответ менеджера",
      "response_quality_score": 0-100,
      "was_handled": true/false,
      "recommendation": "как лучше отработать"
    }
  ],
  "weak_agreement": {
    "detected": true/false,
    "client_phrase": "фраза клиента или null",
    "timestamp": "MM:SS или null",
    "risk_reason": "почему это риск или null",
    "better_manager_phrase": "как менеджер должен был закрепить или null"
  },
  "show_up_prediction": {
    "score": 0-100,
    "risk_level": "low | medium | high | critical",
    "risk_reasons": ["причина 1", "причина 2"],
    "positive_factors": ["фактор 1"],
    "negative_factors": ["фактор 1"],
    "recommendation": "что нужно было сделать менеджеру"
  },
  "emotional_timeline": [
    {
      "timestamp": "MM:SS",
      "client_state": "cold | neutral | interested | engaged | doubtful | resistant | committed | weak_agreement | negative",
      "manager_tone": "confident | neutral | rushed | monotone | pressuring | warm | irritated",
      "note": "что происходит в этот момент",
      "evidence_quote": "цитата"
    }
  ],
  "call_timeline_events": [
    {
      "event_type": "stage | objection | weak_signal | strong_close | risk | tool_used",
      "start_time": "MM:SS",
      "end_time": "MM:SS",
      "description": "описание события",
      "quality_score": 0-100,
      "evidence_quote": "цитата",
      "related_stage": "код этапа",
      "risk_level": "low | medium | high"
    }
  ],
  "phrase_candidates": [
    {
      "phrase_text": "точная фраза из звонка",
      "phrase_type": "best | worst | forbidden | no_show_risk | closing | value | objection | commitment | trust_damage | pressure | false_expectation",
      "sales_stage": "этап продаж",
      "sales_tool": "инструмент или null",
      "timestamp": "MM:SS",
      "explanation": "почему фраза хорошая или плохая",
      "impact_score": -100 до 100
    }
  ],
  "rop_recommendations": [
    {
      "level": "call | manager | team",
      "title": "заголовок рекомендации",
      "main_problem": "суть проблемы",
      "data_evidence": ["факт 1", "факт 2"],
      "business_risk": "влияние на бизнес",
      "recommended_action": "что делать РОПу",
      "priority": "low | medium | high | critical"
    }
  ]
}
"""


def build_prompt(transcript_text: str, checklist_df: pd.DataFrame,
                 stage_weights_df: pd.DataFrame) -> str:
    """
    Строит полный промпт для Gemini.
    transcript_text — полный текст транскрипта с таймкодами и пометками спикеров.
    """
    # Формируем чеклист
    checklist_lines = []
    for _, row in checklist_df.iterrows():
        line = f"  [{row.get('criticality','medium').upper()}] {row['title']}"
        if row.get("description"):
            line += f"\n    → {row['description']}"
        if row.get("forbidden_phrases"):
            line += f"\n    ⛔ Запрещённые формулировки: {row['forbidden_phrases']}"
        if row.get("ai_instruction"):
            line += f"\n    🤖 Инструкция для ИИ: {row['ai_instruction']}"
        if row.get("positive_examples"):
            line += f"\n    ✅ Пример правильного: {row['positive_examples']}"
        if row.get("negative_examples"):
            line += f"\n    ❌ Пример нарушения: {row['negative_examples']}"
        if row.get("recommendation_template"):
            line += f"\n    💡 Шаблон рекомендации: {row['recommendation_template']}"
        checklist_lines.append(line)
    checklist_text = "\n\n".join(checklist_lines)

    # Формируем веса этапов
    weights_lines = []
    for _, row in stage_weights_df.iterrows():
        weights_lines.append(f"  {row['stage_name']} (код: {row['stage_code']}): вес {row['weight']}")
    weights_text = "\n".join(weights_lines) if weights_lines else "  (веса не заданы)"

    # Инструменты продаж
    tools_text = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(SALES_TOOLS))

    # Слабые согласия
    weak_text = ", ".join(f'"{p}"' for p in WEAK_AGREEMENT_PHRASES)

    prompt = f"""Ты — AI-супервайзер и эксперт по телефонным продажам в юридической компании,
которая помогает клиентам с освобождением от военной службы.

КОНТЕКСТ КОМПАНИИ:
- БК = бесплатная консультация (цель звонка — записать клиента)
- ВБ = военный билет
- ОФИС = личная встреча в офисе (клиенты из Москвы, МО, СПб, ЛО — до 150 км, или из городов с офисом — до 100 км)
- ДИСТ = дистанционная консультация (клиенты из других регионов)
- Утиль = клиент не подходит под услугу
- МЛМ = сбор контактов знакомых
- Матрёшка = предложение прийти с другом
- LegalHelp = мобильное приложение компании

━━━━━━━━━━━━━━━━━━━━━━━━━━
ШАГ 1: ОПРЕДЕЛИ ТИП ЗВОНКА
━━━━━━━━━━━━━━━━━━━━━━━━━━
Варианты типов:
- primary_inbound  — первичный входящий (клиент позвонил сам)
- primary_outbound — первичный исходящий (менеджер позвонил первым)
- confirmation     — звонок-подтверждение явки на уже назначенную БК
- repeat           — повторный звонок после прошлого отказа или без результата
- inactive         — нецелевой звонок (недозвон, сброс, короткий разговор до 45 сек, автоответчик)

━━━━━━━━━━━━━━━━━━━━━━━━━━
ШАГ 2: ПРОВЕРЬ АКТИВНОСТЬ
━━━━━━━━━━━━━━━━━━━━━━━━━━
Звонок считается АКТИВНЫМ если:
- длительность > 45 секунд И
- есть содержательный диалог

Если звонок НЕАКТИВНЫЙ:
- is_active_call = false
- Не оценивай по чеклисту
- Укажи причину в summary (недозвон / сброс / автоответчик / слишком короткий)
- Все score-поля = 0
- detected_errors, sales_stage_scores — пустые массивы
- show_up_prediction.score = 0, risk_level = "critical"

━━━━━━━━━━━━━━━━━━━━━━━━━━
ШАГ 3: ОЦЕНИ АКТИВНЫЙ ЗВОНОК
━━━━━━━━━━━━━━━━━━━━━━━━━━

ЧЕКЛИСТ (нарушения для проверки):
{checklist_text}

ВЕСА ЭТАПОВ ПРОДАЖ (для данного типа звонка):
{weights_text}

ИНСТРУМЕНТЫ ПРОДАЖ (детектировать: использован или нет):
{tools_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━
ПРАВИЛА ОЦЕНКИ
━━━━━━━━━━━━━━━━━━━━━━━━━━

ИТОГОВЫЙ QA SCORE (0–100):
Рассчитывается как взвешенное среднее баллов по этапам (используй веса из таблицы выше).
Нормализуй до 100.

REGULATION SCORE (0–100):
Доля соблюдённых обязательных пунктов чеклиста (вес каждого — его criticality).

SALES QUALITY SCORE (0–100):
Субъективная оценка качества продаж: насколько менеджер вёл клиента к цели, использовал инструменты, работал с возражениями.

SPEECH STRUCTURE SCORE (0–100):
Логика диалога, последовательность этапов, отсутствие хаоса, чёткие переходы.

MANAGER CONTROL SCORE (0–100):
Менеджер управлял диалогом или клиент вёл менеджера. Удерживал ли цель. Возвращал ли к записи.

TONE SCORE (0–100):
Уверенность, доброжелательность, спокойствие. Штрафы за давление, раздражение, монотонность.

CLIENT REFLECTION SCORE (0–100):
Насколько клиент стал теплее к концу звонка. Рост доверия и вовлечённости.

SHOW_UP_PROBABILITY (0–100):
Прогноз вероятности, что клиент придёт на консультацию:
80–100 = высокая | 60–79 = средняя | 40–59 = риск | 0–39 = высокий риск
Факторы снижения: "постараюсь", "может быть", "если успею", нет подтверждения адреса, нет резюме, нет фиксации обязательства.

СЛАБОЕ СОГЛАСИЕ — искать фразы: {weak_text}

СКРЫТЫЕ ВОЗРАЖЕНИЯ — искать:
клиент отвечает односложно, уходит от конкретного времени, спрашивает "а зачем ехать?",
говорит "мне просто узнать", меняет тему, просит прислать информацию,
не подтверждает явку уверенно, говорит "я посмотрю".

УРОВНИ КРИТИЧНОСТИ ОШИБОК:
- low = незначительное нарушение (вежливость, темп)
- medium = заметное нарушение (пропущен этап)
- high = серьёзное нарушение (не собрал данные, не отработал возражение)
- critical = критическое нарушение (неверный ОФИС/ДИСТ, ложная информация, фатальные ошибки)

ПРАВИЛА ДЛЯ EVIDENCE:
- Каждая ошибка ОБЯЗАТЕЛЬНО должна иметь evidence_quote — точную цитату из звонка.
- Каждая ошибка ОБЯЗАТЕЛЬНО должна иметь timestamp если есть таймкод.
- Если ошибка спорная или требует проверки — status = "needs_review".
- Не придумывай факты. Если данных нет — пиши null.

━━━━━━━━━━━━━━━━━━━━━━━━━━
ТРАНСКРИПТ ЗВОНКА:
━━━━━━━━━━━━━━━━━━━━━━━━━━
{transcript_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━
ВАЖНО:
━━━━━━━━━━━━━━━━━━━━━━━━━━
- Верни ТОЛЬКО валидный JSON без какого-либо текста снаружи.
- Не добавляй markdown ```json``` обёртку.
- Не добавляй комментарии.
- JSON должен точно соответствовать схеме ниже.
- Все строки на русском языке.
- Числовые поля — числа, не строки.
- Булевые поля — true/false, не строки.

ТРЕБУЕМАЯ JSON-СХЕМА:
{JSON_SCHEMA}
"""
    return prompt


def build_transcription_prompt() -> str:
    """Промпт для транскрибации аудио с диаризацией."""
    return """Транскрибируй аудиозапись телефонного звонка.

Требования:
1. Разделяй речь на сегменты по спикерам.
2. Определяй спикеров: "Менеджер" или "Клиент".
3. Добавляй таймкоды в формате [MM:SS] в начале каждого сегмента.
4. Если спикер неясен — пиши "Неизвестно".
5. Сохраняй речь дословно, включая слова-паразиты, паузы ("э...", "ну...").
6. Каждый сегмент с новой строки.

Формат каждой строки:
[MM:SS] Менеджер: текст речи
[MM:SS] Клиент: текст речи

Верни ТОЛЬКО транскрипт, без лишних пояснений."""
