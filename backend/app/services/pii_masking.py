"""Gemini 전송 직전에 명확한 개인 식별자 형태를 최소 범위로 마스킹한다."""

import re


EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
RRN_RE = re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")
PHONE_RE = re.compile(
    r"(?<!\d)(?:0(?:1[016789]|2|[3-8]\d)[-.\s]?\d{3,4}[-.\s]?\d{4}|1[5-8]\d{2}[-.\s]?\d{4})(?!\d)"
)
SEPARATED_ACCOUNT_RE = re.compile(r"(?<!\d)(?:\d{2,6}[- ]+){2,4}\d{1,6}(?!\d)")
CONTEXT_ACCOUNT_RE = re.compile(
    r"(?P<label>(?:계좌(?:번호)?|입금\s*계좌)\s*[:：]?\s*)(?P<number>\d{10,16})(?!\d)"
)


def _mask_separated_account(match: re.Match) -> str:
    value = match.group(0)
    digit_count = sum(ch.isdigit() for ch in value)
    return "[계좌번호]" if 10 <= digit_count <= 16 else value


def mask_pii(text: str) -> str:
    """전화·이메일·주민등록번호·계좌번호 형태를 고정 표식으로 바꾼다.

    계좌번호는 날짜·점수·일련번호 오탐을 줄이기 위해 여러 구간으로 나뉜 번호 또는
    '계좌/계좌번호/입금계좌' 문맥 뒤의 10~16자리 숫자만 마스킹한다.
    """
    if not text:
        return text or ""

    masked = EMAIL_RE.sub("[이메일]", text)
    masked = RRN_RE.sub("[주민등록번호]", masked)
    masked = PHONE_RE.sub("[전화번호]", masked)
    masked = SEPARATED_ACCOUNT_RE.sub(_mask_separated_account, masked)
    masked = CONTEXT_ACCOUNT_RE.sub(
        lambda match: f"{match.group('label')}[계좌번호]",
        masked,
    )
    return masked
