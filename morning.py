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

# ── 1. 天気（東京）────────────────────────────────────
def get_weather():
    try:
        r = requests.get("https://wttr.in/Tokyo?format=3", timeout=10)
        return r.text.strip()
    except Exception as e:
        return f"天気取得エラー: {e}"

# ── 2. 株価・為替・金────────────────────────────────────
def get_market():
    symbols = {
        "NTT (9432)":       "9432.T",
        "SoftBank (9434)":  "9434.T",
        "SoftBank G (9984)":"9984.T",
        "日経225":           "^N225",
        "USD/JPY":          "USDJPY=X",
        "金(円/g)":          "GC=F",   # USD建て→参考値
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
        except Exception as e:
            lines.append(f"{label}: 取得エラー")
    return "\n".join(lines)

# ── 3. RSSニュース取得（汎用）────────────────────────────
def fetch_rss(url, max_items=4):
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append(f"・{entry.title}")
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

    news = get_news()
    ai_news = get_ai_news()
    astro = get_astronomy()

    message = summarize_with_gemini(weather, market, news, ai_news, astro)
    print(f"--- 送信メッセージ ---\n{message}\n---")

    status = send_line(message)
    print(f"完了 (status={status})")

if __name__ == "__main__":
    main()
