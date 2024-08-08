import subprocess
from message_queue import consumer
from helper import read_config
from datetime import datetime
from exponential_backoff import post_with_backoff, completion_with_backoff
import json
import requests
import re
import time
import os
from ghapi.all import GhApi
import zipfile
import io
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s : %(message)s')

config = read_config('config/config.ini')

def dependency_checker_output_process(output):
    if not bool(output):
        return {}

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
        logging.info(f"Error processing dependency-checker output: {e}")
        return {}

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
    response = post_with_backoff(url=url, json=payload)

    if response.status_code == 200:
        logging.info("Request sent successfully.")
        return response.text
    else:
        logging.info(f"Failed to send request. Status code: {response.status_code}")
        return None

def check_readme_opensource(project_url):
    project_name = os.path.basename(project_url).replace('.git', '')

    if not os.path.exists(project_name):
        subprocess.run(["git", "clone", project_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    readme_file = os.path.join(project_name, "README.OpenSource")
    if os.path.isfile(readme_file):
        with open(readme_file, 'r', encoding='utf-8') as file:
            try:
                content = json.load(file)

                if isinstance(content, list):
                    required_keys = [
                        "Name", "License", "License File",
                        "Version Number", "Owner", "Upstream URL", "Description"
                    ]

                    all_entries_valid = True
                    for entry in content:
                        if not isinstance(entry, dict) or not all(key in entry for key in required_keys):
                            all_entries_valid = False
                            break

                    if all_entries_valid:
                        # return "The README.OpenSource file exists and is properly formatted.", None
                        return True, None
                    else:
                        # return None, "The README.OpenSource file exists and is not properly formatted."
                        return False, "The README.OpenSource file exists and is not properly formatted."

            except json.JSONDecodeError:
                return False, "README.OpenSource is not properly formatted."
    else:
        return False, "README.OpenSource does not exist."

def check_doc_content(project_url, type):
    project_name = os.path.basename(project_url).replace('.git', '')

    if not os.path.exists(project_name):
        subprocess.run(["git", "clone", project_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    dir_list = [project_name, project_name + '/' + 'doc', project_name + '/' + 'docs']

    def get_documents_in_directory(path):
        documents = []
        if not os.path.exists(path):
            return documents
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isfile(full_path) and item.endswith(('.md', '.markdown')):
                documents.append(full_path)
        return documents

    documents = []
    for dir in dir_list:
        documents.extend(get_documents_in_directory(dir))

    if type == "build-doc":
        templates = """
            You are a professional programmer, please assess whether the provided text offers a thorough and in-depth introduction to the processes of software compilation and packaging.
            If the text segment introduce the software compilation and packaging completely, please return 'YES'; otherwise, return 'NO'.
            You need to ensure the accuracy of your answers as much as possible, and if unsure, please simply answer NO. Your response must not include other content.

            Text content as below:

            {text}

        """
    elif type == "api-doc":
        templates = """
            You are a professional programmer, please assess whether the provided text offer a comprehensive introduction to the use of software API.
            If the text segment introduce the software API completely, please return 'YES'; otherwise, return 'NO'.
            You need to ensure the accuracy of your answers as much as possible, and if unsure, please simply answer NO. Your response must not include other content.

            Text content as below:

            {text}

        """
    else:
        logging.info("Unsupported type: {}".format(type))
        return [], None

    build_doc_file = []
    for document in documents:
        with open(document, 'r') as file:
            markdown_text = file.read()
            chunk_size = 3000
            chunks = [markdown_text[i:i+chunk_size] for i in range(0, len(markdown_text), chunk_size)]

        for i, chunk in enumerate(chunks):
            messages = [
                {
                    "role": "user",
                    "content": templates.format(text=chunk)
                }
            ]
            result = completion_with_backoff(model='gpt-3.5-turbo', messages=messages, temperature=0.2)
            if result == "YES":
                build_doc_file.append(document)
                return build_doc_file, None
    return build_doc_file, None

def check_release_content(project_url):
    owner_name = re.match(r"https://(?:github|gitee).com/([^/]+)/", project_url).group(1)
    repo_name = re.sub(r'\.git$', '', os.path.basename(project_url))

    if "github.com" in project_url:
        api = GhApi(owner=owner_name, repo=repo_name)
        try:
            latest_release = api.repos.get_latest_release()
        except Exception as e:
            logging.info("Failed to get latest release for repo: {} \n Error: {}".format(project_url, e))
            return {"is_released": False, "signature_files": [], "release_notes": []}, "Not found"

        latest_release_url = latest_release["zipball_url"]

    elif "gitee.com" in project_url:
        url = f"https://gitee.com/api/v5/repos/{owner_name}/{repo_name}/releases/latest"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                tag_name = response.json()["tag_name"]
                access_token = config["Gitee"]["access_key"]
                # latest_release_url = response.json()["assets"][0]["browser_download_url"]
                latest_release_url = f"https://gitee.com/api/v5/repos/{owner_name}/{repo_name}/zipball?access_token={access_token}&ref={tag_name}"
            else:
                logging.info("Failed to get latest release for repo: {} \n Error: {}".format(project_url, "Not found"))
                return {"is_released": False, "signature_files": [], "release_notes": []}, "Not found"
        except Exception as e:
            logging.info("Failed to get latest release for repo: {} \n Error: {}".format(project_url, e))
            return {"is_released": False, "signature_files": [], "release_notes": []}, "Not found"

    else:
        logging.info("Failed to do release files check for repo: {} \n Error: {}".format(project_url, "Not supported platform."))
        return {"is_released": False, "signature_files": [], "release_notes": []}, "Not supported platform."

    response = requests.get(latest_release_url)
    if response.status_code != 200:
        return {"is_released": True, "signature_files": [], "release_notes": []}, "Failed to download release."

    signature_files = []
    changelog_files = []
    with zipfile.ZipFile(io.BytesIO(response.content), 'r') as zip_ref:
        signature_suffixes = ["*.asc", "*.sig", "*.cer", "*.crt", "*.pem", "*.sha256", "*.sha512"]
        signature_files = [ file for file in zip_ref.namelist() if any(file.lower().endswith(suffix) for suffix in signature_suffixes) ]

        changelog_names = ["changelog", "releasenotes", "release_notes"]
        changelog_files = [ file for file in zip_ref.namelist() if any(name in os.path.basename(file).lower() for name in changelog_names)]

    return {"is_released": True, "signature_files": signature_files, "release_notes": changelog_files}, None

def callback_func(ch, method, properties, body):

    logging.info(f"callback func called at {datetime.now()}")

    message = json.loads(body.decode('utf-8'))
    command_list = message.get('command_list')
    project_url = message.get('project_url')
    callback_url = message.get('callback_url')
    task_metadata = message.get('task_metadata')
    logging.info(project_url)

    res_payload = {
        "command_list": command_list,
        "project_url": project_url,
        "task_metadata": task_metadata,
        "scan_results": {
        }
    }

    # download source code of the project
    shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url}
                fi
            """

    result, error = shell_exec(shell_script)

    if error == None:
        logging.info("download source code done: {}".format(project_url))
    else:
        logging.info("download source code failed: {}, error: {}".format(project_url, error))
        logging.info("put messages to dead letters: {}".format(body))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    for command in command_list:
        if command == 'osv-scanner':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url} > /dev/null
                fi
                # Outputs the results as a JSON object to stdout, with all other output being directed to stderr
                # - this makes it safe to redirect the output to a file.
                # shell_exec function return (None, error) when process.returncode is not 0, so we redirect output to a file and cat.
                osv-scanner --format json -r $project_name > $project_name/result.json
                cat $project_name/result.json
                # rm -rf $project_name > /dev/null
            """

            result, error = shell_exec(shell_script)

            # When osv-scanner tool specify the '--format json' option, only the scan results are output to the standard output.
            # All other information is redirected to the standard error output;
            # Hence, error values are not checked here.
            logging.info("osv-scanner job done: {}".format(project_url))
            osv_result = json.loads(result.decode('utf-8')) if bool(result) else {}
            res_payload["scan_results"]["osv-scanner"] = osv_result

        elif command == 'scancode':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url} > /dev/null
                fi
                scancode -lc --json-pp scan_result.json $project_name --license-score 80 -n 4 > /dev/null
                cat scan_result.json
                rm -rf scan_result.json > /dev/null
                # rm -rf $project_name scan_result.json > /dev/null
            """

            result, error = shell_exec(shell_script)

            if error == None:
                logging.info("scancode job done: {}".format(project_url))
                scancode_result = json.loads(result.decode('utf-8')) if bool(result) else {}
                res_payload["scan_results"]["scancode"] = scancode_result
            else:
                logging.info("scancode job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["scancode"] = {"error": json.dumps(error.decode("utf-8"))}

        elif command == 'binary-checker':
            result, error = shell_exec("./scripts/binary_checker.sh", project_url)

            if error == None:
                logging.info("binary-checker job done: {}".format(project_url))
                result = result.decode('utf-8') if bool(result) else ""
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
                logging.info("binary-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["binary-checker"] = {"error": json.dumps(error.decode("utf-8"))}

        elif command == 'release-checker':

            result, error = check_release_content(project_url)

            if error == None:
                logging.info("release-checker job done: {}".format(project_url))
                res_payload["scan_results"]["release-checker"] = result
            else:
                logging.info("release-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["release-checker"] = {"error": error}

        elif command == 'url-checker':
            from urllib import request
            try:
                with request.urlopen(project_url) as file:
                    if file.status == 200 and file.reason == "OK":
                        logging.info("url-checker job done: {}".format(project_url))
                        url_result = {"url": project_url, "status": "pass", "error": "null"}
                    else:
                        logging.info("url-checker job failed: {}".format(project_url))
                        url_result = {"url": project_url, "status": "fail", "error": file.reason}
            except Exception as e:
                logging.info("gignature-checker job failed: {}, error: {}".format(project_url, e))
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
                    logging.info("Call sonarqube projects search api success: 200")
                    res = json.loads(response.text)
                    is_exit = True if res["paging"]["total"] > 0 else False
                else:
                    logging.info(f"Call sonarqube projects search api failed with status code: {response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.info(f"Call sonarqube projects search api failed with error: {e}")

            if not is_exit:
                sonar_create_procet_api = f"http://{sonar_config['host']}:{sonar_config['port']}/api/projects/create"
                data = {"project": sonar_project_name, "name": sonar_project_name}

                try:
                    response = requests.post(sonar_create_procet_api, auth=auth, data=data)
                    if response.status_code == 200:
                        logging.info("Call sonarqube projects create api success: 200")
                    else:
                        logging.info(f"Call sonarqube projects create api failed with status code: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    logging.info(f"Call sonarqube projects create api failed with error: {e}")

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url} > /dev/null
                fi
                cp -r $project_name ~/ && cd ~
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
                logging.info("sonar-scanner finish scanning project: {}, report querying...".format(project_url))

                sonar_query_measures_api = f"http://{sonar_config['host']}:{sonar_config['port']}/api/measures/component"

                try:
                    # TODO: optimize this, waiting for sonarqube data processing
                    time.sleep(60)
                    response = requests.get(sonar_query_measures_api, auth=auth, params={"component": sonar_project_name, "metricKeys": "coverage,complexity,duplicated_lines_density,lines"})
                    if response.status_code == 200:
                        logging.info("Querying sonar-scanner report success: 200")
                        sonar_result = json.loads(response.text)
                        res_payload["scan_results"]["sonar-scanner"] = sonar_result
                    else:
                        logging.info(f"Querying sonar-scanner report failed with status code: {response.status_code}")
                except requests.exceptions.RequestException as e:
                    logging.info(f"Querying sonar-scanner report failed with error: {e}")

                logging.info("sonar-scanner job done: {}".format(project_url))
            else:
                logging.info("sonar-scanner job failed: {}, error: {}".format(project_url, error))

        elif command == 'dependency-checker':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url} > /dev/null
                fi
                ort analyze -i $project_name -o $project_name -f JSON > /dev/null
                cat $project_name/analyzer-result.json
                # rm -rf $project_name > /dev/null
            """
            result, error = shell_exec(shell_script)

            if error == None:
                logging.info("dependency-checker job done: {}".format(project_url))
                res_payload["scan_results"]["dependency-checker"] = dependency_checker_output_process(result)
            else:
                logging.info("dependency-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["dependency-checker"] = {"error": json.dumps(error.decode("utf-8"))}

        elif command == 'readme-checker':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url} > /dev/null
                fi
                find "$project_name" -type f \( -name "README*" -o -name ".github/README*" -o -name "docs/README*" \) -print
            """

            result, error = shell_exec(shell_script)

            if error == None:
                logging.info("readme-checker job done: {}".format(project_url))
                res_payload["scan_results"]["readme-checker"] = {"readme_file": result.decode('utf-8').split('\n')[:-1]} if bool(result) else {}
            else:
                logging.info("readme-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["readme-checker"] = {"error": json.dumps(error.decode("utf-8"))}

        elif command == 'maintainers-checker':

            shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ ! -e "$project_name" ]; then
                    git clone {project_url} > /dev/null
                fi
                find "$project_name" -type f \( -iname "MAINTAINERS*" -o -iname "OWNERS*" -o -iname "CODEOWNERS*" \) -print
            """

            result, error = shell_exec(shell_script)

            if error == None:
                logging.info("maintainers-checker job done: {}".format(project_url))
                res_payload["scan_results"]["maintainers-checker"] = {"maintainers_file": result.decode('utf-8').split('\n')[:-1]} if bool(result) else {}
            else:
                logging.info("maintainers-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["maintainers-checker"] = {"error": json.dumps(error.decode("utf-8"))}

        elif command == 'readme-opensource-checker':
            result, error  = check_readme_opensource(project_url)
            if error == None:
                logging.info("readme-opensource-checker job done: {}".format(project_url))
                res_payload["scan_results"]["readme-opensource-checker"] = {"readme-opensource-checker": result} if bool(result) else {}
            else:
                logging.info("readme-opensource-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["readme-opensource-checker"] = {"error":error}

        elif command == 'build-doc-checker':
            result, error  = check_doc_content(project_url, "build-doc")
            if error == None:
                logging.info("build-doc-checker job done: {}".format(project_url))
                res_payload["scan_results"]["build-doc-checker"] = {"build-doc-checker": result} if bool(result) else {}
            else:
                logging.info("build-doc-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["build-doc-checker"] = {"error":error}

        elif command == 'api-doc-checker':
            result, error  = check_doc_content(project_url, "api-doc")
            if error == None:
                logging.info("api-doc-checker job done: {}".format(project_url))
                res_payload["scan_results"]["api-doc-checker"] = {"api-doc-checker": result} if bool(result) else {}
            else:
                logging.info("api-doc-checker job failed: {}, error: {}".format(project_url, error))
                res_payload["scan_results"]["api-doc-checker"] = {"error":error}

        else:
            logging.info(f"Unknown command: {command}")

    # remove source code of the project
    shell_script=f"""
                project_name=$(basename {project_url} | sed 's/\.git$//') > /dev/null
                if [ -e "$project_name" ]; then
                    rm -rf $project_name > /dev/null
                fi
            """

    result, error = shell_exec(shell_script)

    if error == None:
        logging.info("remove source code done: {}".format(project_url))
    else:
        logging.info("remove source code failed: {}, error: {}".format(project_url, error))

    if callback_url != None and callback_url != "":
        try:
            response = request_url(callback_url, res_payload)
            logging.info(f"Callback response: {response}")
        except Exception as e:
            logging.info("Error happened when request to callback url: {}".format(e))
            logging.info("put messages to dead letters: {}".format(body))
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

    ch.basic_ack(delivery_tag=method.delivery_tag)

if __name__ == "__main__":
    consumer(config["RabbitMQ"], "opencheck", callback_func)
    logging.info('Agents server ended.')
