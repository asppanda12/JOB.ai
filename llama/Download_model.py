from huggingface_hub import hf_hub_download
import os
from dotenv import load_dotenv

def download_model():
    try:
        # Load environment variables
        load_dotenv()
        
        # Get token from environment variable
        token = os.getenv('HUGGINGFACE_TOKEN')
        
        if not token:
            print("Please set HUGGINGFACE_TOKEN in your environment variables")
            return None
            
        # Create models directory
        os.makedirs("./models", exist_ok=True)
        
        print("Starting model download...")
        print("Downloading smaller LLaMA model...")
        
        # Updated repository and filename
        model_path = hf_hub_download(
            repo_id="TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF",  # Updated repo
            filename="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",   # Updated filename
            local_dir="./models",
            token=token
        )
        print(f"Model downloaded successfully to: {model_path}")
        return model_path
        
    except Exception as e:
        print(f"Error downloading model: {e}")
        return None

if __name__ == "__main__":
    download_model()