"""Настройки системы: менеджеры, команды, AI."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import (
    get_users, get_teams, upsert_user, upsert_team,
    get_conn, init_db,
)

st.set_page_config(page_title="Настройки", page_icon="⚙️", layout="wide")
st.title("⚙️ Настройки")

tabs = st.tabs(["👥 Менеджеры и команды", "🔑 API и ИИ", "🗄️ База данных"])

# ═══════════════════════════════════════════════════
# МЕНЕДЖЕРЫ И КОМАНДЫ
# ═══════════════════════════════════════════════════
with tabs[0]:
    tc1, tc2 = st.columns(2)

    with tc1:
        st.subheader("🏢 Команды")
        teams_df = get_teams()

        if not teams_df.empty:
            st.dataframe(teams_df[["id","name","created_at"]].rename(columns={
                "id":"ID","name":"Название","created_at":"Создана"
            }), use_container_width=True, hide_index=True)
        else:
            st.info("Команд пока нет.")

        with st.form("add_team"):
            new_team = st.text_input("Название новой команды*", placeholder="Команда А")
            if st.form_submit_button("➕ Добавить команду"):
                if new_team.strip():
                    upsert_team(new_team.strip())
                    st.success(f"Команда «{new_team}» добавлена")
                    st.rerun()
                else:
                    st.error("Введите название")

    with tc2:
        st.subheader("👤 Менеджеры")
        mgrs_df = get_users()

        if not mgrs_df.empty:
            show = mgrs_df[["id","name","role","team_name","is_active"]].rename(columns={
                "id":"ID","name":"Имя","role":"Роль",
                "team_name":"Команда","is_active":"Активен"
            })
            show["Активен"] = show["Активен"].apply(lambda x: "✅" if x else "❌")
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            st.info("Менеджеров пока нет.")

        st.divider()
        with st.form("add_manager"):
            nm_name  = st.text_input("Имя менеджера*", placeholder="Иван Иванов")
            nm_email = st.text_input("Email (необязательно)", placeholder="ivan@company.ru")
            nm_role  = st.selectbox("Роль", ["manager", "team_lead", "rop"],
                                    format_func=lambda x: {"manager":"Менеджер","team_lead":"Тимлид","rop":"РОП"}.get(x,x))

            teams_df2 = get_teams()
            team_opts = ["Без команды"] + teams_df2["name"].tolist()
            nm_team  = st.selectbox("Команда", team_opts)
            nm_tid   = None
            if nm_team != "Без команды" and not teams_df2.empty:
                matched = teams_df2[teams_df2["name"] == nm_team]
                if not matched.empty:
                    nm_tid = int(matched["id"].iloc[0])

            if st.form_submit_button("➕ Добавить менеджера", type="primary"):
                if nm_name.strip():
                    upsert_user(nm_name.strip(), role=nm_role,
                                team_id=nm_tid, email=nm_email)
                    st.success(f"Менеджер «{nm_name}» добавлен")
                    st.rerun()
                else:
                    st.error("Введите имя")

    st.divider()

    # Деактивация менеджера
    st.subheader("🗑️ Деактивировать менеджера")
    all_mgrs = get_users()
    if not all_mgrs.empty:
        mgr_to_deact = st.selectbox("Менеджер", all_mgrs["name"].tolist())
        if st.button("⛔ Деактивировать", type="secondary"):
            conn = get_conn()
            matched_id = all_mgrs[all_mgrs["name"] == mgr_to_deact]["id"].iloc[0]
            conn.execute("UPDATE users SET is_active=0 WHERE id=?", (int(matched_id),))
            conn.commit()
            conn.close()
            st.success(f"Менеджер «{mgr_to_deact}» деактивирован")
            st.rerun()


# ═══════════════════════════════════════════════════
# API И ИИ
# ═══════════════════════════════════════════════════
with tabs[1]:
    st.subheader("🔑 Gemini API")

    st.markdown("""
    **Как подключить API-ключ:**

    **Вариант 1 — Streamlit Secrets (рекомендуется для продакшена):**
    1. Открой репозиторий на GitHub
    2. Перейди на Streamlit Cloud → твоё приложение → Settings → Secrets
    3. Добавь:
    ```
    GEMINI_API_KEY = "AIzaSy..."
    ```

    **Вариант 2 — Временный ввод (для тестов):**
    Введи ключ в поле на главной странице (левая панель).

    **Получить ключ бесплатно:** https://aistudio.google.com/apikey
    """)

    from core.ai_pipeline import get_api_key, MODEL_CHAIN
    api_key = get_api_key()

    if api_key:
        st.success(f"✅ API-ключ подключён (первые 8 символов: `{api_key[:8]}...`)")
    else:
        st.warning("⚠️ API-ключ не задан")

    st.divider()
    st.subheader("🤖 Цепочка моделей Gemini")
    st.markdown("Модели используются в этом порядке (при исчерпании квоты — следующая):")
    for i, m in enumerate(MODEL_CHAIN):
        st.markdown(f"  {i+1}. `{m}`")

    st.info("💡 Бесплатный лимит Gemini: ~20 запросов в день на ключ. "
            "Один звонок = 1-2 запроса (транскрипция + анализ).")

    st.divider()
    st.subheader("📊 Мониторинг квот")
    st.markdown("Проверить текущие лимиты: https://ai.dev/rate-limit")


# ═══════════════════════════════════════════════════
# БАЗА ДАННЫХ
# ═══════════════════════════════════════════════════
with tabs[2]:
    st.subheader("🗄️ База данных")

    conn = get_conn()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    st.markdown(f"**Таблиц в БД:** {len(tables)}")

    for t in tables:
        tname = t[0]
        count = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        st.markdown(f"  — `{tname}`: **{count}** записей")

    conn.close()

    st.divider()
    st.subheader("🔄 Переинициализация БД")
    st.warning("⚠️ Не удаляет существующие данные — только добавляет недостающие таблицы и значения по умолчанию.")
    if st.button("🔄 Переинициализировать"):
        init_db()
        st.success("✅ БД переинициализирована")

    st.divider()
    st.subheader("📤 Экспорт всей базы")

    import io, pandas as pd
    conn2 = get_conn()
    try:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for t in tables:
                tname = t[0]
                try:
                    df_t = pd.read_sql(f"SELECT * FROM {tname} LIMIT 10000", conn2)
                    df_t.to_excel(writer, index=False, sheet_name=tname[:31])
                except Exception:
                    pass
        conn2.close()
        st.download_button(
            "⬇️ Скачать всю БД в Excel",
            data=buf.getvalue(),
            file_name="kk_database_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        conn2.close()
        st.error(f"Ошибка экспорта: {e}")
