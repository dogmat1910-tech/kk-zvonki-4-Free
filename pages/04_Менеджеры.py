"""Дашборд обзора команды менеджеров."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import get_manager_stats, get_stage_heatmap, get_users, get_teams
from core.score_calculator import score_to_color, score_to_grade
from components.charts import bar_chart, heatmap, radar_chart, scatter_chart

st.set_page_config(page_title="Менеджеры", page_icon="👥", layout="wide")
st.title("👥 Дашборд менеджеров")

# Фильтры
fc1, fc2 = st.columns(2)
with fc1:
    days = st.selectbox("Период", [7, 14, 30, 60, 90], index=2,
                         format_func=lambda d: f"Последние {d} дней")
with fc2:
    teams_df = get_teams()
    team_opts = ["Все команды"] + teams_df["name"].tolist()
    team_sel = st.selectbox("Команда", team_opts)

mgr_stats = get_manager_stats(days=days)

if mgr_stats.empty or "manager_name" not in mgr_stats.columns:
    st.info("📭 Нет данных. Загрузите и проанализируйте звонки.")
    st.stop()

if team_sel != "Все команды" and "team_name" in mgr_stats.columns:
    mgr_stats = mgr_stats[mgr_stats["team_name"] == team_sel]

if mgr_stats.empty:
    st.info("Нет данных по выбранным фильтрам.")
    st.stop()

mgr_stats = mgr_stats.fillna(0)

# ── Общая таблица ─────────────────────────────────────────────────────────
st.subheader("📊 Сводная таблица")

display_cols = {
    "manager_name": "Менеджер",
    "team_name": "Команда",
    "call_count": "Звонков",
    "avg_qa_score": "QA Score",
    "avg_tone_score": "Тон",
    "avg_client_score": "Клиент",
    "avg_show_up": "Доходимость",
    "avg_closing": "Закрытие",
    "avg_objections": "Возражения",
    "weak_agreements": "Слаб. согл.",
}

show_df = mgr_stats[[c for c in display_cols if c in mgr_stats.columns]].rename(columns=display_cols)
for col in ["QA Score", "Тон", "Клиент", "Доходимость", "Закрытие", "Возражения"]:
    if col in show_df.columns:
        show_df[col] = show_df[col].round(1)

st.dataframe(show_df, use_container_width=True, hide_index=True)

st.divider()

# ── Графики ───────────────────────────────────────────────────────────────
st.subheader("📈 Сравнительные графики")

gc1, gc2 = st.columns(2)

with gc1:
    fig = bar_chart(
        mgr_stats.sort_values("avg_qa_score"),
        x="avg_qa_score", y="manager_name",
        title="QA Score по менеджерам",
        orientation="h",
        color_col="avg_qa_score",
    )
    st.plotly_chart(fig, use_container_width=True)

with gc2:
    fig2 = scatter_chart(
        mgr_stats, x="avg_tone_score", y="avg_show_up",
        title="Тон менеджера × Прогноз доходимости",
        hover_name="manager_name",
        x_label="Tone Score",
        y_label="Show-Up Probability",
    )
    st.plotly_chart(fig2, use_container_width=True)

gc3, gc4 = st.columns(2)

with gc3:
    fig3 = bar_chart(
        mgr_stats.sort_values("avg_show_up"),
        x="avg_show_up", y="manager_name",
        title="Прогноз доходимости по менеджерам",
        orientation="h",
        color="#22C55E",
    )
    st.plotly_chart(fig3, use_container_width=True)

with gc4:
    fig4 = bar_chart(
        mgr_stats.sort_values("weak_agreements", ascending=False),
        x="weak_agreements", y="manager_name",
        title="Слабые согласия по менеджерам",
        orientation="h",
        color="#EAB308",
    )
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Тепловая карта ────────────────────────────────────────────────────────
st.subheader("🗺️ Тепловая карта: менеджеры × этапы")

heat_df = get_stage_heatmap(days=days)
if not heat_df.empty:
    if team_sel != "Все команды" and "team_name" in heat_df.columns:
        heat_df = heat_df  # фильтр по команде добавим в будущем
    fig_h = heatmap(heat_df, "manager_name", "stage_name", "avg_score",
                    "Средний балл по этапам продаж")
    st.plotly_chart(fig_h, use_container_width=True)
else:
    st.info("Нет данных для тепловой карты.")

st.divider()

# ── Карточки менеджеров ───────────────────────────────────────────────────
st.subheader("👤 Карточки менеджеров")

for _, row in mgr_stats.iterrows():
    qa = row.get("avg_qa_score", 0)
    color = score_to_color(qa)
    grade = score_to_grade(qa)

    with st.expander(f"👤 {row.get('manager_name','?')} — QA: {qa:.0f} ({grade})"):
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            st.metric("Звонков", int(row.get("call_count", 0)))
            st.metric("QA Score", f"{qa:.0f}")
        with cc2:
            st.metric("Тон", f"{row.get('avg_tone_score',0):.0f}")
            st.metric("Клиент", f"{row.get('avg_client_score',0):.0f}")
        with cc3:
            st.metric("Доходимость", f"{row.get('avg_show_up',0):.0f}%")
            st.metric("Закрытие", f"{row.get('avg_closing',0):.0f}")
        with cc4:
            st.metric("Слабых согл.", int(row.get("weak_agreements", 0)))
            st.metric("Возражения", f"{row.get('avg_objections',0):.0f}")

        st.caption(f"Команда: {row.get('team_name','—')}")
        st.page_link("pages/05_Менеджер.py",
                     label="📈 Открыть детальную карточку →")
