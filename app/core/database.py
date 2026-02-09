from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./enwis.db"

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) # type: ignore
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session: # type: ignore
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
