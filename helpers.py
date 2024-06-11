from flask import redirect, session
from functools import wraps
import re

def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function


def data(data):
    match = re.match("(\d\d\d\d)-(\d\d)-(\d\d)", data)
    reformat = match.group(3) + "/" + match.group(2) + "/" + match.group(1)
    return reformat

def JIS_to_ISO(data):
    match = re.match("(\d\d)/(\d\d)/(\d\d\d\d)", data)
    if match:
        iso = match.group(3) + "-" + match.group(2) + "-" + match.group(1)
        return iso
    else:
        return None