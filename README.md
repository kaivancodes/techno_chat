# 🤖 TechnoChat Engine

> **A powerful, multi-modal conversational AI and backoffice management system powered by Django.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0%2B-092E20?style=for-the-badge&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Data_Base-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![AI](https://img.shields.io/badge/AI-Multi--Modal-orange?style=for-the-badge)

---

## 📖 Overview

**TechnoChat** is a sophisticated backend engine and chat application designed to provide diverse AI capabilities to its users. By offering specialized functionalities like **General AI Assistance, Image Generation, Web Search, and localized Chat with File (RAG)**, TechnoChat acts as a centralized intelligence hub. 

The application is heavily augmented with a highly polished, premium **Admin Dashboard** allowing seamless management of user profiles, contributors, uploaded files, and chat logs using an aesthetic "Gold / Navy" Island Theme.

## ✨ Key Features

- **💬 Multi-Modal Chat System**:
  - **AI Assistant**: State-of-the-art general conversational capabilities.
  - **Chat with File (RAG)**: Chat contextually with uploaded documents. Supports diverse file types (PDF, DOCX, CSV, Excel, Images) and performs robust statistical table analysis.
  - **Web Search**: Real-time information retrieval powered by Serper.dev.
  - **Create Image**: Dynamic text-to-image and image-to-image generation directly within the chat interface.
  
- **🛡️ Premium Admin Dashboard**:
  - **Dynamic Theming**: Seamless Light and Dark mode toggling.
  - **Advanced Access Control**: Secure Admin Registration and Login flows featuring real-time, 5-point password strength validation and domain verification.
  - **Team Management**: Manage internal "Contributors" and "Admins" across organized teams (Core, HR, etc.).
  - **Centralized Logs**: Track user behavior through detailed file ingestion logs, chat sessions, and individual message histories.

- **📄 Robust File Analysis Pipeline**:
  - Complete ingestion pipeline supporting tabular data (Pandas integration).
  - Automatic, accurate embedding generation by prepending statistical summaries to specific contexts.

## 🛠️ Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend Framework** | Django | Robust Python web framework handling core logic & routing. |
| **Database** | PostgreSQL | Scalable relational data persistence. |
| **Web Search** | Serper.dev | Fast Google Search API integration for real-time web querying. |
| **Image Generation** | Kie.ai + OpenAI-compatible image models | Supports text-to-image and image-to-image generation inside chat. |
| **Frontend Strategy** | HTML / CSS / JS | Vanilla implementation leveraging a bespoke, premium "Island" design system. |

---

## 🚀 Getting Started

Follow these steps to set up the TechnoChat engine locally.

### Prerequisites

- **Python 3.10+** installed.
- **PostgreSQL** installed and running.
- Necessary API Keys for Search and AI Models.

### 📥 Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/yourusername/techno_chat.git
    cd techno_chat
    ```

2.  **Create Custom Virtual Environment**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Environment Configuration**
    Create a `.env` file in the root directory:
    ```bash
    cp .env.example .env
    ```
    
    Populate the `.env` file with your environment specifics:
    ```ini
    # Core Application Settings
    SECRET_KEY='your_django_secret_key'
    DEBUG=True

    # Database
    DATABASE_NAME='techno_chat_db'
    DATABASE_USER='postgres'
    DATABASE_PASSWORD='your_db_password'
    DATABASE_HOST='localhost'
    DATABASE_PORT=5432

    # Vector Database (Pinecone)
    PINECONE_API_KEY='your_pinecone_key'
    PINECONE_HOST_URL='your_index_url'
    PINECONE_NAMESPACE='Files'
    
    # AI Models (Groq / Google)
    GROQ_API_KEY='your_groq_key'
    GROQ_MODEL_LLAMA_70B='llama-3.3-70b-versatile'
    
    GOOGLE_API_KEY='your_google_key'
    GEMINI_MODEL_PRO='gemini-2.5-pro'

    # Web Search (Serper)
    SERPER_API_KEY='your_serper_key'
    SERPER_MAX_RESULTS=6

    # Image Generation
    KIE_API_KEY='your_kie_key'
    OPENAI_TEXT_IMAGE_MODEL='gpt-image-1'
    OPENAI_IMAGE_MODEL='gpt-image-1'

    # Langchain Tracing
    LANGCHAIN_API_KEY='your_langchain_key'
    LANGCHAIN_TRACING_V2="true"
    ```

5.  **Run Migrations**
    ```bash
    python manage.py migrate
    ```

6.  **Start the Server**
    ```bash
    python manage.py runserver
    ```

---

## 🌐 Application Routes

TechnoChat is a full-stack Django web application. The following are the core routes you can access via your browser.

### 👤 User & Contributor Portals

| Route | View | Description |
| :--- | :--- | :--- |
| `/login/` | `login_view` | Main login page for Contributors. |
| `/home/` | `home_view` | The application landing page post-login. |
| `/profile/` | `profile_view` | Contributor profile completion & settings. |

### 🛡️ Admin Portal

| Route | View | Description |
| :--- | :--- | :--- |
| `/admin-login/` | `admin_login_view` | Secure login for TechnoChat Admins. |
| `/admin-dashboard/` | `admin_dashboard_view` | Central management for users, files, and chat logs. |

### 📂 Files & Chat Engine

| Route | View | Description |
| :--- | :--- | :--- |
| `/files/` | `file_list_view` | View and manage uploaded files (PDF, CSV, etc.) for RAG. |
| `/chat/new/` | `create_session_view` | Initiate a new chat session (AI Assistant, Web Search, RAG). |
| `/chat/<id>/` | `chat_view` | Enter a specific active chat session. |
| `/chat/<id>/send/` | `chat_send_view` | Handles all chat modes including Create Image text-to-image and image editing requests. |

---

## 🧪 Example Workflow

1.  **Admin Setup**: Navigate to `/admin-login/` or `/admin-register/`. Sign in and complete your Admin Profile.
2.  **Add Contributors**: From the `/admin-dashboard/`, create a new Contributor account under the "Contributors" section.
3.  **User Login**: As a Contributor, log in via `/login/` and land on `/home/`.
4.  **Upload Context Files**: Navigate to `/files/` and upload data sources (e.g., PDFs or Spreadsheets).
5.  **Start Chatting**: Go to `/chat/new/` and create a session. If using "Chat with File", attach your uploaded documents. Use the `/chat/<id>/` interface to leverage diverse AI models (Groq, Gemini) to answer questions!
6.  **Generate or Edit Images**: In an active chat, switch to **Create Image** mode. Enter a prompt to generate a new image, or upload an image first to perform image-to-image editing directly from the chat UI.

---

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a Pull Request.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---
Made with ❤️ by Technostacks
