"""
ai_pipeline.py — полный pipeline анализа звонка через Gemini.

Шаги:
1. Загрузка аудиофайла в Gemini Files API
2. Транскрибация с диаризацией (менеджер / клиент)
3. AI-анализ по чеклисту и всем метрикам
4. Валидация JSON
5. Сохранение результатов в БД
"""

import os
import time
import tempfile
import logging
import streamlit as st
import google.generativeai as genai

from core.database import (
    get_checklist_rules, get_stage_weights,
    save_transcript, save_analysis, update_call_status,
)
from core.prompt_builder import build_prompt, build_transcription_prompt
from core.json_validator import parse_ai_response

logger = logging.getLogger(__name__)

# Цепочка моделей с фолбэком при исчерпании квоты
MODEL_CHAIN = [
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

AUDIO_MIME_TYPES = {
    ".mp3":  "audio/mp3",
    ".wav":  "audio/wav",
    ".m4a":  "audio/mp4",
    ".ogg":  "audio/ogg",
    ".flac": "audio/flac",
    ".aac":  "audio/aac",
    ".opus": "audio/ogg",
}


def get_api_key() -> str:
    """Получает API-ключ из Streamlit Secrets или session_state."""
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if key:
            return key
    except Exception:
        pass
    return st.session_state.get("api_key", "")


def _try_models(prompt_parts: list, status_placeholder=None) -> str:
    """Пробует модели по цепочке, возвращает текст ответа."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("API-ключ Gemini не задан")
    genai.configure(api_key=api_key)

    last_error = None
    for model_name in MODEL_CHAIN:
        try:
            if status_placeholder:
                status_placeholder.info(f"🤖 Используем модель {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt_parts,
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                ),
            )
            return response.text
        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower() or "503" in msg or "RESOURCE_EXHAUSTED" in msg:
                logger.warning(f"Модель {model_name} исчерпана: {e}")
                last_error = e
                time.sleep(2)
                continue
            raise  # Другие ошибки — пробрасываем
    raise last_error or RuntimeError("Все модели Gemini недоступны")


def transcribe_audio(audio_bytes: bytes, filename: str,
                     status_placeholder=None) -> str:
    """
    Транскрибирует аудио через Gemini.
    Возвращает текст транскрипта с таймкодами и пометками спикеров.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("API-ключ Gemini не задан")
    genai.configure(api_key=api_key)

    ext = os.path.splitext(filename)[1].lower() or ".mp3"
    mime = AUDIO_MIME_TYPES.get(ext, "audio/mp3")

    if status_placeholder:
        status_placeholder.info("🎙️ Загружаем аудио в Gemini...")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        audio_file = genai.upload_file(path=tmp_path, mime_type=mime)

        # Ждём пока файл обработается
        for _ in range(30):
            if audio_file.state.name == "ACTIVE":
                break
            time.sleep(2)
            audio_file = genai.get_file(audio_file.name)

        if status_placeholder:
            status_placeholder.info("📝 Транскрибируем...")

        prompt = build_transcription_prompt()
        transcript_text = _try_models([prompt, audio_file], status_placeholder)
        return transcript_text.strip()
    finally:
        os.unlink(tmp_path)


def parse_transcript_segments(transcript_text: str) -> list[dict]:
    """
    Парсит транскрипт с таймкодами в список сегментов.
    Формат строки: [MM:SS] Спикер: текст
    """
    import re
    segments = []
    pattern = re.compile(
        r"\[(\d{1,2}:\d{2})\]\s*(Менеджер|Клиент|Неизвестно)\s*:\s*(.+)"
    )
    lines = transcript_text.split("\n")
    prev_end = 0.0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            time_str, speaker, text = m.group(1), m.group(2), m.group(3)
            # Конвертируем MM:SS → секунды
            parts = time_str.split(":")
            start_sec = int(parts[0]) * 60 + int(parts[1])
            speaker_key = {"Менеджер": "manager", "Клиент": "client"}.get(speaker, "unknown")
            segments.append({
                "speaker": speaker_key,
                "text": text.strip(),
                "start_time": float(start_sec),
                "end_time": float(start_sec),  # end_time будет уточнён ниже
                "confidence": 1.0,
            })
            prev_end = float(start_sec)
        else:
            # Продолжение предыдущего сегмента
            if segments:
                segments[-1]["text"] += " " + line

    # Проставляем end_time = start_time следующего сегмента
    for i in range(len(segments) - 1):
        segments[i]["end_time"] = segments[i + 1]["start_time"]
    if segments:
        segments[-1]["end_time"] = segments[-1]["start_time"] + 10.0

    return segments


def analyze_call(call_id: int, audio_bytes: bytes, filename: str,
                 status_placeholder=None) -> dict:
    """
    Полный pipeline анализа одного звонка.
    Возвращает словарь с результатами анализа.
    """
    update_call_status(call_id, "processing")

    try:
        # ── Шаг 1: Транскрибация ──────────────────────────────────────
        transcript_text = transcribe_audio(audio_bytes, filename, status_placeholder)
        segments = parse_transcript_segments(transcript_text)
        save_transcript(call_id, transcript_text, segments)

        # ── Шаг 2: Загрузить чеклист и веса этапов из БД ─────────────
        checklist_df = get_checklist_rules(active_only=True)
        # Веса берём для generic primary_outbound — ИИ сам определит тип
        stage_weights_df = get_stage_weights("primary_outbound")

        # ── Шаг 3: Строим промпт ──────────────────────────────────────
        if status_placeholder:
            status_placeholder.info("🧠 Анализируем звонок...")

        prompt = build_prompt(transcript_text, checklist_df, stage_weights_df)

        # ── Шаг 4: Запрашиваем анализ у Gemini ───────────────────────
        api_key = get_api_key()
        genai.configure(api_key=api_key)

        raw_response = _try_models([prompt], status_placeholder)

        # ── Шаг 5: Парсим и валидируем JSON ──────────────────────────
        result = parse_ai_response(raw_response)

        # ── Шаг 6: Пересчитываем веса если тип звонка стал известен ──
        call_type = result.get("call_type", "unknown")
        if call_type not in ("unknown", "inactive"):
            try:
                weights_df = get_stage_weights(call_type)
                if not weights_df.empty:
                    from core.score_calculator import calculate_weighted_score
                    corrected = calculate_weighted_score(
                        result.get("sales_stage_scores", []), weights_df
                    )
                    if corrected > 0:
                        result["qa_score"] = corrected
            except Exception:
                pass

        result["model_name"] = MODEL_CHAIN[0]

        # ── Шаг 7: Сохраняем результат в БД ──────────────────────────
        save_analysis(call_id, result)

        # Обновляем статус и тип звонка в таблице calls
        from core.database import get_conn
        conn = get_conn()
        conn.execute(
            "UPDATE calls SET analysis_status='done', call_type=?, is_active_call=? WHERE id=?",
            (call_type, int(result.get("is_active_call", True)), call_id)
        )
        conn.commit()
        conn.close()

        if status_placeholder:
            status_placeholder.success("✅ Анализ завершён")

        return result

    except Exception as e:
        update_call_status(call_id, "error")
        logger.error(f"Ошибка анализа звонка {call_id}: {e}")
        raise


def run_batch_analysis(calls_data: list[dict], status_container=None) -> dict:
    """
    Анализирует несколько звонков последовательно.
    calls_data: список {"call_id": int, "audio_bytes": bytes, "filename": str}
    Возвращает {"success": N, "errors": [...]}
    """
    success = 0
    errors = []
    total = len(calls_data)

    for i, item in enumerate(calls_data):
        call_id  = item["call_id"]
        filename = item["filename"]

        if status_container:
            status_container.info(f"📞 Обрабатываю {i + 1}/{total}: {filename}")

        try:
            analyze_call(
                call_id=call_id,
                audio_bytes=item["audio_bytes"],
                filename=filename,
            )
            success += 1
        except Exception as e:
            errors.append({"call_id": call_id, "filename": filename, "error": str(e)})
            logger.error(f"Ошибка при обработке {filename}: {e}")

        # Пауза между запросами чтобы не упереться в rate limit
        if i < total - 1:
            time.sleep(3)

    return {"success": success, "errors": errors, "total": total}
