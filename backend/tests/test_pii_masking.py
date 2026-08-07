r"""Gemini 전송 전 개인정보 마스킹 테스트(네트워크·DB 없음).

실행: .venv\Scripts\python.exe tests\test_pii_masking.py
"""

import os
import sys
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for key in ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "GEMINI_API_KEY",
            "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET", "YOUTUBE_API_KEY"):
    os.environ.setdefault(key, "dummy" if "URL" not in key else "https://dummy.supabase.co")

from app.services.pii_masking import mask_pii
import app.services.analyzer as monitor_analyzer
import app.services.batch.analyzer as batch_analyzer


failures = []


def check(name, condition, detail=""):
    print(f"  {'OK  ' if condition else 'FAIL'} {name}" + (f" — {detail}" if not condition and detail else ""))
    if not condition:
        failures.append(name)


print("[명확한 식별자]")
cases = [
    ("전화 010-1234-5678", "전화 [전화번호]"),
    ("연락 02 123 4567", "연락 [전화번호]"),
    ("대표 1588-1234", "대표 [전화번호]"),
    ("메일 user.name+tag@example.co.kr", "메일 [이메일]"),
    ("주민번호 900101-1234567", "주민번호 [주민등록번호]"),
    ("계좌 110-123-456789", "계좌 [계좌번호]"),
    ("입금계좌: 123456789012", "입금계좌: [계좌번호]"),
]
for original, expected in cases:
    check(original, mask_pii(original) == expected, f"got {mask_pii(original)!r}")

print("\n[복합·경계 사례]")
combined = mask_pii("010.1234.5678 / a@b.kr / 900101 2234567 / 123 456 789012")
for marker in ("[전화번호]", "[이메일]", "[주민등록번호]", "[계좌번호]"):
    check(f"복합 입력에 {marker}", marker in combined, combined)

unchanged = [
    "기준일 2026-08-07",
    "거짓점수 67-100점",
    "문서번호 1234567890",  # 계좌 문맥 없는 연속 숫자는 오탐 방지를 위해 유지
    "병무청 상담 안내를 확인하세요",
]
for value in unchanged:
    check(f"오탐 방지: {value}", mask_pii(value) == value, f"got {mask_pii(value)!r}")


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text="{}")


print("\n[수집·2차 검증 공통 Gemini 경로]")
monitor_models = FakeModels()
saved_monitor_client = monitor_analyzer.client
monitor_analyzer.client = SimpleNamespace(models=monitor_models)
try:
    monitor_analyzer._analyze(
        "문의 010-1111-2222",
        "이메일 a@b.kr 주민번호 900101-1234567",
        "지식인",
        [{"name": "담당부서 02-123-4567"}],
    )
finally:
    monitor_analyzer.client = saved_monitor_client

monitor_call = monitor_models.calls[0]
monitor_payload = monitor_call["contents"] + "\n" + monitor_call["config"].system_instruction
check("수집 프롬프트 전화 마스킹", "010-1111-2222" not in monitor_payload and "[전화번호]" in monitor_payload)
check("수집 프롬프트 이메일 마스킹", "a@b.kr" not in monitor_payload and "[이메일]" in monitor_payload)
check("수집 프롬프트 주민번호 마스킹", "900101-1234567" not in monitor_payload and "[주민등록번호]" in monitor_payload)
check("동적 부서 목록도 마스킹", "02-123-4567" not in monitor_payload)

print("\n[엑셀 배치 Gemini 경로]")
batch_models = FakeModels()
saved_batch_client = batch_analyzer.client
saved_find_docs = batch_analyzer.find_relevant_docs
batch_analyzer.client = SimpleNamespace(models=batch_models)
batch_analyzer.find_relevant_docs = lambda _text: ["공식자료 연락처 02-999-8888"]
try:
    batch_analyzer._analyze_single(
        "문의 010-3333-4444, 계좌 110-123-456789",
        "커뮤니티",
        [{"name": "부서", "keywords": ["contact@example.kr"]}],
    )
finally:
    batch_analyzer.client = saved_batch_client
    batch_analyzer.find_relevant_docs = saved_find_docs

batch_payload = batch_models.calls[0]["contents"]
for raw in ("010-3333-4444", "110-123-456789", "contact@example.kr", "02-999-8888"):
    check(f"배치 프롬프트 원문 제거: {raw}", raw not in batch_payload, batch_payload)
for marker in ("[전화번호]", "[계좌번호]", "[이메일]"):
    check(f"배치 프롬프트에 {marker}", marker in batch_payload, batch_payload)

print()
if failures:
    print(f"FAILED ({len(failures)}): {failures}")
    sys.exit(1)
print("ALL TESTS PASSED")
