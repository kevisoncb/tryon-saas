from app.infra.db.database import SessionLocal
from app.infra.db.models import ApiKey


def main():
    db = SessionLocal()
    try:
        key = ApiKey.generate()
        row = ApiKey(name="local-dev", key=key, is_active=True, rpm_limit=60)
        db.add(row)
        db.commit()
        db.refresh(row)
        print("API KEY criada:")
        print(row.key)
    finally:
        db.close()


if __name__ == "__main__":
    main()
