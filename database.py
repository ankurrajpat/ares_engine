import asyncpg

DATABASE_URL = "postgresql://ares_user:ares_password@localhost:5432/ares_db"

async def get_db_pool():
    return await asyncpg.create_pool(DATABASE_URL)

async def init_db():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # DROP in reverse order of dependencies to avoid Foreign Key errors
        await conn.execute('DROP TABLE IF EXISTS match_participants CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS matches CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS matchmaking_queue CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS maps CASCADE;')
        await conn.execute('DROP TABLE IF EXISTS players CASCADE;')
        
        # 1. Master Player Table
        await conn.execute('''
            CREATE TABLE players (
                player_id UUID PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                total_elo INTEGER DEFAULT 1200,
                penalty_until TIMESTAMP WITH TIME ZONE DEFAULT NULL
            );
        ''')

        # 2. Active Queue (Transient data)
        await conn.execute('''
            CREATE TABLE matchmaking_queue (
                player_id UUID PRIMARY KEY REFERENCES players(player_id),
                party_id UUID NOT NULL,
                region VARCHAR(20) NOT NULL,
                latency INTEGER NOT NULL,
                entered_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 3. Maps Table
        await conn.execute('''
            CREATE TABLE maps (
                map_id SERIAL PRIMARY KEY,
                map_name VARCHAR(50) UNIQUE NOT NULL,
                is_active BOOLEAN DEFAULT TRUE
            );
        ''')

        # 4. Matches Ledger
        await conn.execute('''
            CREATE TABLE matches (
                match_id UUID PRIMARY KEY,
                map_name VARCHAR(50),
                region VARCHAR(20),
                avg_elo INTEGER,
                match_type VARCHAR(10), -- 'LOCAL' or 'GLOBAL'
                winner CHAR(1) DEFAULT NULL, -- 'A', 'B', or NULL if ongoing
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        ''')

        # 5. Junction Table (Linking Players to Matches)
        await conn.execute('''
            CREATE TABLE match_participants (
                match_id UUID REFERENCES matches(match_id),
                player_id UUID REFERENCES players(player_id),
                team CHAR(1),
                PRIMARY KEY (match_id, player_id)
            );
        ''')

        # INDEXING for O(log N) search performance
        await conn.execute('CREATE INDEX idx_queue_region ON matchmaking_queue (region, last_seen);')
        
        # Seed maps
        await conn.execute("INSERT INTO maps (map_name) VALUES ('Bind'), ('Haven'), ('Split'), ('Ascent') ON CONFLICT DO NOTHING;")

    await pool.close()
    print("Relational Schema Initialized Successfully!")

   