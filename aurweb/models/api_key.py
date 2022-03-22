from sqlalchemy.orm import relationship

from aurweb import schema
from aurweb.models.declarative import Base


class ApiKey(Base):
    __table__ = schema.ApiKeys
    __tablename__ = __table__.name
    __mapper_args__ = {"primary_key": __table__.c.ID}

    User = relationship("User", back_populates="api_keys")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
