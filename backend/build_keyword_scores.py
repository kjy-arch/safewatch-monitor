"""키워드.xlsx → 사전 필터용 점수 사전(app/data/keyword_scores.json) 생성.

학습자료의 과목별 빈도 사전에서 병역 맥락 단어에 가중치를 부여한다.
생성 파일은 병무청 내부자료 파생물이므로 git에 커밋하지 않는다 (.gitignore).
→ **PC를 새로 설치할 때마다 이 스크립트를 한 번 돌려야 한다.** 안 돌리면 사전 필터가
  조용히 꺼진 채로 동작해 모든 글이 Gemini로 가고 API 비용이 크게 늘어난다.

사용법 (backend 디렉터리에서):
  .venv\\Scripts\\python.exe build_keyword_scores.py                 # 기본 경로 탐색
  .venv\\Scripts\\python.exe build_keyword_scores.py --xlsx "D:\\자료\\키워드.xlsx"
  set KEYWORD_XLSX=D:\\자료\\키워드.xlsx  &&  ... build_keyword_scores.py

학습자료가 갱신되면 새 키워드.xlsx로 다시 실행하면 된다. 단, 사전이 바뀌면
임계치(keyword_scorer.PREFILTER_THRESHOLD 등)의 근거가 달라지므로
validate_prefilter.py로 재검증할 것.
"""
import sys, json, os, argparse
sys.stdout.reconfigure(encoding="utf-8")
import openpyxl

# 원본 학습자료 위치 — PC마다 다르므로 인자 > 환경변수 > 기본 후보 순으로 찾는다
DEFAULT_XLSX_CANDIDATES = [
    (r"C:\Users\somes\OneDrive\Desktop\전문인재\개별과제"
     r"\2024년 학습자료(도입시)외2_암호화 완료\2024년 학습자료(도입시)외2\키워드.xlsx"),
    os.path.join(os.path.expanduser("~"), "Desktop", "키워드.xlsx"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "키워드.xlsx"),
]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "data", "keyword_scores.json")


def resolve_xlsx(cli_path: str | None) -> str:
    """인자 → 환경변수 → 기본 후보 순으로 키워드.xlsx를 찾는다."""
    for path in [cli_path, os.environ.get("KEYWORD_XLSX"), *DEFAULT_XLSX_CANDIDATES]:
        if path and os.path.isfile(path):
            return path
    print("[오류] 키워드.xlsx를 찾지 못했습니다.\n")
    print("이 파일은 병무청 학습자료라 저장소에 포함되지 않습니다. 아래 중 하나로 지정하세요:")
    print("  1) 인자로 지정   : build_keyword_scores.py --xlsx \"경로\\키워드.xlsx\"")
    print("  2) 환경변수 지정 : set KEYWORD_XLSX=경로\\키워드.xlsx")
    print("  3) backend 폴더에 키워드.xlsx를 복사한 뒤 다시 실행\n")
    print("찾아본 위치:")
    for p in DEFAULT_XLSX_CANDIDATES:
        print(f"  - {p}")
    sys.exit(1)

# 시트별 기본 가중치 — '기타'(일반어 3,210개)와 '전체'(중복)는 제외
SHEET_WEIGHTS = {
    "병무기타": 2,
    "정신과":   3,
    "신장체중": 3,
    "외과":     3,
    "질병기타": 3,
}

# 병역 면탈 맥락에서만 쓰이는 고신호 단어 (빈도 사전과 무관하게 고정 가중치)
HIGH_SIGNAL = {
    "정공": 8, "멸공": 8, "눈공": 8, "돼공": 8, "키공": 8,
    "면탈": 8, "브로커": 8, "병역면제": 6, "군면제": 6,
    "면제": 4, "공익": 4, "신검": 4, "재검": 3,
    "4급": 5, "5급": 5, "장기대기": 5, "꿀팁": 4,
    "병사용진단서": 8, "신체검사": 3, "병무청": 3,
}

MIN_FREQ = 5      # 빈도 5 미만 롱테일 제외
MIN_WORD_LEN = 2  # 1글자 단어 제외 (오탐 과다)


def main():
    ap = argparse.ArgumentParser(description="키워드 점수 사전 생성")
    ap.add_argument("--xlsx", help="키워드.xlsx 경로 (미지정 시 KEYWORD_XLSX 환경변수·기본 후보 탐색)")
    xlsx = resolve_xlsx(ap.parse_args().xlsx)
    print(f"원본: {xlsx}")

    scores: dict[str, int] = dict(HIGH_SIGNAL)
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    loaded = 0
    for ws in wb.worksheets:
        sheet_key = ws.title.split("-")[0]
        weight = SHEET_WEIGHTS.get(sheet_key)
        if weight is None:
            continue
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[1]:
                continue
            word = str(row[1]).strip()
            try:
                freq = int(row[2])
            except (TypeError, ValueError):
                continue
            if freq < MIN_FREQ or len(word) < MIN_WORD_LEN:
                continue
            scores[word] = max(scores.get(word, 0), weight)
            loaded += 1
    wb.close()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=0)
    print(f"단어 {len(scores)}개 저장 (시트에서 {loaded}건 로드) → {OUT}")


if __name__ == "__main__":
    main()
