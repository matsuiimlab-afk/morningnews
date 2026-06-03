import os
import sys
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
            headers={"User-Agent": "Mozilla/5.0"}
        )
        return r.text.strip()
    except Exception as e:
        return f"天気取得エラー: {e}"

# ── 2. 株価・為替（金価格なし）───────────────────────────
def get_market():
    symbols = {
        "NTT (9432)":        "9432.T",
        "SoftBank (9434)":   "9434.T",
        "SoftBank G (9984)": "9984.T",
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

    return "\n".join(lines)

# ── 3. RSS取得ユーティリティ──────────────────────────────
def fetch_feed(url):
    """URLからfeedparserオブジェクトを返す。失敗時はNone"""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return feedparser.parse(r.content)
    except Exception as e:
        print(f"  フィード取得失敗 {url}: {e}")
        return None

def entries_to_lines(entries, max_items=10, kw_filter=None):
    """entriesリストから重複排除・キーワードフィルタ済みの行リストを返す"""
    seen = set()
    items = []
    for e in entries:
        title = e.title.strip()
        if title in seen:
            continue
        if kw_filter and not any(k in title for k in kw_filter):
            continue
        seen.add(title)
        items.append(f"・{title}")
        if len(items) >= max_items:
            break
    return items

# ── 4. 各カテゴリ取得──────────────────────────────────
def get_news():
    f1 = fetch_feed("https://www3.nhk.or.jp/rss/news/cat0.xml")  # NHK主要
    f2 = fetch_feed("https://www3.nhk.or.jp/rss/news/cat1.xml")  # NHK社会

    entries = []
    if f1: entries += f1.entries
    if f2: entries += f2.entries

    items = entries_to_lines(entries, max_items=10)
    print(f"  [国内ニュース] {len(items)}件")
    return "\n".join(items) if items else "記事なし"

def get_ai_news():
    f1 = fetch_feed("https://rss.itmedia.co.jp/rss/2.0/aiplus.xml")  # ITmedia AI+
    f2 = fetch_feed("https://gigazine.net/news/rss_2.0/")             # Gigazine

    kw = ["AI", "人工知能", "ChatGPT", "Claude", "Gemini", "OpenAI",
          "Anthropic", "LLM", "生成AI", "機械学習", "深層学習"]

    entries = []
    if f1: entries += f1.entries        # ITmediaは全件対象（AI専門メディア）
    if f2: entries += f2.entries        # GigazineはAIキーワードでフィルタ

    # ITmediaはキーワードフィルタなし、Gigazineはキーワードフィルタあり
    seen = set()
    items = []
    if f1:
        for e in f1.entries:
            title = e.title.strip()
            if title not in seen:
                seen.add(title)
                items.append(f"・{title}")
            if len(items) >= 5:
                break
    if f2:
        for e in f2.entries:
            title = e.title.strip()
            if title in seen:
                continue
            if any(k in title for k in kw):
                seen.add(title)
                items.append(f"・{title}")
            if len(items) >= 8:
                break

    print(f"  [AI動向] {len(items)}件")
    return "\n".join(items) if items else "記事なし"

def get_robotics_and_astronomy():
    """NHK科学とGigazineを1回ずつ取得してロボット・宇宙に振り分け"""
    f_nhk  = fetch_feed("https://www3.nhk.or.jp/rss/news/cat6.xml")
    f_giga = fetch_feed("https://gigazine.net/news/rss_2.0/")

    all_entries = []
    if f_nhk:  all_entries += f_nhk.entries
    if f_giga: all_entries += f_giga.entries

    kw_robot = ["ロボット", "自動化", "自動運転", "ヒューマノイド",
                "Optimus", "ドローン", "drone"]
    kw_astro = ["宇宙", "天文", "NASA", "JAXA", "ロケット", "衛星",
                "惑星", "恒星", "星雲", "銀河", "アルテミス", "探査"]

    robot_items = entries_to_lines(all_entries, max_items=5, kw_filter=kw_robot)
    astro_items = entries_to_lines(all_entries, max_items=4, kw_filter=kw_astro)

    print(f"  [ロボット] {len(robot_items)}件 / [宇宙天文] {len(astro_items)}件")
    robotics = "\n".join(robot_items) if robot_items else "目立った動きなし"
    astro    = "\n".join(astro_items) if astro_items else "目立った動きなし"
    return robotics, astro

# ── 5. Gemini で整形────────────────────────────────────
def summarize_with_gemini(weather, market, news, ai_news, robotics, astro):
    prompt = f"""
あなたは毎朝届く「個人向けモーニングブリーフィング」を作成するアシスタントです。
読者は東京・豊洲在住の個人投資家・フリーランサー（50代男性）です。
興味：AI技術・宇宙・ロボット・株式投資・フリーランス税務

以下の生データをもとに、LINEメッセージを作成してください。

【絶対ルール】
- 渡したニュース見出しは**すべて1行ずつ**触れること。1件に絞って深掘りするのは禁止
- 各ニュースは「タイトル要約 + なぜ重要か1文」の形式で箇条書き
- 株価・気温など数字は必ず入れる
- 絵文字で視認性UP（各セクション冒頭に1つ）
- 全体2000文字以内、セクション6つ（天気／マーケット／国内ニュース／AI動向／ロボット／宇宙）
- マーケットは「数値＋前日比＋一言コメント」形式

【日付】{today}

【天気】
{weather}

【マーケット】
{market}

【国内ニュース（NHK）】
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

# ── 6. LINE送信────────────────────────────────────────
def send_line(text):
    # LINEの1メッセージ上限は5000文字
    MAX = 4800
    if len(text) > MAX:
        text = text[:MAX] + "\n\n…(以下省略)"

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
        print(f"LINE送信失敗: {r.text}")
        sys.exit(1)
    return r.status_code

# ── メイン────────────────────────────────────────────
def main():
    print(f"[{today}] モーニングブリーフィング開始")

    weather = get_weather()
    print(f"天気: {weather}")

    market = get_market()
    print(f"マーケット:\n{market}\n")

    print("RSS取得中...")
    news    = get_news()
    ai_news = get_ai_news()
    robotics, astro = get_robotics_and_astronomy()

    print(f"\n国内ニュース:\n{news}\n")
    print(f"AI動向:\n{ai_news}\n")
    print(f"ロボット:\n{robotics}\n")
    print(f"宇宙天文:\n{astro}\n")

    message = summarize_with_gemini(weather, market, news, ai_news, robotics, astro)
    print(f"--- 送信メッセージ ---\n{message}\n---")

    send_line(message)
    print("完了")

if __name__ == "__main__":
    main()