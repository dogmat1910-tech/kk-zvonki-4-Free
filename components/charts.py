"""
charts.py — переиспользуемые Plotly-графики для дашбордов.
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94A3B8", size=12),
    title_font=dict(color="#F1F5F9", size=14),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94A3B8")),
    xaxis=dict(gridcolor="#1E293B", linecolor="#334155", zerolinecolor="#334155"),
    yaxis=dict(gridcolor="#1E293B", linecolor="#334155", zerolinecolor="#334155"),
    margin=dict(t=40, l=40, r=20, b=40),
)

COLOR_SEQ = ["#6366F1", "#22C55E", "#F97316", "#EAB308", "#EF4444", "#06B6D4", "#8B5CF6"]


def trend_line(df: pd.DataFrame, x: str, y: str, title: str,
               y_label: str = "", color: str = "#6366F1") -> go.Figure:
    """Линейный график тренда."""
    if df.empty:
        return _empty_fig(title)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y], mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=6, color=color),
        fill="tozeroy",
        fillcolor=color.replace(")", ",0.1)").replace("rgb", "rgba") if "rgb" in color else color + "22",
        hovertemplate=f"<b>%{{x}}</b><br>{y_label or y}: %{{y:.1f}}<extra></extra>",
    ))
    fig.update_layout(title=title, **DARK_LAYOUT)
    if y_label:
        fig.update_yaxes(title_text=y_label)
    return fig


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str,
              color: str = "#6366F1", orientation: str = "v",
              color_col: str = None) -> go.Figure:
    """Столбчатый график."""
    if df.empty:
        return _empty_fig(title)
    if color_col and color_col in df.columns:
        colors = df[color_col].map(
            lambda v: "#22C55E" if v >= 70 else "#EAB308" if v >= 50 else "#EF4444"
        ).tolist()
    else:
        colors = color

    fig = go.Figure(go.Bar(
        x=df[x] if orientation == "v" else df[y],
        y=df[y] if orientation == "v" else df[x],
        marker_color=colors,
        orientation=orientation,
        hovertemplate="<b>%{x}</b><br>%{y:.1f}<extra></extra>",
    ))
    fig.update_layout(title=title, **DARK_LAYOUT)
    return fig


def heatmap(df: pd.DataFrame, x: str, y: str, z: str, title: str) -> go.Figure:
    """Тепловая карта (менеджеры × этапы)."""
    if df.empty:
        return _empty_fig(title)
    pivot = df.pivot_table(index=y, columns=x, values=z, aggfunc="mean").fillna(0)
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=[
            [0.0,  "#EF4444"],
            [0.4,  "#F97316"],
            [0.6,  "#EAB308"],
            [0.8,  "#22C55E"],
            [1.0,  "#6366F1"],
        ],
        zmin=0, zmax=100,
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:.0f}<extra></extra>",
        text=pivot.values.round(0).astype(int),
        texttemplate="%{text}",
        colorbar=dict(tickfont=dict(color="#94A3B8")),
    ))
    fig.update_layout(title=title, **DARK_LAYOUT,
                      xaxis=dict(tickangle=-30, **DARK_LAYOUT["xaxis"]))
    return fig


def radar_chart(categories: list, values: list, title: str,
                manager_name: str = "") -> go.Figure:
    """Radar/spider chart для профиля менеджера."""
    if not categories or not values:
        return _empty_fig(title)
    fig = go.Figure(go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill="toself",
        line=dict(color="#6366F1", width=2),
        fillcolor="rgba(99,102,241,0.15)",
        name=manager_name,
    ))
    fig.update_layout(
        title=title,
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(range=[0, 100], tickfont=dict(color="#94A3B8", size=10),
                            gridcolor="#334155"),
            angularaxis=dict(tickfont=dict(color="#94A3B8", size=11),
                             gridcolor="#334155"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94A3B8"),
        margin=dict(t=60, l=60, r=60, b=60),
    )
    return fig


def scatter_chart(df: pd.DataFrame, x: str, y: str, title: str,
                  color: str = None, hover_name: str = None,
                  x_label: str = "", y_label: str = "") -> go.Figure:
    """Scatter plot."""
    if df.empty:
        return _empty_fig(title)
    kwargs = dict(x=df[x], y=df[y], mode="markers",
                  marker=dict(size=8, opacity=0.8, color=color or "#6366F1"))
    if hover_name and hover_name in df.columns:
        kwargs["text"] = df[hover_name]
        kwargs["hovertemplate"] = "<b>%{text}</b><br>" + (x_label or x) + ": %{x:.1f}<br>" + (y_label or y) + ": %{y:.1f}<extra></extra>"

    fig = go.Figure(go.Scatter(**kwargs))
    fig.update_layout(title=title, **DARK_LAYOUT)
    if x_label:
        fig.update_xaxes(title_text=x_label)
    if y_label:
        fig.update_yaxes(title_text=y_label)
    return fig


def donut_chart(labels: list, values: list, title: str) -> go.Figure:
    """Donut / pie chart."""
    if not labels or not values:
        return _empty_fig(title)
    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        hole=0.5,
        marker=dict(colors=COLOR_SEQ[:len(labels)]),
        textfont=dict(color="#F1F5F9"),
        hovertemplate="<b>%{label}</b><br>%{value} (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94A3B8"),
        legend=dict(font=dict(color="#94A3B8"), bgcolor="rgba(0,0,0,0)"),
        margin=dict(t=40, l=10, r=10, b=10),
    )
    return fig


def emotion_timeline_chart(timeline: list) -> go.Figure:
    """График эмоционального состояния клиента по ходу звонка."""
    if not timeline:
        return _empty_fig("Эмоциональный таймлайн")

    state_order = {
        "negative": 0, "resistant": 1, "cold": 2, "doubtful": 3,
        "neutral": 4, "weak_agreement": 4,
        "interested": 6, "engaged": 7, "committed": 8,
    }
    state_labels = {
        "cold": "Холодный", "neutral": "Нейтральный",
        "interested": "Заинтересованный", "engaged": "Вовлечённый",
        "doubtful": "Сомневающийся", "resistant": "Сопротивляющийся",
        "committed": "Готов", "weak_agreement": "Слабое согласие",
        "negative": "Негатив",
    }
    state_colors = {
        "negative": "#EF4444", "resistant": "#F97316",
        "cold": "#94A3B8", "doubtful": "#EAB308",
        "neutral": "#6B7280", "weak_agreement": "#EAB308",
        "interested": "#22D3EE", "engaged": "#22C55E",
        "committed": "#6366F1",
    }

    times  = [t.get("timestamp", "") for t in timeline]
    states = [t.get("client_state", "neutral") for t in timeline]
    values = [state_order.get(s, 4) for s in states]
    colors = [state_colors.get(s, "#94A3B8") for s in states]
    labels = [state_labels.get(s, s) for s in states]
    notes  = [t.get("note", "") for t in timeline]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times, y=values, mode="lines+markers",
        line=dict(color="#6366F1", width=2),
        marker=dict(size=10, color=colors),
        text=labels,
        customdata=notes,
        hovertemplate="<b>%{x}</b><br>Состояние: %{text}<br>%{customdata}<extra></extra>",
    ))
    fig.update_layout(
        title="Эмоциональный таймлайн клиента",
        yaxis=dict(
            tickvals=list(range(9)),
            ticktext=["Негатив", "Сопротивление", "Холодный", "Сомнение",
                      "Нейтральный", "", "Заинтересованный", "Вовлечённый", "Готов к действию"],
            **DARK_LAYOUT["yaxis"],
        ),
        **DARK_LAYOUT,
    )
    return fig


def _empty_fig(title: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="Нет данных", xref="paper", yref="paper",
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(color="#94A3B8", size=14))
    fig.update_layout(title=title, **DARK_LAYOUT)
    return fig
