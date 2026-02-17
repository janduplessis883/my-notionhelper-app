import pandas as pd 
from notionhelper import NotionHelper
from notion_blockify import Blockizer
import streamlit as st
from groq import Groq

from main import get_partners_agenda, send_email, run_partners_agenda, run_team_agenda, run_github_trending_workflow, show_tasks
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
st.logo("images/notion.png", size="medium")
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
    PAGE_SELECTION = ["Python-script-runner", "Partners' Agenda", "Team Agenda", "Tasks", "Calendar", "Human Resources", "Write to URL"]
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
    st.caption("Tasks - Summarize my To-Do list with LLM")
    if 'tasks' not in st.session_state:
        st.session_state['tasks'] = show_tasks()
        
    col1, col2 = st.columns(2)
    
    with col1:
        quick = st.button('Quick Wins', width='stretch', icon=":material/bolt:", type='primary')
        top_five = st.button("5 Quick Tasks", width='stretch', icon=":material/counter_5:", type='primary')
        
    with col2:
        all = st.button("All - Order of Execution", width='stretch', icon=":material/automation:")
        urgent = st.button("All - Order of Urgency", width='stretch', icon=":material/bomb:")
        
    prompt = None
    if quick:
        prompt = f"""Review my TODO list and select 2 items that I can complete in 15 min each, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
    elif top_five:
        prompt = f"""Review my TODO list and select 5 tasks that I can complete in 30 min, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
    elif all:
        prompt = f"""Review my TODO list and list all my task in a logical order to complete them in, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
    elif urgent:
        prompt = f"""Review my TODO list and any URENT tasks, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
    else:
        st.stop()
        
    with st.spinner("LLM doing it's thing...", show_time=True):
        response = ask_groq(prompt)
        with st.expander("LLM Response", icon=":material/robot_2:", expanded=True):
            st.markdown(response)
        with st.expander("Raw markdown code", icon=":material/code:", expanded=False):
            st.code(response)

elif pages == "Calendar":
    st.caption("Calendar")


elif pages == "HR":
    st.caption("HR") 


elif pages == "Write to URL":
    render_notion_page_creator(model=model)


elif pages == "Python-script-runner":
    st.caption("Python-script-runner") 
    c1, c2 = st.columns(2)
    with c1:
        trending_github = st.button("Trending GitHub Repos", icon=":material/deployed_code:", width='stretch')
        if trending_github:
            with st.spinner("Fetching trending GitHub repositories...", show_time=True):
                try:
                    repos_added, duplicates_removed = run_github_trending_workflow()
                    st.success(f":material/check_circle: Successfully added {repos_added} trending Python repositories!")
                    if duplicates_removed > 0:
                        st.info(f":material/delete: Removed {duplicates_removed} duplicate entries")
            
                except Exception as e:
                    st.error(f":material/error: Error running GitHub trending workflow: {e}")
    with c2:
        st.link_button("Notion Github Repos", "https://www.notion.so/janduplessis/2f4fdfd68a9780a1a74fd03b7008ed99?v=2f4fdfd68a9780cbad38000c27fcd66a&source=copy_link", type='secondary', width='stretch', icon=':material/link:')
   