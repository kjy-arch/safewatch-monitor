import pdfplumber
import httpx
from io import BytesIO
from app.core.database import supabase


def extract_text_from_pdf(file_bytes: bytes) -> str:
    text_parts = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text.strip())
    return "\n".join(text_parts)


def extract_text_from_url(url: str) -> str:
    response = httpx.get(url, timeout=15, follow_redirects=True)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type:
        return extract_text_from_pdf(response.content)

    # HTML 페이지 → 태그 제거 후 텍스트 추출
    import re
    text = response.text
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", "\n", text)
    return text.strip()[:5000]  # 너무 길면 자름


def save_official_doc(title: str, doc_type: str, content: str, source: str) -> dict:
    result = supabase.table("official_docs").insert({
        "title": title,
        "doc_type": doc_type,
        "content": content,
        "source": source,
    }).execute()
    return result.data[0]


def find_relevant_docs(text: str, max_docs: int = 3) -> list[str]:
    """
    텍스트에 포함된 키워드로 official_docs 테이블을 검색하여
    관련 문서 내용 목록 반환.
    """
    all_docs = supabase.table("official_docs").select("title, content").execute().data
    if not all_docs:
        return []

    # 텍스트에서 주요 단어 추출 (2글자 이상 명사 후보)
    import re
    words = re.findall(r"[가-힣]{2,}", text)

    scored = []
    for doc in all_docs:
        doc_text = f"{doc['title']} {doc['content']}"
        score = sum(1 for w in words if w in doc_text)
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc["content"][:800] for _, doc in scored[:max_docs]]
