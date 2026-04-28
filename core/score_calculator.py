"""
score_calculator.py — пересчёт взвешенного QA-балла по весам из БД.

Используется для нормализации score-а после того,
как Gemini вернул баллы по каждому этапу.
"""

from typing import Optional
import pandas as pd


def calculate_weighted_score(stage_scores: list[dict], weights_df: pd.DataFrame) -> float:
    """
    Считает взвешенный итоговый балл 0–100.

    stage_scores: список {"stage_code": str, "score": float}
    weights_df:   DataFrame с колонками stage_code, weight
    """
    if not stage_scores:
        return 0.0

    weights = dict(zip(weights_df["stage_code"], weights_df["weight"]))
    total_weight = 0.0
    weighted_sum = 0.0

    for s in stage_scores:
        code  = s.get("stage_code", "")
        score = float(s.get("score", 0))
        w     = weights.get(code, 1.0)
        weighted_sum  += score * w
        total_weight  += w

    if total_weight == 0:
        return 0.0

    return round(min(100.0, max(0.0, weighted_sum / total_weight)), 1)


def determine_risk_level(show_up_score: float) -> str:
    """Уровень риска неявки по score-у доходимости."""
    if show_up_score >= 80:
        return "low"
    elif show_up_score >= 60:
        return "medium"
    elif show_up_score >= 40:
        return "high"
    else:
        return "critical"


def score_to_grade(score: float) -> str:
    """Текстовая оценка балла."""
    if score >= 85:
        return "Отлично"
    elif score >= 70:
        return "Хорошо"
    elif score >= 55:
        return "Удовлетворительно"
    elif score >= 40:
        return "Плохо"
    else:
        return "Критично"


def score_to_color(score: float) -> str:
    """Цвет для отображения балла."""
    if score >= 80:
        return "#22C55E"   # зелёный
    elif score >= 60:
        return "#EAB308"   # жёлтый
    elif score >= 40:
        return "#F97316"   # оранжевый
    else:
        return "#EF4444"   # красный


def risk_color(risk_level: str) -> str:
    """Цвет по уровню риска."""
    return {
        "low":      "#22C55E",
        "medium":   "#EAB308",
        "high":     "#F97316",
        "critical": "#EF4444",
    }.get(risk_level, "#94A3B8")


def criticality_color(criticality: str) -> str:
    """Цвет по критичности ошибки."""
    return {
        "low":      "#94A3B8",
        "medium":   "#EAB308",
        "high":     "#F97316",
        "critical": "#EF4444",
    }.get(criticality, "#94A3B8")


def call_type_label(call_type: str) -> str:
    """Читаемое название типа звонка."""
    return {
        "primary_inbound":  "Входящий первичный",
        "primary_outbound": "Исходящий первичный",
        "confirmation":     "Подтверждение",
        "repeat":           "Повторный",
        "inactive":         "Нецелевой",
        "unknown":          "Не определён",
    }.get(call_type, call_type)


def client_state_label(state: str) -> str:
    """Читаемое название состояния клиента."""
    return {
        "cold":           "Холодный",
        "neutral":        "Нейтральный",
        "interested":     "Заинтересованный",
        "engaged":        "Вовлечённый",
        "doubtful":       "Сомневающийся",
        "resistant":      "Сопротивляющийся",
        "committed":      "Готов к действию",
        "weak_agreement": "Слабое согласие",
        "negative":       "Негатив",
    }.get(state, state)


def manager_tone_label(tone: str) -> str:
    """Читаемое название тона менеджера."""
    return {
        "confident":   "Уверенный",
        "neutral":     "Нейтральный",
        "rushed":      "Торопливый",
        "monotone":    "Монотонный",
        "pressuring":  "Давящий",
        "warm":        "Тёплый",
        "irritated":   "Раздражённый",
    }.get(tone, tone)


def risk_level_label(level: str) -> str:
    return {
        "low":      "Низкий",
        "medium":   "Средний",
        "high":     "Высокий",
        "critical": "Критический",
    }.get(level, level)


def priority_label(priority: str) -> str:
    return {
        "low":      "Низкий",
        "medium":   "Средний",
        "high":     "Высокий",
        "critical": "Критический",
    }.get(priority, priority)


def phrase_type_label(pt: str) -> str:
    return {
        "best":             "Лучшая фраза",
        "worst":            "Худшая фраза",
        "forbidden":        "Запрещённая фраза",
        "no_show_risk":     "Риск неявки",
        "closing":          "Закрытие на БК",
        "value":            "Ценность консультации",
        "objection":        "Работа с возражением",
        "commitment":       "Фиксация явки",
        "trust_damage":     "Подрывает доверие",
        "pressure":         "Давление",
        "false_expectation":"Ложные ожидания",
    }.get(pt, pt)


def analysis_status_label(status: str) -> str:
    return {
        "pending":    "⏳ Ожидает",
        "processing": "🔄 Анализируется",
        "done":       "✅ Готово",
        "error":      "❌ Ошибка",
    }.get(status, status)
