import subprocess
from message_queue import consumer
from helper import read_config
from datetime import datetime
import json
import requests
import re
import time

config = read_config('config/config.ini')

def dependency_checker_output_process(output):
    if output == None:
        return ""

    result = json.loads(output.decode('utf-8'))
    try:
        packages = result["analyzer"]["result"]["packages"]
        result = {"packages_all": [], "packages_with_license_detect": [], "packages_without_license_detect": []}

        for package in packages:
            result["packages_all"].append(package["purl"])
            license = package["declared_licenses"]
            if license != None and len(license) > 0:
                result["packages_with_license_detect"].append(package["purl"])
            else:
                result["packages_without_license_detect"].append(package["purl"])

    except Exception as e:
        print(f"Error processing dependency-checker output: {e}")
        return ""

    return result

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
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print("Request sent successfully.")
        return response.text
    else:
        print(f"Failed to send request. Status code: {response.status_code}")
        return None


def callback_func(ch, method, properties, body):
    print(f"callback func called at {datetime.now()}")
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
                res_payload["scan_results"]["osv-scanner"] = {"error": json.dumps(error.decode("utf-8"))}

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
                res_payload["scan_results"]["scancode"] = {"error": json.dumps(error.decode("utf-8"))}

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
                res_payload["scan_results"]["binary-checker"] = {"error": json.dumps(error.decode("utf-8"))}

        elif command == 'signature-checker':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                git clone {project_url} > /dev/null
                find "$project_name" -type f \( -name "*.asc" -o -name "*.sig" -o -name "*.cer" -o -name "*.crt" -o -name "*.pem" -o -name "*.sha256" -o -name "*.sha512" \) -print
                rm -rf $project_name > /dev/null
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
                res_payload["scan_results"]["signature-checker"] = {"error": json.dumps(error.decode("utf-8"))}

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

        elif command == 'sonar-scanner':

            pattern = r'https?://(?:www\.)?(github\.com|gitee\.com)/([^/]+)/([^/]+)\.git'
            match = re.match(pattern, project_url)
            if match:
                platform, organization, project = match.groups()
            else:
                platform, organization, project = "other", "default", "default"
            sonar_project_name = platform + "_" + organization + "_" + project

            sonar_config = config["SonarQube"]

            sonar_search_procet_api = f"http://{sonar_config['host']}:{sonar_config['port']}/api/projects/search"

            data = {"projects": sonar_project_name}
            auth = (sonar_config["username"], sonar_config["password"])
            is_exit = False

            try:
                response = requests.get(sonar_search_procet_api, auth=auth, params={"projects": sonar_project_name})
                if response.status_code == 200:
                    print("Call sonarqube projects search api success: 200")
                    res = json.loads(response.text)
                    is_exit = True if res["paging"]["total"] > 0 else False
                else:
                    print(f"Call sonarqube projects search api failed with status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                print(f"Call sonarqube projects search api failed with error: {e}")

            if not is_exit:
                sonar_create_procet_api = f"http://{sonar_config['host']}:{sonar_config['port']}/api/projects/create"
                data = {"project": sonar_project_name, "name": sonar_project_name}

                try:
                    response = requests.post(sonar_create_procet_api, auth=auth, data=data)
                    if response.status_code == 200:
                        print("Call sonarqube projects create api success: 200")
                    else:
                        print(f"Call sonarqube projects create api failed with status code: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"Call sonarqube projects create api failed with error: {e}")

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                cd ~ && git clone {project_url} > /dev/null
                sonar-scanner \
                    -Dsonar.projectKey={sonar_project_name} \
                    -Dsonar.sources=$project_name \
                    -Dsonar.host.url=http://{sonar_config['host']}:{sonar_config['port']} \
                    -Dsonar.token={sonar_config['token']} \
                    -Dsonar.exclusions=**/*.java
                rm -rf $project_name > /dev/null
            """

            result, error = shell_exec(shell_script)

            if error == None:
                print("sonar-scanner finish scanning project: {}, report querying...".format(project_url))

                sonar_query_measures_api = f"http://{sonar_config['host']}:{sonar_config['port']}/api/measures/component"

                try:
                    # TODO: optimize this, waiting for sonarqube data processing
                    time.sleep(60)
                    response = requests.get(sonar_query_measures_api, auth=auth, params={"component": sonar_project_name, "metricKeys": "coverage,complexity,duplicated_lines_density,lines"})
                    if response.status_code == 200:
                        print("Querying sonar-scanner report success: 200")
                        sonar_result = json.loads(response.text)
                        res_payload["scan_results"]["sonar-scanner"] = sonar_result
                        print(res_payload)
                    else:
                        print(f"Querying sonar-scanner report failed with status code: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    print(f"Querying sonar-scanner report failed with error: {e}")

                print("sonar-scanner job done: {}".format(project_url))
            else:
                print("sonar-scanner job failed: {}, error: {}".format(project_url, error))

        elif command == 'dependency-checker':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                git clone {project_url} > /dev/null
                ort analyze -i $project_name -o $project_name -f JSON > /dev/null
                cat $project_name/analyzer-result.json
                rm -rf $project_name > /dev/null
            """
            result, error = shell_exec(shell_script)

            if error == None:
                print("dependency-checker job done: {}".format(project_url))
                res_payload["scan_results"]["dependency-checker"] = dependency_checker_output_process(result)
            else:
                print("dependency-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["dependency-checker"] = {"error": json.dumps(error.decode("utf-8"))}

        else:
            print(f"Unknown command: {command}")

    if callback_url != None and callback_url != "":
        response = request_url(callback_url, res_payload)
        print(f"Callback response: {response}")

    ch.basic_ack(delivery_tag=method.delivery_tag)

if __name__ == "__main__":
    consumer(config["RabbitMQ"], "opencheck", callback_func)
    print('Agents are serving. To exit press CTRL+C')
