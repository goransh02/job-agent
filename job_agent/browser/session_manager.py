import os
import json

SESSION_FILE = "session.json"


def load_session(context):

    if os.path.exists(SESSION_FILE):
        context.add_cookies(json.load(open(SESSION_FILE)))


def save_session(context):

    cookies = context.cookies()

    json.dump(cookies, open(SESSION_FILE, "w"))
