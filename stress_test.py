import requests
import random
import time

API_URL = "http://localhost:8000"

def run_stress_test():
    print("🚀 [STRESS_TEST] INITIALIZING MULTI-SIZE PARTY INJECTION...")
    
    total_players_added = 0
    # We will aim for around 50-60 players total using random party sizes
    for i in range(50): 
        # Generate a random party size between 1 and 5
        party_size = random.randint(1, 5)
        
        party_players = []
        for _ in range(party_size):
            bot_id = random.randint(1000, 9999)
            party_players.append({
                "username": f"Bot_{bot_id}",
                "elo": 1100,
                "latency": random.randint(10, 50),
                "region": "IN"
            })
        
        payload = {"players": party_players}
        
        try:
            requests.post(f"{API_URL}/join", json=payload)
            total_players_added += party_size
            print(f"✅ Injected Party of {party_size} (Total Players: {total_players_added})")
        except Exception as e:
            print(f"❌ Failed to add party: {e}")

    print("\n=======================================================")
    print(f"⏳ INJECTION COMPLETE. {total_players_added} total players in queue.")
    print("🧠 The Ares Engine will now attempt to solve the 'Tetris' problem.")
    print("👀 Watch your FastAPI logs to see how it groups the parties!")
    print("=======================================================")

if __name__ == "__main__":
    run_stress_test()