"""
audio_player.py — кастомный HTML/JS аудиоплеер с маркерами ошибок.

Позволяет:
- Play/pause
- Скорость 1x, 1.25x, 1.5x, 2x
- Маркеры ошибок на таймлайне (клик → перемотка)
- Маркеры возражений, слабых согласий, эмоциональных переломов
"""

import streamlit as st
import base64


def _encode_audio(audio_bytes: bytes) -> str:
    return base64.b64encode(audio_bytes).decode("utf-8")


def render_audio_player(audio_bytes: bytes | None, markers: list[dict] | None = None,
                         height: int = 140):
    """
    Отрисовывает кастомный аудиоплеер.

    markers — список маркеров:
    [{"time": 45.0, "label": "Ошибка: не представился", "color": "#EF4444", "type": "error"}]
    """
    if audio_bytes is None:
        st.info("🎵 Аудиофайл недоступен для воспроизведения")
        return

    audio_b64 = _encode_audio(audio_bytes)
    markers = markers or []

    markers_js = str(markers).replace("True", "true").replace("False", "false").replace("None", "null")

    html = f"""
<style>
  .player-wrap {{
    background: #1E293B;
    border-radius: 12px;
    padding: 16px 20px;
    font-family: 'Inter', system-ui, sans-serif;
    color: #F1F5F9;
    border: 1px solid #334155;
  }}
  .player-controls {{
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }}
  .btn {{
    background: #4F46E5;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 6px 14px;
    cursor: pointer;
    font-size: 14px;
    transition: background 0.2s;
  }}
  .btn:hover {{ background: #6366F1; }}
  .btn.secondary {{ background: #334155; }}
  .btn.secondary:hover {{ background: #475569; }}
  .time-display {{
    font-size: 13px;
    color: #94A3B8;
    min-width: 100px;
  }}
  .speed-select {{
    background: #334155;
    color: #F1F5F9;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 13px;
    cursor: pointer;
  }}
  .timeline-wrap {{
    position: relative;
    height: 32px;
    margin-bottom: 8px;
  }}
  .timeline-bg {{
    position: absolute;
    top: 12px;
    left: 0; right: 0;
    height: 8px;
    background: #334155;
    border-radius: 4px;
    cursor: pointer;
  }}
  .timeline-progress {{
    height: 100%;
    background: #6366F1;
    border-radius: 4px;
    width: 0%;
    pointer-events: none;
  }}
  .marker {{
    position: absolute;
    top: 6px;
    width: 4px;
    height: 20px;
    border-radius: 2px;
    cursor: pointer;
    transform: translateX(-50%);
    transition: opacity 0.2s;
    z-index: 10;
  }}
  .marker:hover {{ opacity: 0.7; }}
  .marker-tooltip {{
    display: none;
    position: absolute;
    bottom: 28px;
    left: 50%;
    transform: translateX(-50%);
    background: #0F172A;
    color: #F1F5F9;
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 6px;
    white-space: nowrap;
    border: 1px solid #334155;
    z-index: 20;
  }}
  .marker:hover .marker-tooltip {{ display: block; }}
  .markers-legend {{
    display: flex;
    gap: 16px;
    font-size: 11px;
    color: #94A3B8;
    flex-wrap: wrap;
  }}
  .legend-dot {{
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 4px;
  }}
</style>

<div class="player-wrap">
  <audio id="audio_player" src="data:audio/mp3;base64,{audio_b64}" preload="metadata"></audio>

  <div class="player-controls">
    <button class="btn" id="playBtn" onclick="togglePlay()">▶ Играть</button>
    <button class="btn secondary" onclick="seekRel(-10)">−10с</button>
    <button class="btn secondary" onclick="seekRel(10)">+10с</button>
    <select class="speed-select" onchange="setSpeed(this.value)">
      <option value="1">1×</option>
      <option value="1.25">1.25×</option>
      <option value="1.5">1.5×</option>
      <option value="2">2×</option>
    </select>
    <span class="time-display" id="timeDisplay">0:00 / 0:00</span>
  </div>

  <div class="timeline-wrap" id="timelineWrap">
    <div class="timeline-bg" id="timelineBg" onclick="seekToClick(event)">
      <div class="timeline-progress" id="progress"></div>
    </div>
  </div>

  <div class="markers-legend" id="markersLegend"></div>
</div>

<script>
  const audio    = document.getElementById('audio_player');
  const playBtn  = document.getElementById('playBtn');
  const progress = document.getElementById('progress');
  const timeDis  = document.getElementById('timeDisplay');
  const timeline = document.getElementById('timelineWrap');
  const timelineBg = document.getElementById('timelineBg');
  const legend   = document.getElementById('markersLegend');
  const markers  = {markers_js};

  function fmt(s) {{
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ':' + (sec < 10 ? '0' : '') + sec;
  }}

  function togglePlay() {{
    if (audio.paused) {{
      audio.play();
      playBtn.textContent = '⏸ Пауза';
    }} else {{
      audio.pause();
      playBtn.textContent = '▶ Играть';
    }}
  }}

  function seekRel(sec) {{
    audio.currentTime = Math.max(0, Math.min(audio.duration || 0, audio.currentTime + sec));
  }}

  function setSpeed(v) {{ audio.playbackRate = parseFloat(v); }}

  function seekToClick(e) {{
    const rect = timelineBg.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    audio.currentTime = ratio * (audio.duration || 0);
  }}

  audio.addEventListener('timeupdate', () => {{
    const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
    progress.style.width = pct + '%';
    timeDis.textContent = fmt(audio.currentTime) + ' / ' + fmt(audio.duration || 0);
  }});

  audio.addEventListener('ended', () => {{ playBtn.textContent = '▶ Играть'; }});

  // Рисуем маркеры
  const typeColors = {{
    'error':     '#EF4444',
    'objection': '#F97316',
    'weak':      '#EAB308',
    'emotion':   '#6366F1',
    'tool':      '#22C55E',
  }};

  const typeLabels = {{
    'error':     '❌ Ошибка',
    'objection': '⚠️ Возражение',
    'weak':      '⚡ Слабое согласие',
    'emotion':   '🎭 Эмоция',
    'tool':      '🛠 Инструмент',
  }};

  const legendTypes = new Set();

  audio.addEventListener('loadedmetadata', () => {{
    const dur = audio.duration;
    markers.forEach(m => {{
      if (!m || !m.time) return;
      const pct = (m.time / dur) * 100;
      const color = m.color || typeColors[m.type] || '#6366F1';
      const el = document.createElement('div');
      el.className = 'marker';
      el.style.left = pct + '%';
      el.style.background = color;
      el.innerHTML = '<div class="marker-tooltip">' + (m.label || '') + '</div>';
      el.onclick = (e) => {{ e.stopPropagation(); audio.currentTime = m.time; }};
      timeline.appendChild(el);
      legendTypes.add(m.type || 'error');
    }});

    // Легенда
    legendTypes.forEach(t => {{
      const span = document.createElement('span');
      span.innerHTML = '<span class="legend-dot" style="background:' + (typeColors[t] || '#888') + '"></span>' + (typeLabels[t] || t);
      legend.appendChild(span);
    }});
  }});
</script>
"""
    st.components.v1.html(html, height=height, scrolling=False)


