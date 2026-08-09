from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

#pipe to postgres
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
#parent class for all orm models to inherit from
Base = declarative_base()


#yields a db session per request, closes it after the route finishes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()