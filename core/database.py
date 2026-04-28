"""
database.py — вся работа с SQLite.

Единственный источник правды для всех данных системы.
При необходимости легко заменить на Supabase: достаточно
реализовать те же функции с другим клиентом.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Optional
import pandas as pd

DB_PATH = os.environ.get("DB_PATH", "kk_calls.db")


# ─────────────────────────────────────────────
# ПОДКЛЮЧЕНИЕ
# ─────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────
# ИНИЦИАЛИЗАЦИЯ СХЕМЫ
# ─────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT,
    role        TEXT DEFAULT 'manager',   -- manager | team_lead | rop | admin
    team_id     INTEGER REFERENCES teams(id),
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS calls (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_id          INTEGER REFERENCES users(id),
    team_id             INTEGER REFERENCES teams(id),
    filename            TEXT,
    audio_path          TEXT,
    duration_seconds    INTEGER DEFAULT 0,
    call_type           TEXT DEFAULT 'unknown',
    is_active_call      INTEGER DEFAULT 1,
    direction           TEXT DEFAULT 'outbound',
    uploaded_at         TEXT DEFAULT (datetime('now')),
    call_datetime       TEXT,
    analysis_status     TEXT DEFAULT 'pending',  -- pending|processing|done|error
    review_status       TEXT DEFAULT 'auto',      -- auto|needs_review|reviewed
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS transcripts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id             INTEGER UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    full_text           TEXT,
    language            TEXT DEFAULT 'ru',
    diarization_status  TEXT DEFAULT 'done',
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id   INTEGER REFERENCES transcripts(id) ON DELETE CASCADE,
    speaker         TEXT,   -- 'manager' | 'client'
    text            TEXT,
    start_time      REAL,
    end_time        REAL,
    confidence      REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS checklist_rules (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    title                   TEXT NOT NULL,
    description             TEXT,
    call_type               TEXT DEFAULT 'all',
    sales_stage             TEXT,
    weight                  REAL DEFAULT 1.0,
    criticality             TEXT DEFAULT 'medium', -- low|medium|high|critical|disputed
    is_required             INTEGER DEFAULT 1,
    is_active               INTEGER DEFAULT 1,
    ai_instruction          TEXT,
    positive_examples       TEXT,
    negative_examples       TEXT,
    forbidden_phrases       TEXT,
    recommendation_template TEXT,
    created_at              TEXT DEFAULT (datetime('now')),
    updated_at              TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stage_weights (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_type   TEXT NOT NULL,
    stage_code  TEXT NOT NULL,
    stage_name  TEXT NOT NULL,
    weight      REAL DEFAULT 1.0,
    UNIQUE(call_type, stage_code)
);

CREATE TABLE IF NOT EXISTS qa_analyses (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id                     INTEGER UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    qa_score                    REAL DEFAULT 0,
    regulation_score            REAL DEFAULT 0,
    sales_quality_score         REAL DEFAULT 0,
    speech_structure_score      REAL DEFAULT 0,
    manager_control_score       REAL DEFAULT 0,
    tone_score                  REAL DEFAULT 0,
    client_reflection_score     REAL DEFAULT 0,
    show_up_probability_score   REAL DEFAULT 0,
    objection_handling_score    REAL DEFAULT 0,
    closing_score               REAL DEFAULT 0,
    summary                     TEXT,
    main_problem                TEXT,
    main_risk                   TEXT,
    goal_achieved               INTEGER DEFAULT 0,
    client_name                 TEXT,
    weak_agreement_detected     INTEGER DEFAULT 0,
    weak_agreement_phrase       TEXT,
    weak_agreement_risk         TEXT,
    show_up_risk_level          TEXT DEFAULT 'medium',
    show_up_risk_reasons        TEXT,  -- JSON array
    model_name                  TEXT,
    raw_json                    TEXT,
    created_at                  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sales_stage_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_analysis_id  INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    stage_code      TEXT,
    stage_name      TEXT,
    score           REAL DEFAULT 0,
    weight          REAL DEFAULT 1.0,
    evidence_quote  TEXT,
    timestamp       TEXT,
    explanation     TEXT,
    recommendation  TEXT
);

CREATE TABLE IF NOT EXISTS detected_errors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_analysis_id      INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    call_id             INTEGER REFERENCES calls(id) ON DELETE CASCADE,
    checklist_rule_id   INTEGER REFERENCES checklist_rules(id),
    title               TEXT,
    description         TEXT,
    criticality         TEXT DEFAULT 'medium',
    evidence_quote      TEXT,
    timestamp           TEXT,
    confidence          REAL DEFAULT 1.0,
    status              TEXT DEFAULT 'detected_by_ai',
    reviewed_by         INTEGER REFERENCES users(id),
    reviewed_at         TEXT,
    review_comment      TEXT
);

CREATE TABLE IF NOT EXISTS sales_tools (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_analysis_id  INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    tool_name       TEXT,
    was_used        INTEGER DEFAULT 0,
    quality_score   REAL DEFAULT 0,
    evidence_quote  TEXT,
    timestamp       TEXT,
    recommendation  TEXT
);

CREATE TABLE IF NOT EXISTS objections (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_analysis_id          INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    type                    TEXT,
    is_hidden               INTEGER DEFAULT 0,
    client_phrase           TEXT,
    timestamp               TEXT,
    manager_response        TEXT,
    response_quality_score  REAL DEFAULT 0,
    was_handled             INTEGER DEFAULT 0,
    recommendation          TEXT
);

CREATE TABLE IF NOT EXISTS emotional_timeline (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_analysis_id  INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    timestamp       TEXT,
    client_state    TEXT,
    manager_tone    TEXT,
    note            TEXT,
    evidence_quote  TEXT
);

CREATE TABLE IF NOT EXISTS call_timeline_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    qa_analysis_id  INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    event_type      TEXT,
    start_time      TEXT,
    end_time        TEXT,
    description     TEXT,
    quality_score   REAL DEFAULT 0,
    evidence_quote  TEXT,
    related_stage   TEXT,
    risk_level      TEXT DEFAULT 'low'
);

CREATE TABLE IF NOT EXISTS phrase_library (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id         INTEGER REFERENCES calls(id) ON DELETE CASCADE,
    qa_analysis_id  INTEGER REFERENCES qa_analyses(id) ON DELETE CASCADE,
    manager_id      INTEGER REFERENCES users(id),
    phrase_text     TEXT NOT NULL,
    phrase_type     TEXT DEFAULT 'neutral',  -- best|worst|forbidden|no_show_risk|closing|value|objection|commitment|trust_damage|pressure|false_expectation
    sales_stage     TEXT,
    sales_tool      TEXT,
    timestamp       TEXT,
    explanation     TEXT,
    impact_score    REAL DEFAULT 0,
    status          TEXT DEFAULT 'new',  -- new|approved|rejected
    reviewed_by     INTEGER REFERENCES users(id),
    reviewed_at     TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rop_recommendations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    level               TEXT DEFAULT 'call',  -- call|manager|team|department|training
    manager_id          INTEGER REFERENCES users(id),
    team_id             INTEGER REFERENCES teams(id),
    call_id             INTEGER REFERENCES calls(id),
    title               TEXT,
    main_problem        TEXT,
    data_evidence       TEXT,  -- JSON array
    business_risk       TEXT,
    recommended_action  TEXT,
    priority            TEXT DEFAULT 'medium',  -- low|medium|high|critical
    status              TEXT DEFAULT 'new',  -- new|in_progress|done|archived
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS training_recommendations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scope           TEXT DEFAULT 'manager',  -- manager|team|department
    manager_id      INTEGER REFERENCES users(id),
    team_id         INTEGER REFERENCES teams(id),
    title           TEXT,
    reason          TEXT,
    data_evidence   TEXT,  -- JSON
    weak_stages     TEXT,  -- JSON array
    repeated_errors TEXT,  -- JSON array
    plan_30_min     TEXT,
    plan_45_min     TEXT,
    plan_60_min     TEXT,
    exercises       TEXT,  -- JSON array
    roleplays       TEXT,  -- JSON array
    phrases_to_use  TEXT,  -- JSON array
    phrases_to_avoid TEXT, -- JSON array
    calls_to_review TEXT,  -- JSON array of call IDs
    homework        TEXT,
    metrics_to_check TEXT, -- JSON array
    status          TEXT DEFAULT 'proposed',  -- proposed|approved|completed|archived
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id   INTEGER REFERENCES users(id),
    entity_type     TEXT,
    entity_id       INTEGER,
    action          TEXT,
    before_json     TEXT,
    after_json      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
"""

