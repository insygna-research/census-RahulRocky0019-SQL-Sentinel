import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv()

class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    # Dynamic path to the DB file
    BASE_DIR = Path(__file__).resolve().parents[2]
    DB_URI = f"sqlite:///{BASE_DIR}/data/chinook.db"
    
    MODEL_1 = "llama-3.3-70b-versatile"
    MODEL_2 = "llama-3.1-8b-instant"

    @staticmethod
    def validate():
        if not Config.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY not found in .env file")
        print("All configurations are valid.")

Config.validate()