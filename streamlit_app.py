"""小六壬占卜 — Streamlit 版

本機執行：  streamlit run streamlit_app.py
部署：      推到 GitHub 後，在 https://share.streamlit.io 選此檔為 Main file
"""

import base64
import io
import wave
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import streamlit as st
from lunar_python import Solar

# Streamlit Cloud 主機在 UTC，固定用台灣時間（UTC+8，無日光節約）
TZ = timezone(timedelta(hours=8))

# 放自己的素材即可替換：assets/bg.jpg（背景圖）、assets/bgm.mp3（背景音樂）
ASSETS = Path(__file__).parent / "assets"
BG_IMAGE = ASSETS / "bg.jpg"
BGM_FILE = ASSETS / "bgm.mp3"

EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
BRANCH_HOURS = [
    "23:00–00:59", "01:00–02:59", "03:00–04:59", "05:00–06:59",
    "07:00–08:59", "09:00–10:59", "11:00–12:59", "13:00–14:59",
    "15:00–16:59", "17:00–18:59", "19:00–20:59", "21:00–22:59",
]

XIAO_LIUREN = ["大安", "留連", "速喜", "赤口", "小吉", "空亡"]

EXPLANATIONS = {
    "大安": "大安即「大吉安寧」之意，象徵平安穩定，萬事順利，宜靜不宜動，諸事皆吉。",
    "留連": "留連代表拖延與猶豫，諸事不決，可能會有耽擱或反覆，宜保守觀望。",
    "速喜": "速喜代表喜事快速來臨，萬事皆順，利於行動、求財、婚嫁等事。",
    "赤口": "赤口代表口舌是非、爭執糾紛，不宜見官或交涉，應避免衝突與出行。",
    "小吉": "小吉雖非大好，但仍有進展，小事可成，宜行小事，不可貪大求多。",
    "空亡": "空亡象徵落空與虛無，諸事不利，會有失落或失敗的狀況，宜靜守不動。",
}

IMAGES = {
    "大安": "https://i.imgur.com/bIqsuTV.jpeg",
    "留連": "https://i.imgur.com/NGoCOXc.jpeg",
    "速喜": "https://i.imgur.com/dRHw6Cy.jpeg",
    "赤口": "https://i.imgur.com/nGodzNh.jpeg",
    "小吉": "https://i.imgur.com/OOQS3wL.jpeg",
    "空亡": "https://i.imgur.com/1s3nz58.jpeg",
}

LUCK = {"大安": "吉", "留連": "凶", "速喜": "吉", "赤口": "凶", "小吉": "吉", "空亡": "凶"}


def hour_to_branch_index(hour: int) -> int:
    """0~23 時 → 地支索引（子=0）。23 點屬子時。"""
    return ((hour + 1) // 2) % 12


def xiao_liuren(lunar_month: int, lunar_day: int, branch_index: int):
    """傳統掐指法：由大安起正月，順數至月；由月上起初一，數至日；由日上起子時，數至時。

    回傳 (月落宮, 日落宮, 時落宮)
    """
    m = (lunar_month - 1) % 6
    d = (m + lunar_day - 1) % 6
    h = (d + branch_index) % 6
    return XIAO_LIUREN[m], XIAO_LIUREN[d], XIAO_LIUREN[h]


def to_lunar(dt: datetime):
    """西曆 → 農曆。23 點後屬隔日子時，故以隔日的農曆日起算。"""
    if dt.hour == 23:
        dt = dt + timedelta(hours=1)
    lunar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0).getLunar()
    return lunar


@st.cache_data
def generate_bgm(seconds: int = 48, sr: int = 22050) -> bytes:
    """以五聲音階（宮商角徵羽）合成一段可循環的古風氛圍音樂，回傳 WAV bytes。"""
    rng = np.random.default_rng(8)
    t_total = np.arange(seconds * sr) / sr
    out = np.zeros_like(t_total)

    # 低音持續音（宮 + 徵），緩慢起伏
    swell = 0.6 + 0.4 * np.sin(2 * np.pi * t_total / seconds)
    for f in (130.81, 196.00):
        out += 0.08 * swell * np.sin(2 * np.pi * f * t_total)

    # 撥弦旋律：C D E G A 兩個八度，指數衰減模擬古箏
    scale = [261.63, 293.66, 329.63, 392.00, 440.00, 523.25, 587.33, 659.25]
    beat = 0.75
    note_len = int(3.0 * sr)
    tn = np.arange(note_len) / sr
    env = np.exp(-tn * 2.2) * np.minimum(tn / 0.01, 1)
    idx = 2
    for k in range(int(seconds / beat)):
        if rng.random() < 0.35:  # 留白
            continue
        idx = int(np.clip(idx + rng.choice([-2, -1, 1, 2]), 0, len(scale) - 1))
        f = scale[idx]
        tone = np.sin(2 * np.pi * f * tn) + 0.3 * np.sin(4 * np.pi * f * tn)
        start = int(k * beat * sr)
        seg = (0.18 * env * tone)[: len(out) - start]
        out[start:start + len(seg)] += seg

    # 頭尾淡入淡出，循環時不突兀
    fade = int(2 * sr)
    out[:fade] *= np.linspace(0, 1, fade)
    out[-fade:] *= np.linspace(1, 0, fade)
    out = out / np.max(np.abs(out)) * 0.5

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def apply_background():
    if BG_IMAGE.exists():
        b64 = base64.b64encode(BG_IMAGE.read_bytes()).decode()
        bg = f'url("data:image/jpeg;base64,{b64}") center / cover fixed no-repeat'
    else:
        bg = (
            "radial-gradient(circle at 20% 15%, rgba(255,215,140,.18) 0, transparent 35%),"
            "radial-gradient(circle at 85% 80%, rgba(195,110,0,.22) 0, transparent 40%),"
            "linear-gradient(160deg, #1a1033 0%, #2b1840 45%, #3d1f1f 100%) fixed"
        )
    st.markdown(
        f"""
<style>
[data-testid="stAppViewContainer"] {{ background: {bg}; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] {{
    background: rgba(255, 250, 240, .92);
    border-radius: 16px;
    padding: 2rem 2rem 1.5rem;
    margin-top: 3rem;
    margin-bottom: 3rem;
    box-shadow: 0 8px 32px rgba(0, 0, 0, .35);
    color: #2b1a0e;
}}
</style>
""",
        unsafe_allow_html=True,
    )


