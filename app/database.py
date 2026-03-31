from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone

from app.config import settings

engine = create_engine(settings.database_url)
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ScanRecord(Base):
    __tablename__ = "scans"

    scan_id = Column(String, primary_key=True)
    url = Column(String, nullable=False)
    seo_score = Column(Integer)
    status = Column(String, nullable=False)
    report = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)


def save_scan(scan_id: str, url: str, status: str, seo_score: int = None, report: dict = None):
    with Session() as session:
        record = session.get(ScanRecord, scan_id)
        if record:
            record.status = status
            record.seo_score = seo_score
            record.report = report
        else:
            record = ScanRecord(
                scan_id=scan_id,
                url=url,
                status=status,
                seo_score=seo_score,
                report=report,
            )
            session.add(record)
        session.commit()


def get_scans(domain: str = None, limit: int = 50) -> list[ScanRecord]:
    with Session() as session:
        q = session.query(ScanRecord).order_by(ScanRecord.created_at.desc())
        if domain:
            q = q.filter(ScanRecord.url.contains(domain))
        return q.limit(limit).all()
