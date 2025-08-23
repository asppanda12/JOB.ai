from dotenv import load_dotenv, find_dotenv

env_path = find_dotenv()
print("Loading from:", env_path)

load_dotenv(env_path)