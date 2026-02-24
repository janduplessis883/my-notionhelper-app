import pandas as pd
from notionhelper import NotionHelper
from notion_blockify import Blockizer
import streamlit as st
from groq import Groq
from datetime import date, datetime, timedelta
import html

from main import get_partners_agenda, send_email, run_partners_agenda, run_team_agenda, run_github_trending_workflow, show_tasks
from razor_db_create_new_page import render_notion_page_creator

# Initialize Groq client
client = Groq(api_key=st.secrets["GROQ_API_KEY"])
nh = NotionHelper(st.secrets["NOTION_TOKEN"])




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
st.image("images/notion-logo.png")
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


def save_task_summary_to_notion(summary_markdown: str, summary_title: str) -> str:
    now_iso = datetime.now().astimezone().isoformat(timespec="minutes")
    title_datetime = datetime.now().astimezone().strftime("%d %b %Y %H:%M")
    task_title = f"{summary_title} - {title_datetime}"
    properties = {
        "Task": {
            "title": [
                {
                    "text": {
                        "content": task_title
                    }
                }
            ]
        },
        "Date": {
            "date": {
                "start": now_iso
            }
        },
        "Priority": {
            "select": {
                "name": "High"
            }
        }
    }

    page = nh.new_page_to_data_source(st.secrets["TASKS_ID"], page_properties=properties)
    page_id = page.get("id")
    if not page_id:
        raise ValueError("Notion did not return a page id for the new task summary.")

    blocks = Blockizer().convert(summary_markdown)
    if blocks:
        for i in range(0, len(blocks), 100):
            nh.append_page_body(page_id, blocks=blocks[i:i + 100])
    return page_id

with st.sidebar:
    st.title(":material/settings: Settings")
    PAGE_SELECTION = ["Python Script Runner", "Partners' Agenda", "Team Agenda", "Tasks", "Calendar", "Human Resources", "Write to URL"]
    pages = st.selectbox("Page Selectioon", PAGE_SELECTION, index=0)
    st.divider()
    MODEL_OPTIONS = ["moonshotai/kimi-k2-instruct-0905", "meta-llama/llama-4-maverick-17b-128e-instruct", "qwen/qwen3-32b", "openai/gpt-oss-120b", "groq/compound-mini", "groq/compound"]
    model = st.selectbox("Model Selection", MODEL_OPTIONS, index=3)
    st.space(size=40)
    st.markdown("`janduplessis883`", text_alignment="center")


