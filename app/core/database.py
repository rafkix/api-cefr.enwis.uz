from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./enwis.db"

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Doimiy ochiq ulanishlar
    max_overflow=50,       # Zarurat bo'lganda qo'shimcha ochiladigan ulanishlar
    pool_timeout=30,       # Navbat kutish vaqti
    pool_recycle=1800      # 30 minutda ulanishni yangilash
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) # type: ignore
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session: # type: ignore
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
