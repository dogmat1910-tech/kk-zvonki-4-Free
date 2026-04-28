"""Дашборд тона и психосостояния клиента."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import get_conn
from core.score_calculator import (
    score_to_color, manager_tone_label, client_state_label,
)
from components.charts import (
    trend_line, bar_chart, scatter_chart, donut_chart, heatmap, _empty_fig,
)
import plotly.graph_objects as go

st.set_page_config(page_title="Тон и психосостояние", page_icon="🎭", layout="wide")
st.title("🎭 Тон менеджера и психосостояние клиента")

days = st.selectbox("Период", [7, 14, 30, 60, 90], index=2,
                     format_func=lambda d: f"Последние {d} дней")

conn = get_conn()

# Основные метрики
scores = pd.read_sql(f"""
    SELECT u.name as manager_name,
           AVG(qa.tone_score) as avg_tone,
           AVG(qa.client_reflection_score) as avg_client,
           AVG(qa.show_up_probability_score) as avg_show_up,
           SUM(qa.weak_agreement_detected) as weak_agreements,
           COUNT(*) as call_count
    FROM qa_analyses qa
    JOIN calls c ON qa.call_id=c.id
    JOIN users u ON c.manager_id=u.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
      AND c.analysis_status='done'
    GROUP BY u.name
    ORDER BY avg_tone DESC
""", conn)

# Состояния клиентов
client_states = pd.read_sql(f"""
    SELECT et.client_state, COUNT(*) as count
    FROM emotional_timeline et
    JOIN qa_analyses qa ON et.qa_analysis_id=qa.id
    JOIN calls c ON qa.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
    GROUP BY et.client_state
    ORDER BY count DESC
""", conn)

# Тон менеджеров
mgr_tones = pd.read_sql(f"""
    SELECT et.manager_tone, COUNT(*) as count
    FROM emotional_timeline et
    JOIN qa_analyses qa ON et.qa_analysis_id=qa.id
    JOIN calls c ON qa.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
    GROUP BY et.manager_tone
    ORDER BY count DESC
""", conn)

# Слабые согласия
weak_stats = pd.read_sql(f"""
    SELECT
        COUNT(*) as total,
        SUM(qa.weak_agreement_detected) as weak_count
    FROM qa_analyses qa
    JOIN calls c ON qa.call_id=c.id
    WHERE c.uploaded_at >= datetime('now', '-{days} days')
      AND c.analysis_status='done'
""", conn).iloc[0]

conn.close()

# ── KPI ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

avg_tone   = scores["avg_tone"].mean() if not scores.empty else 0
avg_client = scores["avg_client"].mean() if not scores.empty else 0
total      = int(weak_stats.get("total", 0))
weak       = int(weak_stats.get("weak_count", 0))
weak_pct   = weak / total * 100 if total > 0 else 0

with c1:
    color = score_to_color(avg_tone)
    st.markdown(f"""
    <div style="background:#1E293B;border-radius:10px;padding:16px;border-top:3px solid {color}">
      <div style="font-size:12px;color:#94A3B8">Средний Tone Score</div>
      <div style="font-size:28px;font-weight:700;color:{color}">{avg_tone:.0f}</div>
    </div>
    """, unsafe_allow_html=True)
with c2:
    color2 = score_to_color(avg_client)
    st.markdown(f"""
    <div style="background:#1E293B;border-radius:10px;padding:16px;border-top:3px solid {color2}">
      <div style="font-size:12px;color:#94A3B8">Ср. психосостояние клиента</div>
      <div style="font-size:28px;font-weight:700;color:{color2}">{avg_client:.0f}</div>
    </div>
    """, unsafe_allow_html=True)
with c3:
    st.markdown(f"""
    <div style="background:#1E293B;border-radius:10px;padding:16px;border-top:3px solid #EAB308">
      <div style="font-size:12px;color:#94A3B8">Слабых согласий</div>
      <div style="font-size:28px;font-weight:700;color:#EAB308">{weak_pct:.0f}%</div>
      <div style="font-size:12px;color:#64748B">{weak} из {total}</div>
    </div>
    """, unsafe_allow_html=True)
with c4:
    strong_pct = 100 - weak_pct
    st.markdown(f"""
    <div style="background:#1E293B;border-radius:10px;padding:16px;border-top:3px solid #22C55E">
      <div style="font-size:12px;color:#94A3B8">Сильных согласий</div>
      <div style="font-size:28px;font-weight:700;color:#22C55E">{strong_pct:.0f}%</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ── Графики ───────────────────────────────────────────────────────────────
