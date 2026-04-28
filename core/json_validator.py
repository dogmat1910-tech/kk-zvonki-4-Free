"""
json_validator.py — парсит и валидирует JSON-ответ от Gemini.

Если JSON невалидный — пытается починить автоматически.
Если починить не получается — возвращает безопасный fallback.
"""

import json
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    "call_type", "is_active_call", "qa_score", "regulation_score",
    "sales_quality_score", "speech_structure_score", "manager_control_score",
    "tone_score", "client_reflection_score", "show_up_probability_score",
    "objection_handling_score", "closing_score", "summary",
    "main_problem", "main_risk", "goal_achieved",
    "sales_stage_scores", "detected_errors", "sales_tools",
    "objections", "weak_agreement", "show_up_prediction",
    "emotional_timeline", "call_timeline_events",
    "phrase_candidates", "rop_recommendations",
]

SCORE_FIELDS = [
    "qa_score", "regulation_score", "sales_quality_score",
    "speech_structure_score", "manager_control_score", "tone_score",
    "client_reflection_score", "show_up_probability_score",
    "objection_handling_score", "closing_score",
]

ARRAY_FIELDS = [
    "sales_stage_scores", "detected_errors", "sales_tools",
    "objections", "emotional_timeline", "call_timeline_events",
    "phrase_candidates", "rop_recommendations",
]

VALID_CALL_TYPES = {
    "primary_inbound", "primary_outbound",
    "confirmation", "repeat", "inactive", "unknown",
}

VALID_CRITICALITIES = {"low", "medium", "high", "critical"}
VALID_RISK_LEVELS   = {"low", "medium", "high", "critical"}
VALID_CLIENT_STATES = {
    "cold", "neutral", "interested", "engaged",
    "doubtful", "resistant", "committed", "weak_agreement", "negative",
}
VALID_MANAGER_TONES = {
    "confident", "neutral", "rushed", "monotone",
    "pressuring", "warm", "irritated",
}


def extract_json(text: str) -> Optional[str]:
    """Извлекает JSON из текста — убирает обёртки markdown и лишний текст."""
    text = text.strip()

    # Убрать ```json ... ```
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"^```\s*", "", text)

    # Если текст начинается с {, возвращаем как есть
    if text.startswith("{"):
        return text

    # Ищем первый { ... последний }
    start = text.find("{")
    end   = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]

    return None


def repair_json(text: str) -> Optional[str]:
    """Пытается починить битый JSON — убирает trailing commas, исправляет кавычки."""
    # trailing commas перед } или ]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # одинарные кавычки → двойные (осторожно)
    # Только если нет двойных — не трогаем
    if "'" in text and '"' not in text:
        text = text.replace("'", '"')
    # Обрезать на последнем валидном }
    last = text.rfind("}")
    if last != -1:
        return text[:last + 1]
    return None


def clamp_score(value, lo=0, hi=100) -> float:
    """Ограничивает числовое значение в диапазоне."""
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return 0.0


