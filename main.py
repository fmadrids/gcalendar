from __future__ import print_function
import httplib2

import os
from subprocess import check_call
import datetime
import re

from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

import json
import smtplib

try:
    import argparse
    flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
except ImportError:
    flags = None

EMAIL_FROM = ''
EMAIL_TO = ''
EMAIL_USERNAME = ''
EMAIL_PASSWORD = ''

SERVER_FILE = ''
NOTIFICATION_DAYS = 0

CLIENT_SECRET_FILE = ''
CREDENTIALS_FILE = ''
CALENDAR_ID = ''
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
APPLICATION_NAME = 'StratioCalendar'
NUMEVENTS = 12


def read_servers(server_file):
    f = open(server_file, "r", encoding="utf-8")
    servers = json.load(f)
    f.close()
    return servers


def read_config():
    global EMAIL_FROM
    global EMAIL_TO
    global EMAIL_USERNAME
    global EMAIL_PASSWORD
    global NOTIFICATION_DAYS
    global CLIENT_SECRET_FILE
    global CREDENTIALS_FILE
    global CALENDAR_ID
    global DELTA_TIME
    global SERVER_FILE

    f = open("stratioautomation.conf", "r", encoding="utf-8")
    config = json.load(f)
    EMAIL_FROM = config["email"]["from"]
    EMAIL_TO = config["email"]["to"]
    EMAIL_USERNAME = config["email"]["username"]
    EMAIL_PASSWORD = config["email"]["password"]
    NOTIFICATION_DAYS = int(config["gcalendar"]["notificationdays"])
    CLIENT_SECRET_FILE = config["gcalendar"]["secretfile"]
    CREDENTIALS_FILE = config["gcalendar"]["credentialsfile"]
    CALENDAR_ID = config["gcalendar"]["calendarid"]
    SERVER_FILE = config["serverfile"]
    f.close()


def send_gmail(Text):
    """Sends an email through Gmail

    Used to notify the Systems department that the servers are going to be reinstalled.

    Returns:
        True if it has sent the email successfully
    """

    From = "Stratio Automation"
    To = "Stratio Sistemas"
    Subject = "Server reinstallation"
    msg = 'From: %s\nTo: %s\nSubject: %s\n\n%s' % (From, To, Subject, Text)
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.starttls()
    server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
    server.sendmail(EMAIL_FROM, EMAIL_TO, msg)
    server.quit()
    return True


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    #home_dir = os.path.expanduser('~')
    # TODO: Change homedir
    home_dir = '/home/francisco/Temp'
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir, CREDENTIALS_FILE)
    client_secret_path = os.path.join(credential_dir, CLIENT_SECRET_FILE)

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(client_secret_path, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials


def process_server(server):
    ipminame = server["name"]
    ipmiip = server["ipaddress"]
    ipmiusername = server["username"]
    ipmipassword = server["password"]

    # Send email
    email_text = 'Processing server \"%s\": it is going to be reinstalled!!' % ipminame
    send_gmail(email_text)
    # Configure PXE
    #retcode = check_call(["ipmitool", "-I lanplus", "-A password", "-H" + ipmiip, "-U" + ipmiusername, "-P " + ipmipassword, "chassis power status"])
    retcode = check_call(["ls", "-l"])
    if retcode != 0:
        email_text = 'Error when configuring PXE on server \"%s\"!!' % ipminame
        send_gmail(email_text)
        return
    # Reboot server
    #retcode = check_call(["ipmitool", "-I lanplus", "-A password", "-H" + ipmiip, "-U" + ipmiusername, "-P " + ipmipassword, "chassis power status"])
    retcode = check_call(["ls", "-l"])
    if retcode != 0:
        email_text = 'Error when resetting server \"%s\"!!' % ipminame
        send_gmail(email_text)
        return


def process_event(event, server_list):
    print(event['summary'])

    event_servers = str(event['description']).lower().split(':')

    # Iterate over the servers
    for event_server in event_servers:
        for server in server_list["servers"]:
            if server["name"] == event_server:
                process_server(server)
                break


def main():
    read_config()
    server_list = read_servers(SERVER_FILE)

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)

    ahora = datetime.datetime.utcnow()  # Para poder restar fechas luego
    now = ahora.isoformat() + 'Z' # 'Z' indicates UTC time
    print('Getting the upcoming ' + str(NUMEVENTS) + ' events')
    eventsResult = service.events().list(
        calendarId=CALENDAR_ID, timeMin=now, maxResults=NUMEVENTS, singleEvents=True,
        orderBy='startTime').execute()
    events = eventsResult.get('items', [])

    if not events:
        print('No upcoming events found.')
        exit(0)
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        #Parseamos la fecha del evento para poder meterla en un datetime
        if re.match(r'^.*\+.*$', start):
            prefijo = start[:start.index('+')]
            fecha = datetime.datetime.strptime(prefijo, '%Y-%m-%dT%H:%M:%S')
        elif re.match(r'^[^+]*$', start):
            fecha = datetime.datetime.strptime(start, '%Y-%m-%d')
        else:
            continue
        tdelta = fecha - ahora
        # Se debe reinstalar: menos de un día ¡y que sea en el futuro!
        if tdelta < datetime.timedelta(days=1) and ahora < fecha:
            process_event(event, server_list)
        elif tdelta < datetime.timedelta(days=NOTIFICATION_DAYS) and ahora < fecha:
            msg = 'Please prepare installation of event %s: %s\n\nEvent date: %s' % (event['summary'], event['description'], start)
            send_gmail(msg)

if __name__ == '__main__':
    main()