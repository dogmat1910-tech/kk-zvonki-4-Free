"""Библиотека лучших и худших фраз."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import get_phrase_library, update_phrase_status, get_users
from core.score_calculator import phrase_type_label

st.set_page_config(page_title="Библиотека фраз", page_icon="💬", layout="wide")
st.title("💬 Библиотека фраз")

st.caption("Фразы автоматически выделяются ИИ при анализе звонков. "
           "РОП может подтверждать или отклонять кандидатов.")

# ── Фильтры ──────────────────────────────────────────────────────────────
with st.expander("🔍 Фильтры", expanded=True):
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        phrase_type_opts = [
            "Все типы", "best", "worst", "forbidden",
            "no_show_risk", "closing", "value",
            "objection", "commitment", "trust_damage",
            "pressure", "false_expectation",
        ]
        pt_sel = st.selectbox("Тип фразы", phrase_type_opts,
                              format_func=lambda x: "Все типы" if x == "Все типы" else phrase_type_label(x))
    with fc2:
        mgrs_df = get_users(role="manager")
        mgr_opts = ["Все менеджеры"] + mgrs_df["name"].tolist()
        mgr_sel = st.selectbox("Менеджер", mgr_opts)
        mgr_id_filter = None
        if mgr_sel != "Все менеджеры" and not mgrs_df.empty:
            matched = mgrs_df[mgrs_df["name"] == mgr_sel]
            if not matched.empty:
                mgr_id_filter = int(matched["id"].iloc[0])
    with fc3:
        stage_opts = [
            "Все этапы", "contact", "needs", "qualification",
            "presentation", "objections", "closing",
            "summary", "commitment", "additional",
        ]
        stage_labels = {
            "contact": "Установление контакта",
            "needs": "Выявление потребностей",
            "qualification": "Квалификация",
            "presentation": "Презентация БК",
            "objections": "Работа с возражениями",
            "closing": "Закрытие",
            "summary": "Резюмирование",
            "commitment": "Фиксация явки",
            "additional": "Дополнительно",
        }
        stage_sel = st.selectbox(
            "Этап продаж", stage_opts,
            format_func=lambda x: "Все этапы" if x == "Все этапы" else stage_labels.get(x, x)
        )

pt_filter = None if pt_sel == "Все типы" else pt_sel
stage_filter = None if stage_sel == "Все этапы" else stage_sel

df = get_phrase_library(phrase_type=pt_filter, manager_id=mgr_id_filter,
                         stage=stage_filter, limit=300)

if df.empty:
    st.info("📭 Фразы ещё не собраны. Они появляются автоматически после анализа звонков.")
    st.stop()

st.markdown(f"**Найдено фраз:** {len(df)}")

# ── Вкладки по типам ─────────────────────────────────────────────────────
best_types   = ["best", "closing", "value", "objection", "commitment"]
worst_types  = ["worst", "forbidden", "trust_damage", "pressure", "false_expectation", "no_show_risk"]

tab_best, tab_worst, tab_new, tab_all = st.tabs([
    "✅ Лучшие фразы",
    "❌ Плохие фразы",
    "🆕 На проверке",
    "📋 Все фразы",
])

def render_phrases(phrases_df: pd.DataFrame):
    if phrases_df.empty:
        st.info("Нет фраз в этой категории.")
        return

    for _, row in phrases_df.iterrows():
        impact = row.get("impact_score", 0)
        impact_color = "#22C55E" if impact > 0 else "#EF4444" if impact < 0 else "#94A3B8"
        pt_label = phrase_type_label(row.get("phrase_type", ""))

        with st.expander(
            f"**\"{(row.get('phrase_text','')[:80])}{'...' if len(row.get('phrase_text','')) > 80 else ''}\"**"
        ):
            pc1, pc2 = st.columns([3, 1])
            with pc1:
                st.markdown(f"**Фраза:** _{row.get('phrase_text','')}_")
                if row.get("explanation"):
                    st.markdown(f"**Почему:** {row['explanation']}")
                meta_parts = []
                if row.get("manager_name"):
                    meta_parts.append(f"👤 {row['manager_name']}")
                if row.get("sales_stage"):
                    meta_parts.append(f"📍 {stage_labels.get(row['sales_stage'], row['sales_stage'])}")
                if row.get("sales_tool"):
                    meta_parts.append(f"🛠️ {row['sales_tool']}")
                if row.get("timestamp"):
                    meta_parts.append(f"⏱ {row['timestamp']}")
                if meta_parts:
                    st.caption(" | ".join(meta_parts))

            with pc2:
                st.markdown(
                    f"**Тип:** {pt_label}\n\n"
                    f"**Влияние:** <span style='color:{impact_color};font-weight:700'>"
                    f"{'+' if impact > 0 else ''}{impact:.0f}</span>",
                    unsafe_allow_html=True,
                )
                pid = row.get("id")
                if pid and row.get("status") in ("new", None):
                    if st.button("✅ Одобрить", key=f"ap_{pid}"):
                        update_phrase_status(int(pid), "approved")
                        st.rerun()
                    if st.button("❌ Отклонить", key=f"rj_{pid}"):
                        update_phrase_status(int(pid), "rejected")
                        st.rerun()
                elif row.get("status") == "approved":
                    st.success("✅ Одобрено")
                elif row.get("status") == "rejected":
                    st.error("❌ Отклонено")

with tab_best:
    st.markdown("Фразы, которые хорошо работают в продажах:")
    best_df = df[df["phrase_type"].isin(best_types)] if "phrase_type" in df.columns else pd.DataFrame()
    best_df_sorted = best_df.sort_values("impact_score", ascending=False) if not best_df.empty else best_df
    render_phrases(best_df_sorted)

with tab_worst:
    st.markdown("Фразы, которые снижают качество и доходимость:")
    worst_df = df[df["phrase_type"].isin(worst_types)] if "phrase_type" in df.columns else pd.DataFrame()
    worst_df_sorted = worst_df.sort_values("impact_score") if not worst_df.empty else worst_df
    render_phrases(worst_df_sorted)

with tab_new:
    st.markdown("Фразы, ожидающие ручной проверки РОПа:")
    new_df = df[df["status"] == "new"] if "status" in df.columns else df
    render_phrases(new_df)

with tab_all:
    st.markdown("Все фразы из библиотеки:")

    # Компактная таблица
    show_cols_map = {
        "phrase_text": "Фраза",
        "phrase_type": "Тип",
        "manager_name": "Менеджер",
        "sales_stage": "Этап",
        "impact_score": "Влияние",
        "status": "Статус",
    }
    show_df = df[[c for c in show_cols_map if c in df.columns]].rename(columns=show_cols_map)
    if "Тип" in show_df.columns:
        show_df["Тип"] = show_df["Тип"].apply(lambda x: phrase_type_label(x) if x else "—")
    if "Этап" in show_df.columns:
        show_df["Этап"] = show_df["Этап"].apply(lambda x: stage_labels.get(x, x) if x else "—")
    if "Фраза" in show_df.columns:
        show_df["Фраза"] = show_df["Фраза"].apply(lambda x: x[:80] + "..." if x and len(x) > 80 else x)
    if "Влияние" in show_df.columns:
        show_df["Влияние"] = show_df["Влияние"].round(0)

    st.dataframe(show_df, use_container_width=True, hide_index=True)

    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Фразы")
    st.download_button("⬇️ Экспорт в Excel", data=buf.getvalue(),
                       file_name="phrase_library.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
