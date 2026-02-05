import pandas as pd
import streamlit as st 
from notionhelper import NotionHelper
import json
import os

notion = st.secrets["NOTION_TOKEN"]
resend_api = st.secrets["RESEND_API_KEY"]
partners_db_id = st.secrets["PARTNERS_AGENDA_ID"]
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

def get_partners_agenda(subject = "Partners' Meeting Agenda"):
    # Fetch the data

    work = nh.get_data_source_pages_as_dataframe(partners_db_id)

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

def run_partners_agenda(date_of_meeting, email_list, preview_agenda=False):
    with st.spinner("Generating HTML & Sending email...", show_time=True):
        subject, body = get_partners_agenda(subject = f"Partners' Meeting Agenda - {date_of_meeting}")
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
                    st.success(f":material/done_outline: `{email_return}`  \nTo: `{mail}`  Subject: `{subject}`")
    
            except requests.exceptions.RequestException as e:
                st.error(f"Failed to send email: {e}")
                return None
