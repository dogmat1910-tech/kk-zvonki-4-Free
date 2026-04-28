"""Дашборд этапов продаж."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import get_stage_heatmap, get_conn
from components.charts import heatmap, bar_chart, trend_line, scatter_chart, _empty_fig

st.set_page_config(page_title="Этапы продаж", page_icon="🎯", layout="wide")
st.title("🎯 Дашборд этапов продаж")

days = st.selectbox("Период", [7, 14, 30, 60, 90], index=2,
                     format_func=lambda d: f"Последние {d} дней")

conn = get_conn()

# Средний балл по этапам по отделу
stage_dept = pd.read_sql(f"""
    SELECT sss.stage_name, sss.stage_code,
           AVG(sss.score) as avg_score,
           COUNT(*) as call_count,
           MIN(sss.score) as min_score,
           MAX(sss.score) as max_score
    FROM sales_stage_scores sss
    JOIN qa_analyses qa ON sss.qa_analysis_id=qa.id
    JOIN calls c ON qa.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
      AND c.analysis_status='done'
    GROUP BY sss.stage_name, sss.stage_code
    ORDER BY avg_score ASC
""", conn)

# Этапы × show-up
stage_showup = pd.read_sql(f"""
    SELECT sss.stage_name, sss.score as stage_score,
           qa.show_up_probability_score
    FROM sales_stage_scores sss
    JOIN qa_analyses qa ON sss.qa_analysis_id=qa.id
    JOIN calls c ON qa.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
      AND c.analysis_status='done'
""", conn)

conn.close()

if stage_dept.empty:
    st.info("📭 Нет данных. Загрузите и проанализируйте звонки.")
    st.stop()

# ── KPI этапов ───────────────────────────────────────────────────────────
st.subheader("📊 Баллы по этапам")

best  = stage_dept.nlargest(1, "avg_score").iloc[0]
worst = stage_dept.nsmallest(1, "avg_score").iloc[0]

c1, c2, c3 = st.columns(3)
with c1:
    st.success(f"**✅ Лучший этап:** {best['stage_name']}\n\nСредний балл: **{best['avg_score']:.0f}**")
with c2:
    st.error(f"**❌ Слабый этап:** {worst['stage_name']}\n\nСредний балл: **{worst['avg_score']:.0f}**")
with c3:
    below60 = stage_dept[stage_dept["avg_score"] < 60]
    st.warning(f"**⚠️ Этапов ниже 60:** {len(below60)}\n\n{', '.join(below60['stage_name'].tolist()[:3])}")

st.divider()

# ── Бар-чарт по этапам ───────────────────────────────────────────────────
st.subheader("📊 Средний балл по этапам (весь отдел)")

fig = bar_chart(
    stage_dept, x="avg_score", y="stage_name",
    title="Средний балл по этапам", orientation="h", color_col="avg_score",
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Тепловая карта ────────────────────────────────────────────────────────
st.subheader("🗺️ Тепловая карта: менеджеры × этапы")

heat_df = get_stage_heatmap(days=days)
if not heat_df.empty:
    fig_h = heatmap(heat_df, "manager_name", "stage_name", "avg_score",
                    "Балл по этапам (менеджеры × этапы)")
    st.plotly_chart(fig_h, use_container_width=True)
else:
    st.info("Нет данных для тепловой карты.")

st.divider()

# ── Этапы × Доходимость ───────────────────────────────────────────────────
st.subheader("🎯 Связь этапов с доходимостью")

if not stage_showup.empty and "stage_name" in stage_showup.columns:
    stages_unique = stage_showup["stage_name"].unique().tolist()
    sel_stage = st.selectbox("Этап продаж", stages_unique)
    stage_filtered = stage_showup[stage_showup["stage_name"] == sel_stage]

    fig_sc = scatter_chart(
        stage_filtered,
        x="stage_score", y="show_up_probability_score",
        title=f"{sel_stage} × Вероятность явки",
        x_label=f"Балл этапа: {sel_stage}",
        y_label="Show-Up Probability",
        color="#6366F1",
    )
    st.plotly_chart(fig_sc, use_container_width=True)

    corr = stage_filtered[["stage_score", "show_up_probability_score"]].corr()
    if not corr.empty:
        corr_val = corr.iloc[0, 1]
        st.caption(f"Корреляция: {corr_val:.2f} — {'положительная' if corr_val > 0.3 else 'слабая или отсутствует'}")
else:
    st.info("Нет данных для анализа корреляции.")

st.divider()

# ── Детальная таблица ─────────────────────────────────────────────────────
st.subheader("📋 Детальная таблица этапов")

display = stage_dept.copy()
display.columns = [c.replace("_", " ").capitalize() for c in display.columns]
for col in ["Avg score", "Min score", "Max score"]:
    if col in display.columns:
        display[col] = display[col].round(1)

st.dataframe(display, use_container_width=True, hide_index=True)
