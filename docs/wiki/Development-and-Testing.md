# Development and Testing

> **Relevant source files**
> * [test/test.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test.py)
> * [test/test_token_operator.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_token_operator.py)
> * [test/test_user_manager.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_user_manager.py)

This document provides guidance for developers working on the OpenChecker system, covering development environment setup, testing frameworks, and development workflows. It focuses on the technical aspects of contributing to the codebase and ensuring code quality through comprehensive testing.

For information about deploying OpenChecker in production environments, see [Deployment and Infrastructure](/Laniakea2012/openchecker/6-deployment-and-infrastructure). For details about the overall system architecture, see [Core Architecture](/Laniakea2012/openchecker/2-core-architecture).

## Development Environment Overview

OpenChecker uses a comprehensive testing strategy built around Python's `unittest` framework, with both unit tests for individual components and integration tests for end-to-end API workflows. The development environment supports local testing of core functionality while maintaining compatibility with the containerized production deployment.

```mermaid
flowchart TD

LocalPython["Local Python EnvironmentPython 3.x + Dependencies"]
IDE["Development IDEVS Code / PyCharm"]
Git["Git RepositoryVersion Control"]
UnitTests["Unit Test Suiteunittest framework"]
IntegrationTests["Integration TestsHTTP API Testing"]
TestRunner["Test Runnerpython -m unittest"]
TokenTests["test_token_operator.pyJWT Token Tests"]
UserTests["test_user_manager.pyUser Management Tests"]
APITests["test.pyAPI Integration Tests"]
TokenOperator["token_operator.pycreateTokenForUser, validate_jwt"]
UserManager["user_manager.pyUser, createUser, authenticate"]
FlaskAPI["Flask APIAuth Endpoints"]

    LocalPython --> UnitTests
    LocalPython --> IntegrationTests
    IDE --> TestRunner
    Git --> TestRunner
    UnitTests --> TokenTests
    UnitTests --> UserTests
    IntegrationTests --> APITests
    TokenTests --> TokenOperator
    UserTests --> UserManager
    APITests --> FlaskAPI
subgraph Core_Components_Under_Test ["Core Components Under Test"]
    TokenOperator
    UserManager
    FlaskAPI
end

subgraph Test_Files ["Test Files"]
    TokenTests
    UserTests
    APITests
end

subgraph Testing_Framework ["Testing Framework"]
    UnitTests
    IntegrationTests
    TestRunner
end

subgraph Development_Environment ["Development Environment"]
    LocalPython
    IDE
    Git
end
```

