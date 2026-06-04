import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
from app.core.database import supabase


def send_alerts():
    """높음 판정 + 알림 미발송 기사 → 수신자에게 이메일 발송."""
    recipients = (
        supabase.table("alert_settings")
        .select("email, min_score")
        .eq("is_active", True)
        .execute()
        .data
    )
    if not recipients:
        return

    articles = (
        supabase.table("crawled_articles")
        .select("id, title, content, url, false_score, false_level, false_reason, source_type")
        .eq("alert_sent", False)
        .gte("false_score", 67)
        .order("created_at", desc=True)
        .limit(20)
        .execute()
        .data
    )
    if not articles:
        return

    for recipient in recipients:
        filtered = [a for a in articles if (a["false_score"] or 0) >= recipient["min_score"]]
        if not filtered:
            continue

        try:
            _send_email(recipient["email"], filtered)
            for a in filtered:
                supabase.table("crawled_articles").update({"alert_sent": True}).eq("id", a["id"]).execute()
        except Exception as e:
            print(f"알림 발송 실패 ({recipient['email']}): {e}")


def _send_email(to_email: str, articles: list):
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        print(f"[알림 미발송] SMTP 미설정 — {to_email}에게 보낼 기사 {len(articles)}건")
        return

    subject = f"[SafeWatch] 허위성 높음 탐지 {len(articles)}건"

    rows = ""
    for a in articles:
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee">{a.get('source_type','')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">
            <a href="{a.get('url','')}">{a.get('title','') or a.get('content','')[:50]}</a>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:red;font-weight:bold">{a.get('false_score','')}점</td>
          <td style="padding:8px;border-bottom:1px solid #eee">{a.get('false_reason','')}</td>
        </tr>"""

    body = f"""
    <html><body>
    <h2 style="color:#1F4E79">SafeWatch Monitor 알림</h2>
    <p>허위성 높음으로 분류된 콘텐츠 <strong>{len(articles)}건</strong>이 탐지되었습니다.</p>
    <table style="border-collapse:collapse;width:100%">
      <tr style="background:#1F4E79;color:white">
        <th style="padding:8px">출처</th>
        <th style="padding:8px">내용</th>
        <th style="padding:8px">점수</th>
        <th style="padding:8px">판단이유</th>
      </tr>
      {rows}
    </table>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = settings.SMTP_USER
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "html", "utf-8"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
