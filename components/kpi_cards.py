"""
kpi_cards.py — KPI-карточки для дашборда.
"""

import streamlit as st
from core.score_calculator import score_to_color, risk_color


def kpi_card(label: str, value, delta=None, color: str = "#6366F1",
             suffix: str = "", help_text: str = ""):
    """Рисует одну KPI-карточку через HTML."""
    delta_html = ""
    if delta is not None:
        d_color = "#22C55E" if delta >= 0 else "#EF4444"
        d_sign = "+" if delta >= 0 else ""
        delta_html = f'<div style="font-size:12px;color:{d_color};margin-top:2px">{d_sign}{delta:.1f}</div>'

    html = f"""
    <div style="
        background:#1E293B;
        border:1px solid #334155;
        border-radius:12px;
        padding:16px;
        border-top:3px solid {color};
        min-height:90px;
    " title="{help_text}">
        <div style="font-size:12px;color:#94A3B8;margin-bottom:6px">{label}</div>
        <div style="font-size:26px;font-weight:700;color:#F1F5F9">{value}{suffix}</div>
        {delta_html}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def score_card(label: str, score: float, delta=None, help_text: str = ""):
    """KPI-карточка для score 0–100 с цветовой индикацией."""
    color = score_to_color(score)
    kpi_card(label, f"{score:.0f}", delta=delta, color=color,
             suffix="/100", help_text=help_text)


def risk_card(label: str, risk_level: str, count: int = 0, help_text: str = ""):
    """KPI-карточка для риска."""
    color = risk_color(risk_level)
    labels = {"low": "Низкий", "medium": "Средний", "high": "Высокий", "critical": "Критический"}
    kpi_card(label, count, color=color, help_text=help_text)


def render_kpi_row(stats: dict):
    """Рисует строку основных KPI из dict статистики."""
    c = [st.columns(4), st.columns(4)]

    with c[0][0]:
        kpi_card("Всего звонков", stats.get("total_calls", 0),
                 color="#6366F1", help_text="Всего загружено звонков за период")
    with c[0][1]:
        kpi_card("Активных звонков", stats.get("active_calls", 0),
                 color="#6366F1", help_text="Звонков длительностью >45 сек с диалогом")
    with c[0][2]:
        kpi_card("Проанализировано", stats.get("analyzed_calls", 0),
                 color="#22C55E", help_text="Звонков с завершённым AI-анализом")
    with c[0][3]:
        score_card("Средний QA Score",
                   round(stats.get("avg_qa_score") or 0, 1),
                   help_text="Средневзвешенный балл качества по всем звонкам")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    with c[1][0]:
        score_card("Средний Tone Score",
                   round(stats.get("avg_tone_score") or 0, 1),
                   help_text="Средний балл тона и поведения менеджера")
    with c[1][1]:
        score_card("Психосостояние клиента",
                   round(stats.get("avg_client_score") or 0, 1),
                   help_text="Средний балл вовлечённости и реакции клиента")
    with c[1][2]:
        score_card("Прогноз доходимости",
                   round(stats.get("avg_show_up") or 0, 1),
                   color=score_to_color(stats.get("avg_show_up") or 0),
                   help_text="Средняя вероятность, что клиент дойдёт до офиса")
    with c[1][3]:
        high_risk = stats.get("high_risk_count", 0) or 0
        kpi_card("Высокий риск неявки", high_risk,
                 color="#EF4444" if high_risk > 0 else "#22C55E",
                 help_text="Звонков с высоким или критическим риском неявки")
