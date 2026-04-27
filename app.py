"""
Контроль качества звонков — Streamlit-дэшборд.

Запускать локально:
    pip install -r requirements.txt
    streamlit run app.py

Деплоиться на Streamlit Community Cloud — просто из GitHub.
"""

import streamlit as st
import google.generativeai as genai
import sqlite3
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
import re
import os
import tempfile
import io

# =========================================================================
# КОНФИГУРАЦИЯ
# =========================================================================
DB_PATH = "calls.db"
DEFAULT_MANAGERS = ["Пукля Засерайкин"]

CHECKLIST = """
СИСТЕМА ОЦЕНКИ: за каждое нарушение начисляется удержание.
КОНТЕКСТ КОМПАНИИ: юридические консультации по освобождению от военной службы.
Термины: БК — бесплатная консультация; ВБ — военный билет; ОФИС — личная встреча в офисе;
ДИСТ — дистанционная консультация; утиль — клиент не подходит под услугу;
МЛМ — сбор контактов знакомых; "матрёшка" — предложение прийти с другом/коллегой;
LegalHelp — мобильное приложение компании.

1. УСТАНОВЛЕНИЕ КОНТАКТА
   1.1 (-50) Не представился, не обратился к клиенту по имени, не назвал название компании (в первые 30 секунд)
   1.2 (-50) Не использовал фразы вежливости в течение диалога

2. ВЫЯВЛЕНИЕ ПОТРЕБНОСТЕЙ
   2.1 (-50) Не уточнил населённый пункт клиента
   2.2 (-50) Не уточнил информацию по отсрочке/повестке/отправке
   2.3 (-100) Не уточнил информацию по здоровью

3. ПРЕЗЕНТАЦИЯ БК
   3.1 (-100) Использовал аргумент "Всё бесплатно" — ЗАПРЕЩЕНО
   3.2 (-100) Уклонялся от прямого ответа на вопрос клиента
   3.3 (-100) Предоставлял ложную или недостоверную информацию
   3.4 (-100) Не информировал о приложении LegalHelp

4. ОТРАБОТКА ВОЗРАЖЕНИЙ
   4.1 (-100) Не предпринял достаточных попыток отработать возражения

5. ЗАКРЫТИЕ НА БК
   5.1 (-10000, ВЫСШЕЕ) Неверное распределение ОФИС/ДИСТ
   5.2 (-200) Запись лида из офиса на онлайн или ДИСТ на офис вне регламента
   5.3 (-50) Мнимая альтернатива — не предложил день в день и ближайшие дни
   5.4 (-50) Не резюмировал дату/время/адрес и что взять с собой
   5.5 (-200) Не оставил полный комментарий по шаблону

6. ДОПОЛНИТЕЛЬНО
   6.1 (-200) Неверно выбран результат звонка
   6.2 (-100) Неправильный перенос в утиль
   6.3 (-500) При сборе МЛМ не запросил контакты или не отработал возражения
   6.4 (-150) Не создал искусственный дефицит через текущие скидки
   6.5 (-500) Не предложил "матрёшку"
   6.6 (-5000) Иные фатальные ошибки
"""


PROMPT_TEMPLATE = """Ты — супервайзер отдела контроля качества. Прослушай запись звонка менеджера и оцени её строго по чеклисту.

ЧЕКЛИСТ:
{checklist}

ИНСТРУКЦИЯ:
1. Внимательно прослушай весь звонок.
2. По каждому пункту чеклиста реши: соблюдён, нарушен или не применим.
3. Цитируй конкретные фразы из звонка как обоснование.

ВЫВЕДИ ОТВЕТ В ДВА БЛОКА.

БЛОК 1 — JSON со структурированными данными (между маркерами <<<JSON>>> и <<<END_JSON>>>):

<<<JSON>>>
{{
  "summary": "Краткое резюме звонка в 2-3 предложения",
  "client_name": "Имя клиента, если упоминалось, иначе null",
  "violations": [
    {{
      "point": "1.1",
      "title": "Название пункта",
      "status": "violated | passed | n/a",
      "deduction": 50,
      "quote": "Цитата или обоснование"
    }}
  ],
  "total_deduction": 17300,
  "tone": "Описание тона менеджера в 5-10 словах",
  "client_emotion": "Как менялись эмоции клиента в 5-10 словах",
  "contact_quality": "low | medium | high",
  "strengths": ["Сильная сторона 1", "Сильная сторона 2", "..."],
  "growth_zones": ["Зона роста 1", "Зона роста 2", "..."],
  "recommendations": ["Конкретная рекомендация с примером фразы 1", "..."],
  "needs_team_lead_review": ["Описание ситуации, требующей ручной проверки"]
}}
<<<END_JSON>>>

БЛОК 2 — человекочитаемый отчёт в Markdown.

## Резюме звонка
[2-3 предложения]

## Оценка по чеклисту
[Полная таблица с цитатами]

## Итоговое удержание
[Цифра]

## Эмоции и тон
[Описание]

## Сильные стороны
[Список]

## Зоны роста
[Список]

## Рекомендации
[С примерами фраз]
"""


