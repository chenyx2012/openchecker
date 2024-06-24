import subprocess
from message_queue import consumer
from helper import read_config
import json

config = read_config('config/config.ini')

def shell_exec(shell_script, param=None):
    if param != None:
        process = subprocess.Popen(["/bin/bash", "-c", shell_script + " " + param], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    else:
        process = subprocess.Popen([shell_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    shell_output, error = process.communicate()

    if process.returncode == 0:
        return shell_output, None
    else:
        return None, error

def request_url (url, payload):
    import requests
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print("Request sent successfully.")
        return response.text
    else:
        print(f"Failed to send request. Status code: {response.status_code}")
        return None


def callback_func(ch, method, properties, body):
    message = json.loads(body.decode('utf-8'))
    command_list = message.get('command_list')
    project_url = message.get('project_url')
    callback_url = message.get('callback_url')
    task_metadata = message.get('task_metadata')

    res_payload = {
        "command_list": command_list,
        "project_url": project_url,
        "task_metadata": task_metadata,
        "scan_results": {
        }
    }

    for command in command_list:
        if command == 'osv-scanner':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                git clone {project_url} > /dev/null
                osv-scanner --format json -r $project_name
                rm -rf $project_name > /dev/null
            """

            result, error = shell_exec(shell_script)

            if error == None:
                print("osv-scanner job done: {}".format(project_url))
                osv_result = json.loads(result.decode('utf-8'))
                res_payload["scan_results"]["osv-scanner"] = osv_result
            else:
                print("osv-scanner job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["osv-scanner"] = {"error": error}

        elif command == 'scancode':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                git clone {project_url} > /dev/null
                scancode -lc --json-pp scan_result.json $project_name --unknown-licenses -n 4 > /dev/null
                cat scan_result.json
                rm -rf $project_name scan_result.json > /dev/null
            """

            result, error = shell_exec(shell_script)

            if error == None:
                print("scancode job done: {}".format(project_url))
                scancode_result = json.loads(result.decode('utf-8'))
                res_payload["scan_results"]["scancode"] = scancode_result
            else:
                print("scancode job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["scancode"] = {"error": error}

        elif command == 'binary-checker':
            result, error = shell_exec("./scripts/binary_checker.sh", project_url)

            if error == None:
                print("binary-checker job done: {}".format(project_url))
                result = result.decode('utf-8') if result != None else ""
                data_list = result.split('\n')
                binary_file_list = []
                binary_archive_list = []
                for data in data_list[:-1]:
                    if "Binary file found:" in data:
                        binary_file_list.append(data.split(": ")[1])
                    elif "Binary archive found:" in data:
                        binary_archive_list.append(data.split(": ")[1])
                    else:
                        pass
                binary_result = {"binary_file_list": binary_file_list, "binary_archive_list": binary_archive_list}
                res_payload["scan_results"]["binary-checker"] = binary_result

            else:
                print("binary-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["binary-checker"] = {"error": error}

        elif command == 'signature-checker':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                git clone {project_url} > /dev/null
                find "$project_name" -type f \( -name "*.asc" -o -name "*.sig" -o -name "*.cer" -o -name "*.crt" -o -name "*.pem" -o -name "*.sha256" -o -name "*.sha512" \) -print
                rm -rf $project_name scan_result.json > /dev/null
            """

            result, error = shell_exec(shell_script)

            if error == None:
                print("signature-checker job done: {}".format(project_url))
                result = result.decode('utf-8') if result != None else ""
                data_list = result.split('\n')
                signature_result = {"signature_file_list": data_list[:-1]}
                res_payload["scan_results"]["signature-checker"] = signature_result
            else:
                print("gignature-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["signature-checker"] = {"error": error}

        elif command == 'url-checker':
            from urllib import request
            try:
                with request.urlopen(project_url) as file:
                    if file.status == 200 and file.reason == "OK":
                        print("url-checker job done: {}".format(project_url))
                        url_result = {"url": project_url, "status": "pass", "error": "null"}
                    else:
                        print("url-checker job failed: {}".format(project_url))
                        url_result = {"url": project_url, "status": "fail", "error": file.reason}
            except Exception as e:
                print("gignature-checker job failed: {}, error: {}".format(project_url, e))
                url_result = {"error": e}
            res_payload["scan_results"]["url-checker"] = url_result

        else:
            print(f"Unknown command: {command}")

    if callback_url != None and callback_url != "":
        response = request_url(callback_url, res_payload)
        print(f"Callback response: {response}")

    ch.basic_ack(delivery_tag=method.delivery_tag)

if __name__ == "__main__":
    consumer(config["RabbitMQ"], "opencheck", callback_func)
    print('Agents are serving. To exit press CTRL+C')
