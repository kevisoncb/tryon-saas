import secrets
from database import SessionLocal
from models import ApiKey

def main():
    db = SessionLocal()
    try:
        key = secrets.token_urlsafe(32)
        api = ApiKey(name="local-dev", key=key, rpm_limit=60, is_active=True)
        db.add(api)
        db.commit()
        db.refresh(api)
        print("API KEY criada:")
        print(key)
    finally:
        db.close()

if __name__ == "__main__":
    main()