# =========================================================================
# БАЗА ДАННЫХ
# =========================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uploaded_at TEXT,
            filename TEXT,
            manager TEXT,
            summary TEXT,
            client_name TEXT,
            total_deduction INTEGER,
            tone TEXT,
            client_emotion TEXT,
            contact_quality TEXT,
            strengths TEXT,
            growth_zones TEXT,
            recommendations TEXT,
            needs_review TEXT,
            full_report TEXT,
            violations_json TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS managers (
            name TEXT PRIMARY KEY
        )
    """)
    for m in DEFAULT_MANAGERS:
        c.execute("INSERT OR IGNORE INTO managers (name) VALUES (?)", (m,))
    conn.commit()
    conn.close()


def get_managers():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT name FROM managers ORDER BY name", conn)
    conn.close()
    return df["name"].tolist()


def add_manager(name):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO managers (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def remove_manager(name):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM managers WHERE name = ?", (name,))
    conn.commit()
    conn.close()


def save_call(data):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO calls
        (uploaded_at, filename, manager, summary, client_name,
         total_deduction, tone, client_emotion, contact_quality,
         strengths, growth_zones, recommendations, needs_review,
         full_report, violations_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["uploaded_at"], data["filename"], data["manager"],
        data["summary"], data.get("client_name"),
        data["total_deduction"], data.get("tone"), data.get("client_emotion"),
        data.get("contact_quality"),
        json.dumps(data.get("strengths", []), ensure_ascii=False),
        json.dumps(data.get("growth_zones", []), ensure_ascii=False),
        json.dumps(data.get("recommendations", []), ensure_ascii=False),
        json.dumps(data.get("needs_review", []), ensure_ascii=False),
        data.get("full_report", ""),
        json.dumps(data.get("violations", []), ensure_ascii=False),
    ))
    conn.commit()
    conn.close()


def load_calls(manager_filter=None):
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM calls"
    params = ()
    if manager_filter and manager_filter != "Все":
        query += " WHERE manager = ?"
        params = (manager_filter,)
    query += " ORDER BY uploaded_at DESC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def delete_call(call_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM calls WHERE id = ?", (call_id,))
    conn.commit()
    conn.close()


# =========================================================================
# ВЗАИМОДЕЙСТВИЕ С GEMINI
# =========================================================================
def analyze_audio(audio_bytes, filename, api_key):
    """Отправляет аудио в Gemini и парсит ответ."""
    genai.configure(api_key=api_key)

    suffix = os.path.splitext(filename)[1] or ".mp3"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        audio_file = genai.upload_file(path=tmp_path)
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = PROMPT_TEMPLATE.format(checklist=CHECKLIST)
        response = model.generate_content([prompt, audio_file])
        text = response.text
    finally:
        os.unlink(tmp_path)

    return parse_response(text)


def parse_response(text):
    """Извлекает JSON-блок и человекочитаемую часть из ответа Gemini."""
    json_match = re.search(r"<<<JSON>>>(.+?)<<<END_JSON>>>", text, re.DOTALL)
    if not json_match:
        # fallback: попробуем найти фигурные скобки
        json_match = re.search(r"\{[\s\S]+\}", text)
        if not json_match:
            raise ValueError("Не удалось найти JSON в ответе модели")
        raw = json_match.group(0)
    else:
        raw = json_match.group(1).strip()

    # Иногда модель оборачивает JSON в ```json ... ```
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    parsed = json.loads(raw)

    # Markdown-отчёт — всё, что после END_JSON
    md_match = re.search(r"<<<END_JSON>>>(.+)", text, re.DOTALL)
    full_report = md_match.group(1).strip() if md_match else text

    parsed["full_report"] = full_report
    return parsed


# =========================================================================
# UI
# =========================================================================
st.set_page_config(
    page_title="Контроль качества звонков",
    page_icon="🎧",
    layout="wide",
)

init_db()

# --- Заголовок ---
st.title("🎧 Контроль качества звонков")
st.caption("ИИ-супервайзер слушает звонки и оценивает работу менеджеров по чеклисту")


# --- Боковая панель ---
with st.sidebar:
    st.header("⚙️ Настройки")

    # API key: в проде берётся из secrets, поле ввода показываем только если ключа нет
    api_key = ""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        api_key = ""

    if api_key:
        st.success("✓ API-ключ подключён")
    else:
        manual_key = st.text_input(
            "API-ключ Gemini",
            type="password",
            value=st.session_state.get("api_key", ""),
            help="Получить бесплатно: https://aistudio.google.com/apikey",
        )
        if manual_key:
            st.session_state["api_key"] = manual_key
            api_key = manual_key

    st.divider()

    # Управление менеджерами
    st.subheader("Менеджеры")
    managers = get_managers()
    for m in managers:
        col_a, col_b = st.columns([4, 1])
        col_a.write(f"• {m}")
        if col_b.button("✖", key=f"del_{m}", help=f"Удалить {m}"):
            remove_manager(m)
            st.rerun()

    new_manager = st.text_input("Добавить менеджера", placeholder="Иван Иванов")
    if st.button("Добавить") and new_manager.strip():
        add_manager(new_manager.strip())
        st.rerun()


# --- Вкладки ---
tab_upload, tab_dashboard, tab_detail = st.tabs([
    "📥 Загрузить звонки",
    "📊 Дэшборд",
    "🔍 Просмотр звонка",
])


# ========== ВКЛАДКА 1: загрузка ==========
with tab_upload:
    if not api_key:
        st.warning("⚠️ Сначала введите API-ключ Gemini в боковой панели слева.")
    else:
        managers_list = get_managers()
        if not managers_list:
            st.warning("⚠️ Сначала добавьте хотя бы одного менеджера в боковой панели.")
        else:
            col_left, col_right = st.columns([2, 1])

            with col_left:
                uploaded_files = st.file_uploader(
                    "Перетащите аудиофайлы или нажмите для выбора",
                    type=["mp3", "wav", "m4a", "ogg", "flac"],
                    accept_multiple_files=True,
                )

            with col_right:
                manager_choice = st.selectbox(
                    "Менеджер на этих звонках",
                    managers_list,
                )

            if uploaded_files and st.button("🚀 Запустить анализ", type="primary"):
                progress = st.progress(0.0)
                status = st.empty()
                error_log = []

                for idx, f in enumerate(uploaded_files):
                    status.info(f"Обрабатываю {idx + 1} из {len(uploaded_files)}: {f.name}")
                    try:
                        result = analyze_audio(f.read(), f.name, api_key)
                        save_call({
                            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                            "filename": f.name,
                            "manager": manager_choice,
                            **result,
                        })
                    except Exception as e:
                        error_log.append(f"❌ {f.name}: {e}")
                    progress.progress((idx + 1) / len(uploaded_files))

                status.success(f"Готово! Обработано {len(uploaded_files) - len(error_log)} из {len(uploaded_files)}")
                if error_log:
                    with st.expander("Подробности по ошибкам"):
                        for line in error_log:
                            st.write(line)
                st.balloons()


# ========== ВКЛАДКА 2: дэшборд ==========
with tab_dashboard:
    df = load_calls()

    if df.empty:
        st.info("Пока нет проанализированных звонков. Загрузите хотя бы один на вкладке «Загрузить звонки».")
    else:
        # --- Фильтры ---
        col1, col2, col3 = st.columns(3)
        with col1:
            mgr_filter = st.selectbox("Менеджер", ["Все"] + sorted(df["manager"].unique().tolist()))
        with col2:
            df["uploaded_at_dt"] = pd.to_datetime(df["uploaded_at"])
            min_date, max_date = df["uploaded_at_dt"].min().date(), df["uploaded_at_dt"].max().date()
            date_range = st.date_input("Период", (min_date, max_date))
        with col3:
            quality_filter = st.multiselect(
                "Качество контакта",
                ["high", "medium", "low"],
                default=["high", "medium", "low"],
            )

        # Применяем фильтры
        view = df.copy()
        if mgr_filter != "Все":
            view = view[view["manager"] == mgr_filter]
        if isinstance(date_range, tuple) and len(date_range) == 2:
            d1, d2 = date_range
            view = view[(view["uploaded_at_dt"].dt.date >= d1) & (view["uploaded_at_dt"].dt.date <= d2)]
        view = view[view["contact_quality"].isin(quality_filter)]

        # --- KPI ---
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Звонков", len(view))
        c2.metric("Среднее удержание", f"{int(view['total_deduction'].mean()) if len(view) else 0}")
        c3.metric("Сумма удержаний", f"{int(view['total_deduction'].sum())}")
        c4.metric("Менеджеров", view["manager"].nunique())

        st.divider()

        # --- Графики ---
        if len(view) >= 2:
            cg1, cg2 = st.columns(2)
            with cg1:
                st.subheader("Динамика удержаний по дням")
                daily = view.groupby(view["uploaded_at_dt"].dt.date)["total_deduction"].mean().reset_index()
                daily.columns = ["date", "avg_deduction"]
                fig = px.line(daily, x="date", y="avg_deduction", markers=True)
                st.plotly_chart(fig, use_container_width=True)

            with cg2:
                st.subheader("Среднее удержание по менеджерам")
                by_mgr = view.groupby("manager")["total_deduction"].mean().reset_index().sort_values("total_deduction")
                fig2 = px.bar(by_mgr, x="manager", y="total_deduction")
                st.plotly_chart(fig2, use_container_width=True)

        st.divider()

        # --- Таблица ---
        st.subheader("Список звонков")
        display_cols = ["id", "uploaded_at", "filename", "manager", "client_name",
                        "total_deduction", "contact_quality", "summary"]
        st.dataframe(
            view[display_cols].rename(columns={
                "id": "ID",
                "uploaded_at": "Дата",
                "filename": "Файл",
                "manager": "Менеджер",
                "client_name": "Клиент",
                "total_deduction": "Удержание",
                "contact_quality": "Контакт",
                "summary": "Резюме",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # --- Экспорт ---
        with st.expander("📥 Экспорт в Excel"):
            if st.button("Скачать xlsx"):
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    view[display_cols].to_excel(writer, index=False, sheet_name="Звонки")
                st.download_button(
                    "⬇️ Сохранить файл",
                    data=buf.getvalue(),
                    file_name=f"calls_export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ========== ВКЛАДКА 3: детальный просмотр ==========
with tab_detail:
    df_all = load_calls()
    if df_all.empty:
        st.info("Сначала загрузите хотя бы один звонок.")
    else:
        options = {
            f"#{r['id']} — {r['manager']} — {r['filename']} — удержание {r['total_deduction']}": r["id"]
            for _, r in df_all.iterrows()
        }
        sel = st.selectbox("Выберите звонок", list(options.keys()))
        call_id = options[sel]
        row = df_all[df_all["id"] == call_id].iloc[0]

        st.subheader(f"📞 {row['filename']}")
        st.caption(f"Менеджер: {row['manager']} · Дата: {row['uploaded_at']} · Клиент: {row['client_name'] or '—'}")

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Удержание", row["total_deduction"])
        col_m2.metric("Качество контакта", row["contact_quality"] or "—")
        col_m3.metric("Тон", row["tone"] or "—")

        st.divider()
        st.markdown("### Резюме")
        st.write(row["summary"])

        st.markdown("### Сильные стороны")
        for s in json.loads(row["strengths"] or "[]"):
            st.write(f"✅ {s}")

        st.markdown("### Зоны роста")
        for s in json.loads(row["growth_zones"] or "[]"):
            st.write(f"⚠️ {s}")

        st.markdown("### Рекомендации")
        for s in json.loads(row["recommendations"] or "[]"):
            st.write(f"💡 {s}")

        review = json.loads(row["needs_review"] or "[]")
        if review:
            st.markdown("### Требует ручной проверки тимлида")
            for s in review:
                st.warning(s)

        with st.expander("🔍 Полный отчёт по чеклисту"):
            violations = json.loads(row["violations_json"] or "[]")
            if violations:
                vdf = pd.DataFrame(violations)
                st.dataframe(vdf, use_container_width=True, hide_index=True)
            st.markdown(row["full_report"] or "")

        if st.button("🗑️ Удалить этот звонок", type="secondary"):
            delete_call(call_id)
            st.success("Удалено")
            st.rerun()
