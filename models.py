from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Item(Base):
    __tablename__ = 'itens'

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String, index=True) # Permanente ou Consumo
    descricao = Column(String)
    quantidade = Column(Integer, default=1)
    patrimonio = Column(String, nullable=True)
    local = Column(String, index=True) # Laboratório [...] ou Paiol [...]
    foto_path = Column(String, nullable=True)
    usuario_id = Column(Integer, index=True)
    data_registro = Column(DateTime, default=datetime.utcnow)
