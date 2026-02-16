import pandas as pd
import streamlit as st 
from notionhelper import NotionHelper
import json
import os

notion = st.secrets["NOTION_TOKEN"]
resend_api = st.secrets["RESEND_API_KEY"]
partners_db_id = st.secrets["PARTNERS_AGENDA_ID"]
team_db_id = st.secrets["TEAM_AGENDA_ID"]
tasks_db_id = st.secrets["TASKS_ID"]
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
        body_content += f"<p><img width=\"18\" height=\"18\" src=\"https://img.icons8.com/forma-thin/24/person-male.png\" alt=\"person-male\"/> <b>{item['person']}</b></p><br>"
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
    return run_agenda(team_db_id, date_of_meeting, email_list, preview_agenda, "SMW Team Meeting")


def get_github_trending_page():
    """
    Fetch trending Python repositories from GitHub and add them to Notion database.
    
    Returns:
        int: Number of repositories processed
    """
    import gtrending
    from datetime import datetime
    
    # Fetch trending python repositories for the day
    repos = gtrending.fetch_repos(language="python", spoken_language_code="en", since="daily")
    
    processed_count = 0
    for repo in repos[:20]:
        owner = repo['fullname'].split('/')[0]
        # Reliable way to get the icon (GitHub redirects this to the real image)
        icon_url = f"https://github.com/{owner}.png"
        
        print(f"Stars today: +{repo['currentPeriodStars']}")
        print(f"Total Stars: {repo['stars']}")
        print(f"URL: {repo['url']}")
        print("-" * 20)

        # Ensure todaytime is in ISO 8601 format (YYYY-MM-DD)
        todaytime = datetime.now().date().isoformat()

        properties = {
            'Repo': {
                'title': [
                    {
                        'text': {
                            'content': repo['fullname']
                        }
                    }
                ]
            },
            'URL': {
                'url': repo['url']
            },
            'Stars Today': {
                'number': int(repo['currentPeriodStars'])
            },
            'Total Stars': {
                'number': int(repo['stars'])
            },
            'Date': {
                'date': {
                    'start': todaytime
                }
            },
            'Icon': {
                'files': [
                    {
                        'type': 'external',
                        'name': 'GitHub Icon',
                        'external': {
                            'url': icon_url
                        }
                    }
                ]
            }
        }
        nh.new_page_to_data_source('2f4fdfd6-8a97-805b-a6e9-000b8149b31f', page_properties=properties)
        print("✅")
        processed_count += 1
    
    return processed_count


def delete_duplicate_pages():
    """
    Find and delete duplicate repository entries in the Notion database.
    
    Returns:
        list: List of page IDs that were deleted
    """
    data = nh.get_data_source_pages_as_dataframe('2f4fdfd6-8a97-805b-a6e9-000b8149b31f')
    data['Date'] = pd.to_datetime(data['Date'], format='%Y-%m-%d')
    data.sort_values(by='Date', ascending=False, inplace=True)
    duplicate_ids = data.loc[data.duplicated(subset=['Repo'], keep='first'), 'notion_page_id'].tolist()
    return duplicate_ids


def run_github_trending_workflow():
    """
    Complete workflow: Fetch trending GitHub repos and clean up duplicates.
    
    Returns:
        tuple: (repos_added, duplicates_removed)
    """
    print("🚀 Starting GitHub Trending workflow...")
    
    # Step 1: Fetch and add trending repos
    repos_added = get_github_trending_page()
    print(f"\n✅ Added {repos_added} repositories")
    
    # Step 2: Remove duplicates
    print("\n🔍 Loading DataFrame and checking for duplicates...")
    duplicate_ids = delete_duplicate_pages()
    
    duplicates_removed = 0
    for dup in duplicate_ids:
        outcome = nh.move_page_to_trash(dup)
        print(f"❌ Moved to trash - page_id: {dup}")
        duplicates_removed += 1
    
    print(f"\n✅ Removed {duplicates_removed} duplicate entries")
    print("🎉 GitHub Trending workflow completed!")
    
    return repos_added, duplicates_removed


def show_tasks():
    tasks = nh.get_data_source_pages_as_dataframe(tasks_db_id)
    f_tasks = tasks[['Date','Status','Priority','Task','Formula', 'notion_page_id']].copy()
    f_tasks['Date'] = pd.to_datetime(f_tasks['Date'], format='ISO8601')
    not_done = f_tasks[f_tasks['Status'] != 'Done']
    
    return not_done