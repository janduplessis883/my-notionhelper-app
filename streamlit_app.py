import pandas as pd 
from notionhelper import NotionHelper
from notion_blockify import Blockizer
import streamlit as st
from groq import Groq

from main import get_partners_agenda, send_email, run_partners_agenda, run_team_agenda
from razor_db_create_new_page import render_notion_page_creator

# Initialize Groq client
client = Groq(api_key=st.secrets["GROQ_API_KEY"])




# Streamlit app configuration
st.set_page_config(page_title="<my-notionhelper-app>", page_icon=":material/tooltip:", layout="centered")

# Authentication check
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# If not authenticated, show passcode entry
if not st.session_state.authenticated:
    st.header(":material/lock: Access Required")
    st.markdown("Please enter the passcode to access the application.")
    
    passcode_input = st.text_input("Passcode", type="password", key="passcode_input")
    
    if st.button("Submit", type="primary"):
        if passcode_input == st.secrets["passcode"]:
            st.session_state.authenticated = True
            st.success("Access granted!")
            st.rerun()
        else:
            st.error("Incorrect passcode. Please try again.")
    
    st.stop()

# Main app content (only shown if authenticated)
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

    meeting_date = st.date_input("Select Meeting Date", key="team_meeting_date")
    email_list = st.multiselect("Select Email Recipients", options=['jan.duplessis@nhs.net', 'asteeden@nhs.net', 'jenny.bedford@nhs.net', 'shuman.hussein@nhs.net'], key="team_email_list")
    preview_agenda = st.checkbox("Preview Agenda Before Sending", key="team_preview") 
    if preview_agenda:
        button_text = "Generate & Preview Agenda"
    else:
        button_text = "Send Agenda Email"  
    if st.button(button_text, key="team_button"):
        if not email_list:
            st.warning("Please select at least one email recipient.")
        else:
            run_team_agenda(meeting_date.strftime("%d %b %Y"), email_list, preview_agenda)


elif pages == "Tasks":
    st.caption("Tasks")



elif pages == "Calendar":
    st.caption("Calendar")


elif pages == "HR":
    st.caption("HR") 


elif pages == "Write to URL":
    render_notion_page_creator(model=model)



