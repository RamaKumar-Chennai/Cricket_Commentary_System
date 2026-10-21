from typing import TypedDict
import os
from dotenv import load_dotenv

from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START, END

from flask_client import send_query_to_flask
from sql_insert_select import select_sql_record


from langchain_community.vectorstores import FAISS

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pandas as pd

#from langchain.docstore.document import Document as LangDocument  # for LangChain docs
from langchain_core.documents import Document





class State(TypedDict):
    query: str
    classifier_answer: str   # classifier output: "sql" or "rag"
    agent: str               # which agent ran
    agent_output: str        # agent's output
    final_answer: str        # combined result


def build_classifier_app():
    """Build and return the LangGraph app for query classification."""

    # --- Load environment variables ---
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")

    # --- Initialize Groq LLM for classification ---
    classifier_llm = ChatGroq(
        model="openai/gpt-oss-20b",   # faster model for classification
        api_key=api_key,
        temperature=0
    )

    # --- Classifier prompt ---
    classifier_prompt = PromptTemplate.from_template("""
    You are an intent classifier for a cricket assistant.
    Classify the user query into one of two categories:

    - sql: if it asks about current or live match statistics 
    (runs, overs, wickets, balls delivered, deliveries, scorecard, this innings, 
    top scorer, highest runs in this match, leading run-getter, boundaries, 
    sixes, fours, strike rate in this match, bowler performance such as 
    balls bowled, extras, wickets taken, partnership runs between batters,
    which batters have played in an innings, which bowlers have bowled in an innings,
    who achieved the highest runs, who took the maximum wickets, who scored the most boundaries,
    who is the top scorer in this innings, which bowler conceded the most runs,
    which batter has the best strike rate in this match).
    - rag: if it asks about general cricket knowledge 
    (a player's career stats or history, rules, trivia, records across matches,
    comparisons across tournaments, ICC rankings, historical achievements,
    famous matches, player biographies, cricket laws, or general trivia).

    ### Examples:
    Query: "Who are the batters who have played in innings 1"
    Answer: sql

    Query: "Who are the bowlers who have bowled in innings 2"
    Answer: sql

    Query: "What is the score by KKR"
    Answer: sql

    Query: "Who achieved the highest runs"
    Answer: sql

    Query: "Who took the maximum wickets"
    Answer: sql

    Query: "Which batter hit the most boundaries in this match"
    Answer: sql

    Query: "Give me Sachin Tendulkar’s career batting average"
    Answer: rag

    Query: "Explain the rules of LBW"
    Answer: rag

    Query: "What is Virat Kohli’s highest ODI score"
    Answer: rag

    Query: {query}

    Return exactly one word: either sql or rag. Do not add any other text.


    """)



    # --- Build classifier pipeline ---
    classifier_chain = classifier_prompt | classifier_llm

    # --- LangGraph nodes ---
    def supervisor(state: State):
        query = state["query"]
        intent = classifier_chain.invoke({"query": query}).content.strip().lower()
        print("the intent in supervisor fn is ",intent)
        return {"classifier_answer": intent}


    

    def sql_agent(state: State):
        import re
        from tabulate import tabulate
        print("SQL agent called")
        user_query = state["query"]
        print(" the user query in sgl_agent fn before sending to flask is ", user_query)

        # Step 1: get SQL from Flask
        sql_query = send_query_to_flask(user_query)
        print(" the sql query in sgl_agent fn after sending to flask is ", sql_query)

        # ✅ Clean SQL before execution
        def clean_sql(sql: str) -> str:
            # Collapse multiple spaces/newlines
            sql = re.sub(r'\s+', ' ', sql)
            return sql.strip()

        sql_query = clean_sql(sql_query)
        print(" the cleaned sql query is ", sql_query)



        # Step 2: run SQL against DB
        df = select_sql_record(sql_query)
        print("the answer in sql agent fn is \n", df)

        # Step 3: format for UI
        if df is not None and not df.empty:
            formatted_answer = tabulate(df, headers="keys", tablefmt="psql", showindex=False)
        else:
            formatted_answer = "No results found"

        print("the formatted answer in sql agent fn is \n", formatted_answer)

        return {
            "agent_output": formatted_answer,
            "agent": "sql_agent"
        }

    def relevant_context(state: State):
        
        user_query = state["query"].strip()
        print(" the user query in relevant_context fn is ", user_query)
        
        # 1. Load the word doc
        from docx import Document
        from langchain_core.documents import Document as LangDocument


        doc = Document("Cricket_FAQ.docx")

        texts = []
        for para in doc.paragraphs:
            if para.text.strip():
                texts.append(para.text.strip())

        # Convert list of strings into LangChain Document objects
        docs = [LangDocument(page_content=t, metadata={"source": "Cricket_FAQ.docx"}) for t in texts]       
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        split_docs = splitter.split_documents(docs)


        print("len(split_docs) is ",len(split_docs))
        #len(split_docs) is  


        # Step 5: Convert to embeddings
        emb=HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2",model_kwargs={'device':'cpu'})
        vect=FAISS.from_documents(split_docs,emb)
        vect.save_local("vector_emb")


        #Perform similarity search on FAISS vectorstore.
        #Returns a list of Document objects (with page_content + metadata).            
        
        # --- Initialize Groq LLM for classification ---
        rag_llm = ChatGroq(
                model="openai/gpt-oss-20b",   # faster model for classification
                api_key=api_key,
                temperature=0
            )


             
        # Step 1: Retrieve relevant docs 
        results = vect.similarity_search(query= user_query, k=3)
        context = "\n".join([f"- {d}" for d in results])


        # Step 2: Build prompt
        prompt = f"""
                You are a knowledgeable cricket assistant.
                Answer the user's cricket-related query using only the relevant context provided.
                If the context does not contain the answer, say you don't know instead of guessing.

                User query:
                {user_query}

                Relevant context:
                {context}

                Guidelines:
                - Stick strictly to the retrieved context (rules, player stats, history, formats).
                - Do not invent or hallucinate information.
                - Keep the answer clear, concise, and factual.
                - If multiple possible answers exist in the context, summarize them fairly.

                Final Answer:
                """


        try:
            output = rag_llm.invoke(prompt).content.strip()        
        
        except Exception as e:
            output =  f"LLM invoke failed: {e}"

        
        return output

            

    
    def rag_agent(state: State):
        print("RAG agent called")
        output= relevant_context (state)
        
        return {
            "agent_output": output,
            "agent": "rag_agent"
        }

    def response_agent(state: State):
        return {
            "final_answer": 
                
                f"{state['agent_output']}"
            
        }

    # --- Build the graph ---
    graph = StateGraph(State)
    graph.add_node("supervisor", supervisor)
    graph.add_node("sql_agent", sql_agent)
    graph.add_node("rag_agent", rag_agent)
    graph.add_node("response_agent", response_agent)

    graph.add_edge(START, "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        lambda state: state["classifier_answer"],
        {
            "sql": "sql_agent",
            "rag": "rag_agent"
        }
    )

    graph.add_edge("sql_agent", "response_agent")
    graph.add_edge("rag_agent", "response_agent")
    graph.add_edge("response_agent", END)

    return graph.compile()

def clean_nl_query(query: str) -> str:
    import re 
    # 1. Lowercase
    query = query.lower()
    
    # 2. Remove special characters (keep alphanumeric + spaces)
    query = re.sub(r'[^a-z0-9\s]', '', query)
    
    # 3. Collapse multiple spaces → single space
    query = re.sub(r'\s+', ' ', query).strip()
    
    return query



# --- Public function you can call from main app ---
def classify_query(query: str) -> str:
    """Classify a cricket query and execute the corresponding agent."""
    print("the classify_query fn query before cleaning  is")
    print(query)

    # ✅ Clean NL query
    query = clean_nl_query(query)

    print("the classify_query fn query after cleaning is")
    print(query)

    
    app = build_classifier_app()
    state = {"query": query}
    result = app.invoke(state)

    print("result = app.invoke(state) in classify_query fn is ")
    print(result)

    print("result['final_answer'] in classify_query fn is ",result["final_answer"])

    return result["final_answer"]
