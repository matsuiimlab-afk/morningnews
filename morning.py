import os
import requests
import yfinance as yf
import feedparser
from datetime import datetime
import pytz
import google.generativeai as genai

# ── 環境変数 ──────────────────────────────────────────
LINE_TOKEN  = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER   = os.environ["LINE_USER_ID"]
GEMINI_KEY  = os.environ["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_KEY)

JST = pytz.timezone("Asia/Tokyo")
today = datetime.now(JST).strftime("%Y年%m月%d日 (%a)")

# ── 1. 天気（東京・摂氏）──────────────────────────────
def get_weather():
    try:
        # m=メートル法(℃), format=j1はJSON形式で取得
        r = requests.get(
            "https://wttr.in/Tokyo?format=%l:+%C+%t+%h湿度+%w風&m",
            timeout=10,
            headers={"Accept-Language": "ja"}
        )
        return r.text.strip()
    except Exception as e:
        return f"天気取得エラー: {e}"

# ── 2. 株価・為替・金────────────────────────────────────
def get_market():
    # 金以外のシンボル
    symbols = {
        "NTT (9432)":        "9432.T",
        "SoftBank (9434)":   "9434.T",
        "日経225":            "^N225",
        "USD/JPY":           "USDJPY=X",
    }
    lines = []

    for label, sym in symbols.items():
        try:
            t = yf.Ticker(sym)
            h = t.history(period="2d")
            if len(h) >= 2:
                prev  = h["Close"].iloc[-2]
                curr  = h["Close"].iloc[-1]
                diff  = curr - prev
                pct   = diff / prev * 100
                arrow = "▲" if diff >= 0 else "▼"
                lines.append(f"{label}: {curr:,.2f} {arrow}{abs(pct):.2f}%")
            elif len(h) == 1:
                curr = h["Close"].iloc[-1]
                lines.append(f"{label}: {curr:,.2f}")
        except Exception:
            lines.append(f"{label}: 取得エラー")

    # 金価格: GC=F(USD/トロイオンス) → 円/g 換算
    # 1トロイオンス = 31.1035g
    try:
        gc = yf.Ticker("GC=F")
        fx = yf.Ticker("USDJPY=X")
        gc_h = gc.history(period="2d")
        fx_h = fx.history(period="2d")

        if len(gc_h) >= 1 and len(fx_h) >= 1:
            gold_usd_oz = gc_h["Close"].iloc[-1]   # USD/トロイオンス
            usdjpy      = fx_h["Close"].iloc[-1]    # 円/USD
            gold_jpy_g  = gold_usd_oz * usdjpy / 31.1035  # 円/g

            if len(gc_h) >= 2:
                prev_usd = gc_h["Close"].iloc[-2]
                prev_jpy_g = prev_usd * usdjpy / 31.1035
                pct  = (gold_jpy_g - prev_jpy_g) / prev_jpy_g * 100
                arrow = "▲" if pct >= 0 else "▼"
                lines.append(f"金 (円/g): {gold_jpy_g:,.0f} {arrow}{abs(pct):.2f}%")
            else:
                lines.append(f"金 (円/g): {gold_jpy_g:,.0f}")
        else:
            lines.append("金 (円/g): 取得エラー")
    except Exception as e:
        lines.append(f"金 (円/g): 取得エラー ({e})")

    return "\n".join(lines)

# ── 3. RSSニュース取得（汎用）────────────────────────────
def fetch_rss(url, max_items=10):
    try:
        feed = feedparser.parse(url)
        items = [f"・{entry.title}" for entry in feed.entries[:max_items]]
        return "\n".join(items) if items else "記事なし"
    except Exception as e:
        return f"RSS取得エラー: {e}"

def get_news():
    url = "https://news.google.com/rss/search?q=%E6%97%A5%E6%9C%AC+%E7%B5%8C%E6%B8%88+%E6%94%BF%E6%B2%BB&hl=ja&gl=JP&ceid=JP:ja"
    return fetch_rss(url)

def get_ai_news():
    url = "https://news.google.com/rss/search?q=AI+%E4%BA%BA%E5%B7%A5%E7%9F%A5%E8%83%BD+%E6%9C%80%E6%96%B0&hl=ja&gl=JP&ceid=JP:ja"
    return fetch_rss(url)

def get_astronomy():
    url = "https://news.google.com/rss/search?q=%E5%AE%87%E5%AE%99+%E5%A4%A9%E6%96%87+NASA&hl=ja&gl=JP&ceid=JP:ja"
    return fetch_rss(url, 3)

# ── 4. Gemini で整形────────────────────────────────────
def summarize_with_gemini(weather, market, news, ai_news, astro):
    prompt = f"""
あなたは毎朝のモーニングブリーフィングアシスタントです。
以下の情報をLINEメッセージとして整形してください。

【条件】
- 絵文字を適度に使って見やすく
- 各セクションは短くコンパクトに
- 全体で1500文字以内に収める
- 余計な前置き・後書き不要、本文だけ出力

【日付】{today}

【天気】
{weather}

【マーケット】
{market}

【国内ニュース】
{news}

【AI動向】
{ai_news}

【宇宙・天文】
{astro}
"""
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    return response.text.strip()

# ── 5. LINE送信────────────────────────────────────────
def send_line(text):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "to": LINE_USER,
        "messages": [{"type": "text", "text": text}]
    }
    r = requests.post(url, headers=headers, json=payload)
    print(f"LINE status: {r.status_code}")
    if r.status_code != 200:
        print(r.text)
    return r.status_code

# ── メイン────────────────────────────────────────────
def main():
    print(f"[{today}] モーニングブリーフィング開始")

    weather = get_weather()
    print(f"天気: {weather}")

    market = get_market()
    print(f"マーケット:\n{market}")

    news    = get_news()
    ai_news = get_ai_news()
    astro   = get_astronomy()

    message = summarize_with_gemini(weather, market, news, ai_news, astro)
    print(f"--- 送信メッセージ ---\n{message}\n---")

    status = send_line(message)
    print(f"完了 (status={status})")

if __name__ == "__main__":
    main()