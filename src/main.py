from flask import Flask, request
from flask_restful import Resource, Api
from flask_jwt import JWT, jwt_required, current_identity
from user_manager import authenticate, identity
from token_operator import secret_key
from datetime import timedelta
import os
from message_queue import read_config, test_rabbitmq_connection, create_queue, publish_message
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = secret_key
# app.config['JWT_AUTH_URL_RULE'] = '/auth'
app.config['JWT_EXPIRATION_DELTA'] = timedelta(days=30)

api = Api(app)

jwt = JWT(app, authenticate, identity)

config = read_config('config/config.ini')

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
            "callback_url": payload['callback_url'],
            "task_metadata": payload['task_metadata']
        }

        pub_res = publish_message(config, "opencheck", json.dumps(message_body))

        return "Message received: {}, start check, the results would sent to callback_url you passed later.".format(message_body)


api.add_resource(Test, '/test')
api.add_resource(OpenCheck, '/opencheck')


def init():
    test_rabbitmq_connection(config)
    create_queue(config, "opencheck")


if __name__ == '__main__':
    init()

    use_ssl = False  # Set this to True to enable SSL
    if use_ssl:
        ssl_context = ('/path/to/certificate.crt', '/path/to/private.key')
        app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), ssl_context=ssl_context)
    else:
        app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