st.subheader("📊 Тон менеджеров")

if not scores.empty:
    sc1, sc2 = st.columns(2)
    with sc1:
        fig = bar_chart(
            scores.sort_values("avg_tone"),
            x="avg_tone", y="manager_name",
            title="Средний Tone Score по менеджерам",
            orientation="h", color_col="avg_tone",
        )
        st.plotly_chart(fig, use_container_width=True)

    with sc2:
        fig2 = scatter_chart(
            scores, x="avg_tone", y="avg_client",
            title="Tone Score × Психосостояние клиента",
            hover_name="manager_name",
            x_label="Tone Score", y_label="Client Reflection Score",
            color="#6366F1",
        )
        st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Состояния клиентов ────────────────────────────────────────────────────
st.subheader("🎭 Распределение психосостояний клиентов")

if not client_states.empty:
    state_labels = [client_state_label(s) for s in client_states["client_state"]]
    state_colors = {
        "cold": "#94A3B8", "neutral": "#6B7280", "interested": "#22D3EE",
        "engaged": "#22C55E", "doubtful": "#EAB308", "resistant": "#F97316",
        "committed": "#6366F1", "weak_agreement": "#F59E0B", "negative": "#EF4444",
    }

    ss1, ss2 = st.columns(2)
    with ss1:
        colors_list = [state_colors.get(s, "#94A3B8") for s in client_states["client_state"]]
        fig_bar = go.Figure(go.Bar(
            x=state_labels, y=client_states["count"],
            marker_color=colors_list,
            hovertemplate="<b>%{x}</b><br>Количество: %{y}<extra></extra>",
        ))
        fig_bar.update_layout(
            title="Состояния клиентов",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94A3B8"), margin=dict(t=40, l=40, r=20, b=60),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with ss2:
        fig_d = donut_chart(state_labels, client_states["count"].tolist(),
                            "Доля состояний клиентов")
        st.plotly_chart(fig_d, use_container_width=True)

st.divider()

# ── Тон менеджеров ────────────────────────────────────────────────────────
st.subheader("🎙️ Распределение тональностей менеджеров")

if not mgr_tones.empty:
    tone_labels = [manager_tone_label(t) for t in mgr_tones["manager_tone"]]
    tc1, tc2 = st.columns(2)
    with tc1:
        tone_colors = {
            "confident": "#22C55E", "neutral": "#94A3B8",
            "rushed": "#EAB308", "monotone": "#6B7280",
            "pressuring": "#F97316", "warm": "#6366F1",
            "irritated": "#EF4444",
        }
        colors_t = [tone_colors.get(t, "#94A3B8") for t in mgr_tones["manager_tone"]]
        fig_t = go.Figure(go.Bar(
            x=tone_labels, y=mgr_tones["count"],
            marker_color=colors_t,
        ))
        fig_t.update_layout(
            title="Тональности менеджеров",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94A3B8"), margin=dict(t=40, l=40, r=20, b=60),
        )
        st.plotly_chart(fig_t, use_container_width=True)

    with tc2:
        fig_td = donut_chart(tone_labels, mgr_tones["count"].tolist(),
                             "Доля тональностей")
        st.plotly_chart(fig_td, use_container_width=True)

st.divider()

# ── Связь тона с доходимостью ─────────────────────────────────────────────
st.subheader("📈 Связь тона с прогнозом доходимости")

if not scores.empty:
    fig_sc = scatter_chart(
        scores, x="avg_tone", y="avg_show_up",
        title="Tone Score × Show-Up Probability",
        hover_name="manager_name",
        x_label="Tone Score",
        y_label="Show-Up Probability",
        color="#22C55E",
    )
    st.plotly_chart(fig_sc, use_container_width=True)

    st.markdown("**Вывод:** менеджеры с более высоким Tone Score, как правило, "
                "дают более высокий прогноз доходимости клиентов.")
