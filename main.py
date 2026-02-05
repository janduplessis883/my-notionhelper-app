import pandas as pd
import streamlit as st 
from notionhelper import NotionHelper
import json
import os

notion = st.secrets["NOTION_TOKEN"]
resend_api = st.secrets["RESEND_API_KEY"]
partners_db_id = st.secrets["PARTNERS_AGENDA_ID"]
team_db_id = st.secrets["TEAM_AGENDA_ID"]
nh = NotionHelper(notion)

import os, requests, json, sys
from notionhelper import NotionHelper

# Authentication
# TIP: Move this to an environment variable later for better security!

URL='https://api.resend.com/emails'

def send_email(to, subject, text, reply_to='jan.duplessis@nhs.net', from_email='hello@attribut.me'):

    headers={'Authorization':f'Bearer {resend_api}','Content-Type':'application/json'}
    data={'from': from_email, 'to':[to], 'subject':subject, 'html':text}
    if reply_to: data['reply_to']=reply_to
    r=requests.post(URL, headers=headers, data=json.dumps(data))
    r.raise_for_status()
    return r.json()

def get_agenda(database_id: str, subject: str = "Meeting Agenda"):
    """
    Generic function to get agenda from any database.
    
    Args:
        database_id: The Notion database ID to fetch from
        subject: The email subject line
        
    Returns:
        Tuple of (subject, html_body)
    """
    # Fetch the data
    work = nh.get_data_source_pages_as_dataframe(database_id)

    print("✅ Data fetched successfully!")
    current = work[work['Completed'] == False]
    # Select columns and rename them to match your lowercase/snake_case requirements

    df_subset = current[['Completed', 'Agenda Item', 'Brief Description', 'Person', 'notion_page_id']].copy()
    df_subset.columns = ['discussed', 'agenda_item', 'brief_description', 'person', 'notion_page_id']
    df_subset.sort_values(by=['person', 'agenda_item'], ascending=True, inplace=True, ignore_index=True)

    # Convert the DataFrame to a list of dictionaries
    result = df_subset.to_dict(orient='records')

    # Format the agenda items into an HTML template
    with open('notification_template.html', 'r') as f:
        template = f.read()
    body = template.replace('{{SUBJECT}}', subject)
    body_content = ""
    for item in result:
        body_content += f"<h3>{item['agenda_item']}</h3>"
        body_content += f"<p>{item['brief_description']}</p>"
        body_content += f"<p>Person: <b>{item['person']}</b></p><br>"
    body = body.replace('{{BODY}}', body_content)

    return subject, body


def get_partners_agenda(subject: str = "Partners' Meeting Agenda"):
    """Get Partners' agenda - wrapper for get_agenda."""
    return get_agenda(partners_db_id, subject)


def get_team_agenda(subject: str = "Team Meeting Agenda"):
    """Get Team agenda - wrapper for get_agenda."""
    return get_agenda(team_db_id, subject)


def run_agenda(database_id: str, date_of_meeting: str, email_list: list, preview_agenda: bool = False, meeting_type: str = "Meeting"):
    """
    Generic function to run agenda generation and email sending.
    
    Args:
        database_id: The Notion database ID to fetch from
        date_of_meeting: Date string for the meeting
        email_list: List of email addresses
        preview_agenda: Whether to preview only or send emails
        meeting_type: Type of meeting for subject line
    """
    with st.spinner("Generating HTML & Sending email...", show_time=True):
        subject, body = get_agenda(database_id, subject=f"{meeting_type} Agenda - {date_of_meeting}")
        if preview_agenda:
            expander_text = "HTML Email Preview"
        else:
            expander_text = "HTML Email Preview + Send Email"
        with st.expander(expander_text, icon=":material/html:"):
            st.html(body)
            
        if preview_agenda == False:
            try:
                for mail in email_list:
                    email_return = send_email(mail, subject, body)
                    st.success(f":material/done_outline: `{email_return}`  \nTo: `{mail}`  \nSubject: `{subject}`")
    
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to send email: {e}")
                return None


def run_partners_agenda(date_of_meeting: str, email_list: list, preview_agenda: bool = False):
    """Run Partners' agenda - wrapper for run_agenda."""
    return run_agenda(partners_db_id, date_of_meeting, email_list, preview_agenda, "Partners' Meeting")


def run_team_agenda(date_of_meeting: str, email_list: list, preview_agenda: bool = False):
    """Run Team agenda - wrapper for run_agenda."""
    return run_agenda(team_db_id, date_of_meeting, email_list, preview_agenda, "Team Meeting")
