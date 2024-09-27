import datetime
import unittest
import jwt
from openchecker.token_operator import createTokenForUser, validate_jwt

class TestJWTFunctions(unittest.TestCase):

    def setUp(self):
        # Note: sercret keys are prohibited from being hard-coded.
        # TODO: optimize the implementation here according to your needs.
        self.secret_key = "test_secret_key"

    def test_createTokenForUser(self):
        # Mock a user
        class MockUser:
            def __init__(self, id, name):
                self.id = id
                self.name = name

        user = MockUser(123, "test_user")
        token = createTokenForUser(user.id)
        self.assertIsNotNone(token)

        decoded_token = jwt.decode(token, self.secret_key, algorithms=['HS256'])
        self.assertEqual(decoded_token['user_id'], user.id)
        self.assertEqual(decoded_token['user_name'], user.name)
        self.assertIsInstance(decoded_token['expir'], datetime.datetime)

    def test_validate_jwt_valid_token(self):
        # Mock a user
        class MockUser:
            def __init__(self, id, name):
                self.id = id
                self.name = name

        user = MockUser(123, "test_user")
        token = createTokenForUser(user.id)
        result = validate_jwt(token)
        self.assertTrue(result)

    def test_validate_jwt_invalid_token(self):
        invalid_token = "invalid_token"
        result = validate_jwt(invalid_token)
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()