"""키워드.xlsx → 사전 필터용 점수 사전(app/data/keyword_scores.json) 생성.

학습자료의 과목별 빈도 사전에서 병역 맥락 단어에 가중치를 부여한다.
생성 파일은 병무청 내부자료 파생물이므로 git에 커밋하지 않는다 (.gitignore).

사용법: .venv\\Scripts\\python.exe build_keyword_scores.py
"""
import sys, json, os
sys.stdout.reconfigure(encoding="utf-8")
import openpyxl

XLSX = (r"C:\Users\somes\OneDrive\Desktop\전문인재\개별과제"
        r"\2024년 학습자료(도입시)외2_암호화 완료\2024년 학습자료(도입시)외2\키워드.xlsx")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "data", "keyword_scores.json")

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
    scores: dict[str, int] = dict(HIGH_SIGNAL)
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
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
