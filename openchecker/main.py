from flask import Flask, request
from flask_restful import Resource, Api
from flask_jwt import JWT, jwt_required, current_identity
from user_manager import authenticate, identity
from datetime import timedelta
import os
from message_queue import test_rabbitmq_connection, create_queue, publish_message
from helper import read_config
import json

jwt_config = read_config('config/config.ini', "JWT")
secret_key = jwt_config.get("secret_key", "your_secret_key")
expires_minutes = int(jwt_config.get("expires_minutes", 30))

app = Flask(__name__)
app.config['SECRET_KEY'] = secret_key
# app.config['JWT_AUTH_URL_RULE'] = '/auth'
app.config['JWT_EXPIRATION_DELTA'] = timedelta(minutes=expires_minutes)

api = Api(app)

jwt = JWT(app, authenticate, identity)

config = read_config('config/config.ini', "RabbitMQ")

class Test(Resource):
    @jwt_required()
    def get(self):
        return current_identity

    @jwt_required()
    def post(self):
        payload = request.get_json()
        message = payload['message']

        return "Message received: {}, test pass!".format(message)

class OpenCheck(Resource):
    @jwt_required()
    def post(self):
        payload = request.get_json()

        #TODO  do request body check here.

        message_body = {
            "command_list": payload['commands'],
            "project_url": payload['project_url'],
            "commit_hash": payload.get("commit_hash"),
            "access_token": payload.get("access_token"),
            "callback_url": payload['callback_url'],
            "task_metadata": payload['task_metadata']
        }

        pub_res = publish_message(config, "opencheck", json.dumps(message_body))

        return "Message received: {}, start check, the results would sent to callback_url you passed later.".format(message_body)


api.add_resource(Test, '/test')
api.add_resource(OpenCheck, '/opencheck')


def init():
    test_rabbitmq_connection(config)
    create_queue(config, "dead_letters")
    create_queue(config, "opencheck", arguments={'x-dead-letter-exchange': '', 'x-dead-letter-routing-key': 'dead_letters'})

if __name__ == '__main__':
    init()

    server_config = read_config('config/config.ini', "OpenCheck")

    use_ssl = False  # Set this to True to enable SSL
    if use_ssl:
        ssl_context = (server_config["ssl_crt_path"], server_config["ssl_key_path"])
        app.run(debug=False, host=server_config["host"], port=int(server_config["port"]), ssl_context=ssl_context)
    else:
        app.run(debug=False, host=server_config["host"], port=int(server_config["port"]))
