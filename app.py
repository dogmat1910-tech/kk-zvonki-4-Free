"""
КК ИИ — AI-платформа контроля качества звонков для РОПа.
Точка входа Streamlit. Инициализирует БД и настраивает навигацию.
"""

import streamlit as st
import sys, os

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import init_db

st.set_page_config(
    page_title="КК ИИ — Контроль качества",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Инициализация БД при первом запуске
init_db()

# ── Боковая панель: API-ключ ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🎯 КК ИИ")
    st.caption("AI-платформа для РОПа")
    st.divider()

    # API-ключ
    api_key = ""
    try:
        api_key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        api_key = ""

    if api_key:
        st.success("✅ Gemini API подключён")
        st.session_state["api_key"] = api_key
    else:
        stored = st.session_state.get("api_key", "")
        key_input = st.text_input(
            "🔑 API-ключ Gemini",
            value=stored,
            type="password",
            placeholder="AIza...",
            help="Получить бесплатно: https://aistudio.google.com/apikey",
        )
        if key_input:
            st.session_state["api_key"] = key_input
            st.success("✅ Ключ сохранён")
        elif not stored:
            st.warning("⚠️ Введите API-ключ для работы ИИ")

    st.divider()
    st.markdown(
        "<div style='font-size:11px;color:#64748B'>Анализ через Google Gemini.<br>"
        "Free tier: ~20 звонков/день.<br>"
        "Данные хранятся локально.</div>",
        unsafe_allow_html=True,
    )

# ── Главная страница ───────────────────────────────────────────────────────
st.title("🎯 КК ИИ — Контроль качества звонков")
st.markdown(
    "AI-супервайзер для РОПа: транскрибирует звонки, оценивает по чеклисту, "
    "анализирует тон, психосостояние клиента, прогнозирует доходимость и формирует тренинги."
)

st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("""
    **📊 Дашборды**
    - Главный дашборд РОПа
    - Менеджеры и команды
    - Этапы продаж
    - Ошибки и тон
    """)
with col2:
    st.markdown("""
    **📞 Звонки**
    - Загрузка аудио
    - AI-транскрипция
    - Детальный разбор
    - Эмоциональный таймлайн
    """)
with col3:
    st.markdown("""
    **🎓 Развитие**
    - Библиотека фраз
    - AI-тренинги
    - Рекомендации РОПу
    - Редактор чеклиста
    """)

st.markdown("---")
st.markdown(
    "👈 **Выберите раздел в меню слева** для начала работы.",
    unsafe_allow_html=True,
)