DEFAULT_CHECKLIST = [
    # 1. Установление контакта
    ("Не представился, не назвал компанию, не обратился по имени", "В первые 30 секунд: представиться, назвать компанию, обратиться по имени клиента", "all", "contact", 1.0, "medium", 1, "Проверь: звучат ли имя менеджера, название компании и имя клиента в первые 30 секунд", "— Здравствуйте, меня зовут Алексей, компания ЮридическийПартнёр, я правильно понимаю, что обращаюсь к Дмитрию?", "— Алло, здравствуйте.", "", "Скажи: 'Здравствуйте, [имя клиента], меня зовут [имя менеджера], компания [название].'"),
    ("Не использовал фразы вежливости", "Использование фраз: 'подскажите, пожалуйста', 'спасибо', 'уточните, пожалуйста'", "all", "contact", 0.5, "low", 0, "Проверь наличие вежливых оборотов в течение всего диалога", "— Подскажите, пожалуйста...", "— Так значит вы...", "", "Добавь 'пожалуйста', 'спасибо' и подобные фразы в речь."),
    # 2. Выявление потребностей
    ("Не уточнил населённый пункт клиента", "Уточнить город/регион для корректного распределения ОФИС/ДИСТ", "primary_inbound,primary_outbound,repeat", "qualification", 1.5, "high", 1, "Проверь, спрашивал ли менеджер город или регион клиента", "— Скажите, из какого вы города?", "— Так, понятно. Ну что, давайте запишемся?", "", "Добавь вопрос: 'Из какого вы города/региона?'"),
    ("Не уточнил наличие повестки/отсрочки/статуса", "Уточнить: есть ли повестка, отсрочка, когда отправка", "primary_inbound,primary_outbound,repeat", "needs", 1.5, "high", 1, "Проверь, спрашивал ли менеджер про повестку, отсрочку или статус призыва", "— Скажите, уже пришла повестка или вы пока на стадии...?", "— Ясно. Тогда приходите к нам.", "", "Задай вопрос: 'Вам уже пришла повестка? Есть действующая отсрочка?'"),
    ("Не уточнил информацию по здоровью", "Уточнить: когда последний раз обследовался, есть ли медицинские документы", "primary_inbound,primary_outbound,repeat", "needs", 2.0, "high", 1, "Проверь, задавал ли менеджер вопросы про состояние здоровья", "— Есть какие-то хронические заболевания или медицинские документы?", "— Окей, понял.", "", "Спроси: 'Как у вас со здоровьем? Есть медицинские документы?'"),
    # 3. Презентация БК
    ("Использовал запрещённый аргумент «всё бесплатно»", "ЗАПРЕЩЕНО: 'мы бесплатно освободим вас', 'бесплатно поможем получить ВБ'", "all", "presentation", 2.0, "critical", 1, "Проверь, использовал ли менеджер запрещённую формулировку про 'бесплатность' освобождения", "", "— Мы бесплатно вам всё сделаем.", "'всё бесплатно', 'бесплатно освободим', 'ВБ бесплатно'", "Заменить: 'Консультация бесплатная, на ней специалист разберёт вашу ситуацию и даст план действий.'"),
    ("Уклонялся от прямого ответа на вопрос клиента", "На прямой вопрос — прямой ответ, затем дополнение", "all", "presentation", 1.5, "medium", 1, "Проверь случаи, когда клиент задавал прямой вопрос, а менеджер уходил в сторону", "— Да, именно так. Позвольте уточнить детали...", "— Ну это... зависит от многих факторов, в общем...", "", "Сначала отвечай прямо: 'Да' или 'Нет', потом объясняй."),
    ("Предоставил ложную или недостоверную информацию", "Запрещено вводить клиента в заблуждение о возможностях компании", "all", "presentation", 2.0, "critical", 1, "Проверь, не давал ли менеджер заведомо ложных обещаний или неверных фактов", "", "— Мы гарантируем, что вы не попадёте в армию.", "", "Использовать только проверенные формулировки, без гарантий исхода."),
    ("Не упомянул приложение LegalHelp", "Обязательно спросить, знает ли клиент о приложении, и порекомендовать скачать", "primary_inbound,primary_outbound", "presentation", 1.0, "medium", 1, "Проверь, упоминал ли менеджер приложение LegalHelp", "— Кстати, у нас есть мобильное приложение LegalHelp — скачайте, там можно...", "— Ладно, тогда до встречи!", "LegalHelp", "Добавить: 'Кстати, есть наше приложение LegalHelp — там удобно отслеживать ситуацию.'"),
    # 4. Возражения
    ("Недостаточно отработал возражения клиента", "Выслушать, понять опасения, привести аргументы, не спорить, вернуть к записи", "all", "objections", 2.0, "high", 1, "Проверь, как менеджер работал с возражениями: выслушал ли, аргументировал ли, вернул ли к цели", "— Понимаю ваши сомнения. Именно для этого и нужна консультация — специалист оценит ситуацию лично.", "— Ну всё понятно, просто приходите.", "", "Используй структуру: выслушать → уточнить → аргументировать → вернуть к записи."),
    # 5. Закрытие
    ("Неверное распределение ОФИС/ДИСТ", "МСК/МО/СПб/ЛО (до 150 км) и города с офисом (до 100 км) — офис; остальные — ДИСТ", "primary_inbound,primary_outbound,repeat", "closing", 10.0, "critical", 1, "КРИТИЧНО: проверь, правильно ли определён формат консультации для данного города", "", "— Ну давайте онлайн, удобнее же.", "", "Обязательно уточни город и проверь по регламенту: офис или ДИСТ."),
    ("Запись офисного лида на онлайн или ДИСТ на офис без причины", "Запрещено записывать в офис, если клиент дистанционный, и наоборот", "primary_inbound,primary_outbound,repeat", "closing", 2.0, "high", 1, "Проверь корректность формата записи относительно локации клиента", "", "— Ну ладно, запишу вас онлайн, раз вы из Москвы.", "", "Уточни город — запиши по регламенту."),
    ("Мнимая альтернатива — не предложил ближайшие даты", "Предлагать варианты день в день и ближайшие дни", "primary_inbound,primary_outbound,confirmation,repeat", "closing", 1.0, "medium", 1, "Проверь, предлагал ли менеджер конкретные ближайшие варианты", "— Могу записать вас сегодня в 16:00 или завтра в 11:00 — что удобнее?", "— Ну когда вам удобно?", "", "Называй конкретные варианты: 'сегодня в X или завтра в Y'."),
    ("Не резюмировал дату, время, адрес и что взять", "Обязательное резюме: дата, время, адрес, что взять с собой", "primary_inbound,primary_outbound,confirmation,repeat", "closing", 1.5, "high", 1, "Проверь, проговорил ли менеджер в конце дату, время, адрес и список документов", "— Итак, вы записаны: завтра в 15:00, адрес ул.Ленина 5, возьмите паспорт и медицинские документы.", "— Ну окей, до свидания.", "", "Всегда завершай резюме: 'Итого: [дата], [время], [адрес], возьмите [документы].'"),
    ("Не оставил полный комментарий по шаблону", "Шаблон: ВОЗРАСТ, ГОРОД, УЧЁБА, ВОЕНКОМАТ, ПОВЕСТКА, КАК ПЛАНИРУЕТ ДЕЙСТВОВАТЬ, ЖАЛОБЫ, ПОТРЕБНОСТЬ", "primary_inbound,primary_outbound", "closing", 2.0, "high", 1, "Это поле заполняется в CRM — проверь по контексту, насколько полно менеджер собрал информацию", "Собрал: возраст, город, наличие повестки, жалобы на здоровье, ситуацию по учёбе.", "", "", "Собери в разговоре: возраст, город, учёба/работа, военкомат, повестка, жалобы."),
    # 6. Дополнительно
    ("Неверно выбрал итог звонка", "Итог звонка должен отражать реальный результат", "all", "additional", 2.0, "medium", 1, "Проверь, соответствует ли итог реальному результату звонка по содержанию диалога", "", "Клиент записался, но менеджер выставил 'перезвонить'.", "", "Итог: если записан — 'запись', если отказ — 'отказ', если перенос — 'перенос'."),
    ("Неправильный перенос в утиль", "Утиль только для: иностранцев без гражданства, уже имеющих ВБ, служащих/служивших без интереса, спама", "all", "additional", 1.0, "medium", 0, "Проверь, корректно ли клиент определён как нецелевой (утиль)", "", "Клиент сомневается — менеджер отправил в утиль.", "", "Утиль — только по чётким критериям регламента."),
    ("Не запросил контакты знакомых (МЛМ) или не отработал возражения", "При сборе МЛМ — запросить контакты и отработать возражения при их наличии", "primary_inbound,primary_outbound", "additional", 5.0, "high", 1, "Проверь, предпринял ли менеджер попытку собрать контакты знакомых", "— Кстати, если у ваших друзей или знакомых похожая ситуация — могу записать и их, дайте контакт?", "— Ладно, до свидания.", "", "Добавь: 'Есть ли друзья или знакомые, которых тоже беспокоит эта тема?'"),
    ("Не создал искусственный дефицит через скидки", "Если запись в офис — обязательно упомянуть скидку месяца", "primary_inbound,primary_outbound", "additional", 1.5, "medium", 0, "Проверь, упоминал ли менеджер текущие скидки или специальные предложения", "— Кстати, в этом месяце у нас действует скидка — можем зафиксировать её прямо сейчас.", "", "", "Упомяни: 'Сейчас действует скидка месяца — можем зафиксировать на консультации.'"),
    ("Не предложил «матрёшку»", "Предложить клиенту прийти с другом/коллегой и собрать МЛМ", "primary_inbound,primary_outbound", "additional", 5.0, "high", 1, "Проверь, предлагал ли менеджер привести друга/коллегу на консультацию", "— Кстати, если хотите, можете прийти с другом — мы сможем проконсультировать сразу двоих.", "", "", "Добавь: 'Можете взять с собой друга — проконсультируем сразу обоих.'"),
    ("Иные фатальные ошибки", "Запись без договорённости; отмена чужой записи; фраза 'к сожалению, в вашем городе нет офиса'", "all", "additional", 10.0, "critical", 0, "Проверь наличие фатальных нарушений: отмены чужих записей, записи без согласия клиента", "", "— К сожалению, в вашем городе нет офиса...", "'к сожалению, нет офиса'", "Фраза про отсутствие офиса — заменить: 'Для вас лучше всего подойдёт дистанционный формат — это удобнее и быстрее.'"),
]