# ---------------- UI ----------------

st.set_page_config(page_title="小六壬占卜", page_icon="🧙", layout="centered")
apply_background()

with st.sidebar:
    st.subheader("🎵 背景音樂")
    st.caption("瀏覽器不允許網頁自動發出聲音，請開啟開關或按播放鍵。")
    if st.toggle("播放音樂", value=False):
        if BGM_FILE.exists():
            st.audio(str(BGM_FILE), format="audio/mpeg", loop=True, autoplay=True)
        else:
            st.audio(generate_bgm(), format="audio/wav", loop=True, autoplay=True)

st.title("🧙 小六壬占卜")

with st.expander("小六壬占卜教學"):
    st.markdown(
        """
小六壬，又稱「馬前課」、「掐指神算」，相傳為諸葛亮所創。以**農曆月、日與時辰**，
在六個宮位（大安、留連、速喜、赤口、小吉、空亡）上依序推數，得出所問之事的吉凶。

**起課方法**
1. 從「大安」起正月，順數到農曆月份。
2. 從月份落宮起初一，順數到農曆日期。
3. 從日期落宮起子時，順數到當下時辰，最後落宮即為結果。

**適用範圍**：事物吉凶、求財、出行、尋人尋物、感情、健康等短期之事。
"""
    )
    for name in XIAO_LIUREN:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"**{name}**（{LUCK[name]}）：{EXPLANATIONS[name]}")
        c2.image(IMAGES[name], width=120)

now = datetime.now(TZ)
use_now = st.toggle("使用當前時間（台灣時間）", value=True)

if use_now:
    query_dt = now
    st.caption(f"現在時間：{now:%Y-%m-%d %H:%M}")
else:
    col1, col2 = st.columns(2)
    picked_date = col1.date_input(
        "選擇日期", value=now.date(), min_value=date(1901, 1, 1), max_value=date(2099, 12, 31)
    )
    branch_index = col2.selectbox(
        "選擇時辰",
        options=range(12),
        index=hour_to_branch_index(now.hour),
        format_func=lambda i: f"{EARTHLY_BRANCHES[i]}時（{BRANCH_HOURS[i]}）",
    )
    # 取該時辰的代表小時（子時用 0 點，避免跨日）
    rep_hour = 0 if branch_index == 0 else branch_index * 2 - 1
    query_dt = datetime(picked_date.year, picked_date.month, picked_date.day, rep_hour, tzinfo=TZ)

question = st.text_input("心中所問之事（可不填）", placeholder="例如：這次面試是否順利？")

if st.button("🔮 起課", type="primary", width="stretch"):
    lunar = to_lunar(query_dt)
    lunar_month = abs(lunar.getMonth())  # 閏月為負數，依本月計
    lunar_day = lunar.getDay()
    b_idx = hour_to_branch_index(query_dt.hour)

    m_res, d_res, h_res = xiao_liuren(lunar_month, lunar_day, b_idx)

    st.divider()
    if question:
        st.markdown(f"**所問：** {question}")

    leap = "閏" if lunar.getMonth() < 0 else ""
    st.markdown(
        f"**農曆：** {lunar.getYearInGanZhi()}年 {leap}{lunar.getMonthInChinese()}月"
        f"{lunar.getDayInChinese()}　**時辰：** {EARTHLY_BRANCHES[b_idx]}時"
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("月（%d月）" % lunar_month, m_res)
    c2.metric("日（%d日）" % lunar_day, d_res)
    c3.metric("時（%s時）" % EARTHLY_BRANCHES[b_idx], h_res)

    st.subheader(f"占卜結果：{h_res}（{LUCK[h_res]}）")
    if LUCK[h_res] == "吉":
        st.success(EXPLANATIONS[h_res])
    else:
        st.warning(EXPLANATIONS[h_res])
    st.image(IMAGES[h_res], width="stretch")

st.caption("僅供娛樂參考")