if pages == "Partners' Agenda":
    st.caption("Partners' Agenda")

    meeting_date = st.date_input("Select Meeting Date")
    email_list = st.multiselect("Select Email Recipients", options=['jan.duplessis@nhs.net', 'asteeden@nhs.net', 'jenny.bedford@nhs.net', 'shuman.hussein@nhs.net'], default=['jan.duplessis@nhs.net'])
    preview_agenda = st.checkbox("Preview Agenda Before Sending", value=True)
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
    email_list = st.multiselect("Select Email Recipients", options=['jan.duplessis@nhs.net', 'asteeden@nhs.net', 'jenny.bedford@nhs.net', 'shuman.hussein@nhs.net'], key="team_email_list", default=['jan.duplessis@nhs.net'])
    preview_agenda = st.checkbox("Preview Agenda Before Sending", key="team_preview", value=True)
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
        quick = st.button('Quick Wins', width='stretch', icon=":material/bolt:")
        top_five = st.button("5 Quick Tasks", width='stretch', icon=":material/counter_5:")

    with col2:
        all = st.button("All - Order of Execution", width='stretch', icon=":material/automation:")
        urgent = st.button("All - Order of Urgency", width='stretch', icon=":material/bomb:")

    prompt = None
    summary_title = None
    if quick:
        prompt = f"""Review my TODO list and select 2 items that I can complete in 15 min each, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
        summary_title = "2 Consolidated Tasks"
    elif top_five:
        prompt = f"""Review my TODO list and select 5 tasks that I can complete in 30 min, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
        summary_title = "5 Consolidated Tasks"
    elif all:
        prompt = f"""Review my TODO list and list all my task in a logical order to complete them in, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
        summary_title = "Consolidated Tasks"
    elif urgent:
        prompt = f"""Review my TODO list and any URENT tasks, don't use tables in your response.
        Here is my todo list:
        {st.session_state['tasks']}
        """
        summary_title = "Urgent Consolidated Tasks"
    else:
        st.stop()

    with st.spinner("LLM doing it's thing...", show_time=True):
        response = ask_groq(prompt)
        with st.expander("LLM Response", icon=":material/robot_2:", expanded=True):
            st.markdown(response)
        with st.expander("Raw markdown code", icon=":material/code:", expanded=False):
            st.code(response, wrap_lines=True, language='markdown')

        try:
            page_id = save_task_summary_to_notion(response, summary_title or "Consolidated Tasks")
            st.success(f":material/check_circle: Saved summary to Tasks database (Page ID: `{page_id}`)")
        except Exception as e:
            st.error(f":material/error: Failed to save summary to Tasks database: {e}")

elif pages == "Calendar":
    st.caption("Calendar - This is what your week looks like.")
    today = date.today()
    end_date = today + timedelta(days=7)

    cal = nh.get_data_source_pages_as_dataframe('303fdfd6-8a97-80f6-bbcc-000b5fe219ab')
    cal['Date'] = pd.to_datetime(cal['Date'], format='mixed', dayfirst=False, utc=True, errors='coerce')
    next_week = cal[(cal['Date'].dt.date >= today) & (cal['Date'].dt.date <= end_date)].copy()
    next_week.sort_values(by='Date', ascending=True, inplace=True)

    def get_value(row, options):
        for col in options:
            if col in row.index:
                value = row[col]
                if isinstance(value, (list, tuple, set)):
                    items = [str(v) for v in value if pd.notna(v)]
                    if items:
                        return ", ".join(items)
                    continue
                try:
                    if pd.notna(value):
                        return str(value)
                except Exception:
                    # Fallback for any non-scalar values not handled above
                    if value is not None:
                        return str(value)
        return ""

    def format_start_datetime(ts):
        if pd.isna(ts):
            return "No start date"
        local_tz = datetime.now().astimezone().tzinfo
        local_ts = ts.tz_convert(local_tz) if getattr(ts, "tzinfo", None) else ts
        return local_ts.strftime("%a %d %b %Y, %H:%M")

    if next_week.empty:
        st.info("No calendar events found for the next 7 days.")
    else:
        cards = [
            "<style>"
            ".cal-wrap { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }"
            ".cal-card { border: 1px solid #e3e8ef; border-radius: 12px; padding: 14px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }"
            ".cal-date { font-size: 0.85rem; font-weight: 700; color: #4294c2; margin-bottom: 6px; }"
            ".cal-event { font-size: 1.05rem; font-weight: 700; color: #14213d; margin-bottom: 6px; }"
            ".cal-desc { font-size: 0.85rem; color: #2f3e46; margin-bottom: 8px; }"
            ".cal-meta { font-size: 0.85rem; color: #495057; margin-bottom: 4px; }"
            ".cal-link a { color: #4294c2; text-decoration: none; }"
            ".cal-link a:hover { text-decoration: underline; }"
            "</style>",
            '<div class="cal-wrap">',
        ]
        for _, row in next_week.iterrows():
            date_str = html.escape(format_start_datetime(row['Date']))
            event = html.escape(get_value(row, ["Event", "Name", "Title"]) or "Untitled Event")
            desc = html.escape(get_value(row, ["Description", "Discription", "Brief Description"]) or "No description")
            tag = html.escape(get_value(row, ["Tag", "Tags"]) or "N/A")
            teams_url = get_value(row, ["Teams Link", "Teams URL", "Teams Url", "URL", "Link"])

            teams_html = (
                f'<a href="{html.escape(teams_url, quote=True)}" target="_blank" rel="noopener noreferrer">Open Teams</a>'
                if teams_url
                else "N/A"
            )
            cards.append(
                f'<div class="cal-card">'
                f'<div class="cal-date">{date_str}</div>'
                f'<div class="cal-event">{event}</div>'
                f'<div class="cal-desc">{desc}</div>'
                f'<div class="cal-meta"><b>Tag:</b> {tag}</div>'
                f'<div class="cal-meta cal-link"><b>Teams URL:</b> {teams_html}</div>'
                f'</div>'
            )
        cards.append("</div>")
        st.html("".join(cards))


elif pages == "HR":
    st.caption("HR")


elif pages == "Write to URL":
    render_notion_page_creator(model=model)


elif pages == "Python Script Runner":
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
