import requests

baseURL = 'http://localhost:8080/'

headers = {
    'Content-Type': 'application/json'
}

if __name__ == "__main__":
    authURL = baseURL + 'auth'
    
    authPayload = {
        'username': 'temporary_user',
        'password': 'default_password'
    }

    try:
        response = requests.post(url=authURL, headers=headers, json=authPayload)
    except Exception as e:
        print(e)
    else:
        # status_code = response.status_code
        resPayload = response.json()
        if 'access_token' in resPayload:
            access_token = response.json()['access_token']
            print(access_token)
        else:
            print(resPayload)
            exit()

    testURL = baseURL + 'test'
    headers['Authorization'] = 'JWT' + ' ' + access_token
    payload = {
        "message": 'ping for test'
    }

    try:
        response = requests.post(url=testURL, headers=headers, json=payload)
    except Exception as e:
        print(e)
    else:
        # print(response)
        print(response.json())