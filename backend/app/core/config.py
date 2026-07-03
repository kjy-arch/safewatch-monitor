from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SECRET_KEY: str
    GEMINI_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    YOUTUBE_API_KEY: str
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    APP_ENV: str = "development"
    APP_PORT: int = 8001
    CORS_ORIGINS: str = "*"  # 쉼표 구분 목록. 운영 배포 시 대시보드 도메인으로 제한

    class Config:
        env_file = ".env"

settings = Settings()
