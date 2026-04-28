"""Детальная страница конкретного звонка — самая важная страница системы."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import json

from core.database import (
    get_calls, get_call, get_analysis, get_transcript,
    update_error_status, update_phrase_status,
)
from core.score_calculator import (
    score_to_color, score_to_grade, risk_color, criticality_color,
    call_type_label, client_state_label, manager_tone_label,
    risk_level_label, priority_label, phrase_type_label,
)
from components.audio_player import render_audio_player, build_markers_from_analysis
from components.charts import emotion_timeline_chart, radar_chart, _empty_fig

st.set_page_config(page_title="Разбор звонка", page_icon="🔍", layout="wide")

# ── Выбор звонка ─────────────────────────────────────────────────────────
st.title("🔍 Разбор звонка")

df = get_calls(limit=500)
if df.empty:
    st.info("📭 Пока нет звонков. Загрузите аудиофайлы на странице «Звонки».")
    st.stop()

analyzed = df[df["analysis_status"] == "done"]

if analyzed.empty:
    st.warning("Нет проанализированных звонков. Дождитесь завершения анализа.")
    st.stop()

options = {}
for _, r in analyzed.iterrows():
    label = (f"#{r['id']} | {r.get('manager_name','?')} | "
             f"{r.get('filename','?')} | "
             f"QA: {r.get('qa_score') or 0:.0f} | "
             f"{call_type_label(r.get('call_type',''))}")
    options[label] = r["id"]

sel_label = st.selectbox("Выберите звонок", list(options.keys()))
call_id = options[sel_label]

call = get_call(call_id)
analysis = get_analysis(call_id)
transcript = get_transcript(call_id)

if not call:
    st.error("Звонок не найден")
    st.stop()

if not analysis:
    st.warning("Анализ ещё не готов или произошла ошибка.")
    st.stop()

# ── HEADER ────────────────────────────────────────────────────────────────
active_badge = "🟢 Активный" if call.get("is_active_call") else "🔴 Нецелевой"
goal_badge   = "✅ Цель достигнута" if analysis.get("goal_achieved") else "❌ Цель не достигнута"

st.markdown(f"""
<div style="background:#1E293B;border-radius:12px;padding:16px 20px;
     border:1px solid #334155;margin-bottom:16px">
  <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center">
    <div style="flex:1;min-width:200px">
      <div style="font-size:20px;font-weight:700;color:#F1F5F9">{call.get('filename','')}</div>
      <div style="font-size:13px;color:#94A3B8;margin-top:4px">
        👤 {call.get('manager_name','?')} &nbsp;|&nbsp;
        📅 {(call.get('call_datetime') or call.get('uploaded_at',''))[:10]} &nbsp;|&nbsp;
        🕐 {call.get('duration_seconds', 0) // 60}:{call.get('duration_seconds', 0) % 60:02d} &nbsp;|&nbsp;
        {active_badge} &nbsp;|&nbsp; {goal_badge}
      </div>
    </div>
    <div style="font-size:13px;color:#94A3B8">
      {call_type_label(call.get('call_type',''))}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── АУДИОПЛЕЕР ────────────────────────────────────────────────────────────
audio_path = call.get("audio_path")
audio_bytes = None
if audio_path and os.path.exists(audio_path):
    with open(audio_path, "rb") as af:
        audio_bytes = af.read()

if audio_bytes:
    markers = build_markers_from_analysis(analysis)
    render_audio_player(audio_bytes, markers)
else:
    st.info("🎵 Аудиофайл не прикреплён к этому звонку (анализ сохранён без файла).")

st.divider()

# ── БАЛЛЫ ────────────────────────────────────────────────────────────────
st.subheader("📊 Общие баллы")

score_items = [
    ("QA Score", "qa_score"),
    ("Регламент", "regulation_score"),
    ("Качество продаж", "sales_quality_score"),
    ("Структура речи", "speech_structure_score"),
    ("Управление диалогом", "manager_control_score"),
    ("Тон менеджера", "tone_score"),
    ("Психосостояние клиента", "client_reflection_score"),
    ("Прогноз доходимости", "show_up_probability_score"),
    ("Работа с возражениями", "objection_handling_score"),
    ("Закрытие", "closing_score"),
]

cols = st.columns(5)
for i, (label, key) in enumerate(score_items):
    val = round(analysis.get(key) or 0, 0)
    color = score_to_color(val)
    with cols[i % 5]:
        st.markdown(f"""
        <div style="background:#1E293B;border-radius:10px;padding:12px;
             border-top:3px solid {color};text-align:center;margin-bottom:8px">
          <div style="font-size:11px;color:#94A3B8">{label}</div>
          <div style="font-size:24px;font-weight:700;color:{color}">{val:.0f}</div>
          <div style="font-size:11px;color:#64748B">{score_to_grade(val)}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ── AI SUMMARY ────────────────────────────────────────────────────────────
st.subheader("🤖 Резюме от ИИ")
sc1, sc2, sc3 = st.columns(3)
with sc1:
    st.markdown(f"**Краткое резюме:**\n\n{analysis.get('summary') or '—'}")
with sc2:
    st.markdown(f"**Главная проблема:**\n\n{analysis.get('main_problem') or '—'}")
with sc3:
    st.markdown(f"**Главный риск для РОПа:**\n\n{analysis.get('main_risk') or '—'}")

st.divider()

# ── ЭТАПЫ ПРОДАЖ ──────────────────────────────────────────────────────────
st.subheader("📋 Оценка этапов продаж")

stage_scores = analysis.get("stage_scores", [])
if stage_scores:
    # Radar chart
    categories = [s["stage_name"] for s in stage_scores if s.get("stage_name")]
    values     = [s.get("score", 0) for s in stage_scores if s.get("stage_name")]
    if categories:
        fig_radar = radar_chart(categories, values, "Профиль звонка по этапам",
                                call.get("manager_name", ""))
        st.plotly_chart(fig_radar, use_container_width=True)

    for stage in stage_scores:
        score = stage.get("score", 0)
        color = score_to_color(score)
        with st.expander(
            f"{'✅' if score >= 70 else '⚠️' if score >= 45 else '❌'} "
            f"{stage.get('stage_name','Этап')} — {score:.0f}/100",
            expanded=(score < 50)
        ):
            ec1, ec2 = st.columns([1, 2])
            with ec1:
                st.markdown(f"**Балл:** <span style='color:{color};font-size:20px;font-weight:700'>{score:.0f}</span>", unsafe_allow_html=True)
                if stage.get("timestamp"):
                    st.markdown(f"**Таймкод:** {stage['timestamp']}")
                if stage.get("weight"):
                    st.markdown(f"**Вес этапа:** {stage['weight']}")
            with ec2:
                if stage.get("explanation"):
                    st.markdown(f"**Оценка ИИ:**\n{stage['explanation']}")
                if stage.get("evidence_quote"):
                    st.markdown(f"**Цитата:**\n> {stage['evidence_quote']}")
                if stage.get("recommendation"):
                    st.info(f"💡 {stage['recommendation']}")
else:
    st.info("Данные по этапам отсутствуют.")

st.divider()

# ── ОШИБКИ ────────────────────────────────────────────────────────────────
st.subheader("❌ Обнаруженные ошибки")

errors = analysis.get("errors", [])
if errors:
    crit_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    errors_sorted = sorted(errors, key=lambda e: crit_order.get(e.get("criticality", "low"), 4))

    for err in errors_sorted:
        crit = err.get("criticality", "medium")
        color = criticality_color(crit)
        crit_labels = {"low": "Низкая", "medium": "Средняя",
                       "high": "Высокая", "critical": "Критическая"}
        status_icons = {
            "detected_by_ai": "🤖",
            "needs_review":   "👀",
            "approved":       "✅",
            "rejected":       "❌",
            "disputed":       "⚡",
        }
        icon = status_icons.get(err.get("status", "detected_by_ai"), "🤖")
        conf = err.get("confidence", 1.0)

        with st.expander(
            f"{icon} [{crit_labels.get(crit, crit).upper()}] {err.get('title','Ошибка')}",
            expanded=(crit in ("critical", "high"))
        ):
            ec1, ec2 = st.columns([2, 1])
            with ec1:
                if err.get("description"):
                    st.markdown(f"**Описание:** {err['description']}")
                if err.get("evidence_quote"):
                    st.markdown(f"**Цитата:**\n> _{err['evidence_quote']}_")
                if err.get("timestamp"):
                    st.markdown(f"**Таймкод:** {err['timestamp']}")
                st.markdown(f"**Уверенность ИИ:** {conf*100:.0f}%")

            with ec2:
                st.markdown(f"**Статус:** {icon} {err.get('status','')}")
                err_id = err.get("id")
                if err_id:
                    if err.get("status") in ("detected_by_ai", "needs_review"):
                        bc1, bc2 = st.columns(2)
                        with bc1:
                            if st.button("✅ Подтвердить", key=f"approve_{err_id}"):
                                update_error_status(err_id, "approved")
                                st.rerun()
                        with bc2:
                            if st.button("❌ Отклонить", key=f"reject_{err_id}"):
                                update_error_status(err_id, "rejected")
                                st.rerun()
                        comment = st.text_input("Комментарий", key=f"comment_{err_id}", placeholder="Необязательно")
                        if st.button("👀 На проверку", key=f"review_{err_id}"):
                            update_error_status(err_id, "needs_review", comment)
                            st.rerun()
else:
    st.success("✅ Ошибок не обнаружено")

st.divider()

# ── ИНСТРУМЕНТЫ ПРОДАЖ ────────────────────────────────────────────────────
st.subheader("🛠️ Инструменты продаж")

tools = analysis.get("sales_tools", [])
if tools:
    used   = [t for t in tools if t.get("was_used")]
    missed = [t for t in tools if not t.get("was_used")]

    tc1, tc2 = st.columns(2)
    with tc1:
        st.markdown(f"**✅ Использовано ({len(used)})**")
        for t in used:
            q = t.get("quality_score", 0)
            color = score_to_color(q)
            with st.expander(f"✅ {t.get('tool_name','Инструмент')} — {q:.0f}/100"):
                if t.get("evidence_quote"):
                    st.markdown(f"> _{t['evidence_quote']}_")
                if t.get("timestamp"):
                    st.caption(f"⏱ {t['timestamp']}")
                if t.get("recommendation"):
                    st.info(f"💡 {t['recommendation']}")

    with tc2:
        st.markdown(f"**❌ Пропущено ({len(missed)})**")
        for t in missed:
            with st.expander(f"❌ {t.get('tool_name','Инструмент')}"):
                if t.get("recommendation"):
                    st.warning(f"💡 {t['recommendation']}")
else:
    st.info("Данные по инструментам отсутствуют.")

st.divider()

# ── ВОЗРАЖЕНИЯ ────────────────────────────────────────────────────────────
st.subheader("💬 Возражения")

objections = analysis.get("objections", [])
if objections:
    for obj in objections:
        hidden = obj.get("is_hidden", False)
        handled = obj.get("was_handled", False)
        icon = "👻" if hidden else "💬"
        handled_icon = "✅" if handled else "❌"

        with st.expander(f"{icon} {'Скрытое: ' if hidden else ''}{obj.get('type','Возражение')} {handled_icon}"):
            oc1, oc2 = st.columns(2)
            with oc1:
                if obj.get("client_phrase"):
                    st.markdown(f"**Фраза клиента:**\n> _{obj['client_phrase']}_")
                if obj.get("timestamp"):
                    st.caption(f"⏱ {obj['timestamp']}")
                if obj.get("manager_response"):
                    st.markdown(f"**Ответ менеджера:**\n{obj['manager_response']}")
            with oc2:
                q = obj.get("response_quality_score", 0)
                color = score_to_color(q)
                st.markdown(f"**Качество ответа:** <span style='color:{color};font-weight:700'>{q:.0f}/100</span>", unsafe_allow_html=True)
                if obj.get("recommendation"):
                    st.info(f"💡 {obj['recommendation']}")
else:
    st.success("✅ Возражений не обнаружено")

st.divider()

# ── СЛАБОЕ СОГЛАСИЕ ───────────────────────────────────────────────────────
st.subheader("⚡ Детектор слабого согласия")

wa = analysis.get("weak_agreement") or {}
if isinstance(wa, str):
    try:
        wa = json.loads(wa)
    except Exception:
        wa = {}

if wa.get("detected"):
    st.warning("⚡ Обнаружено слабое согласие!")
    wc1, wc2 = st.columns(2)
    with wc1:
        st.markdown(f"**Фраза клиента:**\n> _{wa.get('client_phrase','')}_")
        if wa.get("timestamp"):
            st.caption(f"⏱ {wa.get('timestamp')}")
        st.markdown(f"**Почему это риск:**\n{wa.get('risk_reason','')}")
    with wc2:
        if wa.get("better_manager_phrase"):
            st.info(f"💡 Как надо было сказать:\n\n**«{wa['better_manager_phrase']}»**")
else:
    st.success("✅ Слабого согласия не обнаружено")

st.divider()

# ── ПРОГНОЗ ДОХОДИМОСТИ ───────────────────────────────────────────────────
st.subheader("🎯 Прогноз доходимости")

sp = analysis.get("show_up_prediction")
if isinstance(sp, str):
    try:
        sp = json.loads(sp)
    except Exception:
        sp = {}
sp = sp or {}

score_su = sp.get("score", analysis.get("show_up_probability_score", 0))
risk_lv = sp.get("risk_level", analysis.get("show_up_risk_level", "medium"))
color_su = score_to_color(score_su)
color_r  = risk_color(risk_lv)

su1, su2, su3 = st.columns(3)
with su1:
    st.markdown(f"""
    <div style="text-align:center;background:#1E293B;border-radius:12px;padding:20px;
         border-top:4px solid {color_su}">
      <div style="font-size:42px;font-weight:700;color:{color_su}">{score_su:.0f}%</div>
      <div style="color:#94A3B8">Вероятность явки</div>
    </div>
    """, unsafe_allow_html=True)
with su2:
    st.markdown(f"""
    <div style="text-align:center;background:#1E293B;border-radius:12px;padding:20px;
         border-top:4px solid {color_r}">
      <div style="font-size:22px;font-weight:700;color:{color_r}">{risk_level_label(risk_lv)}</div>
      <div style="color:#94A3B8">Уровень риска</div>
    </div>
    """, unsafe_allow_html=True)
with su3:
    pos = sp.get("positive_factors", [])
    neg = sp.get("negative_factors", [])
    if isinstance(pos, str):
        try: pos = json.loads(pos)
        except: pos = []
    if isinstance(neg, str):
        try: neg = json.loads(neg)
        except: neg = []
    st.markdown(f"**✅ Позитивные факторы:** {len(pos)}")
    st.markdown(f"**⚠️ Факторы риска:** {len(neg)}")

if sp.get("risk_reasons"):
    risk_reasons = sp["risk_reasons"]
    if isinstance(risk_reasons, str):
        try: risk_reasons = json.loads(risk_reasons)
        except: risk_reasons = [risk_reasons]
    st.markdown("**Причины риска:**")
    for r in risk_reasons:
        st.markdown(f"  — {r}")

if sp.get("recommendation"):
    st.warning(f"💡 Что нужно было сделать: {sp['recommendation']}")

st.divider()

# ── ЭМОЦИОНАЛЬНЫЙ ТАЙМЛАЙН ────────────────────────────────────────────────
st.subheader("🎭 Эмоциональный таймлайн")

etl = analysis.get("emotional_timeline", [])
if etl:
    fig_emo = emotion_timeline_chart(etl)
    st.plotly_chart(fig_emo, use_container_width=True)

    st.markdown("**Ключевые моменты:**")
    for moment in etl:
        client_st = client_state_label(moment.get("client_state", ""))
        mgr_tone  = manager_tone_label(moment.get("manager_tone", ""))
        note = moment.get("note", "")
        ts   = moment.get("timestamp", "")
        st.markdown(
            f"  **{ts}** — Клиент: _{client_st}_ | Менеджер: _{mgr_tone}_ — {note}"
        )
else:
    st.info("Данные эмоционального таймлайна отсутствуют.")

st.divider()

# ── ТАЙМЛАЙН ЗВОНКА ───────────────────────────────────────────────────────
st.subheader("⏱️ AI Call Timeline")

timeline_events = analysis.get("timeline_events", [])
if timeline_events:
    for ev in timeline_events:
        risk = ev.get("risk_level", "low")
        color = risk_color(risk)
        type_icons = {
            "stage": "📍", "objection": "💬", "weak_signal": "⚡",
            "strong_close": "🎯", "risk": "⚠️", "tool_used": "🛠️",
        }
        icon = type_icons.get(ev.get("event_type", ""), "•")
        q = ev.get("quality_score", 0)

        st.markdown(
            f"**{ev.get('start_time','?')}–{ev.get('end_time','?')}** "
            f"{icon} {ev.get('description','')}"
            f"{'  ⚠️' if risk in ('high','critical') else ''}",
        )
        if ev.get("evidence_quote"):
            st.caption(f"> {ev['evidence_quote']}")
else:
    st.info("Данные таймлайна отсутствуют.")

st.divider()

# ── ТРАНСКРИПТ ────────────────────────────────────────────────────────────
st.subheader("📄 Транскрипт")

if transcript:
    segs = transcript.get("segments", [])
    if segs:
        for seg in segs:
            speaker = seg.get("speaker", "unknown")
            text    = seg.get("text", "")
            ts_s    = seg.get("start_time", 0)
            ts_str  = f"{int(ts_s)//60}:{int(ts_s)%60:02d}"

            if speaker == "manager":
                st.markdown(
                    f"<div style='background:#1E293B;border-left:3px solid #6366F1;"
                    f"padding:8px 12px;margin:4px 0;border-radius:0 8px 8px 0'>"
                    f"<span style='color:#6366F1;font-size:11px;font-weight:600'>"
                    f"МЕНЕДЖЕР {ts_str}</span><br>"
                    f"<span style='color:#F1F5F9'>{text}</span></div>",
                    unsafe_allow_html=True,
                )
            elif speaker == "client":
                st.markdown(
                    f"<div style='background:#0F172A;border-left:3px solid #22C55E;"
                    f"padding:8px 12px;margin:4px 0;border-radius:0 8px 8px 0'>"
                    f"<span style='color:#22C55E;font-size:11px;font-weight:600'>"
                    f"КЛИЕНТ {ts_str}</span><br>"
                    f"<span style='color:#F1F5F9'>{text}</span></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption(f"[{ts_str}] {text}")
    elif transcript.get("transcript", {}).get("full_text"):
        st.text(transcript["transcript"]["full_text"])
else:
    st.info("Транскрипт недоступен.")

st.divider()

# ── ФРАЗЫ ────────────────────────────────────────────────────────────────
st.subheader("💬 Фразы из звонка")

phrases = analysis.get("phrases", [])
if phrases:
    best   = [p for p in phrases if p.get("phrase_type") in ("best", "closing", "commitment", "value")]
    worst  = [p for p in phrases if p.get("phrase_type") in ("worst", "forbidden", "trust_damage", "pressure")]

    pc1, pc2 = st.columns(2)
    with pc1:
        st.markdown(f"**✅ Сильные фразы ({len(best)})**")
        for p in best[:5]:
            with st.expander(f"✅ \"{p.get('phrase_text','')[:60]}...\"" if len(p.get('phrase_text','')) > 60 else f"✅ \"{p.get('phrase_text','')}\""):
                st.markdown(f"_{p.get('explanation','')}_")
                if p.get("timestamp"):
                    st.caption(f"⏱ {p['timestamp']} | {phrase_type_label(p.get('phrase_type',''))}")

    with pc2:
        st.markdown(f"**❌ Слабые фразы ({len(worst)})**")
        for p in worst[:5]:
            with st.expander(f"❌ \"{p.get('phrase_text','')[:60]}...\"" if len(p.get('phrase_text','')) > 60 else f"❌ \"{p.get('phrase_text','')}\""):
                st.markdown(f"_{p.get('explanation','')}_")
                if p.get("timestamp"):
                    st.caption(f"⏱ {p['timestamp']} | {phrase_type_label(p.get('phrase_type',''))}")
                pid = p.get("id")
                if pid:
                    if st.button("📚 В библиотеку", key=f"lib_{pid}"):
                        update_phrase_status(pid, "approved")
                        st.success("Добавлено в библиотеку")
else:
    st.info("Фразы не выделены.")

st.divider()

# ── РЕКОМЕНДАЦИИ РОПУ ─────────────────────────────────────────────────────
st.subheader("📌 Рекомендации для РОПа")

recs = analysis.get("recommendations", [])
if recs:
    priority_icons = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
    for rec in recs:
        icon = priority_icons.get(rec.get("priority", "medium"), "🟡")
        with st.expander(f"{icon} {rec.get('title','Рекомендация')}"):
            if rec.get("main_problem"):
                st.markdown(f"**Проблема:** {rec['main_problem']}")
            if rec.get("business_risk"):
                st.markdown(f"**Бизнес-риск:** {rec['business_risk']}")
            if rec.get("recommended_action"):
                st.success(f"**Действие РОПа:** {rec['recommended_action']}")
            evidence = rec.get("data_evidence", [])
            if isinstance(evidence, str):
                try: evidence = json.loads(evidence)
                except: evidence = [evidence]
            if evidence:
                st.markdown("**Данные:**")
                for ev in evidence:
                    st.markdown(f"  — {ev}")
else:
    st.info("Рекомендации не сформированы.")
