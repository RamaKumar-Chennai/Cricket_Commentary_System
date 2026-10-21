import json
from langchain_community.document_loaders import Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
import google.generativeai as genai
from dotenv import load_dotenv
import os



# --- Load environment variables ---
load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")

# --- Configure Gemini ---
genai.configure(api_key=gemini_api_key)

# Gemini wrapper
from langchain_google_genai import ChatGoogleGenerativeAI
sql_llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

# --- Step 1: Load both Word docs ---

loader1 = Docx2txtLoader(r"D:\VS_CODE\INTEL-AIML\Automated_Sports_Commentary_System\QUESTION_SQL.docx")

docs = loader1.load() 

# --- Step 2: Split into chunks ---
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
split_docs = splitter.split_documents(docs)

# --- Step 3: Build embeddings + FAISS vector store ---
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vect = FAISS.from_documents(split_docs, embeddings)
vect.save_local("vector_emb")

# --- Step 4: Wrap vector search in a function ---

#Perform similarity search on FAISS vectorstore.
#Returns a list of Document objects (with page_content + metadata).

def vector_search(query, top_k=3):
    """Perform similarity search on the vector DB."""
    results = vect.similarity_search(query, k=top_k)
    context = "\n".join([f"- {d.page_content} | {d.metadata}" for d in results])
    return context

context= vector_search(query, top_val=3) 

# --- Chatbot answer (RAG Part) ---
def get_answer(query: str):
    # Step 1: Retrieve relevant docs 
    
    

    # Step 2: Build prompt
    prompt = (
        f""" You are an AI assistant.You need to generate SQL query for the user's natural language query.
            
            This is the user query.
            User query: {query}

            Use this relevant context to answer the customer's query.
            Relevant context:{context}"""
        
    )

    try:
        output = llm.invoke(prompt).strip()        
        
    except Exception as e:
        output =  f"Ollama invoke failed: {e}"

    return output
