# 🏏 Autonomous Sports Commentary System

An AI-powered cricket commentary platform that replays historical matches ball-by-ball and generates real-time commentary using multiple AI agents. The system supports live score tracking, cricket Q&A, speech-to-text, text-to-speech, and an interactive Gradio interface.

## ✨ Features

- AI-generated ball-by-ball cricket commentary
- Multi-Agent Architecture using LangGraph
- Match replay from Cricsheet datasets
- Natural Language Cricket Q&A
- SQL-powered statistics retrieval
- Speech-to-Text using Whisper Tiny
- Text-to-Speech using pyttsx3
- Interactive Gradio Dashboard

## 🛠️ Tech Stack

- Python
- LangChain
- LangGraph
- Gradio
- SQL
- Groq (GPT-OSS-120B)
- Hugging Face Transformers
- OpenAI Whisper Tiny (Speech-to-Text)
- pyttsx3 (Text-to-Speech)

## 📊 System Flow

```text
Cricsheet Dataset
        ↓
SQL Database
        ↓
Match Replay Engine
        ↓
LangGraph Multi-Agent System
(Commentary Agent | SQL Agent | Q&A Agent)
        ↓
Speech Services (STT + TTS)
        ↓
Gradio User Interface
```

## 📂 Dataset

- Cricsheet Ball-by-Ball Cricket Dataset
- https://cricsheet.org

## 🎯 Key Learnings

- Multi-Agent AI Systems
- RAG-based Question Answering
- SQL Integration with LLMs
- Agent Routing with LangGraph
- Speech AI Applications
- Prompt Engineering
- Generative AI Application Development

## 👨‍💻 Author

**Rama Kumar**
