"""Дашборд ошибок."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import get_error_stats, get_conn
from core.score_calculator import criticality_color
from components.charts import bar_chart, trend_line, donut_chart, _empty_fig

st.set_page_config(page_title="Ошибки", page_icon="❌", layout="wide")
st.title("❌ Дашборд ошибок")

days = st.selectbox("Период", [7, 14, 30, 60, 90], index=2,
                     format_func=lambda d: f"Последние {d} дней")

conn = get_conn()

# Основные метрики
meta = pd.read_sql(f"""
    SELECT
        COUNT(*) as total_errors,
        SUM(CASE WHEN status='needs_review' THEN 1 ELSE 0 END) as needs_review,
        SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved,
        SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected,
        SUM(CASE WHEN criticality='critical' THEN 1 ELSE 0 END) as critical_count,
        SUM(CASE WHEN criticality='high' THEN 1 ELSE 0 END) as high_count,
        AVG(confidence) as avg_confidence
    FROM detected_errors de
    JOIN calls c ON de.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
""", conn).iloc[0]

# Ошибки по менеджерам
mgr_errors = pd.read_sql(f"""
    SELECT u.name as manager_name, COUNT(de.id) as error_count,
           SUM(CASE WHEN de.criticality='critical' THEN 1 ELSE 0 END) as critical
    FROM detected_errors de
    JOIN calls c ON de.call_id=c.id
    JOIN users u ON c.manager_id=u.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
    GROUP BY u.name
    ORDER BY error_count DESC
""", conn)

# Тренд ошибок
err_trend = pd.read_sql(f"""
    SELECT DATE(c.uploaded_at) as date,
           COUNT(de.id) as error_count,
           SUM(CASE WHEN de.criticality='critical' THEN 1 ELSE 0 END) as critical
    FROM detected_errors de
    JOIN calls c ON de.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
    GROUP BY DATE(c.uploaded_at)
    ORDER BY date
""", conn)

conn.close()

# ── KPI ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("Всего ошибок", int(meta.get("total_errors", 0)))
with c2:
    st.metric("Критических", int(meta.get("critical_count", 0)),
              delta=None if not meta.get("critical_count") else None)
with c3:
    st.metric("Требуют проверки", int(meta.get("needs_review", 0)))
with c4:
    st.metric("Подтверждено", int(meta.get("approved", 0)))
with c5:
    st.metric("Уверенность ИИ", f"{(meta.get('avg_confidence') or 0)*100:.0f}%")

st.divider()

# ── Тренд ────────────────────────────────────────────────────────────────
st.subheader("📈 Динамика ошибок")

if not err_trend.empty:
    tc1, tc2 = st.columns(2)
    with tc1:
        fig = trend_line(err_trend, "date", "error_count",
                         "Всего ошибок по дням", "Ошибок", color="#EF4444")
        st.plotly_chart(fig, use_container_width=True)
    with tc2:
        fig2 = trend_line(err_trend, "date", "critical",
                          "Критических ошибок по дням", "Критических", color="#F97316")
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Нет данных для тренда.")

st.divider()

# ── По критичности и менеджерам ───────────────────────────────────────────
st.subheader("📊 Структура ошибок")

err_df = get_error_stats(days=days)

ec1, ec2, ec3 = st.columns(3)

with ec1:
    if not err_df.empty and "criticality" in err_df.columns:
        crit_counts = err_df.groupby("criticality")["count"].sum()
        labels_map = {"low": "Низкая", "medium": "Средняя",
                      "high": "Высокая", "critical": "Критическая"}
        labels = [labels_map.get(l, l) for l in crit_counts.index]
        fig_d = donut_chart(labels, crit_counts.values.tolist(), "По критичности")
        st.plotly_chart(fig_d, use_container_width=True)

with ec2:
    if not mgr_errors.empty:
        fig_mgr = bar_chart(
            mgr_errors.sort_values("error_count"),
            x="error_count", y="manager_name",
            title="Ошибок по менеджерам", orientation="h", color="#EF4444",
        )
        st.plotly_chart(fig_mgr, use_container_width=True)

with ec3:
    if not mgr_errors.empty:
        fig_crit = bar_chart(
            mgr_errors.sort_values("critical"),
            x="critical", y="manager_name",
            title="Критических ошибок", orientation="h", color="#F97316",
        )
        st.plotly_chart(fig_crit, use_container_width=True)

st.divider()

# ── Топ ошибок ────────────────────────────────────────────────────────────
st.subheader("🔝 Топ повторяющихся ошибок")

if not err_df.empty:
    fig_top = bar_chart(
        err_df.head(15), x="count", y="title",
        title="Частота ошибок (топ-15)", orientation="h", color="#EF4444",
    )
    st.plotly_chart(fig_top, use_container_width=True)

    st.markdown("**Детальная таблица:**")
    display_df = err_df.copy()
    crit_labels = {"low": "Низкая", "medium": "Средняя",
                   "high": "Высокая", "critical": "Критическая"}
    display_df["criticality"] = display_df["criticality"].map(crit_labels)
    display_df.columns = ["Ошибка", "Критичность", "Количество", "Ср. уверенность"]
    display_df["Ср. уверенность"] = (display_df["Ср. уверенность"] * 100).round(0).astype(int).astype(str) + "%"
    st.dataframe(display_df, use_container_width=True, hide_index=True)
else:
    st.success("✅ Ошибок не зафиксировано за выбранный период.")

st.divider()

# ── Очередь проверки ──────────────────────────────────────────────────────
st.subheader("👀 Очередь ручной проверки")

conn = get_conn()
review_queue = pd.read_sql("""
    SELECT de.id, de.title, de.criticality, de.evidence_quote,
           de.confidence, de.created_at,
           u.name as manager_name, c.filename
    FROM detected_errors de
    JOIN calls c ON de.call_id=c.id
    JOIN users u ON c.manager_id=u.id
    WHERE de.status='needs_review'
    ORDER BY de.criticality DESC, de.created_at DESC
    LIMIT 50
""", conn)
conn.close()

if not review_queue.empty:
    st.info(f"Ошибок на проверке: **{len(review_queue)}**")

    from core.database import update_error_status
    for _, row in review_queue.iterrows():
        crit = row.get("criticality", "medium")
        crit_labels = {"low": "Низкая", "medium": "Средняя",
                       "high": "Высокая", "critical": "Критическая"}
        with st.expander(
            f"👀 [{crit_labels.get(crit, crit).upper()}] {row['title']} "
            f"— {row.get('manager_name','?')} | {row.get('filename','?')}"
        ):
            if row.get("evidence_quote"):
                st.markdown(f"> _{row['evidence_quote']}_")
            st.caption(f"Уверенность ИИ: {row.get('confidence',0)*100:.0f}%")

            bc1, bc2 = st.columns(2)
            with bc1:
                if st.button("✅ Подтвердить", key=f"q_approve_{row['id']}"):
                    update_error_status(int(row["id"]), "approved")
                    st.rerun()
            with bc2:
                if st.button("❌ Отклонить", key=f"q_reject_{row['id']}"):
                    update_error_status(int(row["id"]), "rejected")
                    st.rerun()
else:
    st.success("✅ Очередь пуста — всё проверено")