def validate_and_fix(data: dict) -> dict:
    """Приводит структуру к ожидаемому формату, исправляет типы."""

    # Тип звонка
    if data.get("call_type") not in VALID_CALL_TYPES:
        data["call_type"] = "unknown"

    # is_active_call — bool
    data["is_active_call"] = bool(data.get("is_active_call", True))

    # Баллы — числа 0-100
    for field in SCORE_FIELDS:
        data[field] = clamp_score(data.get(field, 0))

    # goal_achieved — bool
    data["goal_achieved"] = bool(data.get("goal_achieved", False))

    # Массивы — гарантируем list
    for field in ARRAY_FIELDS:
        if not isinstance(data.get(field), list):
            data[field] = []

    # weak_agreement — гарантируем dict
    if not isinstance(data.get("weak_agreement"), dict):
        data["weak_agreement"] = {
            "detected": False, "client_phrase": None,
            "timestamp": None, "risk_reason": None,
            "better_manager_phrase": None,
        }
    else:
        wa = data["weak_agreement"]
        wa["detected"] = bool(wa.get("detected", False))

    # show_up_prediction — гарантируем dict
    if not isinstance(data.get("show_up_prediction"), dict):
        data["show_up_prediction"] = {
            "score": 0, "risk_level": "medium",
            "risk_reasons": [], "positive_factors": [],
            "negative_factors": [], "recommendation": "",
        }
    else:
        sp = data["show_up_prediction"]
        sp["score"] = clamp_score(sp.get("score", 0))
        if sp.get("risk_level") not in VALID_RISK_LEVELS:
            sp["risk_level"] = "medium"
        for arr_key in ("risk_reasons", "positive_factors", "negative_factors"):
            if not isinstance(sp.get(arr_key), list):
                sp[arr_key] = []

    # Ошибки — исправляем criticality
    for err in data.get("detected_errors", []):
        if err.get("criticality") not in VALID_CRITICALITIES:
            err["criticality"] = "medium"
        err["confidence"] = clamp_score(err.get("confidence", 0.9), 0, 1)
        if err.get("status") not in ("detected_by_ai", "needs_review"):
            err["status"] = "detected_by_ai"

    # Инструменты продаж
    for tool in data.get("sales_tools", []):
        tool["was_used"] = bool(tool.get("was_used", False))
        tool["quality_score"] = clamp_score(tool.get("quality_score", 0))

    # Возражения
    for obj in data.get("objections", []):
        obj["is_hidden"] = bool(obj.get("is_hidden", False))
        obj["was_handled"] = bool(obj.get("was_handled", False))
        obj["response_quality_score"] = clamp_score(obj.get("response_quality_score", 0))

    # Эмоциональный таймлайн
    for et in data.get("emotional_timeline", []):
        if et.get("client_state") not in VALID_CLIENT_STATES:
            et["client_state"] = "neutral"
        if et.get("manager_tone") not in VALID_MANAGER_TONES:
            et["manager_tone"] = "neutral"

    # Таймлайн событий
    for ev in data.get("call_timeline_events", []):
        ev["quality_score"] = clamp_score(ev.get("quality_score", 0))
        if ev.get("risk_level") not in VALID_RISK_LEVELS:
            ev["risk_level"] = "low"

    # Фразы
    for p in data.get("phrase_candidates", []):
        p["impact_score"] = max(-100, min(100, float(p.get("impact_score", 0) or 0)))

    # Рекомендации РОПу
    for r in data.get("rop_recommendations", []):
        if r.get("priority") not in VALID_RISK_LEVELS:
            r["priority"] = "medium"
        if r.get("level") not in ("call", "manager", "team", "department", "training"):
            r["level"] = "call"
        if not isinstance(r.get("data_evidence"), list):
            r["data_evidence"] = []

    return data


def fallback_result(error_msg: str) -> dict:
    """Безопасный результат при полном провале парсинга."""
    return {
        "call_type": "unknown",
        "is_active_call": False,
        "client_name": None,
        "qa_score": 0, "regulation_score": 0, "sales_quality_score": 0,
        "speech_structure_score": 0, "manager_control_score": 0,
        "tone_score": 0, "client_reflection_score": 0,
        "show_up_probability_score": 0, "objection_handling_score": 0,
        "closing_score": 0,
        "summary": f"Ошибка парсинга ответа ИИ: {error_msg}",
        "main_problem": "Не удалось распарсить ответ модели",
        "main_risk": "Требуется ручная проверка",
        "goal_achieved": False,
        "sales_stage_scores": [], "detected_errors": [],
        "sales_tools": [], "objections": [],
        "weak_agreement": {
            "detected": False, "client_phrase": None,
            "timestamp": None, "risk_reason": None,
            "better_manager_phrase": None,
        },
        "show_up_prediction": {
            "score": 0, "risk_level": "critical",
            "risk_reasons": ["Анализ недоступен"], "positive_factors": [],
            "negative_factors": [], "recommendation": "",
        },
        "emotional_timeline": [], "call_timeline_events": [],
        "phrase_candidates": [], "rop_recommendations": [],
        "_parse_error": error_msg,
    }


def parse_ai_response(raw_text: str) -> dict:
    """
    Главная функция: парсит сырой текст от Gemini → валидный dict.
    При ошибке пытается починить, при полном провале — возвращает fallback.
    """
    if not raw_text or not raw_text.strip():
        return fallback_result("Пустой ответ от модели")

    # Шаг 1: извлечь JSON
    json_str = extract_json(raw_text)
    if not json_str:
        return fallback_result("JSON не найден в ответе модели")

    # Шаг 2: парсинг
    try:
        data = json.loads(json_str)
        return validate_and_fix(data)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error: {e}, trying repair...")

    # Шаг 3: попытка починки
    repaired = repair_json(json_str)
    if repaired:
        try:
            data = json.loads(repaired)
            return validate_and_fix(data)
        except json.JSONDecodeError as e2:
            logger.error(f"JSON repair failed: {e2}")

    return fallback_result("JSON невалиден и не поддаётся автоматическому ремонту")
