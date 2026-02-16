from notionhelper import NotionHelper
import json
import os

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
nh = NotionHelper(NOTION_TOKEN)

import os, requests, json, sys
from notionhelper import NotionHelper

# Authentication
# TIP: Move this to an environment variable later for better security!

URL='https://api.resend.com/emails'

def send_email(to, subject, text, reply_to='jan.duplessis@nhs.net', from_email='hello@attribut.me'):
    headers={'Authorization':f'Bearer {RESEND_API_KEY}','Content-Type':'application/json'}
    data={'from': from_email, 'to':[to], 'subject':subject, 'html':text}
    if reply_to: data['reply_to']=reply_to
    r=requests.post(URL, headers=headers, data=json.dumps(data))
    r.raise_for_status()
    return r.json()

def get_partners_agenda(subject = "Partners' Meeting Agenda"):
    # Fetch the data
    print("🫛 Fetching data from Notion...")
    work = nh.get_data_source_pages_as_dataframe('21cfdfd6-8a97-801e-afbe-000bbceea6f9')

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
        body_content += f"<h2>{item['agenda_item']}</h2>"
        body_content += f"<p>{item['brief_description']}</p>"
        body_content += f"<p>Person: <b>{item['person']}</b></p><br>"
    body = body.replace('{{BODY}}', body_content)

    return subject, body

if __name__ == '__main__':
    TEST_RUN = True         #🅾️ Important Test before sending 
    date_of_meeting = '6 Feb 2026'
    
    if TEST_RUN:
        email_list = 'drjanduplessis@icloud.com'
    else:
        email_list = 'jan.duplessis@nhs.net'
        
    
    subject, body = get_partners_agenda(subject = f"Partners' Meeting Agenda - {date_of_meeting}")
    
    send_email(email_list, subject, body)
    print(f"📧 Email sent with subject: {subject} to {email_list}")