Sources: [test/test_token_operator.py L1-L47](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_token_operator.py#L1-L47)

 [test/test_user_manager.py L1-L42](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_user_manager.py#L1-L42)

 [test/test.py L1-L43](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test.py#L1-L43)

## Testing Framework Architecture

The testing system is organized into distinct layers, each targeting specific functionality within the OpenChecker system. The framework uses Python's built-in `unittest` module and follows standard testing patterns.

```mermaid
flowchart TD

TestRunner["unittest.main()"]
TestDiscovery["Test Discoverytest_*.py patterns"]
TestExecution["Test ExecutionsetUp -> test_* -> tearDown"]
TestJWTFunctions["TestJWTFunctionstest_token_operator.py"]
JWTMethods["test_createTokenForUser()test_validate_jwt_valid_token()test_validate_jwt_invalid_token()"]
TestUserFunctions["TestUserFunctionstest_user_manager.py"]
UserMethods["test_createUser()test_indexUserWithID()test_indexUserWithName()test_authenticate()test_identity()"]
APITest["API Integration Testtest.py"]
HTTPFlow["Auth Request -> Token -> Protected Endpoint"]

    TestDiscovery --> TestJWTFunctions
    TestDiscovery --> TestUserFunctions
    TestDiscovery --> APITest
    TestExecution --> JWTMethods
    TestExecution --> UserMethods
    TestExecution --> HTTPFlow
subgraph Integration_Tests ["Integration Tests"]
    APITest
    HTTPFlow
end

subgraph User_Management_Tests ["User Management Tests"]
    TestUserFunctions
    UserMethods
end

subgraph Authentication_Tests ["Authentication Tests"]
    TestJWTFunctions
    JWTMethods
end

subgraph Test_Execution_Flow ["Test Execution Flow"]
    TestRunner
    TestDiscovery
    TestExecution
    TestRunner --> TestDiscovery
end
```

Sources: [test/test_token_operator.py L6-L47](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_token_operator.py#L6-L47)

 [test/test_user_manager.py L6-L42](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_user_manager.py#L6-L42)

 [test/test.py L9-L43](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test.py#L9-L43)

## Unit Testing Components

### JWT Token Testing

The JWT token functionality is tested through the `TestJWTFunctions` class, which validates token creation and validation mechanisms used for API authentication.

| Test Method | Purpose | Key Assertions |
| --- | --- | --- |
| `test_createTokenForUser` | Validates token creation for user authentication | Token contains correct `user_id`, `user_name`, and `expir` fields |
| `test_validate_jwt_valid_token` | Ensures valid tokens pass validation | Returns `True` for properly formatted tokens |
| `test_validate_jwt_invalid_token` | Ensures invalid tokens are rejected | Returns `False` for malformed tokens |

The tests use a mock user class and test secret key for isolation from production configuration. Critical functions tested include:

* `createTokenForUser(user_id)` - Token generation function
* `validate_jwt(token)` - Token validation function

Sources: [test/test_token_operator.py L4-L47](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_token_operator.py#L4-L47)

### User Management Testing

The `TestUserFunctions` class provides comprehensive testing for user operations, including user creation, lookup, and authentication workflows.

```mermaid
flowchart TD

SetUp["setUp() methodCreates test user and lookup tables"]
MockConfig["Test Configurationdefault_username: testuserdefault_password: testpassword"]
TestUser["Test User ObjectUUID-based ID generation"]
CreateTest["test_createUser()Tests user creation"]
IndexIDTest["test_indexUserWithID()Tests user lookup by ID"]
IndexNameTest["test_indexUserWithName()Tests user lookup by name"]
AuthTest["test_authenticate()Tests credential validation"]
IdentityTest["test_identity()Tests payload-based lookup"]
CreateUser["createUser(name, password, access)"]
IndexUserWithID["indexUserWithID(user_id)"]
IndexUserWithName["indexUserWithName(username)"]
Authenticate["authenticate(username, password)"]
Identity["identity(payload)"]

    CreateTest --> CreateUser
    IndexIDTest --> IndexUserWithID
    IndexNameTest --> IndexUserWithName
    AuthTest --> Authenticate
    IdentityTest --> Identity
subgraph Core_Functions ["Core Functions"]
    CreateUser
    IndexUserWithID
    IndexUserWithName
    Authenticate
    Identity
end

subgraph User_Operations_Tests ["User Operations Tests"]
    IndexNameTest
    AuthTest
    IdentityTest
end

subgraph User_Test_Setup ["User Test Setup"]
    SetUp
    MockConfig
    TestUser
    CreateTest
    IndexIDTest
    SetUp --> MockConfig
    SetUp --> TestUser
end
```

Sources: [test/test_user_manager.py L4-L42](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_user_manager.py#L4-L42)

## Integration Testing

### API Integration Test Workflow

The integration test in `test.py` validates the complete authentication and API access workflow, demonstrating the end-to-end functionality of the OpenChecker API.

| Test Phase | HTTP Method | Endpoint | Purpose |
| --- | --- | --- | --- |
| Authentication | POST | `/auth` | Obtain JWT access token |
| Protected Request | POST | `/test` | Validate token-protected endpoint access |

The test workflow follows this sequence:

1. **Authentication Request**: Posts credentials to `/auth` endpoint
2. **Token Extraction**: Extracts `access_token` from response JSON
3. **Protected Request**: Uses token in `Authorization: JWT <token>` header
4. **Response Validation**: Verifies successful access to protected endpoint

```
# Key request patterns from test.py
authPayload = {
    'username': 'temporary_user',
    'password': 'default_password'
}

headers['Authorization'] = 'JWT' + ' ' + access_token
```

Sources: [test/test.py L10-L43](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test.py#L10-L43)

## Development Workflow

### Local Development Setup

For local development, developers need to set up the Python environment and dependencies required for testing and development.

```mermaid
flowchart TD

Start["Start Development"]
Clone["git clone repository"]
Venv["python -m venv venvsource venv/bin/activate"]
Install["pip install -r requirements.txt"]
UnitTest["python -m unittest test.test_token_operatorpython -m unittest test.test_user_manager"]
IntegrationTest["python test/test.py(requires running API server)"]
AllTests["python -m unittest discover test/"]
LocalAPI["python main.pyor flask run"]
LocalPort["Unsupported markdown: link"]

    Start --> Clone
    Clone --> Venv
    Venv --> Install

    Install --> UnitTest
    Install --> LocalAPI
    LocalPort --> IntegrationTest
subgraph Development_Server ["Development Server"]
    LocalAPI
    LocalPort
    LocalAPI --> LocalPort
end

subgraph Testing_Workflow ["Testing Workflow"]
    UnitTest
    IntegrationTest
    AllTests
end
```

Sources: [test/test.py

3](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test.py#L3-L3)

### Test Execution Commands

| Test Type | Command | Description |
| --- | --- | --- |
| All Unit Tests | `python -m unittest discover test/` | Runs all test files matching `test_*.py` pattern |
| Token Tests | `python -m unittest test.test_token_operator` | Tests JWT token functionality only |
| User Tests | `python -m unittest test.test_user_manager` | Tests user management functionality only |
| Integration Test | `python test/test.py` | Requires running API server on localhost:8080 |

### Test Configuration Requirements

The tests require specific configuration setup for proper execution:

* **Secret Keys**: Test files use hardcoded test secrets (noted as requiring optimization)
* **Default Credentials**: Integration tests use `temporary_user` / `default_password`
* **Local Server**: Integration tests expect API server running on `localhost:8080`
* **Dependencies**: Tests require `jwt`, `requests`, `uuid`, and `secrets` modules

Sources: [test/test_token_operator.py L9-L11](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_token_operator.py#L9-L11)

 [test/test_user_manager.py L8-L15](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_user_manager.py#L8-L15)

 [test/test.py L3-L14](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test.py#L3-L14)

## Testing Best Practices

### Mock Objects and Test Isolation

The test suite demonstrates proper use of mock objects to isolate functionality under test:

```
# Example from test_token_operator.py
class MockUser:
    def __init__(self, id, name):
        self.id = id
        self.name = name
```

### Test Data Management

Tests use controlled test data to ensure predictable results:

* UUID-based user ID generation for uniqueness
* Predefined username/password combinations
* Isolated test configurations separate from production

### Error Handling Testing

The test suite includes both positive and negative test cases:

* Valid token validation tests
* Invalid token rejection tests
* Successful authentication tests
* Failed authentication scenarios

Sources: [test/test_token_operator.py L14-L44](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_token_operator.py#L14-L44)

 [test/test_user_manager.py L8-L39](https://github.com/Laniakea2012/openchecker/blob/00a9732e/test/test_user_manager.py#L8-L39)