import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

DB_PATH = os.path.join(os.path.dirname(__file__), 'inventory.db')
ENGINE = create_engine(f'sqlite:///{DB_PATH}', echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)

def init_db():
    Base.metadata.create_all(bind=ENGINE)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
