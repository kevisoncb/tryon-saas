from app.infra.db.database import engine
from app.infra.db.models import Base

Base.metadata.create_all(bind=engine)
print("Banco inicializado com sucesso.")
