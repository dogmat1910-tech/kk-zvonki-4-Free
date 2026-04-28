"""AI-тренинги для менеджеров."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json
import pandas as pd

from core.database import (
    get_trainings, save_training, update_training_status,
    get_manager_stats, get_stage_heatmap, get_error_stats,
    get_users, get_teams, get_conn,
)
from core.ai_pipeline import _try_models, get_api_key

st.set_page_config(page_title="AI-тренинги", page_icon="🎓", layout="wide")
st.title("🎓 AI-тренинги")

tabs = st.tabs(["📋 Список тренингов", "🤖 Сгенерировать тренинг"])

# ═══════════════════════════════════════════════════
# ВКЛАДКА 1: СПИСОК
# ═══════════════════════════════════════════════════
with tabs[0]:
    df = get_trainings()

    if df.empty:
        st.info("📭 Тренингов пока нет. Сгенерируйте первый тренинг на вкладке справа.")
        st.stop()

    status_colors = {
        "proposed":  "#EAB308",
        "approved":  "#22C55E",
        "completed": "#6366F1",
        "archived":  "#94A3B8",
    }
    status_labels = {
        "proposed":  "⏳ Предложен",
        "approved":  "✅ Одобрен",
        "completed": "🎯 Завершён",
        "archived":  "📦 В архиве",
    }

    for _, row in df.iterrows():
        color = status_colors.get(row.get("status", "proposed"), "#94A3B8")
        label = status_labels.get(row.get("status", "proposed"), "")

        with st.expander(
            f"{label} | {row.get('title','Тренинг')} "
            f"— {row.get('manager_name') or row.get('team_name') or 'Вся команда'}"
        ):
            tc1, tc2 = st.columns([3, 1])

            with tc1:
                if row.get("reason"):
                    st.markdown(f"**Почему этот тренинг:**\n{row['reason']}")

                weak = row.get("weak_stages", "[]")
                if isinstance(weak, str):
                    try: weak = json.loads(weak)
                    except: weak = []
                if weak:
                    st.markdown(f"**Слабые этапы:** {', '.join(weak)}")

                errors = row.get("repeated_errors", "[]")
                if isinstance(errors, str):
                    try: errors = json.loads(errors)
                    except: errors = []
                if errors:
                    st.markdown(f"**Типичные ошибки:** {', '.join(errors[:5])}")

                # Планы
                plan_tabs = st.tabs(["30 минут", "45 минут", "60 минут"])
                with plan_tabs[0]:
                    st.markdown(row.get("plan_30_min") or "—")
                with plan_tabs[1]:
                    st.markdown(row.get("plan_45_min") or "—")
                with plan_tabs[2]:
                    st.markdown(row.get("plan_60_min") or "—")

                # Фразы
                phrases_use = row.get("phrases_to_use", "[]")
                phrases_avoid = row.get("phrases_to_avoid", "[]")
                if isinstance(phrases_use, str):
                    try: phrases_use = json.loads(phrases_use)
                    except: phrases_use = []
                if isinstance(phrases_avoid, str):
                    try: phrases_avoid = json.loads(phrases_avoid)
                    except: phrases_avoid = []

                if phrases_use or phrases_avoid:
                    pc1, pc2 = st.columns(2)
                    with pc1:
                        if phrases_use:
                            st.markdown("**✅ Внедрить фразы:**")
                            for p in phrases_use[:5]:
                                st.markdown(f"  — _{p}_")
                    with pc2:
                        if phrases_avoid:
                            st.markdown("**❌ Убрать фразы:**")
                            for p in phrases_avoid[:5]:
                                st.markdown(f"  — _{p}_")

                if row.get("homework"):
                    st.markdown(f"**Домашнее задание:**\n{row['homework']}")

                metrics = row.get("metrics_to_check", "[]")
                if isinstance(metrics, str):
                    try: metrics = json.loads(metrics)
                    except: metrics = []
                if metrics:
                    st.markdown(f"**Метрики для проверки через 7 дней:** {', '.join(metrics)}")

            with tc2:
                st.markdown(f"**Статус:** {label}")
                st.markdown(f"**Тип:** {row.get('scope','team')}")
                st.markdown(f"**Создан:** {(row.get('created_at',''))[:10]}")

                tid = row.get("id")
                if tid:
                    if row.get("status") == "proposed":
                        if st.button("✅ Одобрить", key=f"tr_ap_{tid}"):
                            update_training_status(int(tid), "approved")
                            st.rerun()
                    if row.get("status") == "approved":
                        if st.button("🎯 Завершить", key=f"tr_done_{tid}"):
                            update_training_status(int(tid), "completed")
                            st.rerun()
                    if st.button("📦 В архив", key=f"tr_arc_{tid}"):
                        update_training_status(int(tid), "archived")
                        st.rerun()


# ═══════════════════════════════════════════════════
# ВКЛАДКА 2: ГЕНЕРАЦИЯ
# ═══════════════════════════════════════════════════
with tabs[1]:
    st.subheader("🤖 Сгенерировать AI-тренинг")

    api_key = get_api_key()
    if not api_key:
        st.error("⚠️ Введите API-ключ Gemini на главной странице.")
        st.stop()

    gc1, gc2 = st.columns(2)
    with gc1:
        scope = st.selectbox("Для кого", ["team", "manager", "department"],
                              format_func=lambda x: {"team": "Для команды", "manager": "Для менеджера",
                                                      "department": "Для отдела"}[x])
        days_g = st.selectbox("На основе данных за", [7, 14, 30], index=1,
                              format_func=lambda d: f"{d} дней")

    with gc2:
        if scope == "manager":
            mgrs_df = get_users(role="manager")
            mgr_g_name = st.selectbox("Менеджер", mgrs_df["name"].tolist() if not mgrs_df.empty else [])
            mgr_g_id = int(mgrs_df[mgrs_df["name"] == mgr_g_name]["id"].iloc[0]) if not mgrs_df.empty else None
        else:
            mgr_g_id = None
            teams_df = get_teams()
            team_g_name = st.selectbox("Команда", (["Все"] + teams_df["name"].tolist()) if not teams_df.empty else ["Все"])

    if st.button("🤖 Сгенерировать тренинг", type="primary"):
        with st.spinner("ИИ анализирует данные и формирует тренинг..."):
            # Собираем аналитику для промпта
            mgr_stats = get_manager_stats(days=days_g)
            stage_data = get_stage_heatmap(days=days_g)
            err_data = get_error_stats(days=days_g)

            # Слабые этапы
            if not stage_data.empty:
                weak_stages_list = (
                    stage_data.groupby("stage_name")["avg_score"].mean()
                    .sort_values().head(5).index.tolist()
                )
            else:
                weak_stages_list = []

            # Частые ошибки
            top_errors = err_data["title"].tolist()[:10] if not err_data.empty else []

            # Строим промпт для генерации тренинга
            context = f"""
