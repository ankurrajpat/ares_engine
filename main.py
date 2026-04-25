import uuid
import asyncio
import random
from collections import defaultdict
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, get_db_pool
from schemas import PartyJoin

# --- WEBSOCKET MANAGER ---

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, party_id: str):
        await websocket.accept()
        self.active_connections[party_id] = websocket
        print(f"[WebSocket] Party {party_id} connected.")

    def disconnect(self, party_id: str):
        if party_id in self.active_connections:
            del self.active_connections[party_id]
            print(f"[WebSocket] Party {party_id} disconnected.")

    async def send_personal_message(self, message: dict, party_id: str):
        if party_id in self.active_connections:
            await self.active_connections[party_id].send_json(message)

ws_manager = ConnectionManager()

# --- UTILITY FUNCTIONS ---

def calculate_team_elo(party_list):
    """Calculates average Elo for a list of parties (team)."""
    all_players = [player for party in party_list for player in party]
    if not all_players:
        return 0
    total_elo = sum(p['total_elo'] for p in all_players)
    return total_elo / len(all_players)

# --- BACKGROUND TASKS (THE ARES ENGINE) ---

async def continuous_cleanup(app):
    """Purges players from matchmaking_queue if they haven't sent a heartbeat."""
    while True:
        try:
            if hasattr(app.state, "pool"):
                async with app.state.pool.acquire() as conn:
                    deleted = await conn.execute('''
                        DELETE FROM matchmaking_queue 
                        WHERE last_seen < NOW() - INTERVAL '300 seconds'
                    ''')
                    count = deleted.split(" ")[1]
                    if int(count) > 0:
                        print(f"[Ares Cleanup] Purged {count} disconnected players.")
        except Exception as e:
            print(f"[Cleanup Error] {e}")
        
        await asyncio.sleep(15)


