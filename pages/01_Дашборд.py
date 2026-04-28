"""Главный дашборд РОПа."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.express as px

from core.database import (
    get_dashboard_stats, get_trend_data, get_manager_stats,
    get_stage_heatmap, get_error_stats, get_users, get_teams,
)
from core.score_calculator import score_to_color, risk_color, call_type_label
from components.kpi_cards import render_kpi_row, kpi_card, score_card
from components.charts import (
    trend_line, bar_chart, heatmap, scatter_chart, donut_chart, _empty_fig,
)

st.set_page_config(page_title="Дашборд РОПа", page_icon="📊", layout="wide")
st.title("📊 Главный дашборд РОПа")

# ── Фильтры ──────────────────────────────────────────────────────────────
with st.expander("🔍 Фильтры", expanded=False):
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        days = st.selectbox("Период", [7, 14, 30, 60, 90], index=2,
                             format_func=lambda d: f"Последние {d} дней")
    with fc2:
        teams_df = get_teams()
        team_options = ["Все команды"] + teams_df["name"].tolist()
        team_sel = st.selectbox("Команда", team_options)
        team_id = None if team_sel == "Все команды" else int(
            teams_df[teams_df["name"] == team_sel]["id"].iloc[0])
    with fc3:
        mgrs_df = get_users(role="manager")
        mgr_options = ["Все менеджеры"] + mgrs_df["name"].tolist()
        mgr_sel = st.selectbox("Менеджер", mgr_options)
        mgr_id = None if mgr_sel == "Все менеджеры" else int(
            mgrs_df[mgrs_df["name"] == mgr_sel]["id"].iloc[0])

# ── KPI ──────────────────────────────────────────────────────────────────
stats = get_dashboard_stats(manager_id=mgr_id, team_id=team_id, days=days)

if stats.get("total_calls", 0) == 0:
    st.info("📭 Пока нет данных за выбранный период. Загрузите звонки на странице «Звонки».")
    st.stop()

render_kpi_row(stats)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# Дополнительный ряд KPI
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Слабых согласий", stats.get("weak_agreement_count", 0),
             color="#EAB308", help_text="Звонки, где клиент дал слабое подтверждение")
with c2:
    kpi_card("Критичных ошибок", stats.get("critical_errors", 0),
             color="#EF4444", help_text="Ошибки с критичностью 'critical'")
with c3:
    kpi_card("Требуют проверки", stats.get("needs_review", 0),
             color="#F97316", help_text="Спорные моменты, требующие ручного просмотра")
with c4:
    achieved = stats.get("goal_achieved_count", 0) or 0
    analyzed = stats.get("analyzed_calls", 0) or 1
    kpi_card("Цель достигнута",
             f"{round(achieved / analyzed * 100)}%",
             color="#22C55E",
             help_text="Доля звонков, в которых цель (запись) достигнута")

st.divider()

# ── Тренды ───────────────────────────────────────────────────────────────
st.subheader("📈 Динамика показателей")

tc1, tc2 = st.columns(2)

with tc1:
    trend_df = get_trend_data("qa_score", days=days, manager_id=mgr_id)
    fig = trend_line(trend_df, "date", "value", "QA Score по дням", "QA Score")
    st.plotly_chart(fig, use_container_width=True)

with tc2:
    trend_df2 = get_trend_data("show_up_probability_score", days=days, manager_id=mgr_id)
    fig2 = trend_line(trend_df2, "date", "value", "Прогноз доходимости по дням",
                      "Show-Up Probability", color="#22C55E")
    st.plotly_chart(fig2, use_container_width=True)

tc3, tc4 = st.columns(2)

with tc3:
    trend_df3 = get_trend_data("tone_score", days=days, manager_id=mgr_id)
    fig3 = trend_line(trend_df3, "date", "value", "Tone Score по дням",
                      "Tone Score", color="#6366F1")
    st.plotly_chart(fig3, use_container_width=True)

with tc4:
    trend_df4 = get_trend_data("client_reflection_score", days=days, manager_id=mgr_id)
    fig4 = trend_line(trend_df4, "date", "value", "Психосостояние клиента по дням",
                      "Client Reflection Score", color="#F97316")
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Менеджеры ─────────────────────────────────────────────────────────────
st.subheader("👥 Рейтинг менеджеров")

mgr_stats = get_manager_stats(days=days)
if not mgr_stats.empty and "manager_name" in mgr_stats.columns:
    mgr_stats = mgr_stats.dropna(subset=["avg_qa_score"])
    mgr_stats["avg_qa_score"] = mgr_stats["avg_qa_score"].fillna(0)

    mc1, mc2 = st.columns(2)
    with mc1:
        fig_mgr = bar_chart(
            mgr_stats.sort_values("avg_qa_score"),
            x="avg_qa_score", y="manager_name",
            title="Средний QA Score по менеджерам",
            orientation="h",
            color_col="avg_qa_score",
        )
        st.plotly_chart(fig_mgr, use_container_width=True)

    with mc2:
        fig_mgr2 = bar_chart(
            mgr_stats.sort_values("avg_show_up"),
            x="avg_show_up", y="manager_name",
            title="Средний прогноз доходимости",
            orientation="h",
            color="#22C55E",
        )
        st.plotly_chart(fig_mgr2, use_container_width=True)

    # Таблица менеджеров
    display_cols = {
        "manager_name": "Менеджер",
        "team_name": "Команда",
        "call_count": "Звонков",
        "avg_qa_score": "QA Score",
        "avg_tone_score": "Tone",
        "avg_client_score": "Клиент",
        "avg_show_up": "Доходимость",
        "weak_agreements": "Слабых согл.",
    }
    show_df = mgr_stats[[c for c in display_cols if c in mgr_stats.columns]].rename(columns=display_cols)
    for col in ["QA Score", "Tone", "Клиент", "Доходимость"]:
        if col in show_df.columns:
            show_df[col] = show_df[col].round(1)
    st.dataframe(show_df, use_container_width=True, hide_index=True)
else:
    st.info("Нет данных по менеджерам за выбранный период.")

st.divider()

# ── Тепловая карта этапов ─────────────────────────────────────────────────
st.subheader("🗺️ Менеджеры × Этапы продаж")

heatmap_df = get_stage_heatmap(days=days)
if not heatmap_df.empty:
    fig_heat = heatmap(heatmap_df, "manager_name", "stage_name", "avg_score",
                       "Средний балл по этапам")
    st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info("Нет данных для тепловой карты.")

st.divider()

# ── Топ ошибок ────────────────────────────────────────────────────────────
st.subheader("❌ Топ повторяющихся ошибок")

err_df = get_error_stats(days=days)
if not err_df.empty:
    ec1, ec2 = st.columns([2, 1])
    with ec1:
        err_top = err_df.head(10)
        fig_err = bar_chart(
            err_top, x="count", y="title",
            title="Частота ошибок", orientation="h", color="#EF4444",
        )
        st.plotly_chart(fig_err, use_container_width=True)

    with ec2:
        # Donut по критичности
        if "criticality" in err_df.columns:
            crit_counts = err_df.groupby("criticality")["count"].sum()
            labels_map = {"low": "Низкая", "medium": "Средняя",
                          "high": "Высокая", "critical": "Критическая"}
            labels = [labels_map.get(l, l) for l in crit_counts.index]
            fig_d = donut_chart(labels, crit_counts.values.tolist(),
                                "По критичности")
            st.plotly_chart(fig_d, use_container_width=True)
else:
    st.info("Нет данных по ошибкам.")
