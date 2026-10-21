
import requests

API_URL = "https://dweller-silicon-cloak.ngrok-free.dev/generate_sql"
#https://dweller-silicon-cloak.ngrok-free.dev

#user_query = "Who is the top scorer"

def send_query_to_flask(query):
    response = requests.post(API_URL, json={"query": query})
    sql=response.json()["sql"]
    return sql


#print(send_query_to_flask(user_query))