DEFAULT_STAGE_WEIGHTS = [
    # Первичный исходящий
    ("primary_outbound", "contact", "Установление контакта", 1.0),
    ("primary_outbound", "needs", "Выявление потребностей", 1.5),
    ("primary_outbound", "qualification", "Квалификация", 1.5),
    ("primary_outbound", "presentation", "Презентация БК", 1.5),
    ("primary_outbound", "objections", "Работа с возражениями", 2.0),
    ("primary_outbound", "closing", "Закрытие", 2.0),
    ("primary_outbound", "summary", "Резюмирование", 1.0),
    ("primary_outbound", "commitment", "Фиксация явки", 1.5),
    ("primary_outbound", "speech", "Стройность речи", 0.5),
    ("primary_outbound", "control", "Управление диалогом", 1.0),
    ("primary_outbound", "salesmanship", "Продажность", 1.5),
    ("primary_outbound", "tone", "Тон менеджера", 0.5),
    ("primary_outbound", "client_state", "Психосостояние клиента", 0.5),
    ("primary_outbound", "client_reaction", "Реакция клиента", 0.5),
    # Первичный входящий
    ("primary_inbound", "contact", "Установление контакта", 1.0),
    ("primary_inbound", "needs", "Выявление потребностей", 1.5),
    ("primary_inbound", "qualification", "Квалификация", 1.5),
    ("primary_inbound", "presentation", "Презентация БК", 2.0),
    ("primary_inbound", "objections", "Работа с возражениями", 2.0),
    ("primary_inbound", "closing", "Закрытие", 2.0),
    ("primary_inbound", "summary", "Резюмирование", 1.0),
    ("primary_inbound", "commitment", "Фиксация явки", 1.5),
    ("primary_inbound", "speech", "Стройность речи", 0.5),
    ("primary_inbound", "control", "Управление диалогом", 1.0),
    ("primary_inbound", "salesmanship", "Продажность", 1.0),
    ("primary_inbound", "tone", "Тон менеджера", 0.5),
    ("primary_inbound", "client_state", "Психосостояние клиента", 0.5),
    ("primary_inbound", "client_reaction", "Реакция клиента", 0.5),
    # Подтверждение
    ("confirmation", "contact", "Установление контакта", 1.0),
    ("confirmation", "reminder", "Напоминание о консультации", 2.0),
    ("confirmation", "confirm_datetime", "Подтверждение даты и времени", 2.0),
    ("confirmation", "confirm_address", "Подтверждение адреса", 1.5),
    ("confirmation", "what_to_bring", "Что взять с собой", 1.5),
    ("confirmation", "motivation", "Усиление мотивации прийти", 2.0),
    ("confirmation", "risk_detection", "Выявление риска неявки", 2.0),
    ("confirmation", "doubts", "Отработка сомнений", 1.5),
    ("confirmation", "final_confirm", "Финальное подтверждение", 2.0),
    ("confirmation", "tone", "Тон менеджера", 0.5),
    ("confirmation", "client_state", "Психосостояние клиента", 0.5),
    # Повторный
    ("repeat", "contact", "Восстановление контакта", 1.5),
    ("repeat", "past_call_link", "Привязка к прошлому разговору", 1.5),
    ("repeat", "past_refusal", "Выявление причины прошлого отказа", 2.0),
    ("repeat", "problem_update", "Актуализация проблемы", 2.0),
    ("repeat", "new_value", "Новая ценность консультации", 2.0),
    ("repeat", "objections", "Работа с повторным возражением", 2.0),
    ("repeat", "closing", "Закрытие на следующий шаг", 2.0),
    ("repeat", "tone", "Тон менеджера", 0.5),
    ("repeat", "client_reaction", "Реакция клиента", 0.5),
]


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)

    # Заполнить чеклист если пустой
    count = conn.execute("SELECT COUNT(*) FROM checklist_rules").fetchone()[0]
    if count == 0:
        conn.executemany(
            """INSERT INTO checklist_rules
               (title, description, call_type, sales_stage, weight, criticality,
                is_required, ai_instruction, positive_examples, negative_examples,
                forbidden_phrases, recommendation_template)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            DEFAULT_CHECKLIST
        )

    # Заполнить веса этапов если пусто
    count2 = conn.execute("SELECT COUNT(*) FROM stage_weights").fetchone()[0]
    if count2 == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO stage_weights (call_type, stage_code, stage_name, weight) VALUES (?,?,?,?)",
            DEFAULT_STAGE_WEIGHTS
        )

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ПОЛЬЗОВАТЕЛИ И КОМАНДЫ
# ─────────────────────────────────────────────

def get_teams() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql("SELECT * FROM teams ORDER BY name", conn)
    conn.close()
    return df


def get_users(role: Optional[str] = None, team_id: Optional[int] = None) -> pd.DataFrame:
    conn = get_conn()
    q = "SELECT u.*, t.name as team_name FROM users u LEFT JOIN teams t ON u.team_id=t.id WHERE u.is_active=1"
    params = []
    if role:
        q += " AND u.role=?"
        params.append(role)
    if team_id:
        q += " AND u.team_id=?"
        params.append(team_id)
    q += " ORDER BY u.name"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def get_managers() -> pd.DataFrame:
    return get_users(role="manager")


def upsert_user(name: str, role: str = "manager", team_id: Optional[int] = None, email: str = "") -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (name, role, team_id, email) VALUES (?,?,?,?) RETURNING id",
        (name, role, team_id, email)
    )
    uid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return uid


def upsert_team(name: str) -> int:
    conn = get_conn()
    existing = conn.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    if existing:
        conn.close()
        return existing[0]
    cur = conn.execute("INSERT INTO teams (name) VALUES (?) RETURNING id", (name,))
    tid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return tid


# ─────────────────────────────────────────────
# ЗВОНКИ
# ─────────────────────────────────────────────

def save_call(data: dict) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO calls
           (manager_id, team_id, filename, audio_path, duration_seconds,
            call_type, is_active_call, direction, uploaded_at, call_datetime,
            analysis_status, review_status, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (
            data.get("manager_id"), data.get("team_id"),
            data.get("filename"), data.get("audio_path"),
            data.get("duration_seconds", 0),
            data.get("call_type", "unknown"),
            int(data.get("is_active_call", True)),
            data.get("direction", "outbound"),
            data.get("uploaded_at", datetime.now().isoformat(timespec="seconds")),
            data.get("call_datetime"),
            data.get("analysis_status", "pending"),
            data.get("review_status", "auto"),
            data.get("notes"),
        )
    )
    call_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return call_id


def update_call_status(call_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE calls SET analysis_status=? WHERE id=?", (status, call_id))
    conn.commit()
    conn.close()


def get_calls(manager_id: Optional[int] = None, team_id: Optional[int] = None,
              limit: int = 500) -> pd.DataFrame:
    conn = get_conn()
    q = """
        SELECT c.*, u.name as manager_name, t.name as team_name,
               qa.qa_score, qa.tone_score, qa.client_reflection_score,
               qa.show_up_probability_score, qa.show_up_risk_level,
               qa.weak_agreement_detected, qa.summary,
               (SELECT COUNT(*) FROM detected_errors de WHERE de.call_id=c.id) as error_count,
               (SELECT COUNT(*) FROM detected_errors de WHERE de.call_id=c.id AND de.status='needs_review') as review_count
        FROM calls c
        LEFT JOIN users u ON c.manager_id=u.id
        LEFT JOIN teams t ON c.team_id=t.id
        LEFT JOIN qa_analyses qa ON qa.call_id=c.id
        WHERE 1=1
    """
    params = []
    if manager_id:
        q += " AND c.manager_id=?"
        params.append(manager_id)
    if team_id:
        q += " AND c.team_id=?"
        params.append(team_id)
    q += f" ORDER BY c.uploaded_at DESC LIMIT {limit}"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def get_call(call_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        """SELECT c.*, u.name as manager_name, t.name as team_name
           FROM calls c
           LEFT JOIN users u ON c.manager_id=u.id
           LEFT JOIN teams t ON c.team_id=t.id
           WHERE c.id=?""", (call_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_call(call_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM calls WHERE id=?", (call_id,))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ТРАНСКРИПТ
# ─────────────────────────────────────────────

def save_transcript(call_id: int, full_text: str, segments: list) -> int:
    conn = get_conn()
    conn.execute("DELETE FROM transcripts WHERE call_id=?", (call_id,))
    cur = conn.execute(
        "INSERT INTO transcripts (call_id, full_text) VALUES (?,?) RETURNING id",
        (call_id, full_text)
    )
    tid = cur.fetchone()[0]
    if segments:
        conn.executemany(
            "INSERT INTO transcript_segments (transcript_id, speaker, text, start_time, end_time, confidence) VALUES (?,?,?,?,?,?)",
            [(tid, s.get("speaker"), s.get("text"), s.get("start_time"), s.get("end_time"), s.get("confidence", 1.0)) for s in segments]
        )
    conn.commit()
    conn.close()
    return tid


def get_transcript(call_id: int) -> Optional[dict]:
    conn = get_conn()
    t = conn.execute("SELECT * FROM transcripts WHERE call_id=?", (call_id,)).fetchone()
    if not t:
        conn.close()
        return None
    segs = conn.execute(
        "SELECT * FROM transcript_segments WHERE transcript_id=? ORDER BY start_time",
        (t["id"],)
    ).fetchall()
    conn.close()
    return {"transcript": dict(t), "segments": [dict(s) for s in segs]}


# ─────────────────────────────────────────────
# QA-АНАЛИЗ
# ─────────────────────────────────────────────

def save_analysis(call_id: int, result: dict) -> int:
    conn = get_conn()
    conn.execute("DELETE FROM qa_analyses WHERE call_id=?", (call_id,))

    sp = result.get("show_up_prediction", {})
    wa = result.get("weak_agreement", {})

    cur = conn.execute(
        """INSERT INTO qa_analyses
           (call_id, qa_score, regulation_score, sales_quality_score,
            speech_structure_score, manager_control_score, tone_score,
            client_reflection_score, show_up_probability_score,
            objection_handling_score, closing_score,
            summary, main_problem, main_risk, goal_achieved, client_name,
            weak_agreement_detected, weak_agreement_phrase, weak_agreement_risk,
            show_up_risk_level, show_up_risk_reasons,
            model_name, raw_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (
            call_id,
            result.get("qa_score", 0), result.get("regulation_score", 0),
            result.get("sales_quality_score", 0), result.get("speech_structure_score", 0),
            result.get("manager_control_score", 0), result.get("tone_score", 0),
            result.get("client_reflection_score", 0), result.get("show_up_probability_score", 0),
            result.get("objection_handling_score", 0), result.get("closing_score", 0),
            result.get("summary"), result.get("main_problem"), result.get("main_risk"),
            int(result.get("goal_achieved", False)), result.get("client_name"),
            int(wa.get("detected", False)), wa.get("client_phrase"),
            wa.get("risk_reason"),
            sp.get("risk_level", "medium"),
            json.dumps(sp.get("risk_reasons", []), ensure_ascii=False),
            result.get("model_name", "gemini"), json.dumps(result, ensure_ascii=False),
        )
    )
    qa_id = cur.fetchone()[0]

    # Этапы продаж
    for s in result.get("sales_stage_scores", []):
        conn.execute(
            """INSERT INTO sales_stage_scores
               (qa_analysis_id, stage_code, stage_name, score, weight,
                evidence_quote, timestamp, explanation, recommendation)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (qa_id, s.get("stage_code"), s.get("stage_name"),
             s.get("score", 0), s.get("weight", 1.0),
             s.get("evidence_quote"), s.get("timestamp"),
             s.get("explanation"), s.get("recommendation"))
        )

    # Ошибки
    for e in result.get("detected_errors", []):
        conn.execute(
            """INSERT INTO detected_errors
               (qa_analysis_id, call_id, title, description, criticality,
                evidence_quote, timestamp, confidence, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (qa_id, call_id, e.get("checklist_rule_title", e.get("title")),
             e.get("description"), e.get("criticality", "medium"),
             e.get("evidence_quote"), e.get("timestamp"),
             e.get("confidence", 0.9), e.get("status", "detected_by_ai"))
        )

    # Инструменты продаж
    for t in result.get("sales_tools", []):
        conn.execute(
            """INSERT INTO sales_tools
               (qa_analysis_id, tool_name, was_used, quality_score,
                evidence_quote, timestamp, recommendation)
               VALUES (?,?,?,?,?,?,?)""",
            (qa_id, t.get("tool_name"), int(t.get("was_used", False)),
             t.get("quality_score", 0), t.get("evidence_quote"),
             t.get("timestamp"), t.get("recommendation"))
        )

    # Возражения
    for o in result.get("objections", []):
        conn.execute(
            """INSERT INTO objections
               (qa_analysis_id, type, is_hidden, client_phrase, timestamp,
                manager_response, response_quality_score, was_handled, recommendation)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (qa_id, o.get("type"), int(o.get("is_hidden", False)),
             o.get("client_phrase"), o.get("timestamp"),
             o.get("manager_response"), o.get("response_quality_score", 0),
             int(o.get("was_handled", False)), o.get("recommendation"))
        )

    # Эмоциональный таймлайн
    for e in result.get("emotional_timeline", []):
        conn.execute(
            """INSERT INTO emotional_timeline
               (qa_analysis_id, timestamp, client_state, manager_tone, note, evidence_quote)
               VALUES (?,?,?,?,?,?)""",
            (qa_id, e.get("timestamp"), e.get("client_state"),
             e.get("manager_tone"), e.get("note"), e.get("evidence_quote"))
        )

    # Таймлайн событий
    for ev in result.get("call_timeline_events", []):
        conn.execute(
            """INSERT INTO call_timeline_events
               (qa_analysis_id, event_type, start_time, end_time, description,
                quality_score, evidence_quote, related_stage, risk_level)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (qa_id, ev.get("event_type"), ev.get("start_time"), ev.get("end_time"),
             ev.get("description"), ev.get("quality_score", 0),
             ev.get("evidence_quote"), ev.get("related_stage"),
             ev.get("risk_level", "low"))
        )

    # Фразы для библиотеки
    for p in result.get("phrase_candidates", []):
        conn.execute(
            """INSERT INTO phrase_library
               (call_id, qa_analysis_id, phrase_text, phrase_type,
                sales_stage, sales_tool, timestamp, explanation, impact_score)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (call_id, qa_id, p.get("phrase_text"), p.get("phrase_type", "neutral"),
             p.get("sales_stage"), p.get("sales_tool"),
             p.get("timestamp"), p.get("explanation"), p.get("impact_score", 0))
        )

    # Рекомендации РОПу
    for r in result.get("rop_recommendations", []):
        conn.execute(
            """INSERT INTO rop_recommendations
               (level, call_id, title, main_problem, data_evidence,
                business_risk, recommended_action, priority)
               VALUES (?,?,?,?,?,?,?,?)""",
            (r.get("level", "call"), call_id, r.get("title"),
             r.get("main_problem"),
             json.dumps(r.get("data_evidence", []), ensure_ascii=False),
             r.get("business_risk"), r.get("recommended_action"),
             r.get("priority", "medium"))
        )

    conn.commit()
    conn.close()
    return qa_id


def get_analysis(call_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM qa_analyses WHERE call_id=?", (call_id,)).fetchone()
    if not row:
        conn.close()
        return None
    qa = dict(row)
    qa_id = qa["id"]

    qa["stage_scores"] = [dict(r) for r in conn.execute(
        "SELECT * FROM sales_stage_scores WHERE qa_analysis_id=? ORDER BY stage_code", (qa_id,)
    ).fetchall()]
    qa["errors"] = [dict(r) for r in conn.execute(
        "SELECT * FROM detected_errors WHERE qa_analysis_id=? ORDER BY criticality DESC", (qa_id,)
    ).fetchall()]
    qa["sales_tools"] = [dict(r) for r in conn.execute(
        "SELECT * FROM sales_tools WHERE qa_analysis_id=? ORDER BY tool_name", (qa_id,)
    ).fetchall()]
    qa["objections"] = [dict(r) for r in conn.execute(
        "SELECT * FROM objections WHERE qa_analysis_id=? ORDER BY timestamp", (qa_id,)
    ).fetchall()]
    qa["emotional_timeline"] = [dict(r) for r in conn.execute(
        "SELECT * FROM emotional_timeline WHERE qa_analysis_id=? ORDER BY timestamp", (qa_id,)
    ).fetchall()]
    qa["timeline_events"] = [dict(r) for r in conn.execute(
        "SELECT * FROM call_timeline_events WHERE qa_analysis_id=? ORDER BY start_time", (qa_id,)
    ).fetchall()]
    qa["phrases"] = [dict(r) for r in conn.execute(
        "SELECT * FROM phrase_library WHERE qa_analysis_id=?", (qa_id,)
    ).fetchall()]
    qa["recommendations"] = [dict(r) for r in conn.execute(
        "SELECT * FROM rop_recommendations WHERE call_id=?", (call_id,)
    ).fetchall()]
    conn.close()
    return qa


def update_error_status(error_id: int, status: str, comment: str = "", reviewer_id: Optional[int] = None):
    conn = get_conn()
    conn.execute(
        "UPDATE detected_errors SET status=?, review_comment=?, reviewed_by=?, reviewed_at=? WHERE id=?",
        (status, comment, reviewer_id, datetime.now().isoformat(), error_id)
    )
    conn.commit()
    conn.close()


def update_phrase_status(phrase_id: int, status: str, reviewer_id: Optional[int] = None):
    conn = get_conn()
    conn.execute(
        "UPDATE phrase_library SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
        (status, reviewer_id, datetime.now().isoformat(), phrase_id)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ЧЕКЛИСТ
# ─────────────────────────────────────────────

def get_checklist_rules(call_type: Optional[str] = None, active_only: bool = True) -> pd.DataFrame:
    conn = get_conn()
    q = "SELECT * FROM checklist_rules WHERE 1=1"
    params = []
    if active_only:
        q += " AND is_active=1"
    if call_type:
        q += " AND (call_type='all' OR call_type LIKE ?)"
        params.append(f"%{call_type}%")
    q += " ORDER BY sales_stage, weight DESC"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def upsert_checklist_rule(data: dict) -> int:
    conn = get_conn()
    if data.get("id"):
        conn.execute(
            """UPDATE checklist_rules SET
               title=?, description=?, call_type=?, sales_stage=?,
               weight=?, criticality=?, is_required=?, is_active=?,
               ai_instruction=?, positive_examples=?, negative_examples=?,
               forbidden_phrases=?, recommendation_template=?,
               updated_at=datetime('now')
               WHERE id=?""",
            (data["title"], data.get("description"), data.get("call_type", "all"),
             data.get("sales_stage"), data.get("weight", 1.0), data.get("criticality", "medium"),
             int(data.get("is_required", True)), int(data.get("is_active", True)),
             data.get("ai_instruction"), data.get("positive_examples"),
             data.get("negative_examples"), data.get("forbidden_phrases"),
             data.get("recommendation_template"), data["id"])
        )
        rule_id = data["id"]
    else:
        cur = conn.execute(
            """INSERT INTO checklist_rules
               (title, description, call_type, sales_stage, weight, criticality,
                is_required, is_active, ai_instruction, positive_examples,
                negative_examples, forbidden_phrases, recommendation_template)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
            (data["title"], data.get("description"), data.get("call_type", "all"),
             data.get("sales_stage"), data.get("weight", 1.0), data.get("criticality", "medium"),
             int(data.get("is_required", True)), int(data.get("is_active", True)),
             data.get("ai_instruction"), data.get("positive_examples"),
             data.get("negative_examples"), data.get("forbidden_phrases"),
             data.get("recommendation_template"))
        )
        rule_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return rule_id


def get_stage_weights(call_type: str) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql(
        "SELECT * FROM stage_weights WHERE call_type=? ORDER BY stage_code",
        conn, params=(call_type,)
    )
    conn.close()
    return df


def update_stage_weight(call_type: str, stage_code: str, weight: float):
    conn = get_conn()
    conn.execute(
        "UPDATE stage_weights SET weight=? WHERE call_type=? AND stage_code=?",
        (weight, call_type, stage_code)
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# ДАШБОРД — агрегаты
# ─────────────────────────────────────────────

def get_dashboard_stats(manager_id: Optional[int] = None, team_id: Optional[int] = None,
                         days: int = 30) -> dict:
    conn = get_conn()
    params = [days]
    base_filter = "AND c.uploaded_at >= datetime('now', ? || ' days')"
    mgr_filter = ""
    if manager_id:
        mgr_filter += " AND c.manager_id=?"
        params.append(manager_id)
    if team_id:
        mgr_filter += " AND c.team_id=?"
        params.append(team_id)

    q = f"""
        SELECT
            COUNT(c.id) as total_calls,
            SUM(c.is_active_call) as active_calls,
            SUM(CASE WHEN c.analysis_status='done' THEN 1 ELSE 0 END) as analyzed_calls,
            AVG(qa.qa_score) as avg_qa_score,
            AVG(qa.tone_score) as avg_tone_score,
            AVG(qa.client_reflection_score) as avg_client_score,
            AVG(qa.show_up_probability_score) as avg_show_up,
            SUM(CASE WHEN qa.show_up_risk_level='high' THEN 1 ELSE 0 END) as high_risk_count,
            SUM(CASE WHEN qa.weak_agreement_detected=1 THEN 1 ELSE 0 END) as weak_agreement_count,
            SUM(CASE WHEN qa.goal_achieved=1 THEN 1 ELSE 0 END) as goal_achieved_count
        FROM calls c
        LEFT JOIN qa_analyses qa ON qa.call_id=c.id
        WHERE 1=1 {base_filter} {mgr_filter}
    """
    # Rebuild params list
    params_rebuilt = [f"-{days}"]
    if manager_id:
        params_rebuilt.append(manager_id)
    if team_id:
        params_rebuilt.append(team_id)

    row = conn.execute(q, params_rebuilt).fetchone()
    stats = dict(row) if row else {}

    # Ошибки
    err_q = f"""
        SELECT COUNT(de.id) as total_errors,
               SUM(CASE WHEN de.status='needs_review' THEN 1 ELSE 0 END) as needs_review,
               SUM(CASE WHEN de.criticality='critical' THEN 1 ELSE 0 END) as critical_errors
        FROM detected_errors de
        JOIN calls c ON de.call_id=c.id
        WHERE 1=1 {base_filter} {mgr_filter}
    """
    err_row = conn.execute(err_q, params_rebuilt).fetchone()
    if err_row:
        stats.update(dict(err_row))

    conn.close()
    return stats


def get_trend_data(metric: str = "qa_score", days: int = 30,
                   manager_id: Optional[int] = None) -> pd.DataFrame:
    conn = get_conn()
    params = [f"-{days}"]
    mgr_filter = ""
    if manager_id:
        mgr_filter = " AND c.manager_id=?"
        params.append(manager_id)
    q = f"""
        SELECT DATE(c.uploaded_at) as date,
               AVG(qa.{metric}) as value,
               COUNT(c.id) as call_count
        FROM calls c
        LEFT JOIN qa_analyses qa ON qa.call_id=c.id
        WHERE c.uploaded_at >= datetime('now', ? || ' days')
              AND c.analysis_status='done' {mgr_filter}
        GROUP BY DATE(c.uploaded_at)
        ORDER BY date
    """
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def get_manager_stats(days: int = 30) -> pd.DataFrame:
    conn = get_conn()
    q = f"""
        SELECT u.id, u.name as manager_name, t.name as team_name,
               COUNT(c.id) as call_count,
               AVG(qa.qa_score) as avg_qa_score,
               AVG(qa.tone_score) as avg_tone_score,
               AVG(qa.client_reflection_score) as avg_client_score,
               AVG(qa.show_up_probability_score) as avg_show_up,
               SUM(CASE WHEN qa.weak_agreement_detected=1 THEN 1 ELSE 0 END) as weak_agreements,
               AVG(qa.closing_score) as avg_closing,
               AVG(qa.objection_handling_score) as avg_objections
        FROM users u
        LEFT JOIN calls c ON c.manager_id=u.id
              AND c.uploaded_at >= datetime('now', '-{days} days')
        LEFT JOIN qa_analyses qa ON qa.call_id=c.id
        WHERE u.role='manager' AND u.is_active=1
        GROUP BY u.id, u.name, t.name
        ORDER BY avg_qa_score DESC
    """
    df = pd.read_sql(q, conn)
    conn.close()
    return df


def get_stage_heatmap(days: int = 30) -> pd.DataFrame:
    conn = get_conn()
    q = f"""
        SELECT u.name as manager_name, sss.stage_name, AVG(sss.score) as avg_score
        FROM sales_stage_scores sss
        JOIN qa_analyses qa ON sss.qa_analysis_id=qa.id
        JOIN calls c ON qa.call_id=c.id
        JOIN users u ON c.manager_id=u.id
        WHERE c.uploaded_at >= datetime('now', '-{days} days')
              AND c.analysis_status='done'
        GROUP BY u.name, sss.stage_name
        ORDER BY u.name, sss.stage_name
    """
    df = pd.read_sql(q, conn)
    conn.close()
    return df


def get_error_stats(days: int = 30) -> pd.DataFrame:
    conn = get_conn()
    q = f"""
        SELECT de.title, de.criticality,
               COUNT(*) as count,
               AVG(de.confidence) as avg_confidence
        FROM detected_errors de
        JOIN calls c ON de.call_id=c.id
        WHERE c.uploaded_at >= datetime('now', '-{days} days')
        GROUP BY de.title, de.criticality
        ORDER BY count DESC
        LIMIT 30
    """
    df = pd.read_sql(q, conn)
    conn.close()
    return df


def get_phrase_library(phrase_type: Optional[str] = None, manager_id: Optional[int] = None,
                        stage: Optional[str] = None, limit: int = 200) -> pd.DataFrame:
    conn = get_conn()
    q = """
        SELECT pl.*, u.name as manager_name, c.filename, c.call_datetime
        FROM phrase_library pl
        LEFT JOIN users u ON pl.manager_id=u.id
        LEFT JOIN calls c ON pl.call_id=c.id
        WHERE pl.status != 'rejected'
    """
    params = []
    if phrase_type:
        q += " AND pl.phrase_type=?"
        params.append(phrase_type)
    if manager_id:
        q += " AND pl.manager_id=?"
        params.append(manager_id)
    if stage:
        q += " AND pl.sales_stage=?"
        params.append(stage)
    q += f" ORDER BY pl.impact_score DESC LIMIT {limit}"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def get_recommendations(level: Optional[str] = None, manager_id: Optional[int] = None,
                          priority: Optional[str] = None, days: int = 30) -> pd.DataFrame:
    conn = get_conn()
    q = """
        SELECT r.*, u.name as manager_name, c.filename
        FROM rop_recommendations r
        LEFT JOIN users u ON r.manager_id=u.id
        LEFT JOIN calls c ON r.call_id=c.id
        WHERE r.created_at >= datetime('now', ? || ' days')
    """
    params = [f"-{days}"]
    if level:
        q += " AND r.level=?"
        params.append(level)
    if manager_id:
        q += " AND r.manager_id=?"
        params.append(manager_id)
    if priority:
        q += " AND r.priority=?"
        params.append(priority)
    q += " ORDER BY r.created_at DESC"
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


def get_trainings() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql(
        """SELECT tr.*, u.name as manager_name, t.name as team_name
           FROM training_recommendations tr
           LEFT JOIN users u ON tr.manager_id=u.id
           LEFT JOIN teams t ON tr.team_id=t.id
           ORDER BY tr.created_at DESC""",
        conn
    )
    conn.close()
    return df


def save_training(data: dict) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO training_recommendations
           (scope, manager_id, team_id, title, reason, data_evidence,
            weak_stages, repeated_errors, plan_30_min, plan_45_min, plan_60_min,
            exercises, roleplays, phrases_to_use, phrases_to_avoid,
            calls_to_review, homework, metrics_to_check, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
        (
            data.get("scope", "team"), data.get("manager_id"), data.get("team_id"),
            data.get("title"), data.get("reason"),
            json.dumps(data.get("data_evidence", []), ensure_ascii=False),
            json.dumps(data.get("weak_stages", []), ensure_ascii=False),
            json.dumps(data.get("repeated_errors", []), ensure_ascii=False),
            data.get("plan_30_min"), data.get("plan_45_min"), data.get("plan_60_min"),
            json.dumps(data.get("exercises", []), ensure_ascii=False),
            json.dumps(data.get("roleplays", []), ensure_ascii=False),
            json.dumps(data.get("phrases_to_use", []), ensure_ascii=False),
            json.dumps(data.get("phrases_to_avoid", []), ensure_ascii=False),
            json.dumps(data.get("calls_to_review", []), ensure_ascii=False),
            data.get("homework"), json.dumps(data.get("metrics_to_check", []), ensure_ascii=False),
            data.get("status", "proposed")
        )
    )
    tid = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return tid


def update_training_status(training_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE training_recommendations SET status=? WHERE id=?", (status, training_id))
    conn.commit()
    conn.close()
