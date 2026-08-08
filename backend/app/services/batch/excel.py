import pandas as pd
import openpyxl
from io import BytesIO
from typing import List, Dict, Any
from zipfile import BadZipFile, ZipFile
from app.services.excel_safety import sanitize_workbook


VALID_SOURCE_TYPES = {"언론", "SNS", "커뮤니티", "유튜브"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DATA_ROWS = 1000

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


def _validate_xlsx_container(file_bytes: bytes) -> None:
    """이름만 .xlsx인 파일과 과도하게 압축된 파일을 파싱 전에 거부한다."""
    try:
        with ZipFile(BytesIO(file_bytes)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
                raise ValueError("유효한 .xlsx 파일이 아닙니다.")
            uncompressed_size = sum(info.file_size for info in archive.infolist())
            if uncompressed_size > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("압축을 푼 엑셀 파일 크기는 50MB 이하여야 합니다.")
    except BadZipFile as e:
        raise ValueError("유효한 .xlsx 파일이 아닙니다.") from e


def parse_excel(file_bytes: bytes, max_rows: int = MAX_DATA_ROWS) -> List[Dict[str, Any]]:
    if not file_bytes:
        raise ValueError("빈 파일은 업로드할 수 없습니다.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError("파일 크기는 10MB 이하여야 합니다.")
    _validate_xlsx_container(file_bytes)

    try:
        df = _read_with_header_detection(file_bytes)
    except Exception as e:
        raise ValueError("유효한 .xlsx 파일이 아닙니다.") from e
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
        if len(rows) > max_rows:
            raise ValueError(f"분석할 데이터는 최대 {max_rows:,}행까지 업로드할 수 있습니다.")

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
        sanitize_workbook(writer.book)
    return buf.getvalue()


def _autofit(ws):
    for col in ws.columns:
        max_len = max((len(str(cell.value or "")) for cell in col), default=0)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)


def _pivot(df, index_col: str, column_col: str):
    """행×열 교차표 (합계 포함)."""
    return pd.crosstab(df[index_col], df[column_col], margins=True, margins_name="합계")


def build_quarterly_excel(articles: List[Dict], dept_map: Dict, period: str) -> bytes:
    """분기 보고서: 부서별·유형별·사이트별·월별·의도유형 집계 다중시트 엑셀.

    부서별 시트는 **복수 부서 매칭(요구 Q4)을 반영해 소관 부서마다 1건씩 계상**한다.
    한 글이 2개 부서에 걸치면 두 부서 모두에서 세어진다("하나의 기사가 여러 부서에
    걸치는 경우가 종종 있습니다"). 그래서 부서별 시트 합계는 총 건수보다 클 수 있어,
    요약 시트에 그 사실을 명시한다. 다른 시트는 글 1건을 1건으로만 센다.
    """
    def base(a):
        return {
            "월":       (a.get("created_at") or "")[:7],
            "분류구분":  a.get("category") or "(미분류)",
            "조치유형":  a.get("action_type") or "(미분류)",
            "거짓척도":  a.get("false_level") or "(미분류)",
            "의도유형":  a.get("intent_type") or "(미분류)",
            "출처":     a.get("source_type") or "(미상)",
            # 수집분/업로드분 구분 — 통합 보고서에서 어느 경로로 들어온 건인지 (Phase 4)
            "구분":     a.get("origin") or "(미상)",
        }

    rows, dept_rows = [], []
    multi = 0
    for a in articles:
        rows.append(base(a))
        ids = [a.get("department_id"), a.get("department_id_2")]
        names = [dept_map.get(i) for i in ids if i]
        names = [n for n in names if n]
        if len(names) > 1:
            multi += 1
        for name in (names or ["(미배정)"]):
            dept_rows.append({**base(a), "부서": name})

    df = pd.DataFrame(rows)
    ddf = pd.DataFrame(dept_rows)

    # 요약 시트 (long-format)
    summary = [["기간", period, ""], ["총 건수", "", len(df)]]
    if multi:
        summary.append(["복수 부서 매칭", f"{multi}건 — 부서별 시트는 부서마다 1건씩 계상", ""])
    if not df.empty:
        for dim in ["구분", "조치유형", "분류구분", "거짓척도", "의도유형", "출처"]:
            for item, cnt in df[dim].value_counts().items():
                summary.append([dim, item, int(cnt)])
    summary_df = pd.DataFrame(summary, columns=["구분", "항목", "건수"])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="요약", index=False)
        if not df.empty:
            _pivot(df, "월", "분류구분").to_excel(writer, sheet_name="월별_분류구분")
            _pivot(ddf, "부서", "분류구분").to_excel(writer, sheet_name="부서별_분류구분")
            _pivot(df, "출처", "분류구분").to_excel(writer, sheet_name="사이트별_분류구분")
            _pivot(ddf, "부서", "조치유형").to_excel(writer, sheet_name="부서별_조치유형")
        for ws in writer.sheets.values():
            _autofit(ws)
        sanitize_workbook(writer.book)
    return buf.getvalue()
