import uuid
from secrets import compare_digest
from helper import read_config

class User:
    def __init__(self, id, username, password, access=['request']):
        self.id = id
        self.name = username
        self.password = password
        self.access = access

    def __str__(self):
        return f"User(id='{str(self.id)}')"

config = read_config('config/config.ini', "UserManager")
userList = [User(str(uuid.uuid5(uuid.NAMESPACE_DNS, config["default_username"])), config["default_username"], config["default_password"])]
usernameTable = {u.name: u for u in userList}
useridTable = {u.id: u for u in userList}

def createUser(username, password, access):
    userList.append(User(str(uuid.uuid5(uuid.NAMESPACE_DNS, username)), username, password, access))

def indexUserWithID(userID):
    return useridTable.get(userID, None)

def indexUserWithName(userName):
    return usernameTable.get(userName, None)

def authenticate(username, password):
    user = usernameTable.get(username, None)
    if user and compare_digest(user.password.encode('utf-8'), password.encode('utf-8')):
        return user

def identity(payload):
    userID = payload['identity']
    return useridTable.get(userID, None)