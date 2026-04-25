from pydantic import BaseModel
from typing import List

class Player(BaseModel):
    username: str
    elo: int
    latency: int
    region: str # Added region (e.g., "IN", "US-EAST", "EU-WEST")

class PartyJoin(BaseModel):
    players: List[Player]