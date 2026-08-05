import pandas as pd
import openpyxl
from io import BytesIO
from typing import List, Dict, Any


VALID_SOURCE_TYPES = {"언론", "SNS", "커뮤니티", "유튜브"}

# 컬럼명 자동 인식 매핑 (한글/영문 모두 지원)
#
# ⚠️ TEXT_ALIASES는 **순서가 곧 우선순위**라서 튜플이어야 한다. set으로 두면 순회 순서가
#   임의라, 제목·내용이 모두 있는 엑셀에서 짧은 '제목'이 원문으로 선택돼 본문이 통째로
#   분류에서 빠지는 일이 생긴다(실제로 발생). 본문 계열을 앞에, 제목은 최후순위에 둔다.
TEXT_ALIASES = (
    "원문", "내용", "내 용", "본문", "text", "텍스트", "기사내용", "기사본문",
    "게시글", "게시내용", "댓글", "내용물",
    "제목", "타이틀", "title",   # 본문 열이 전혀 없을 때만 쓰는 최후 수단
)
SOURCE_TYPE_ALIASES = (
    "source_type", "출처", "출처유형", "유형", "구분", "type", "분류",
)
SOURCE_URL_ALIASES = (
    "source_url", "url", "링크", "주소", "출처링크", "기사링크", "원문링크",
)


def _find_col(columns, aliases):
    """컬럼명 목록에서 aliases를 **앞에서부터** 찾아 먼저 맞는 컬럼명 반환."""
    cols_lower = {c.strip().lower(): c for c in columns}
    for alias in aliases:
        if alias.lower() in cols_lower:
            return cols_lower[alias.lower()]
    return None


def _looks_like_header(values) -> bool:
    """행의 값들이 헤더처럼 보이는지 — 인식 가능한 별칭이 하나라도 있으면 헤더."""
    known = set(TEXT_ALIASES) | set(SOURCE_TYPE_ALIASES) | set(SOURCE_URL_ALIASES)
    return any(str(v).strip().lower() in known for v in values if str(v).strip())


def _read_with_header_detection(file_bytes: bytes, max_scan: int = 5) -> pd.DataFrame:
    """상단 제목행(예: 'SafeWatch Monitor 수집 결과 — ...')을 건너뛰고 진짜 헤더 행을 찾아 읽는다.

    Monitor 산출 엑셀처럼 1행이 제목이면 pandas가 그것을 헤더로 잡아 컬럼이 Unnamed:N이 되고,
    컬럼 인식이 실패해 엉뚱한 열(번호 등)을 원문으로 쓰게 되므로 헤더 위치를 탐지한다.
    """
    raw = pd.read_excel(BytesIO(file_bytes), dtype=str, header=None).fillna("")
    for i in range(min(max_scan, len(raw))):
        if _looks_like_header(raw.iloc[i].tolist()):
            df = raw.iloc[i + 1:].copy()
            df.columns = [str(c).strip() for c in raw.iloc[i].tolist()]
            return df.reset_index(drop=True)
    # 헤더를 못 찾으면 기존 동작(첫 행을 헤더로) 유지
    return pd.read_excel(BytesIO(file_bytes), dtype=str).fillna("")


def parse_excel(file_bytes: bytes) -> List[Dict[str, Any]]:
    df = _read_with_header_detection(file_bytes)
    df = df.fillna("")

    cols = list(df.columns)

    # 컬럼명 자동 인식
    text_col = _find_col(cols, TEXT_ALIASES)
    source_type_col = _find_col(cols, SOURCE_TYPE_ALIASES)
    source_url_col = _find_col(cols, SOURCE_URL_ALIASES)

    # 인식된 컬럼이 없으면 순서 기반으로 처리 (첫 번째 컬럼 = 원문)
    if not text_col:
        text_col = cols[0] if cols else None

    if not text_col:
        raise ValueError("엑셀에서 텍스트 컬럼을 찾을 수 없습니다.")

    rows = []
    for _, row in df.iterrows():
        text = str(row[text_col]).strip()
        if not text or text == "nan":
            continue

        source_type = str(row[source_type_col]).strip() if source_type_col else "언론"
        if source_type not in VALID_SOURCE_TYPES:
            source_type = "언론"

        source_url = str(row[source_url_col]).strip() if source_url_col else ""

        rows.append({
            "text": text,
            "source_type": source_type,
            "source_url": source_url,
        })

    return rows


def build_result_excel(original_rows: List[Dict], analysis_results: List[Dict]) -> bytes:
    """
    원본 행 + 분석 결과를 합쳐서 엑셀 파일 바이트로 반환.
    """
    records = []
    for row, result in zip(original_rows, analysis_results):
        records.append({
            "원문":           row["text"],
            "출처":           row["source_type"],
            "URL":            row.get("source_url", ""),
            "거짓점수(0-100)": result.get("false_score", ""),
            "거짓척도":        result.get("false_level", ""),
            "분류구분":        result.get("category", ""),
            "조치유형":        result.get("action_type", ""),
            "판단이유":        result.get("false_reason", ""),
            "의도유형":        result.get("intent_type", ""),
            "내용유형":        result.get("content_type", ""),
            "연관부서1":       result.get("department", ""),
            "연관부서2":       result.get("department_2", ""),
        })

    df = pd.DataFrame(records)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="분석결과")
        ws = writer.sheets["분석결과"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)
    return buf.getvalue()


def _autofit(ws):
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)


def _pivot(df, index_col: str, column_col: str):
    """행×열 교차표 (합계 포함)."""
    return pd.crosstab(df[index_col], df[column_col], margins=True, margins_name="합계")


def build_quarterly_excel(articles: List[Dict], dept_map: Dict, period: str) -> bytes:
    """분기 보고서: 부서별·유형별·사이트별·월별·의도유형 집계 다중시트 엑셀."""
    rows = []
    for a in articles:
        d1 = a.get("department_id")
        rows.append({
            "월":       (a.get("created_at") or "")[:7],
            "부서":     dept_map.get(d1, "(미배정)") if d1 else "(미배정)",
            "분류구분":  a.get("category") or "(미분류)",
            "조치유형":  a.get("action_type") or "(미분류)",
            "거짓척도":  a.get("false_level") or "(미분류)",
            "의도유형":  a.get("intent_type") or "(미분류)",
            "출처":     a.get("source_type") or "(미상)",
        })
    df = pd.DataFrame(rows)

    # 요약 시트 (long-format)
    summary = [["기간", period, ""], ["총 건수", "", len(df)]]
    if not df.empty:
        for dim in ["조치유형", "분류구분", "거짓척도", "의도유형", "출처"]:
            for item, cnt in df[dim].value_counts().items():
                summary.append([dim, item, int(cnt)])
    summary_df = pd.DataFrame(summary, columns=["구분", "항목", "건수"])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="요약", index=False)
        if not df.empty:
            _pivot(df, "월", "분류구분").to_excel(writer, sheet_name="월별_분류구분")
            _pivot(df, "부서", "분류구분").to_excel(writer, sheet_name="부서별_분류구분")
            _pivot(df, "출처", "분류구분").to_excel(writer, sheet_name="사이트별_분류구분")
            _pivot(df, "부서", "조치유형").to_excel(writer, sheet_name="부서별_조치유형")
        for ws in writer.sheets.values():
            _autofit(ws)
    return buf.getvalue()
