"""Админка чеклиста — редактирование правил оценки."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from core.database import (
    get_checklist_rules, upsert_checklist_rule,
    get_stage_weights, update_stage_weight, get_conn,
)

st.set_page_config(page_title="Чеклист", page_icon="✅", layout="wide")
st.title("✅ Редактор чеклиста")

st.caption("Все правила хранятся в базе данных. Изменения применяются к следующим анализам.")

tabs = st.tabs(["📋 Правила чеклиста", "⚖️ Веса этапов"])

# ═══════════════════════════════════════════════════
# ВКЛАДКА 1: ПРАВИЛА
# ═══════════════════════════════════════════════════
with tabs[0]:
    # Фильтры
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        show_inactive = st.checkbox("Показать отключённые", value=False)
    with fc2:
        call_type_filter = st.selectbox("Тип звонка", [
            "Все", "all", "primary_inbound", "primary_outbound",
            "confirmation", "repeat",
        ], format_func=lambda x: {
            "Все": "Все", "all": "Все типы", "primary_inbound": "Входящий",
            "primary_outbound": "Исходящий", "confirmation": "Подтверждение",
            "repeat": "Повторный",
        }.get(x, x))
    with fc3:
        stage_filter = st.selectbox("Этап", [
            "Все", "contact", "needs", "qualification",
            "presentation", "objections", "closing",
            "summary", "commitment", "additional",
        ], format_func=lambda x: {
            "Все": "Все", "contact": "Установление контакта",
            "needs": "Потребности", "qualification": "Квалификация",
            "presentation": "Презентация БК", "objections": "Возражения",
            "closing": "Закрытие", "summary": "Резюмирование",
            "commitment": "Фиксация явки", "additional": "Дополнительно",
        }.get(x, x))

    rules_df = get_checklist_rules(active_only=not show_inactive)

    if call_type_filter != "Все" and "call_type" in rules_df.columns:
        rules_df = rules_df[
            (rules_df["call_type"] == call_type_filter) |
            (rules_df["call_type"] == "all")
        ]
    if stage_filter != "Все" and "sales_stage" in rules_df.columns:
        rules_df = rules_df[rules_df["sales_stage"] == stage_filter]

    st.markdown(f"**Правил: {len(rules_df)}**")

    # Список правил
    crit_colors = {"low": "🔵", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    crit_labels = {"low": "Низкая", "medium": "Средняя",
                   "high": "Высокая", "critical": "Критическая"}

    for _, rule in rules_df.iterrows():
        active_icon = "✅" if rule.get("is_active") else "⛔"
        crit = rule.get("criticality", "medium")
        icon = crit_colors.get(crit, "🟡")
        rule_id = rule.get("id")

        with st.expander(
            f"{active_icon} {icon} [{crit_labels.get(crit,'?').upper()}] {rule['title']}",
            expanded=False
        ):
            with st.form(key=f"rule_form_{rule_id}"):
                rf1, rf2 = st.columns(2)
                with rf1:
                    title = st.text_input("Название", value=rule.get("title", ""))
                    description = st.text_area("Описание", value=rule.get("description", "") or "", height=80)
                    call_type = st.selectbox("Тип звонка", [
                        "all", "primary_inbound", "primary_outbound",
                        "confirmation", "repeat",
                        "primary_inbound,primary_outbound",
                        "primary_inbound,primary_outbound,repeat",
                        "primary_inbound,primary_outbound,confirmation,repeat",
                    ], index=0 if rule.get("call_type") not in [
                        "all", "primary_inbound", "primary_outbound",
                        "confirmation", "repeat",
                        "primary_inbound,primary_outbound",
                        "primary_inbound,primary_outbound,repeat",
                        "primary_inbound,primary_outbound,confirmation,repeat",
                    ] else [
                        "all", "primary_inbound", "primary_outbound",
                        "confirmation", "repeat",
                        "primary_inbound,primary_outbound",
                        "primary_inbound,primary_outbound,repeat",
                        "primary_inbound,primary_outbound,confirmation,repeat",
                    ].index(rule.get("call_type", "all")))

                    sales_stage = st.selectbox("Этап", [
                        "contact", "needs", "qualification", "presentation",
                        "objections", "closing", "summary", "commitment", "additional",
                    ], index=0 if rule.get("sales_stage") not in [
                        "contact", "needs", "qualification", "presentation",
                        "objections", "closing", "summary", "commitment", "additional",
                    ] else [
                        "contact", "needs", "qualification", "presentation",
                        "objections", "closing", "summary", "commitment", "additional",
                    ].index(rule.get("sales_stage", "contact")))

                with rf2:
                    weight = st.slider("Вес правила", 0.5, 10.0, float(rule.get("weight", 1.0)), 0.5)
                    criticality = st.selectbox("Критичность",
                                               ["low", "medium", "high", "critical"],
                                               index=["low", "medium", "high", "critical"].index(
                                                   rule.get("criticality", "medium")))
                    is_required = st.checkbox("Обязательное", value=bool(rule.get("is_required", True)))
                    is_active   = st.checkbox("Активно", value=bool(rule.get("is_active", True)))

                ai_instruction = st.text_area("Инструкция для ИИ",
                                              value=rule.get("ai_instruction", "") or "", height=80)
                positive_ex = st.text_area("Пример правильного выполнения",
                                           value=rule.get("positive_examples", "") or "", height=60)
                negative_ex = st.text_area("Пример нарушения",
                                           value=rule.get("negative_examples", "") or "", height=60)
                forbidden   = st.text_area("Запрещённые фразы (через запятую)",
                                           value=rule.get("forbidden_phrases", "") or "", height=50)
                rec_template = st.text_area("Шаблон рекомендации",
                                            value=rule.get("recommendation_template", "") or "", height=60)

                if st.form_submit_button("💾 Сохранить изменения", type="primary"):
                    upsert_checklist_rule({
                        "id": rule_id,
                        "title": title,
                        "description": description,
                        "call_type": call_type,
                        "sales_stage": sales_stage,
                        "weight": weight,
                        "criticality": criticality,
                        "is_required": is_required,
                        "is_active": is_active,
                        "ai_instruction": ai_instruction,
                        "positive_examples": positive_ex,
                        "negative_examples": negative_ex,
                        "forbidden_phrases": forbidden,
                        "recommendation_template": rec_template,
                    })
                    st.success("✅ Правило обновлено")
                    st.rerun()

    st.divider()
    st.subheader("➕ Добавить новое правило")

    with st.form("new_rule_form"):
        nf1, nf2 = st.columns(2)
        with nf1:
            n_title = st.text_input("Название*")
            n_desc  = st.text_area("Описание", height=80)
            n_ct    = st.selectbox("Тип звонка", ["all", "primary_inbound",
                                                    "primary_outbound", "confirmation", "repeat"])
            n_stage = st.selectbox("Этап", ["contact", "needs", "qualification",
                                             "presentation", "objections", "closing",
                                             "summary", "commitment", "additional"])
        with nf2:
            n_weight = st.slider("Вес", 0.5, 10.0, 1.0, 0.5)
            n_crit   = st.selectbox("Критичность", ["low", "medium", "high", "critical"])
            n_req    = st.checkbox("Обязательное", value=True)

        n_ai_instr = st.text_area("Инструкция для ИИ", height=80)
        n_pos_ex   = st.text_area("Пример правильного", height=60)
        n_neg_ex   = st.text_area("Пример нарушения", height=60)
        n_forbid   = st.text_area("Запрещённые фразы", height=50)
        n_rec      = st.text_area("Шаблон рекомендации", height=60)

        if st.form_submit_button("➕ Добавить правило", type="primary"):
            if n_title.strip():
                upsert_checklist_rule({
                    "title": n_title, "description": n_desc,
                    "call_type": n_ct, "sales_stage": n_stage,
                    "weight": n_weight, "criticality": n_crit,
                    "is_required": n_req, "is_active": True,
                    "ai_instruction": n_ai_instr,
                    "positive_examples": n_pos_ex,
                    "negative_examples": n_neg_ex,
                    "forbidden_phrases": n_forbid,
                    "recommendation_template": n_rec,
                })
                st.success("✅ Правило добавлено")
                st.rerun()
            else:
                st.error("Укажите название правила")


# ═══════════════════════════════════════════════════
# ВКЛАДКА 2: ВЕСА ЭТАПОВ
# ═══════════════════════════════════════════════════
with tabs[1]:
    st.subheader("⚖️ Веса этапов продаж по типу звонка")
    st.caption("Веса влияют на итоговый QA Score. Большой вес = этап важнее.")

    call_type_sel = st.selectbox("Тип звонка", [
        "primary_outbound", "primary_inbound", "confirmation", "repeat"
    ], format_func=lambda x: {
        "primary_outbound": "Исходящий первичный",
        "primary_inbound": "Входящий первичный",
        "confirmation": "Подтверждение",
        "repeat": "Повторный",
    }.get(x, x))

    weights_df = get_stage_weights(call_type_sel)

    if not weights_df.empty:
        for _, w_row in weights_df.iterrows():
            wc1, wc2 = st.columns([3, 1])
            with wc1:
                st.markdown(f"**{w_row['stage_name']}** (`{w_row['stage_code']}`)")
            with wc2:
                new_weight = st.number_input(
                    "Вес", min_value=0.1, max_value=10.0,
                    value=float(w_row["weight"]), step=0.5,
                    key=f"w_{call_type_sel}_{w_row['stage_code']}",
                    label_visibility="collapsed",
                )
                if new_weight != w_row["weight"]:
                    update_stage_weight(call_type_sel, w_row["stage_code"], new_weight)
                    st.rerun()
    else:
        st.info(f"Нет весов для типа '{call_type_sel}'.")
