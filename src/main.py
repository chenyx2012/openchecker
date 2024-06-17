from flask import Flask, request
from flask_restful import Resource, Api
from flask_jwt import JWT, jwt_required, current_identity
from user_manager import authenticate, identity
from token_operator import secret_key
from datetime import timedelta
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secret_key
# app.config['JWT_AUTH_URL_RULE'] = '/auth'
app.config['JWT_EXPIRATION_DELTA'] = timedelta(days=30)

api = Api(app)

jwt = JWT(app, authenticate, identity)

class Test(Resource):
    @jwt_required()
    def get(self):
        return current_identity

    @jwt_required()
    def post(self):
        payload = request.get_json()
        message = payload['message']

        return "Message received: {}, test pass!".format(message)

api.add_resource(Test, '/test')

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=int(os.environ.get('PORT', 8080)))