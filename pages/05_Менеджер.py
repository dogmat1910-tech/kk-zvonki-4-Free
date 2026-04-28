"""Детальная карточка менеджера — динамика, сравнение, рекомендации."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import (
    get_users, get_calls, get_trend_data, get_stage_heatmap,
    get_error_stats, get_recommendations, get_conn,
)
from core.score_calculator import (
    score_to_color, score_to_grade, priority_label, risk_level_label,
)
from components.charts import (
    trend_line, bar_chart, radar_chart, scatter_chart, _empty_fig,
)

st.set_page_config(page_title="Менеджер", page_icon="📈", layout="wide")
st.title("📈 Карточка менеджера")

# ── Выбор менеджера ───────────────────────────────────────────────────────
mgrs_df = get_users(role="manager")
if mgrs_df.empty:
    st.info("Менеджеры не добавлены. Перейдите в «Настройки».")
    st.stop()

mgr_name = st.selectbox("Выберите менеджера", mgrs_df["name"].tolist())
mgr_row = mgrs_df[mgrs_df["name"] == mgr_name].iloc[0]
mgr_id = int(mgr_row["id"])

days = st.selectbox("Период", [7, 14, 30, 60, 90], index=2,
                     format_func=lambda d: f"Последние {d} дней")

# ── KPI ──────────────────────────────────────────────────────────────────
from core.database import get_dashboard_stats
stats = get_dashboard_stats(manager_id=mgr_id, days=days)

if stats.get("total_calls", 0) == 0:
    st.info(f"📭 У менеджера {mgr_name} нет звонков за выбранный период.")
    st.stop()

c1, c2, c3, c4, c5 = st.columns(5)
with c1: st.metric("Звонков", stats.get("total_calls", 0))
with c2: st.metric("QA Score", f"{stats.get('avg_qa_score') or 0:.0f}")
with c3: st.metric("Тон", f"{stats.get('avg_tone_score') or 0:.0f}")
with c4: st.metric("Доходимость", f"{stats.get('avg_show_up') or 0:.0f}%")
with c5: st.metric("Слаб. согл.", stats.get("weak_agreement_count", 0))

st.divider()

# ── Динамика ─────────────────────────────────────────────────────────────
st.subheader("📈 Динамика показателей")

tc1, tc2 = st.columns(2)
with tc1:
    df_qa = get_trend_data("qa_score", days=days, manager_id=mgr_id)
    fig = trend_line(df_qa, "date", "value", f"QA Score — {mgr_name}", "QA Score")
    st.plotly_chart(fig, use_container_width=True)

with tc2:
    df_su = get_trend_data("show_up_probability_score", days=days, manager_id=mgr_id)
    fig2 = trend_line(df_su, "date", "value", "Прогноз доходимости", "Show-Up %", color="#22C55E")
    st.plotly_chart(fig2, use_container_width=True)

tc3, tc4 = st.columns(2)
with tc3:
    df_tone = get_trend_data("tone_score", days=days, manager_id=mgr_id)
    fig3 = trend_line(df_tone, "date", "value", "Тон менеджера", "Tone Score", color="#6366F1")
    st.plotly_chart(fig3, use_container_width=True)

with tc4:
    df_cl = get_trend_data("client_reflection_score", days=days, manager_id=mgr_id)
    fig4 = trend_line(df_cl, "date", "value", "Психосостояние клиента", "Client Score", color="#F97316")
    st.plotly_chart(fig4, use_container_width=True)

st.divider()

# ── Профиль по этапам ─────────────────────────────────────────────────────
st.subheader("🕸️ Профиль по этапам продаж")

conn = get_conn()
stage_df = pd.read_sql(f"""
    SELECT sss.stage_name, AVG(sss.score) as avg_score
    FROM sales_stage_scores sss
    JOIN qa_analyses qa ON sss.qa_analysis_id=qa.id
    JOIN calls c ON qa.call_id=c.id
    WHERE c.manager_id={mgr_id}
      AND c.uploaded_at >= datetime('now', '-{days} days')
    GROUP BY sss.stage_name
""", conn)
conn.close()

if not stage_df.empty:
    rc1, rc2 = st.columns([1, 1])
    with rc1:
        categories = stage_df["stage_name"].tolist()
        values     = stage_df["avg_score"].round(1).tolist()
        fig_r = radar_chart(categories, values, f"Профиль: {mgr_name}", mgr_name)
        st.plotly_chart(fig_r, use_container_width=True)

    with rc2:
        fig_bar = bar_chart(
            stage_df.sort_values("avg_score"),
            x="avg_score", y="stage_name",
            title="Баллы по этапам",
            orientation="h",
            color_col="avg_score",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # Выявляем слабые этапы
    weak_stages = stage_df[stage_df["avg_score"] < 60].sort_values("avg_score")
    if not weak_stages.empty:
        st.warning("⚠️ Слабые этапы (< 60 баллов):")
        for _, s in weak_stages.iterrows():
            st.markdown(f"  — **{s['stage_name']}**: {s['avg_score']:.0f}/100")
else:
    st.info("Нет данных по этапам.")

st.divider()

# ── Топ ошибок менеджера ─────────────────────────────────────────────────
st.subheader("❌ Типичные ошибки")

conn = get_conn()
err_df = pd.read_sql(f"""
    SELECT de.title, de.criticality, COUNT(*) as count
    FROM detected_errors de
    JOIN calls c ON de.call_id=c.id
    WHERE c.manager_id={mgr_id}
      AND c.uploaded_at >= datetime('now', '-{days} days')
    GROUP BY de.title, de.criticality
    ORDER BY count DESC
    LIMIT 15
""", conn)
conn.close()

if not err_df.empty:
    fig_err = bar_chart(
        err_df.head(10), x="count", y="title",
        title="Частые ошибки", orientation="h", color="#EF4444",
    )
    st.plotly_chart(fig_err, use_container_width=True)
else:
    st.success("✅ Ошибок не зафиксировано")

st.divider()

# ── Список звонков менеджера ──────────────────────────────────────────────
st.subheader("📞 Звонки")

calls_df = get_calls(manager_id=mgr_id, limit=50)
if not calls_df.empty:
    show_cols = {
        "id": "ID", "uploaded_at": "Дата",
        "filename": "Файл", "analysis_status": "Статус",
        "qa_score": "QA", "tone_score": "Тон",
        "show_up_probability_score": "Доходимость",
        "error_count": "Ошибок",
    }
    disp = calls_df[[c for c in show_cols if c in calls_df.columns]].rename(columns=show_cols)
    for col in ["QA", "Тон", "Доходимость"]:
        if col in disp.columns:
            disp[col] = disp[col].apply(lambda v: f"{v:.0f}" if pd.notna(v) and v else "—")
    st.dataframe(disp, use_container_width=True, hide_index=True)

st.divider()

# ── Рекомендации РОПу ─────────────────────────────────────────────────────
st.subheader("📌 Рекомендации для РОПа")

recs_df = get_recommendations(manager_id=mgr_id, days=days)
if not recs_df.empty:
    priority_icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    for _, rec in recs_df.iterrows():
        icon = priority_icons.get(rec.get("priority", "medium"), "🟡")
        with st.expander(f"{icon} {rec.get('title','Рекомендация')}"):
            if rec.get("main_problem"):
                st.markdown(f"**Проблема:** {rec['main_problem']}")
            if rec.get("business_risk"):
                st.markdown(f"**Бизнес-риск:** {rec['business_risk']}")
            if rec.get("recommended_action"):
                st.success(f"**Действие:** {rec['recommended_action']}")
else:
    st.info("Рекомендации ещё не сформированы (нужно больше звонков).")
