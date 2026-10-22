from __future__ import annotations

import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import FinanceDataReader as fdr

st.set_page_config(page_title="한국 주식 타이밍 분석", page_icon="📈", layout="wide")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
    :root { --ink:#172033; --muted:#687386; --line:#e8edf3; --blue:#2563eb; --soft:#f6f8fb; }
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .stApp { background: linear-gradient(180deg, #f8fafc 0%, #ffffff 48%); color:var(--ink); }
    [data-testid="stHeader"] { background:transparent; }
    .block-container { max-width: 1080px; padding: 3.2rem 2rem 4rem; }
    .hero { text-align:center; padding: 1rem 0 2.1rem; }
    .hero-badge { display:inline-block; background:#eaf1ff; color:#2456c7; border-radius:999px; padding:.35rem .75rem; font-size:.78rem; font-weight:700; letter-spacing:.02em; }
    .hero h1 { margin:.8rem 0 .45rem; font-size:2.25rem; letter-spacing:-.06em; color:#111827; }
    .hero p { margin:0; color:var(--muted); font-size:.96rem; }
    .search-card { background:#fff; border:1px solid var(--line); border-radius:20px; padding:1.25rem 1.35rem .9rem; box-shadow:0 12px 35px rgba(29,48,78,.07); margin-bottom:1.6rem; }
    .search-label { font-size:.82rem; color:#536174; font-weight:700; margin-bottom:.35rem; }
    [data-testid="stTextInput"] label { display:none; }
    [data-testid="stTextInput"] input { border:0; background:#f4f7fb; border-radius:12px; padding:.85rem 1rem; font-size:1rem; }
    [data-testid="stTextInput"] input:focus { border-color:#8bb0ff; box-shadow:0 0 0 2px #dbe7ff; }
    .search-card [data-testid="stButton"] button { height:2.75rem; border-radius:12px; background:var(--blue); border:0; font-weight:700; }
    .status { color:#536174; font-size:.82rem; margin:.35rem 0 1.1rem; }
    .status strong { color:#2456c7; }
    .section-title { font-size:.82rem; color:#697586; font-weight:800; letter-spacing:.04em; margin:.7rem 0 .65rem; }
    [data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1rem 1.05rem; box-shadow:0 7px 22px rgba(29,48,78,.05); }
    [data-testid="stMetricLabel"] { color:#778397; font-size:.78rem; }
    [data-testid="stMetricValue"] { color:#172033; font-size:1.25rem; }
    .verdict-note { color:#687386; font-size:.82rem; line-height:1.55; margin:.7rem .15rem 0; }
    [data-testid="stTabs"] { margin-top:1.35rem; }
    [data-baseweb="tab-list"] { gap:1.35rem; border-bottom:1px solid var(--line); }
    [data-baseweb="tab"] { color:#7a8595; font-weight:600; padding: .7rem .1rem; }
    [aria-selected="true"] { color:var(--blue) !important; }
    [data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
    .stAlert { border-radius:14px; }
    .footer-note { text-align:center; color:#9aa4b2; font-size:.76rem; padding-top:2.5rem; }
</style>
""", unsafe_allow_html=True)

# 검증 전까지 실험용 설정입니다.
RULE_WEIGHTS = {"trend": 2.0, "momentum": 2.0, "volume": 1.0, "structure": 2.0}
NAME_TO_TICKER = {"삼성전자": "005930.KS", "삼성전자우": "005935.KS", "sk하이닉스": "000660.KS", "현대차": "005380.KS", "네이버": "035420.KS", "카카오": "035720.KS", "lg에너지솔루션": "373220.KS"}

@st.cache_data(ttl=86400, show_spinner=False)
def load_universe() -> pd.DataFrame:
    """KRX 전체 종목 목록을 하루 한 번 받아 검색에 사용합니다."""
    listing = fdr.StockListing("KRX")
    if listing is None or listing.empty:
        raise ValueError("KRX 종목 목록이 비어 있습니다.")
    code_col = "Code" if "Code" in listing.columns else "Symbol"
    name_col = "Name" if "Name" in listing.columns else "종목명"
    market_col = "Market" if "Market" in listing.columns else "시장구분"
    if not all(c in listing.columns for c in [code_col, name_col, market_col]):
        raise ValueError("종목 목록의 열 구성이 예상과 다릅니다.")
    universe = listing[[code_col, name_col, market_col]].copy()
    universe.columns = ["Code", "Name", "Market"]
    universe = universe[universe["Market"].isin(["KOSPI", "KOSDAQ"])].dropna()
    universe["Code"] = universe["Code"].astype(str).str.zfill(6)
    return universe.drop_duplicates("Code").sort_values(["Market", "Name"]).reset_index(drop=True)

def resolve_ticker(query: str, universe: pd.DataFrame | None = None) -> tuple[str, str, str]:
    q = query.strip()
    key = q.lower().replace(" ", "")
    if key in NAME_TO_TICKER:
        return NAME_TO_TICKER[key], q, "KOSPI"
    code = re.sub(r"[^0-9]", "", q)
    if universe is not None and not universe.empty:
        hit = universe[universe["Code"] == code] if len(code) == 6 else universe[universe["Name"].str.contains(q, case=False, na=False)]
        if not hit.empty:
            row = hit.iloc[0]
            suffix = "KS" if row["Market"] == "KOSPI" else "KQ"
            return f"{row['Code']}.{suffix}", str(row["Name"]), str(row["Market"])
    if len(code) == 6:
        return f"{code}.KS", q, "미확인"
    return q.upper(), q, "미확인"

@st.cache_data(ttl=900, show_spinner=False)
def load_data(ticker: str) -> tuple[pd.DataFrame, datetime, str]:
    end = datetime.now() + timedelta(days=1)
    start = end - timedelta(days=365 * 5 + 20)
    yahoo_error = None
    try:
        raw = yf.download(ticker, start=start.date(), end=end.date(), auto_adjust=False, progress=False, threads=False)
        if raw is None or raw.empty:
            raise ValueError("Yahoo Finance 응답이 비어 있습니다.")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns={"Adj Close": "Adj_Close"})
        source = "Yahoo Finance (yfinance)"
    except Exception as exc:
        yahoo_error = str(exc)
        code = ticker.split(".")[0]
        try:
            raw = fdr.DataReader(code, start=start.date(), end=end.date())
            if raw is None or raw.empty:
                raise ValueError("FinanceDataReader 응답이 비어 있습니다.")
            source = "FinanceDataReader 국내 일봉 대체 조회"
        except Exception as fallback_exc:
            raise ValueError(f"Yahoo Finance와 대체 데이터 조회가 모두 실패했습니다. Yahoo: {yahoo_error}; 대체: {fallback_exc}") from fallback_exc
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in raw.columns]
    if missing:
        raise ValueError(f"필수 열이 없습니다: {', '.join(missing)}")
    cols = needed + (["Adj_Close"] if "Adj_Close" in raw else [])
    df = raw[cols].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.apply(pd.to_numeric, errors="coerce").dropna(subset=needed)
    df["Turnover"] = df["Close"] * df["Volume"]
    return df, datetime.now(), source

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    for n in [5, 20, 60, 120]:
        x[f"MA{n}"] = x["Close"].rolling(n).mean()
    delta = x["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    x["RSI14"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    ema12 = x["Close"].ewm(span=12, adjust=False).mean()
    ema26 = x["Close"].ewm(span=26, adjust=False).mean()
    x["MACD"] = ema12 - ema26
    x["MACD_Signal"] = x["MACD"].ewm(span=9, adjust=False).mean()
    x["MACD_Hist"] = x["MACD"] - x["MACD_Signal"]
    x["Volume_MA20"] = x["Volume"].rolling(20).mean()
    x["BB_Mid"] = x["Close"].rolling(20).mean()
    std = x["Close"].rolling(20).std(ddof=0)
    x["BB_Upper"] = x["BB_Mid"] + 2 * std
    x["BB_Lower"] = x["BB_Mid"] - 2 * std
    prev_close = x["Close"].shift(1)
    tr = pd.concat([x["High"] - x["Low"], (x["High"] - prev_close).abs(), (x["Low"] - prev_close).abs()], axis=1).max(axis=1)
    x["ATR14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return x

def verdict(x: pd.DataFrame) -> tuple[str, float, list[str]]:
    y = x.dropna().iloc[-2:]
    r, p = y.iloc[-1], y.iloc[-2]
    score, reasons = 0.0, []
    trend = 1 if r.Close > r.MA20 > r.MA60 else (-1 if r.Close < r.MA20 < r.MA60 else 0)
    score += trend * RULE_WEIGHTS["trend"]
    reasons.append(f"추세: {'상승' if trend == 1 else '하락' if trend == -1 else '혼조'}")
    macd = 1 if r.MACD > r.MACD_Signal and r.MACD_Hist > p.MACD_Hist else (-1 if r.MACD < r.MACD_Signal and r.MACD_Hist < p.MACD_Hist else 0)
    rsi = 1 if 40 <= r.RSI14 <= 65 and r.RSI14 > p.RSI14 else (-1 if r.RSI14 >= 70 or (r.RSI14 < 45 and r.RSI14 < p.RSI14) else 0)
    score += (macd + rsi) * RULE_WEIGHTS["momentum"] / 2
    reasons.append(f"모멘텀: MACD {'개선' if macd == 1 else '악화' if macd == -1 else '중립'}, RSI {r.RSI14:.1f}")
    vol = 1 if r.Close > p.Close and r.Volume > r.Volume_MA20 else (-1 if r.Close < p.Close and r.Volume > r.Volume_MA20 else 0)
    score += vol * RULE_WEIGHTS["volume"]
    reasons.append(f"거래량: 20일 평균 대비 {r.Volume / r.Volume_MA20:.2f}배")
    structure = 1 if r.Close > r.BB_Mid and r.Close > p.Close else (-1 if r.Close < r.BB_Mid and r.Close < p.Close else 0)
    score += structure * RULE_WEIGHTS["structure"]
    reasons.append(f"가격 구조: 볼린저 중단 {'상회' if structure == 1 else '하회' if structure == -1 else '혼조'}")
    return ("매수 판단" if score >= 3.5 else "매도 판단" if score <= -3.5 else "관망"), round(score, 2), reasons

def signal_level(label: str, score: float) -> str:
    if label == "관망":
        return "상" if abs(score) <= 1.0 else "중" if abs(score) <= 2.5 else "하"
    strength = abs(score)
    return "상" if strength >= 5.0 else "중" if strength >= 3.5 else "하"

def signal_comment(label: str, level: str) -> str:
    """판단 카드의 등급을 실제 행동 관점에서 짧게 설명합니다."""
    if label == "관망":
        if level == "상":
            return "매수 쪽으로 기울었다는 뜻이 아닙니다. 신규 매수·매도 모두 서두르지 말고 방향이 확인될 때까지 관망하세요."
        if level == "중":
            return "신호가 섞여 있습니다. 보유자는 추세를 확인하고, 신규 매수는 작은 비중으로도 서두르지 않는 편이 안전합니다."
        return "매수·매도 신호가 크게 충돌합니다. 신규 매수와 추가 매수는 피하고, 변동성이 안정될 때까지 관망하세요."
    if label == "매수 판단":
        return "여러 지표가 매수 쪽으로 같은 방향을 보인다는 뜻입니다. 그래도 한 번에 전액 매수하지 말고 분할 검토하세요."
    return "여러 지표가 매도 쪽으로 같은 방향을 보인다는 뜻입니다. 보유자는 비중 축소를 검토하되, 신규 공매도를 의미하지는 않습니다."

def price_chart(x: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Candlestick(x=x.index, open=x.Open, high=x.High, low=x.Low, close=x.Close, name="가격"))
    for n, color in [(5, "#f59e0b"), (20, "#2563eb"), (60, "#16a34a"), (120, "#9333ea")]:
        fig.add_trace(go.Scatter(x=x.index, y=x[f"MA{n}"], name=f"MA{n}", line={"color": color, "width": 1.4}))
    fig.update_layout(height=520, xaxis_rangeslider_visible=False, legend_orientation="h", margin=dict(l=10, r=10, t=20, b=10))
    return fig

st.markdown("""
<div class="hero">
  <span class="hero-badge">KOREAN STOCK INSIGHT</span>
  <h1>한국 주식 타이밍 분석</h1>
  <p>실제 시장 데이터를 바탕으로 주요 지표와 흐름을 간결하게 확인하세요.</p>
</div>
""", unsafe_allow_html=True)
st.markdown('<div class="search-label">분석할 종목을 검색하세요</div>', unsafe_allow_html=True)
query = st.text_input("종목명 또는 6자리 종목코드", value="삼성전자", placeholder="예: 삼성전자 또는 005930")
run_analysis = st.button("분석 실행", type="primary", use_container_width=True)

if run_analysis or query:
    try:
        universe = load_universe()
        ticker, display_name, market = resolve_ticker(query, universe)
        data, fetched_at, data_source = load_data(ticker)
        x = add_indicators(data)
        label, score, reasons = verdict(x)
        recent = x.tail(252)
        st.markdown(f'<div class="status"><strong>{display_name}</strong> · {ticker} · {market} · 전체 {len(universe):,}개 종목 검색 가능 · 분석 기간 {data.index.min().date()} ~ {data.index.max().date()} · 자료원 {data_source}</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-title">QUICK SUMMARY</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        last = x.iloc[-1]
        c1.metric("최종 판단", f"{label} · {signal_level(label, score)}")
        c2.metric("규칙 점수", f"{score:+.2f}")
        c3.metric("최근 종가", f"{last.Close:,.0f}원")
        c4.metric("RSI(14)", f"{last.RSI14:.1f}")
        level = signal_level(label, score)
        st.markdown(f'<div class="verdict-note"><strong>주석:</strong> {signal_comment(label, level)}</div>', unsafe_allow_html=True)
        tab2, tab3, tab4 = st.tabs(["기간별 구조", "판단 근거", "출처·조건"])
        with tab2:
            rows = []
            for name, n in [("단기", 20), ("중기", 60), ("장기", 120), ("12개월", min(252, len(x)))]:
                z = x.tail(n)
                rows.append({"관점": name, "고점": z.High.max(), "저점": z.Low.min(), "최근 고점 대비 하락률": last.Close / z.High.max() - 1, "최근 저점 대비 반등률": last.Close / z.Low.min() - 1})
            st.dataframe(pd.DataFrame(rows).style.format({"고점": "{:,.0f}", "저점": "{:,.0f}", "최근 고점 대비 하락률": "{:.2%}", "최근 저점 대비 반등률": "{:.2%}"}), use_container_width=True)
            st.info("지지선·저항선은 각 기간의 저점·고점을 후보로 표시한 단순 기준입니다.")
        with tab3:
            st.write("점수 기여 요약")
            for reason in reasons:
                st.write(f"- {reason}")
            st.warning("가중치와 임계값은 초기 실험값입니다. 과거 데이터에 맞춘 반복 조정은 과최적화를 일으킬 수 있습니다. 백테스트 기능은 다음 단계에서 추가합니다.")
        with tab4:
            st.write(f"- 실제 사용 자료원: {data_source}")
            st.write("- 우선 조회 주소: https://finance.yahoo.com/ · 대체 조회: FinanceDataReader 국내 데이터 제공 경로")
            st.write(f"- 조회 시각: {fetched_at.strftime('%Y-%m-%d %H:%M:%S')} (실행 PC 시간)")
            st.write("- 데이터: 일봉 OHLCV 및 가능할 경우 수정주가(Adj Close), 약 5년 요청")
            st.write("- 지연·이용 조건: 무료 보조 데이터이며 공식 KRX 실시간/보장 API가 아닙니다. 지연·누락·수정 가능성이 있고 Yahoo Finance 이용약관과 제공 한도를 따라야 합니다.")
            st.write("- KRX 대조: 종목 목록은 KRX 목록 조회를 사용하며, 가격은 Yahoo 우선·실패 시 국내 대체 경로를 사용합니다.")
            st.info("KRX Open API는 공식 일별매매정보를 제공하지만 인증키 신청이 필요합니다. 키 발급 후 공식 소스를 우선 사용하도록 연결할 수 있습니다.")
        st.download_button("분석 데이터 CSV 저장", x.to_csv(index=True).encode("utf-8-sig"), file_name=f"{ticker.replace('.', '_')}_analysis.csv", mime="text/csv")
        st.markdown('<div class="footer-note">교육·검증용 분석 도구 · 투자 권유가 아니며 실제 주문 기능은 포함하지 않습니다.</div>', unsafe_allow_html=True)
    except Exception as exc:
        st.error(f"데이터를 가져오지 못했습니다: {exc}")
        st.info("임의의 가격 데이터는 사용하지 않았습니다. 인터넷 연결, 종목코드(예: 005930), 데이터 제공처 응답 상태를 확인하세요.")

