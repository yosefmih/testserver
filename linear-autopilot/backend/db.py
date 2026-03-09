import asyncpg
import os
from pathlib import Path

pool: asyncpg.Pool | None = None

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def init_pool(database_url: str) -> asyncpg.Pool:
    global pool
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    return pool


async def close_pool():
    global pool
    if pool:
        await pool.close()
        pool = None


async def get_pool() -> asyncpg.Pool:
    if pool is None:
        raise RuntimeError("Database pool not initialized")
    return pool


async def run_migrations():
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT now()
            )
        """)

        applied = {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for f in migration_files:
            version = int(f.stem.split("_")[0])
            if version in applied:
                continue
            sql = f.read_text()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
