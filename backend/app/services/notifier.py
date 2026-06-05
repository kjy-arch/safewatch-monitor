import smtplib
from io import BytesIO
from datetime import date, datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.core.config import settings
from app.core.database import supabase


# ── 엑셀 생성 ─────────────────────────────────────────────
LEVEL_COLORS = {"높음": "FFCCCC", "중간": "FFF2CC", "낮음": "CCFFCC"}

COLUMNS = [
    ("번호",     5),
    ("출처",     8),
    ("게시일",   14),
    ("거짓점수", 9),
    ("거짓척도", 8),
    ("의도유형", 12),
    ("내용유형", 12),
    ("판단이유", 30),
    ("소관부서", 14),
    ("원문",     50),
    ("링크",     30),
    ("대응상태", 10),
]


def _build_excel(articles: list) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "수집결과"

    today_str = date.today().strftime("%Y년 %m월 %d일")
    ws.merge_cells("A1:L1")
    title_cell = ws["A1"]
    title_cell.value = f"SafeWatch Monitor 수집 결과 — {today_str}"
    title_cell.font = Font(bold=True, size=13, color="FFFFFF")
    title_cell.fill = PatternFill("solid", fgColor="1F4E79")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # 헤더
    thin = Side(style="thin", color="AAAAAA")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for col_idx, (col_name, col_width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=col_name)
        cell.font      = Font(bold=True, color="FFFFFF", size=10)
        cell.fill      = PatternFill("solid", fgColor="2E75B6")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = border
        ws.column_dimensions[get_column_letter(col_idx)].width = col_width
    ws.row_dimensions[2].height = 22

    # 데이터
    for row_num, a in enumerate(articles, start=3):
        dept = (a.get("departments") or {}).get("name", "") if isinstance(a.get("departments"), dict) else ""
        pub  = a.get("published_at", "")[:16].replace("T", " ") if a.get("published_at") else ""
        level = a.get("false_level") or "미분류"
        bg    = LEVEL_COLORS.get(level, "FFFFFF")

        row_data = [
            row_num - 2,
            a.get("source_type", ""),
            pub,
            a.get("false_score", ""),
            level,
            a.get("intent_type", ""),
            a.get("content_type", ""),
            a.get("false_reason", ""),
            dept,
            (a.get("content") or a.get("title") or "")[:200],
            a.get("url", ""),
            a.get("response_status", "미확인"),
        ]

        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=value)
            cell.fill      = PatternFill("solid", fgColor=bg)
            cell.alignment = Alignment(vertical="top", wrap_text=(col_idx in (9, 10)))
            cell.border    = border
            cell.font      = Font(size=9)
            if col_idx == 3:
                cell.alignment = Alignment(horizontal="center", vertical="top")
            if col_idx == 4:
                cell.alignment = Alignment(horizontal="center", vertical="top")

    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:L{len(articles) + 2}"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── 통계 요약 ─────────────────────────────────────────────
