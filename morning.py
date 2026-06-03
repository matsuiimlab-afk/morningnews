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
    symbols = {
        "NTT (9432)":        "9432.T",
        "SoftBank (9434)":   "9434.T",
        "SoftBank G (9984)": "9984.T",
        "日経225":            "^N225",
        "USD/JPY":           "USDJPY=X",
    }
    lines = []
    usdjpy = None

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
                if sym == "USDJPY=X":
                    usdjpy = curr
            elif len(h) == 1:
                curr = h["Close"].iloc[-1]
                lines.append(f"{label}: {curr:,.2f}")
                if sym == "USDJPY=X":
                    usdjpy = curr
        except Exception:
            lines.append(f"{label}: 取得エラー")

    # 金価格: GC=F(USD/oz) × USDJPY ÷ 31.1035 = 円/g
    try:
        gc_h = yf.Ticker("GC=F").history(period="2d")
        if usdjpy is None:
            fx_h = yf.Ticker("USDJPY=X").history(period="1d")
            usdjpy = fx_h["Close"].iloc[-1] if len(fx_h) >= 1 else 155.0
        if len(gc_h) >= 1:
            gold_usd_oz = gc_h["Close"].iloc[-1]
            gold_jpy_g  = gold_usd_oz * usdjpy / 31.1035
            if len(gc_h) >= 2:
                prev_jpy_g = gc_h["Close"].iloc[-2] * usdjpy / 31.1035
                pct   = (gold_jpy_g - prev_jpy_g) / prev_jpy_g * 100
                arrow = "▲" if pct >= 0 else "▼"
                lines.append(
                    f"金 (円/g): {gold_jpy_g:,.0f} {arrow}{abs(pct):.2f}%"
                    f"  ※({gold_usd_oz:,.0f}USD/oz×{usdjpy:.1f}÷31.1)"
                )
            else:
                lines.append(f"金 (円/g): {gold_jpy_g:,.0f}")
        else:
            lines.append("金 (円/g): 取得エラー")
    except Exception as e:
        lines.append(f"金 (円/g): 取得エラー ({e})")

    return "\n".join(lines)

# ── 3. RSSニュース取得（汎用）────────────────────────────
def fetch_rss(url, label="", max_items=8):
    try:
        feed = feedparser.parse(url)
        items = [f"・{e.title}" for e in feed.entries[:max_items]]
        print(f"  [{label}] {len(feed.entries)}件取得")
        return "\n".join(items) if items else "記事なし"
    except Exception as e:
        return f"RSS取得エラー: {e}"

def get_news():
    # 社会・事件・災害など主要ニュース（過去1日）
    url = (
        "https://news.google.com/rss/search"
        "?q=日本+事件+OR+災害+OR+社会+OR+経済+OR+企業+when:1d"
        "&hl=ja&gl=JP&ceid=JP:ja"
    )
    return fetch_rss(url, "国内ニュース")

def get_ai_news():
    # AI・LLM・生成AI関連（過去3日）
    url = (
        "https://news.google.com/rss/search"
        "?q=生成AI+OR+LLM+OR+ChatGPT+OR+Claude+OR+Gemini+OR+OpenAI+OR+Anthropic+when:3d"
        "&hl=ja&gl=JP&ceid=JP:ja"
    )
    return fetch_rss(url, "AI動向")

def get_robotics():
    # ロボット・自動化関連（過去7日）
    url = (
        "https://news.google.com/rss/search"
        "?q=ロボット+OR+ヒューマノイド+OR+自動化+OR+Tesla+Optimus+when:7d"
        "&hl=ja&gl=JP&ceid=JP:ja"
    )
    return fetch_rss(url, "ロボット", max_items=5)

def get_astronomy():
    # 宇宙・天文（過去7日）
    url = (
        "https://news.google.com/rss/search"
        "?q=宇宙+OR+天文+OR+NASA+OR+JAXA+OR+アルテミス+when:7d"
        "&hl=ja&gl=JP&ceid=JP:ja"
    )
    return fetch_rss(url, "宇宙天文", max_items=4)

# ── 4. Gemini で整形────────────────────────────────────
def summarize_with_gemini(weather, market, news, ai_news, robotics, astro):
    prompt = f"""
あなたは毎朝届く「個人向けモーニングブリーフィング」を作成するアシスタントです。
読者は東京・豊洲在住の個人投資家・フリーランサー（50代男性）です。
興味：AI技術・宇宙・ロボット・株式投資・フリーランス税務

以下の生データをもとに、**読んで実際に役立つ** LINEメッセージを作成してください。

【作成ルール】
- 各セクションは「見出し＋数値/事実＋背景＋今日どう動くか」の構成
- 単なる羅列で終わらせず、背景・理由・示唆を1文添える
- 数字を必ず入れる（株価・気温・変動率など）
- 絵文字で視認性UP（各セクション冒頭に1つ）
- 全体2000文字以内、セクション6つ（天気／マーケット／国内ニュース／AI動向／ロボット／宇宙）
- 各セクションのニュースは渡した件数すべてに触れる（1件に絞らない）

【日付】{today}

【天気】
{weather}

【マーケット】
{market}

【国内ニュース（社会・経済・企業）】
{news}

【AI動向】
{ai_news}

【ロボット・自動化】
{robotics}

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
    print(f"マーケット:\n{market}\n")

    print("RSS取得中...")
    news     = get_news()
    ai_news  = get_ai_news()
    robotics = get_robotics()
    astro    = get_astronomy()

    print(f"\n国内ニュース:\n{news}\n")
    print(f"AI動向:\n{ai_news}\n")
    print(f"ロボット:\n{robotics}\n")
    print(f"宇宙天文:\n{astro}\n")

    message = summarize_with_gemini(weather, market, news, ai_news, robotics, astro)
    print(f"--- 送信メッセージ ---\n{message}\n---")

    status = send_line(message)
    print(f"完了 (status={status})")

if __name__ == "__main__":
    main()