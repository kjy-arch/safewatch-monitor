from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SECRET_KEY: str
    GEMINI_API_KEY: str
    # 분류자(배치) 계열 서비스가 참조 — app/services/batch/analyzer.py
    GEMINI_MODEL: str = "gemini-2.5-flash"
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    YOUTUBE_API_KEY: str
    # SNS 크롤러 자격증명 — 미설정 시 해당 크롤러는 no-op (기본값 "" 이라 로드 실패 없음)
    INSTAGRAM_ACCESS_TOKEN: str = ""
    INSTAGRAM_BUSINESS_ACCOUNT_ID: str = ""
    X_BEARER_TOKEN: str = ""
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    APP_ENV: str = "development"
    APP_PORT: int = 8001
    # 평일 08:00 자동 수집 스케줄 사용 여부. 테스트 단계에는 false(수동 실행만),
    # 운영 전환 시 .env에서 AUTO_CRAWL=true 로 켠다.
    AUTO_CRAWL: bool = False
    # 수집 완료 시 결과 엑셀을 저장할 폴더. 미설정이면 사용자 다운로드 폴더(~/Downloads).
    EXPORT_DIR: str = ""
    # 화면은 운영 시 백엔드와 같은 origin에서 제공된다. 아래 값은 Vite 개발 서버만 허용한다.
    # LAN/서버 배포로 전환할 때는 인증을 먼저 추가하고 .env에 필요한 origin만 명시한다.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    class Config:
        env_file = ".env"
        # 분류자 .env를 합쳐도 미정의 키로 기동 실패하지 않게 (SUPABASE_PUBLISHABLE_KEY 등)
        extra = "ignore"

settings = Settings()
