#!/usr/bin/env python3
import os, requests, json, sys
API_KEY=open(os.path.expanduser('~/.config/resend/api_key')).read().strip()
URL='https://api.resend.com/emails'

def send_email(to, subject, text, reply_to=None, from_email='hello@attribut.me'):
    headers={'Authorization':f'Bearer {API_KEY}','Content-Type':'application/json'}
    data={'from': from_email, 'to':[to], 'subject':subject, 'text':text}
    if reply_to: data['reply_to']=reply_to
    r=requests.post(URL, headers=headers, data=json.dumps(data))
    r.raise_for_status()
    return r.json()

if __name__=='__main__':
    if len(sys.argv)<4:
        print('Usage: send_via_resend.py to subject bodyfile [reply_to]')
        sys.exit(1)
    to=sys.argv[1]
    subject=sys.argv[2]
    body=open(sys.argv[3]).read()
    reply_to=sys.argv[4] if len(sys.argv)>4 else None
    print(send_email(to,subject,body,reply_to))
