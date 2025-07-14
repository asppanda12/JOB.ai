# Use a pipeline as a high-level helper
from transformers import pipeline

# Define save directory
save_directory = "model_save"  # or any path where you want to save the model

messages = [
    {"role": "user", "content": "Who are you?"},
]
pipe = pipeline("text-generation", model="meta-llama/Llama-3.3-70B-Instruct")
pipe(messages)
pipe.model.save_pretrained(save_directory)
pipe.tokenizer.save_pretrained(save_directory)