Ты — эксперт по обучению продажам и коуч менеджеров по работе с клиентами.

ДАННЫЕ ЗА ПОСЛЕДНИЕ {days_g} ДНЕЙ:

Слабые этапы продаж (наименьший средний балл):
{chr(10).join(f"- {s}" for s in weak_stages_list) or "Нет данных"}

Наиболее частые ошибки:
{chr(10).join(f"- {e}" for e in top_errors) or "Нет данных"}

Средние показатели команды:
{mgr_stats[['manager_name','avg_qa_score','avg_tone_score','avg_show_up']].to_string() if not mgr_stats.empty else "Нет данных"}

КОНТЕКСТ:
Компания продаёт юридические консультации по освобождению от военной службы.
Цель менеджера — записать клиента на бесплатную консультацию (БК) и повысить вероятность его явки в офис.

ЗАДАЧА:
На основе данных создай структурированный тренинг для {'менеджера ' + (mgr_g_name if scope == 'manager' else '') if scope == 'manager' else 'команды'}.

ВЕРНИ СТРОГО JSON:
{{
  "title": "Тема тренинга",
  "reason": "Почему именно этот тренинг нужен сейчас (2-3 предложения)",
  "weak_stages": ["этап1", "этап2"],
  "repeated_errors": ["ошибка1", "ошибка2"],
  "plan_30_min": "Детальный план на 30 минут (markdown)",
  "plan_45_min": "Детальный план на 45 минут (markdown)",
  "plan_60_min": "Детальный план на 60 минут (markdown)",
  "exercises": ["Упражнение 1", "Упражнение 2", "Упражнение 3"],
  "roleplays": ["Сценарий ролевой игры 1", "Сценарий 2"],
  "phrases_to_use": ["Фраза 1 для внедрения", "Фраза 2"],
  "phrases_to_avoid": ["Плохая фраза 1", "Плохая фраза 2"],
  "homework": "Домашнее задание",
  "metrics_to_check": ["Метрика 1 для проверки через 7 дней", "Метрика 2"],
  "data_evidence": ["Факт 1 из данных", "Факт 2"]
}}
"""
            try:
                raw = _try_models([context])
                from core.json_validator import extract_json
                json_str = extract_json(raw)
                training_data = json.loads(json_str) if json_str else {}

                if training_data:
                    training_data["scope"] = scope
                    training_data["manager_id"] = mgr_g_id
                    tid = save_training(training_data)
                    st.success(f"✅ Тренинг создан! ID: {tid}")
                    st.json(training_data)
                    st.rerun()
                else:
                    st.error("Не удалось распарсить ответ ИИ. Попробуйте ещё раз.")

            except Exception as e:
                st.error(f"Ошибка генерации: {e}")
