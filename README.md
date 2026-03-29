🎵 AI Song Lyrics Generator

An end-to-end AI-powered application that extracts lyrics from any song using advanced audio processing and speech recognition.

🚀 Overview

This project allows users to upload an audio file (MP3/WAV) and automatically generate its lyrics using a multi-stage AI pipeline.

It combines:

🎧 Audio preprocessing
🎤 Vocal separation
🧠 Speech-to-text (AI)
✍️ Text cleaning & formatting
🖥️ Interactive UI
✨ Features
🎵 Upload songs and extract lyrics instantly
🎤 Vocal isolation using AI
🧠 Accurate transcription using Whisper
✍️ Clean, formatted lyrics output
⏱️ Timestamped segments (for subtitles/karaoke)
📊 Metadata (language, word count, processing time)
🧾 Downloadable lyrics
⚙️ Full pipeline transparency (step tracking)
🧠 How It Works
Upload Audio
     ↓
File Handler
     ↓
Audio Processing (convert, normalize, resample)
     ↓
Vocal Separation (Spleeter)
     ↓
Speech Recognition (Whisper)
     ↓
Text Cleaning & Formatting
     ↓
Final Lyrics Output

🏗️ Project Structure
song-lyrics-generator/
│
├── app/
│   ├── main.py              # Streamlit UI
│   ├── config.py           # Configuration
│   │
│   ├── routes/
│   │   └── upload.py       # Pipeline controller
│   │
│   ├── services/
│   │   ├── audio_processor.py
│   │   ├── vocal_separator.py
│   │   ├── transcriber.py
│   │   └── text_cleaner.py
│   │
│   ├── utils/
│   │   ├── file_handler.py
│   │   └── logger.py
│
├── data/
│   ├── input/
│   ├── output/
│   └── temp/
│
├── run.py                  # Application entry point
├── requirements.txt
└── README.md

⚙️ Installation
1. Clone the repository
git clone <your-repo-link>
cd song-lyrics-generator
2. Install dependencies
pip install -r requirements.txt
3. Install FFmpeg (Required)
Windows: Download from official site and add to PATH
Linux:
sudo apt install ffmpeg
▶️ Running the Application
Option 1 (Recommended)
python run.py
Option 2
streamlit run app/main.py
📦 Requirements
Python 3.9+
FFmpeg
GPU (optional, for faster processing)
🧪 Example Output
Language: English
Words: 120
Processing Time: ~10–20 seconds

Output:

Hello world  
How are you  
This is a song  
...
⚠️ Limitations
Fast or noisy songs may reduce accuracy
Rap songs are harder to transcribe
Requires good audio quality
Processing time depends on hardware
🚀 Future Improvements
🎤 Real-time microphone input
🎬 Subtitle (.srt) export
🌍 Multi-language translation
🎶 Karaoke mode (word highlighting)
☁️ Cloud deployment
🧠 Technologies Used
Python
Streamlit
OpenAI Whisper
Spleeter
Librosa
FFmpeg

⭐ Acknowledgements
OpenAI Whisper for speech recognition
Deezer Spleeter for vocal separation
Open-source community
📜 License

This project is for educational purposes.