def _summary_html(articles: list, today_str: str) -> str:
    total   = len(articles)
    high    = sum(1 for a in articles if a.get("false_level") == "높음")
    mid     = sum(1 for a in articles if a.get("false_level") == "중간")
    low     = sum(1 for a in articles if a.get("false_level") == "낮음")
    unclf   = total - high - mid - low

    by_src  = {}
    for a in articles:
        s = a.get("source_type", "기타")
        by_src[s] = by_src.get(s, 0) + 1

    src_rows = "".join(
        f"<tr><td style='padding:4px 12px'>{k}</td><td style='padding:4px 12px;text-align:center'>{v}건</td></tr>"
        for k, v in sorted(by_src.items(), key=lambda x: -x[1])
    )

    return f"""
<html><body style="font-family:'맑은 고딕',sans-serif;color:#333">
<div style="max-width:600px;margin:0 auto">

  <div style="background:#1F4E79;color:white;padding:20px;border-radius:8px 8px 0 0">
    <h2 style="margin:0;font-size:18px">📡 SafeWatch Monitor 일일 수집 결과</h2>
    <p style="margin:4px 0 0;font-size:13px;opacity:.85">{today_str} 수집분 — 첨부 엑셀 파일 참조</p>
  </div>

  <div style="background:#f8f9fa;padding:20px;border:1px solid #dee2e6">

    <h3 style="color:#1F4E79;margin-top:0">📊 오늘의 수집 요약</h3>
    <table style="width:100%;border-collapse:collapse">
      <tr>
        <td style="padding:10px;text-align:center;background:#fff;border-radius:6px;border:1px solid #dee2e6;width:25%">
          <div style="font-size:28px;font-weight:bold;color:#1F4E79">{total}</div>
          <div style="font-size:12px;color:#666">전체 수집</div>
        </td>
        <td style="width:4%"></td>
        <td style="padding:10px;text-align:center;background:#FFCCCC;border-radius:6px;border:1px solid #FFAAAA;width:20%">
          <div style="font-size:24px;font-weight:bold;color:#CC0000">{high}</div>
          <div style="font-size:12px;color:#CC0000">높음</div>
        </td>
        <td style="width:2%"></td>
        <td style="padding:10px;text-align:center;background:#FFF2CC;border-radius:6px;border:1px solid #FFDD99;width:20%">
          <div style="font-size:24px;font-weight:bold;color:#996600">{mid}</div>
          <div style="font-size:12px;color:#996600">중간</div>
        </td>
        <td style="width:2%"></td>
        <td style="padding:10px;text-align:center;background:#CCFFCC;border-radius:6px;border:1px solid #99DD99;width:20%">
          <div style="font-size:24px;font-weight:bold;color:#006600">{low}</div>
          <div style="font-size:12px;color:#006600">낮음</div>
        </td>
      </tr>
    </table>

    <h3 style="color:#1F4E79;margin-top:20px">📂 출처별 수집 현황</h3>
    <table style="width:100%;border-collapse:collapse;background:white;border:1px solid #dee2e6;border-radius:6px">
      {src_rows}
    </table>

    {"<div style='margin-top:16px;padding:12px;background:#FFEEEE;border-left:4px solid #CC0000;border-radius:4px'><strong style='color:#CC0000'>⚠️ 긴급 주의</strong> — 거짓척도 <strong>높음</strong> {high}건이 탐지되었습니다. 첨부 파일의 붉은 행을 우선 확인하세요.</div>" if high > 0 else ""}

    <div style="margin-top:16px;padding:12px;background:#E8F0FB;border-radius:4px;font-size:12px;color:#555">
      📎 첨부 엑셀 파일에 전체 수집 결과가 포함되어 있습니다.<br>
      컬럼: 출처 / 게시일 / 거짓점수 / 척도 / 의도유형 / 내용유형 / 판단이유 / 소관부서 / 링크 / 대응상태
    </div>
  </div>

  <div style="background:#f1f3f5;padding:10px;text-align:center;font-size:11px;color:#999;border-radius:0 0 8px 8px">
    SafeWatch Monitor · 병무청 정보기획과
  </div>
</div>
</body></html>"""


# ── 발송 메인 ─────────────────────────────────────────────
def send_alerts():
    """당일 수집된 전체 기사를 엑셀 첨부로 이메일 발송."""
    recipients = (
        supabase.table("alert_settings")
        .select("email")
        .eq("is_active", True)
        .execute()
        .data
    )
    if not recipients:
        return

    # 오늘 수집분 전체
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(hours=9)  # KST 00:00 → UTC

    articles = (
        supabase.table("crawled_articles")
        .select("*, departments(name)")
        .gte("created_at", today_start.isoformat())
        .order("false_score", desc=True)
        .execute()
        .data
    )

    if not articles:
        print("[알림] 오늘 수집된 기사 없음 — 발송 건너뜀")
        return

    today_str   = date.today().strftime("%Y년 %m월 %d일")
    filename    = f"safewatch_{date.today().strftime('%Y%m%d')}.xlsx"
    excel_bytes = _build_excel(articles)
    html_body   = _summary_html(articles, today_str)

    for r in recipients:
        try:
            _send(r["email"], f"[SafeWatch] {today_str} 수집 결과",
                  html_body, excel_bytes, filename)
            print(f"[알림] 발송 완료 → {r['email']} ({len(articles)}건)")
        except Exception as e:
            print(f"[알림] 발송 실패 ({r['email']}): {e}")

    # 발송 완료 표시
    ids = [a["id"] for a in articles]
    if ids:
        supabase.table("crawled_articles").update({"alert_sent": True}).in_("id", ids).execute()


def _send(to: str, subject: str, html: str, attachment: bytes, filename: str):
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        print(f"[알림 미발송] SMTP 미설정 — {to} / {filename} ({len(attachment)//1024}KB)")
        return

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = settings.SMTP_USER
    msg["To"]      = to
    msg.attach(MIMEText(html, "html", "utf-8"))

    part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    part.set_payload(attachment)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
