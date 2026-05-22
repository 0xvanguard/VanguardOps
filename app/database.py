from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

# Asumiendo PostgreSQL como se confirmó en el stack
SQLALCHEMY_DATABASE_URL = "postgresql://user:password@localhost/vanguardops"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
