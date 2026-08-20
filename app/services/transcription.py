import os
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def transcribe_audio(filepath: str) -> str:
    with open(filepath, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(filepath), audio_file.read()),
            model="whisper-large-v3",
            response_format="text",
        )
    return transcription if isinstance(transcription, str) else transcription.text