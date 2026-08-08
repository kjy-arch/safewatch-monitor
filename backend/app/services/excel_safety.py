"""외부·사용자 입력을 Excel 셀에 쓸 때 수식으로 해석되지 않게 한다."""

FORMULA_PREFIXES = ("=", "+", "-", "@")
LEADING_WHITESPACE = " \t\r\n"


def safe_excel_value(value):
    """위험한 수식 시작 문자를 가진 문자열을 Excel의 일반 텍스트로 고정한다."""
    if not isinstance(value, str):
        return value
    candidate = value.lstrip(LEADING_WHITESPACE)
    if candidate.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def sanitize_workbook(workbook) -> None:
    """openpyxl workbook의 모든 문자열 셀을 제자리에서 안전하게 변환한다."""
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.value = safe_excel_value(cell.value)