def build_markers_from_analysis(analysis: dict) -> list[dict]:
    """Строит список маркеров из результатов анализа."""
    markers = []

    def ts_to_sec(ts: str) -> float | None:
        if not ts:
            return None
        try:
            parts = ts.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            pass
        return None

    # Ошибки
    for err in analysis.get("errors", []):
        t = ts_to_sec(err.get("timestamp"))
        if t is not None:
            color = {"low": "#94A3B8", "medium": "#EAB308",
                     "high": "#F97316", "critical": "#EF4444"}.get(err.get("criticality", "medium"), "#EF4444")
            markers.append({
                "time": t,
                "label": (err.get("title") or "Ошибка")[:60],
                "color": color,
                "type": "error",
            })

    # Возражения
    for obj in analysis.get("objections", []):
        t = ts_to_sec(obj.get("timestamp"))
        if t is not None:
            markers.append({
                "time": t,
                "label": ("Скрытое: " if obj.get("is_hidden") else "") + (obj.get("type") or "Возражение")[:50],
                "color": "#F97316",
                "type": "objection",
            })

    # Слабое согласие
    wa = analysis.get("weak_agreement") or {}
    if wa.get("detected"):
        t = ts_to_sec(wa.get("timestamp"))
        if t is not None:
            markers.append({
                "time": t,
                "label": "Слабое согласие: " + (wa.get("client_phrase") or "")[:40],
                "color": "#EAB308",
                "type": "weak",
            })

    # Эмоциональные переломы
    for et in analysis.get("emotional_timeline", []):
        t = ts_to_sec(et.get("timestamp"))
        if t is not None and et.get("note"):
            markers.append({
                "time": t,
                "label": et["note"][:50],
                "color": "#6366F1",
                "type": "emotion",
            })

    return markers