async def continuous_matchmaker(app):
    """
    The Autonomous Matchmaking Loop. 
    Sweeps active regions every 3 seconds to find and execute matches using Advanced Bin-Packing.
    """
    # In a real system, these would be fetched from a 'regions' DB table
    active_regions = ["IN", "US-EAST"] 

    while True:
        try:
            if hasattr(app.state, "pool"):
                async with app.state.pool.acquire() as conn:
                    for region in active_regions:
                        # The "Drain Loop" - Keep matching in this region until empty
                        while True:
                            async with conn.transaction():
                                # 1. Check for the oldest player to determine wait time
                                oldest = await conn.fetchrow('''
                                    SELECT entered_at FROM matchmaking_queue 
                                    WHERE region = $1 ORDER BY entered_at ASC LIMIT 1
                                ''', region)

                                if not oldest:
                                    break # Queue is entirely empty for this region

                                wait_time = (datetime.now(timezone.utc) - oldest['entered_at'].replace(tzinfo=timezone.utc)).total_seconds()
                                
                                # 2. Fetch a healthy batch of players (LIMIT 100 ensures we don't slice parties in half)
                                base_query = '''
                                    SELECT q.*, p.username, p.total_elo 
                                    FROM matchmaking_queue q 
                                    JOIN players p ON q.player_id = p.player_id
                                '''
                                if wait_time > 60:
                                    records = await conn.fetch(base_query + " ORDER BY q.entered_at ASC LIMIT 100")
                                    match_type = "GLOBAL"
                                else:
                                    records = await conn.fetch(base_query + " WHERE q.region = $1 ORDER BY q.entered_at ASC LIMIT 100", region)
                                    match_type = "LOCAL"

                                if len(records) < 10:
                                    break  # Not enough total players to even try

                                # 3. Group records into indivisible parties
                                parties = defaultdict(list)
                                for r in records:
                                    parties[str(r['party_id'])].append(dict(r))

                                party_list = list(parties.items())

                                # 4. The "Tetris" Algorithm: Recursive Subset Sum to perfectly pack 5 slots
                                def find_team(available_parties, target_size=5):
                                    def backtrack(index, current_size, current_team):
                                        if current_size == target_size:
                                            return current_team
                                        if current_size > target_size or index >= len(available_parties):
                                            return None
                                        
                                        p_id, players = available_parties[index]
                                        
                                        # Branch 1: Try adding this party to the team
                                        res = backtrack(index + 1, current_size + len(players), current_team + [(p_id, players)])
                                        if res is not None:
                                            return res
                                            
                                        # Branch 2: Skip this party and try the next ones
                                        return backtrack(index + 1, current_size, current_team)
                                        
                                    return backtrack(0, 0, [])

                                # 5. Form Team Alpha
                                team_a_data = find_team(party_list)
                                if not team_a_data:
                                    break  # Break out to wait for more players to fill gaps

                                # Remove Team Alpha's parties from the available pool
                                used_a_ids = {p_id for p_id, _ in team_a_data}
                                remaining_parties = [p for p in party_list if p[0] not in used_a_ids]

                                # 6. Form Team Bravo
                                team_b_data = find_team(remaining_parties)
                                if not team_b_data:
                                    break  # Break out to wait for more players to fill gaps

                                # 7. Unpack the optimized teams
                                team_a = [players for _, players in team_a_data]
                                team_b = [players for _, players in team_b_data]

                                used_party_ids = [uuid.UUID(p_id) for p_id, _ in team_a_data] + [uuid.UUID(p_id) for p_id, _ in team_b_data]

                                # 8. Validate Elo Thresholds
                                avg_a = calculate_team_elo(team_a)
                                avg_b = calculate_team_elo(team_b)
                                elo_diff = abs(avg_a - avg_b)
                                threshold = 50 + ((wait_time // 15) * 50)

                                if elo_diff > threshold:
                                    break # Gap too high, break out and wait for threshold relaxation

                                # 9. Match Execution & Ledger Commit
                                map_rec = await conn.fetchrow("SELECT map_name FROM maps WHERE is_active = TRUE ORDER BY RANDOM() LIMIT 1")
                                selected_map = map_rec['map_name'] if map_rec else "Training Grounds"
                                match_id = uuid.uuid4()

                                await conn.execute('''
                                    INSERT INTO matches (match_id, map_name, region, avg_elo, match_type)
                                    VALUES ($1, $2, $3, $4, $5)
                                ''', match_id, selected_map, region, int((avg_a + avg_b)/2), match_type)

                                for p in [item for sublist in team_a for item in sublist]:
                                    await conn.execute('INSERT INTO match_participants (match_id, player_id, team) VALUES ($1, $2, $3)', match_id, p['player_id'], 'A')
                                for p in [item for sublist in team_b for item in sublist]:
                                    await conn.execute('INSERT INTO match_participants (match_id, player_id, team) VALUES ($1, $2, $3)', match_id, p['player_id'], 'B')

                                await conn.execute('DELETE FROM matchmaking_queue WHERE party_id = ANY($1::uuid[])', used_party_ids)

                                print(f"\n{'='*50}")
                                print(f"🔥 [ARES DEPLOYMENT] MATCH_ID: {match_id}")
                                print(f"🗺️  MAP: {selected_map} | REGION: {region} | TYPE: {match_type}")
                                print(f"{'-'*50}")
                                print(f"🔵 TEAM_ALPHA: {' + '.join([f'Party[{len(p)}]' for p in team_a])}")
                                print(f"🔴 TEAM_BRAVO: {' + '.join([f'Party[{len(p)}]' for p in team_b])}")
                                print(f"📊 AVG_ELO: {int((avg_a + avg_b)/2)} | ELO_DIFF: {int(elo_diff)}")
                                print(f"{'='*50}\n")

                            # --- WEBSOCKET ALERT EXECUTION ---
                            # This happens outside the DB transaction to prevent locking if WS hangs
                            match_payload = {
                                "event": "MATCH_FOUND",
                                "match_id": str(match_id),
                                "map": selected_map,
                                "avg_elo": int((avg_a + avg_b) / 2),
                                "team_a": [p['username'] for party in team_a for p in party],
                                "team_b": [p['username'] for party in team_b for p in party],
                            }

                            for p_id in used_party_ids:
                                await ws_manager.send_personal_message(match_payload, str(p_id))

        except Exception as e:
            print(f"⚠️ [Matchmaker Fault] {e}")
        
        # Engine Tick Rate: 3 Seconds
        await asyncio.sleep(3)


# --- LIFESPAN MANAGEMENT ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Connecting to Relational Database...")
    await init_db()
    app.state.pool = await get_db_pool()
    
    # Ignite both Engine cores simultaneously
    cleanup_task = asyncio.create_task(continuous_cleanup(app))
    matchmaker_task = asyncio.create_task(continuous_matchmaker(app))
    
    print("Ares Engine, WebSockets & Background Monitor Ready!")
    yield
    
    cleanup_task.cancel()
    matchmaker_task.cancel()
    await app.state.pool.close()

app = FastAPI(title="Ares Executive Matchmaking", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---

@app.get("/")
async def root():
    return {"status": "Ares Online", "engine": "Autonomous Relational Tick"}

@app.post("/join")
async def join_queue(party: PartyJoin):
    party_id = uuid.uuid4()
    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            for p in party.players:
                player_record = await conn.fetchrow('''
                    INSERT INTO players (player_id, username, total_elo)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (username) DO UPDATE SET total_elo = $3
                    RETURNING player_id
                ''', uuid.uuid4(), p.username, p.elo)
                
                await conn.execute('''
                    INSERT INTO matchmaking_queue (player_id, party_id, region, latency)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (player_id) DO UPDATE SET 
                        last_seen = NOW(), 
                        region = $3, 
                        latency = $4
                ''', player_record['player_id'], party_id, p.region, p.latency)
                
    return {"message": "Party Joined", "party_id": party_id}

@app.websocket("/ws/{party_id}")
async def websocket_endpoint(websocket: WebSocket, party_id: str):
    await ws_manager.connect(websocket, party_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(party_id)
    except Exception as e:
        ws_manager.disconnect(party_id)

@app.patch("/heartbeat/{party_id}")
async def player_heartbeat(party_id: uuid.UUID):
    async with app.state.pool.acquire() as conn:
        await conn.execute('''
            UPDATE matchmaking_queue 
            SET last_seen = NOW() 
            WHERE party_id = $1
        ''', party_id)
    return {"status": "alive"}

@app.get("/queue")
async def view_queue():
    async with app.state.pool.acquire() as conn:
        records = await conn.fetch('''
            SELECT q.party_id, p.username, p.total_elo, q.latency, q.region, q.entered_at 
            FROM matchmaking_queue q
            JOIN players p ON q.player_id = p.player_id
            ORDER BY q.entered_at ASC;
        ''')
    parties = defaultdict(list)
    for row in records:
        parties[str(row['party_id'])].append(dict(row))
    return {"waiting_parties": parties, "total_count": len(records)}

@app.post("/match/{match_id}/resolve")
async def resolve_match(match_id: uuid.UUID, winner: str):
    if winner not in ['A', 'B']:
        raise HTTPException(status_code=400, detail="Winner must be 'A' or 'B'")

    async with app.state.pool.acquire() as conn:
        async with conn.transaction():
            match_record = await conn.fetchrow("SELECT winner FROM matches WHERE match_id = $1", match_id)
            if not match_record:
                raise HTTPException(status_code=404, detail="Match not found")
            if match_record['winner'] is not None:
                raise HTTPException(status_code=400, detail="Match already resolved")

            await conn.execute("UPDATE matches SET winner = $1 WHERE match_id = $2", winner, match_id)
            
            participants = await conn.fetch('''
                SELECT player_id, team FROM match_participants WHERE match_id = $1
            ''', match_id)
            
            for p in participants:
                elo_change = 25 if p['team'] == winner else -20
                await conn.execute('''
                    UPDATE players 
                    SET total_elo = total_elo + $1 
                    WHERE player_id = $2
                ''', elo_change, p['player_id'])
                
    return {"message": f"Match {match_id} resolved. Winners: Team {winner}. Elo updated."}

@app.get("/matches")
async def get_recent_matches(limit: int = 50):
    async with app.state.pool.acquire() as conn:
        records = await conn.fetch('''
            SELECT 
                match_id, 
                map_name as map, 
                region, 
                avg_elo, 
                match_type, 
                winner,
                created_at 
            FROM matches 
            ORDER BY created_at DESC 
            LIMIT $1
        ''', limit)
        
        matches = []
        for r in records:
            match_dict = dict(r)
            match_dict['match_id'] = str(match_dict['match_id'])
            match_dict['created_at'] = match_dict['created_at'].isoformat()
            matches.append(match_dict)
            
    return matches

@app.get("/leaderboard")
async def get_leaderboard():
    async with app.state.pool.acquire() as conn:
        records = await conn.fetch("SELECT username, total_elo FROM players ORDER BY total_elo DESC LIMIT 10")
    return {"top_players": [dict(r) for r in records]}

@app.get("/stats")
async def get_system_stats():
    async with app.state.pool.acquire() as conn:
        queue_count = await conn.fetchval("SELECT count(*) FROM matchmaking_queue")
        
        matches_today = await conn.fetchval('''
            SELECT count(*) FROM matches 
            WHERE created_at > NOW() - INTERVAL '24 hours'
        ''')
        
        # --- NEW: Match Success Rate ---
        # Calculates the percentage of players who successfully passed through the engine
        matched_players = await conn.fetchval('SELECT COUNT(DISTINCT player_id) FROM match_participants')
        total_players = await conn.fetchval('SELECT COUNT(*) FROM players')
        
        success_rate = 0
        if total_players > 0:
            success_rate = round((matched_players / total_players) * 100, 1)

        engine_load = min(int((queue_count / 100) * 100), 100)

    return {
        "active_queue": queue_count,
        "matches_today": matches_today,
        "success_rate": f"{success_rate}%",
        "engine_load": f"{engine_load}%"
    }

@app.get("/analytics/throughput")
async def get_throughput():
    async with app.state.pool.acquire() as conn:
        records = await conn.fetch('''
            SELECT 
                to_char(created_at, 'HH24:MI') as time, 
                count(*) as matches
            FROM matches 
            WHERE created_at > NOW() - INTERVAL '30 minutes'
            GROUP BY time
            ORDER BY time ASC
        ''')
        
        regions = await conn.fetch('''
            SELECT region as name, count(*) as value 
            FROM matches 
            GROUP BY region
        ''')
        
        return {
            "throughput": [dict(r) for r in records],
            "regions": [dict(r) for r in regions]
        }