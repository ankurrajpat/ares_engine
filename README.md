#  Ares Executive Matchmaking System

A **real-time 5v5 matchmaking backend** built using FastAPI, PostgreSQL, and WebSockets.  
It simulates a modern multiplayer game matchmaking system with **ELO-based balancing, party support, and live notifications**.

---

##  Features

-  5v5 Matchmaking Engine  
-  Party-based queue system  
-  Dynamic ELO balancing  
-  Region-aware + global matchmaking  
-  Real-time notifications via WebSockets  
-  Automatic cleanup of inactive players  
-  Leaderboard system  
-  Random map selection  

---

##  Tech Stack

- Backend: FastAPI (async)  
- Database: PostgreSQL  
- DB Driver: asyncpg  
- Real-time: WebSockets  
- Validation: Pydantic  
- Concurrency: asyncio  

---

## System Architecture

Client → FastAPI → PostgreSQL
↓
Matchmaking Engine
↓
WebSockets
↓
Client


---

## Database Schema

### Tables:
- players → stores player data (ELO, username)  
- matchmaking_queue → active queue  
- matches → match records  
- match_participants → player-match mapping  
- maps → available maps  

---
### ER Diagram:
<img width="1280" height="853" alt="WhatsApp Image 2026-04-23 at 10 02 28" src="https://github.com/user-attachments/assets/983c7ae8-f1b9-447e-a4ed-ce3b36c91d0b" />

---


## How It Works

### 1. Join Queue
- Player sends request to `/join`  
- Stored in:
  - players  
  - matchmaking_queue  

---

### 2. Queue Management
- Players send heartbeat (`/heartbeat`)  
- Inactive players removed automatically  

---

### 3. Matchmaking
- Triggered via `/match`

Steps:
1. Fetch players from queue  
2. Group by party  
3. Form 5v5 teams  
4. Calculate average ELO  
5. Apply dynamic threshold  

---

### 4. Match Creation
- Random map selected  
- Stored in:
  - matches  
  - match_participants  
- Players removed from queue  

---

### 5. Real-Time Notification

{
  "event": "MATCH_FOUND",
  "match_id": "...",
  "map": "...",
  "team_a": [...],
  "team_b": [...]
}

## 6. Match Resolution

- Endpoint: `/match/{match_id}/resolve`

Updates:
- Winner
- Player ELO (+25 / -20)

---

## Installation & Setup

### 1. Clone Repo

git clone https://github.com/your-username/ares-matchmaking.git
cd ares-matchmaking

### 2. Install Dependencies

pip install -r requirements.txt

### 3. Setup PostgreSQL

Create the database:
CREATE DATABASE ares_db;

Update the connection string in database.py
DATABASE_URL = "postgresql://user:password@localhost:5432/ares_db"

### 4. Run the Server

uvicorn main:app --reload

##  Key Design Decisions

* **Separation of Data:** Distinct handling of permanent vs. transient data to optimize storage and speed.
* **Async Architecture:** Built for high scalability using non-blocking I/O.
* **Dynamic Matchmaking:** Constraints that evolve based on user wait times to balance match quality and speed.
* **Party Integrity:** Logic specifically designed to preserve pre-made groups during the matching process.

##  Performance Optimizations

* **Connection Pooling:** Efficient database communication via `asyncpg`.
* **Indexed Queries:** Optimized lookups for `region` and `last_seen` fields.
* **Batch Operations:** Reduced overhead by processing multiple data points simultaneously.
* **Non-blocking Execution:** Full async implementation to maximize throughput.

##  Limitations

* **Basic ELO System:** Currently utilizes a foundational algorithm rather than an advanced ranking model.
* **Concurrency Locking:** No specific locking mechanism in the matchmaking loop (potential for race conditions in multi-node setups).
* **Role-based Matching:** Does not currently account for specific player roles (e.g., Tank, Healer, DPS).
* **Single-node Architecture:** Designed as a monolithic service rather than a distributed cluster.

##  Future Improvements

* **Advanced Ranking:** Implementation of Glicko-2 or more sophisticated Elo variants.
* **Distributed Service:** Transitioning to a microservices-based distributed matchmaking system.
* **Role Balancing:** Ensuring teams have a fair distribution of player roles.
* **Map Veto System:** Allowing players to vote on or ban specific maps.
* **Anti-smurf Detection:** Algorithms to identify and re-rank outlier accounts.

##  Conclusion

This project demonstrates a scalable, real-time matchmaking system inspired by modern multiplayer games, combining:

* **Database Design:** Structured for high-frequency reads and writes.
* **Backend Engineering:** Robust logic for handling complex player states.
* **Real-time Communication:** Low-latency updates for active sessions.

##  Author

Developed as a backend systems project for learning:

* **DBMS Concepts**
* **System Design**
* **Async Programming**
