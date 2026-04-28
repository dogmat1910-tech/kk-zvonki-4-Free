"""Список звонков с фильтрами и загрузкой новых."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from datetime import datetime

from core.database import (
    get_calls, save_call, get_users, get_teams, delete_call, get_conn,
)
from core.ai_pipeline import analyze_call, get_api_key
from core.score_calculator import (
    score_to_color, call_type_label, analysis_status_label, risk_level_label,
)

st.set_page_config(page_title="Звонки", page_icon="📞", layout="wide")
st.title("📞 Звонки")

tabs = st.tabs(["📥 Загрузить звонки", "📋 Список звонков"])

# ═══════════════════════════════════════════════════
# ВКЛАДКА 1: ЗАГРУЗКА
# ═══════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Загрузить и проанализировать звонки")

    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ Сначала введите API-ключ Gemini в боковой панели на главной странице.")
        st.stop()

    mgrs_df = get_users(role="manager")
    if mgrs_df.empty:
        st.warning("⚠️ Сначала добавьте менеджеров на странице «Настройки».")
        st.stop()

    uc1, uc2 = st.columns([2, 1])

    with uc1:
        uploaded = st.file_uploader(
            "Перетащите аудиофайлы или нажмите для выбора",
            type=["mp3", "wav", "m4a", "ogg", "flac", "aac", "opus"],
            accept_multiple_files=True,
            help="Поддерживаются форматы: MP3, WAV, M4A, OGG, FLAC, AAC, OPUS",
        )

    with uc2:
        mgr_names = mgrs_df["name"].tolist()
        mgr_sel = st.selectbox("Менеджер", mgr_names)
        mgr_id = int(mgrs_df[mgrs_df["name"] == mgr_sel]["id"].iloc[0])

        call_date = st.date_input("Дата звонков", value=datetime.today())
        direction = st.selectbox("Направление", ["outbound", "inbound"],
                                 format_func=lambda x: "Исходящий" if x == "outbound" else "Входящий")

    if uploaded:
        st.info(f"Выбрано файлов: {len(uploaded)}")

        with st.expander("ℹ️ Как работает анализ"):
            st.markdown("""
            1. **Транскрипция** — Gemini переводит аудио в текст с разделением менеджер/клиент
            2. **Анализ** — ИИ оценивает по чеклисту, этапам продаж, тону, психосостоянию
            3. **Сохранение** — все результаты сохраняются в базу данных
            4. **Дашборды** — данные сразу появляются в дашбордах

            ⏱️ Один звонок занимает ~1–3 минуты. Лимит бесплатного Gemini ~20 звонков/день.
            """)

        if st.button("🚀 Запустить анализ", type="primary"):
            progress = st.progress(0.0)
            status   = st.empty()
            errors   = []

            for i, f in enumerate(uploaded):
                status.info(f"📞 {i+1}/{len(uploaded)}: {f.name}")
                try:
                    audio_bytes = f.read()

                    # Сохраняем звонок
                    call_id = save_call({
                        "manager_id": mgr_id,
                        "filename": f.name,
                        "direction": direction,
                        "call_datetime": call_date.isoformat(),
                        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
                        "analysis_status": "pending",
                    })

                    # Анализируем
                    analyze_call(
                        call_id=call_id,
                        audio_bytes=audio_bytes,
                        filename=f.name,
                        status_placeholder=status,
                    )

                except Exception as e:
                    errors.append(f"❌ {f.name}: {e}")

                progress.progress((i + 1) / len(uploaded))

            if errors:
                status.warning(f"Завершено с ошибками ({len(errors)} из {len(uploaded)})")
                with st.expander("Подробности ошибок"):
                    for err in errors:
                        st.write(err)
            else:
                status.success(f"✅ Готово! Проанализировано {len(uploaded)} звонков")
                st.balloons()


# ═══════════════════════════════════════════════════
# ВКЛАДКА 2: СПИСОК ЗВОНКОВ
# ═══════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Все звонки")

    # Фильтры
    with st.expander("🔍 Фильтры", expanded=True):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            mgrs_df2 = get_users(role="manager")
            mgr_filter_opts = ["Все"] + mgrs_df2["name"].tolist()
            mgr_filter = st.selectbox("Менеджер", mgr_filter_opts, key="list_mgr")
        with fc2:
            type_opts = ["Все типы", "primary_outbound", "primary_inbound",
                         "confirmation", "repeat", "inactive"]
            type_filter = st.selectbox("Тип звонка", type_opts,
                                       format_func=lambda x: x if x == "Все типы" else call_type_label(x))
        with fc3:
            status_opts = ["Все", "done", "pending", "processing", "error"]
            status_filter = st.selectbox("Статус анализа", status_opts,
                                          format_func=lambda x: x if x == "Все" else analysis_status_label(x))
        with fc4:
            active_filter = st.selectbox("Активность", ["Все", "Активные", "Неактивные"])

    # Загружаем звонки
    filter_mgr_id = None
    if mgr_filter != "Все" and not mgrs_df2.empty:
        matched = mgrs_df2[mgrs_df2["name"] == mgr_filter]
        if not matched.empty:
            filter_mgr_id = int(matched["id"].iloc[0])

    df = get_calls(manager_id=filter_mgr_id, limit=1000)

    if df.empty:
        st.info("📭 Нет звонков. Загрузите аудиофайлы на вкладке «Загрузить звонки».")
        st.stop()

    # Применяем фильтры
    if type_filter != "Все типы":
        df = df[df["call_type"] == type_filter]
    if status_filter != "Все":
        df = df[df["analysis_status"] == status_filter]
    if active_filter == "Активные":
        df = df[df["is_active_call"] == 1]
    elif active_filter == "Неактивные":
        df = df[df["is_active_call"] == 0]

    st.markdown(f"**Найдено:** {len(df)} звонков")

    # Форматируем для отображения
    display = df.copy()

    def fmt_score(v):
        if pd.isna(v) or v == 0:
            return "—"
        return f"{v:.0f}"

    def fmt_risk(v):
        if pd.isna(v) or not v:
            return "—"
        labels = {"low": "🟢 Низкий", "medium": "🟡 Средний",
                  "high": "🟠 Высокий", "critical": "🔴 Критический"}
        return labels.get(v, v)

    # Стилизация колонок
    cols_map = {
        "id": "ID",
        "uploaded_at": "Дата загрузки",
        "filename": "Файл",
        "manager_name": "Менеджер",
        "call_type": "Тип",
        "is_active_call": "Активный",
        "analysis_status": "Статус",
        "qa_score": "QA",
        "tone_score": "Тон",
        "show_up_probability_score": "Доходимость",
        "show_up_risk_level": "Риск неявки",
        "error_count": "Ошибок",
        "weak_agreement_detected": "Слаб. согл.",
    }

    show_cols = [c for c in cols_map if c in display.columns]
    display = display[show_cols].rename(columns=cols_map)

    if "Тип" in display.columns:
        display["Тип"] = display["Тип"].apply(lambda x: call_type_label(x) if x else "—")
    if "Активный" in display.columns:
        display["Активный"] = display["Активный"].apply(lambda x: "✅" if x else "❌")
    if "Статус" in display.columns:
        display["Статус"] = display["Статус"].apply(analysis_status_label)
    if "Риск неявки" in display.columns:
        display["Риск неявки"] = display["Риск неявки"].apply(fmt_risk)
    if "Слаб. согл." in display.columns:
        display["Слаб. согл."] = display["Слаб. согл."].apply(lambda x: "⚡ Да" if x else "")
    for col in ["QA", "Тон", "Доходимость"]:
        if col in display.columns:
            display[col] = display[col].apply(fmt_score)

    st.dataframe(display, use_container_width=True, hide_index=True)

    # Экспорт
    with st.expander("📥 Экспорт в Excel"):
        import io
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            display.to_excel(writer, index=False, sheet_name="Звонки")
        st.download_button(
            "⬇️ Скачать xlsx",
            data=buf.getvalue(),
            file_name=f"calls_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.divider()

    # Удаление звонка
    if not df.empty:
        del_id = st.number_input("ID звонка для удаления", min_value=1, step=1, value=None)
        if del_id and st.button("🗑️ Удалить звонок", type="secondary"):
            delete_call(int(del_id))
            st.success(f"Звонок #{del_id} удалён")
            st.rerun()
