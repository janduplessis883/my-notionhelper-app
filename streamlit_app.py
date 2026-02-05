import pandas as pd 
from notionhelper import NotionHelper
from notion_blockify import Blockizer
import streamlit as st


from main import get_partners_agenda, send_email, run_partners_agenda
from razor_db_create_new_page import render_notion_page_creator




# Streamlit app configuration
st.set_page_config(page_title="<my-notionhelper-app>", page_icon=":material/tooltip:", layout="centered")

st.header("<my-notionhelper-app>")
st.logo("images/logo.png", size="medium")
# Simple function to get a response from Groq
def ask_groq(prompt: str, model: str = "openai/gpt-oss-120b"):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=model,
    )
    try:
        return chat_completion.choices[0].message.content
    except Exception as e:
        st.error(f"Error getting response from Groq: {e}")
        return "Error: Could not get a response from Groq."

with st.sidebar:
    st.title(":material/settings: Settings")
    PAGE_SELECTION = ["Partners' Agenda", "Team Agenda", "Tasks", "Calendar", "HR", "Write to URL"]
    pages = st.selectbox("Page Selectioon", PAGE_SELECTION, index=0)
    st.divider()
    MODEL_OPTIONS = ["moonshotai/kimi-k2-instruct-0905", "meta-llama/llama-4-maverick-17b-128e-instruct", "qwen/qwen3-32b", "openai/gpt-oss-120b", "groq/compound-mini", "groq/compound"]
    model = st.selectbox("Model Selection", MODEL_OPTIONS, index=3)
    st.space(size=40)
    st.markdown("`janduplessis883`", text_alignment="center")


if pages == "Partners' Agenda":
    st.caption("Partners' Agenda")

    meeting_date = st.date_input("Select Meeting Date")
    email_list = st.multiselect("Select Email Recipients", options=['jan.duplessis@nhs.net', 'asteeden@nhs.net', 'jenny.bedford@nhs.net', 'shuman.hussein@nhs.net'])
    preview_agenda = st.checkbox("Preview Agenda Before Sending") 
    if preview_agenda:
        button_text = "Generate & Preview Agenda"
    else:
        button_text = "Send Agenda Email"  
    if st.button(button_text):
        if not email_list:
            st.warning("Please select at least one email recipient.")
        else:
            run_partners_agenda(meeting_date.strftime("%d %b %Y"), email_list, preview_agenda)  
    

elif pages == "Team Agenda":
    st.caption("Team Agenda")


elif pages == "Tasks":
    st.caption("Tasks")



elif pages == "Calendar":
    st.caption("Calendar")


elif pages == "HR":
    st.caption("HR") 


elif pages == "Write to URL":
    render_notion_page_creator(model=model)



