# dAIbetes - Diabetes AI assistant
**AI Diabetes Assistant** - developed as a project for the Gemma 4 Good Hackathon. 

⚠️ **Medical Disclaimer:** This application is NOT a medical device. It is a prototype developed for educational and hackathon purposes only. It has not undergone clinical testing. Always consult a healthcare professional for medical advice and treatment.

# Overview
dAIbetes is an intelligent assistant created to provide concrete support for individuals facing the daily challenges of diabetes, especially those who may struggle to manage the complexity of the disease independently.

Recognizing that reliable help shouldn't depend on a signal, GemmaPulse is designed to break down technological barriers: it requires no internet connection. By leveraging the local power of Gemma 4, the app provides grounded medical support even in remote locations or offline situations. This ensures that the user is never alone in managing their health, providing a "safety net" that is available in any place, at any hour.

# Key Features

**📸 Multimodal Meal Analysis:** Upload a photo of your meal; the AI identifies the food and estimates its carbohydrate content.

**🧮 Smart Insulin Calculator:** Add multiple items to your "plate" for a total carbohydrate count and precise insulin dose suggestions (based on I:C Ratio).

**💉 Active Insulin Correction:** Prevents "insulin stacking" by calculating Insulin on Board (IOB) for corrections between meals.

**💬 Medical RAG Chat:** A chat interface grounded in medical protocols to answer your questions about nutrition and management.

**📊 Health Insights:** Visualizes glucose trends and generates AI-driven weekly clinical reports.

**🆘 Safety Protocols:** Quick access to emergency rules (like the "Rule of 15") for hypo/hyperglycemia.

# Getting started
Follow these steps to run dAIbetes locally on your machine:

### 1. Prerequisites
Ensure you have **Python 3.9+** and **Ollama** installed on your system.
* Download Ollama: [ollama.com](https://ollama.com)

### 2. Prepare the AI models
Open your terminal and download the three models required for the app:
```bash
ollama pull gemma4
ollama pull llava
ollama pull nomic-embed-text
```

### 3. Clone the repository

### 4. Install the dependencies
Install the necessary python libraries:
```bash
pip install -r requirements.txt
```
### 5. Run the application
Start the Stramlit interface:
```bash
streamlit run app.py
```
The app will automatically open in your default browser.

## Tech stack
* **LLM:** Gemma 4 (via Ollama)
* **Vision:** Llava
* **Embeddings:** Nomic-embed-text
* **Orchestration:** LangChain
* **Database:** ChromaDB (Local Vector Store)
* **Frontend:** Streamlit
