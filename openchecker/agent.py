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
from ghapi.all import GhApi, paged
import zipfile
import io
import yaml
from urllib.parse import urlparse
from constans import shell_script_handlers
from typing import Any, List, Dict
from pathlib import Path
from platform_adapter import platform_manager
from common import shell_exec
from checks.fuzzing_checker import fuzzing_checker
from checks.dangerous_workflow_checker import dangerous_workflow_checker
from checks.bestpractices_checker import bestpractices_checker
from checks.packaging_checker import packaging_checker
from checks.pinned_dependencies_checker import pinned_dependencies_checker
from checks.sast_checker import sast_checker
from checks.security_policy_checker import security_policy_checker
from checks.token_permissions_checker import token_permissions_checker
from checks.webhooks_checker import webhooks_checker
from openchecker.logger import get_logger, log_performance

# Get logger for agent module
logger = get_logger('openchecker.agent')


file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(file_dir)
config_file = os.path.join(project_root, "config", "config.ini")
config = read_config(config_file)

def get_licenses_name(data):
    return next(
        (license['meta']['title'] 
         for license in data.get('licenses', []) 
         if license.get('meta', {}).get('title')), 
        None
    )

def ruby_licenses(data):
    github_url_pattern = "https://github.com/"
    for item in data["analyzer"]["result"]["packages"]:
        declared_licenses = item["declared_licenses"]
        homepage_url = item.get('homepage_url', '')
        vcs_url = item.get('vcs_processed', {}).get('url', '').replace('.git', '')

        # Check if declared_licenses is empty
        if not declared_licenses or len(declared_licenses)==0:
            # Prioritize checking if vcs_url is a GitHub address
            if vcs_url.startswith(github_url_pattern):
                project_url = vcs_url
            elif homepage_url.startswith(github_url_pattern):
                project_url = homepage_url
            else:
                project_url = None
            # If a valid GitHub address is found, clone the repository and call licensee
            if project_url:
                shell_script = shell_script_handlers["license-detector"].format(project_url=project_url)
                result, error = shell_exec(shell_script)
                if error == None:
                    try:
                        license_info = json.loads(result)
                        licenses_name = get_licenses_name(license_info)
                        item['declared_licenses'].append(licenses_name)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON from {project_url}: {e}")
                else:
                    logger.error("ruby_licenses job failed: {}, error: {}".format(project_url, error))
    return data

def dependency_checker_output_process(output):
    if not bool(output):
        return {}

    result = json.loads(output.decode('utf-8'))
    result = ruby_licenses(result)
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
        logger.error(f"Error processing dependency-checker output: {e}")
        return {}

    return result


def request_url (url, payload):
    response = post_with_backoff(url=url, json=payload)

    if response.status_code == 200:
        return response.text, None
    else:
        return None, f"Failed to send request. Status code: {response.status_code}"

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
        do_link_include_check = True
        templates = """
            You are a professional programmer, please assess whether the provided text offers a thorough and in-depth introduction to the processes of software compilation and packaging.
            If the text segment introduce the software compilation and packaging completely, please return 'YES'; otherwise, return 'NO'.
            You need to ensure the accuracy of your answers as much as possible, and if unsure, please simply answer NO. Your response must not include other content.

            Text content as below:

            {text}

        """
    elif type == "api-doc":
        do_link_include_check = False
        templates = """
            You are a professional programmer, please assess whether the provided text offer a comprehensive introduction to the use of software API.
            If the text segment introduce the software API completely, please return 'YES'; otherwise, return 'NO'.
            You need to ensure the accuracy of your answers as much as possible, and if unsure, please simply answer NO. Your response must not include other content.

            Text content as below:

            {text}

        """
    else:
        logger.info("Unsupported type: {}".format(type))
        return [], None

    satisfied_doc_file = []
    for document in documents:
        with open(document, 'r') as file:
            markdown_text = file.read()
            chunk_size = 3000
            chunks = [markdown_text[i:i+chunk_size] for i in range(0, len(markdown_text), chunk_size)]

        for _, chunk in enumerate(chunks):
            messages = [
                {
                    "role": "user",
                    "content": templates.format(text=chunk)
                }
            ]

            external_build_doc_link = "https://gitee.com/openharmony-tpc/docs/blob/master/OpenHarmony_har_usage.md"
            if do_link_include_check and external_build_doc_link.lower() in chunk.lower():
                return satisfied_doc_file, None

            result = completion_with_backoff(messages=messages, temperature=0.2)
            if result == "YES":
                satisfied_doc_file.append(document)
                return satisfied_doc_file, None
    return satisfied_doc_file, None

def get_all_releases_with_assets(project_url):
    """
    Get all releases and their assets, supporting github.com, gitee.com and gitcode.com.
    Returns:
        list: Each element is a release dict containing tag, name, assets and other fields.
        str or None: Error message, None if no error.
    """
    return platform_manager.get_releases(project_url)

def check_release_contents(project_url, type="notes", check_repo=False):
    """
    Check if all release packages of the specified project contain content files of the specified type.

    Function description:
    - Supports GitHub and Gitee platforms.
    - Iterate through all releases, download the archive package (zipball) of each release.
    - Check different types of content according to the type parameter:
        - "notes": Check changelog, releasenotes, release_notes and other files
        - "sbom": Check SBOM files (CDX, SPDX format)
    - Returns whether each release contains the specified content and its filename list.

    Parameters:
        project_url (str): Repository address of the project, supports GitHub and Gitee.
        type (str): Check type, "notes" or "sbom", default is "notes".
        check_repo (bool): Whether to also check repository source code, default is False.

    Returns:
        tuple: (result_dict, error)
            result_dict: {
                "is_released": bool,  # Whether there are releases
                "release_contents": [
                    {
                        "tag": version number,
                        "release_name": release name,
                        "has_content": whether there are specified content files,
                        "content_files": filename list,
                        "error": None or error message
                    }, ...
                ]
            }
            error: None or error message string
    """
    try:
        if type not in ["notes", "sbom"]:
            return {"is_released": False, "release_contents": []}, f"Unsupported type: {type}"
        
        owner_match = re.match(r"https://(?:github|gitee|gitcode).com/([^/]+)/", project_url)
        if not owner_match:
            return {"is_released": False, "release_contents": []}, "Invalid project URL format"
        
        owner_name = owner_match.group(1)
        repo_name = re.sub(r'\.git$', '', os.path.basename(project_url))

        all_releases, error = get_all_releases_with_assets(project_url)
        if error:
            return {"is_released": False, "release_contents": []}, error

        if not all_releases:
            return {"is_released": False, "release_contents": []}, "No releases found"

        file_patterns = _get_file_patterns(type)
        
        results = []
        for rel in all_releases:
            if rel.get('draft', False) or rel.get('prerelease', False):
                continue
                
            tag = rel.get("tag_name", "")
            release_name = rel.get("name", tag)
            
            zip_url = _get_zipball_url(project_url, owner_name, repo_name, tag)
            if not zip_url:
                results.append(_create_result_entry(tag, release_name, False, [], "No zipball_url"))
                continue
            
            found_files, error_msg = _check_zip_contents(zip_url, file_patterns)
            results.append(_create_result_entry(tag, release_name, bool(found_files), found_files, error_msg))
            
        return {"is_released": bool(results), "release_contents": results}, None
        
    except Exception as e:
        logger.error(f"Release contents check failed for {project_url}: {e}")
        return {"is_released": False, "release_contents": []}, f"Internal error: {str(e)}"


def _get_file_patterns(content_type):
    """
    Get file matching patterns based on content type.
    
    Args:
        content_type (str): Content type, "notes" or "sbom"
        
    Returns:
        list: List of file matching patterns
    """
    if content_type == "notes":
        return ["changelog", "releasenotes", "release_notes", "release", "release-notes"]
    elif content_type == "sbom":
        return [
            r'(?i).+\.(cdx\.json|cdx\.xml|spdx|spdx\.json|spdx\.xml|spdx\.y[a?]ml|spdx\.rdf|spdx\.rdf\.xml)'
        ]
    else:
        return []


def _get_zipball_url(project_url, owner_name, repo_name, tag):
    """
    Get zipball download URL.
    
    Args:
        project_url (str): Project URL
        owner_name (str): Owner name
        repo_name (str): Repository name
        tag (str): Tag name
        
    Returns:
        str: zipball URL, returns None if failed to get
    """
    return platform_manager.get_zipball_url(project_url, tag)


def _check_zip_contents(zip_url, file_patterns):
    """
    Check contents in zip file.
    
    Args:
        zip_url (str): zip file download URL
        file_patterns (list): List of file matching patterns
        
    Returns:
        tuple: (found_files, error_msg)
            found_files: List of found files
            error_msg: Error message, None if no error
    """
    try:
        response = requests.get(zip_url, timeout=30)
        if response.status_code != 200:
            return [], f"Failed to download release zip: {response.status_code}"
        
        with zipfile.ZipFile(io.BytesIO(response.content), 'r') as zip_ref:
            found_files = []
            for file_pattern in file_patterns:
                if isinstance(file_pattern, str):
                    for file_name in zip_ref.namelist():
                        base_name = os.path.basename(file_name).lower()
                        if base_name == file_pattern.lower():
                            found_files.append(file_name)
                else:
                    for file_name in zip_ref.namelist():
                        if re.match(file_pattern, file_name):
                            found_files.append(file_name)
            
            return found_files, None
            
    except requests.exceptions.Timeout:
        return [], "Download timeout"
    except requests.exceptions.RequestException as e:
        return [], f"Download failed: {str(e)}"
    except zipfile.BadZipFile:
        return [], "Invalid zip file"
    except Exception as e:
        return [], f"Failed to check release zip: {str(e)}"


def _create_result_entry(tag, release_name, has_content, content_files, error_msg):
    """
    Create result entry.
    
    Args:
        tag (str): Tag name
        release_name (str): Release name
        has_content (bool): Whether there is content
        content_files (list): List of content files
        error_msg (str): Error message
        
    Returns:
        dict: Result entry
    """
    return {
        "tag": tag,
        "release_name": release_name,
        "has_content": has_content,
        "content_files": content_files,
        "error": error_msg
    }

def check_signed_release(project_url):
    """
    Check if all release assets contain signature files, supports github.com and gitee.com.
    Returns: {
        'is_released': bool,  # Whether there are releases
        'signed_files': [
            {
                'tag': tag,
                'release_name': release_name,
                'signature_files': [filename list],
                'error': None or error message
            }, ...
        ]
    }, None or error
    """
    signature_exts = [
        ".minisig", ".asc", ".sig", ".sign", ".sigstore", ".intoto.jsonl"
    ]
    
    all_releases, error = get_all_releases_with_assets(project_url)
    if error:
        return {"is_released": False, "signed_files": []}, error
    
    if not all_releases:
        return {"is_released": False, "signed_files": []}, "No releases found"

    results = []
    for rel in all_releases:
        if rel.get('draft', False) or rel.get('prerelease', False):
            continue
        tag = rel.get("tag_name", "")
        release_name = rel.get("name", tag)
        assets = rel.get("assets", [])
        found_files = [a['name'] for a in assets if any(a['name'].lower().endswith(ext) for ext in signature_exts)]
        results.append({
            "tag": tag,
            "release_name": release_name,
            "signature_files": found_files,
            "error": None
        })
    return {"is_released": bool(results), "signed_files": results}, None

@log_performance('openchecker.agent')
def callback_func(ch, method, properties, body):
    """
    Message queue callback function, handles project check tasks
    
    Args:
        ch: Message channel
        method: Message method
        properties: Message properties
        body: Message body
    """
    logger.info(f"Starting to process message queue task", 
               extra={'extra_fields': {
                   'delivery_tag': method.delivery_tag,
                   'timestamp': datetime.now().isoformat()
               }})

    try:
        message = json.loads(body.decode('utf-8'))
        command_list = message.get('command_list', [])
        project_url = message.get('project_url')
        commit_hash = message.get("commit_hash")
        access_token = message.get("access_token")
        callback_url = message.get('callback_url')
        task_metadata = message.get('task_metadata', {})
        version_number = task_metadata.get("version_number", "None")
        
        project_url = project_url.replace(".git", "")
        logger.info(f"Starting to process project: {project_url}", 
                   extra={'extra_fields': {
                       'project_url': project_url,
                       'command_count': len(command_list),
                       'commands': command_list,
                       'callback_url': callback_url,
                       'version_number': version_number
                   }})

        if not project_url:
            logger.error("Project URL is required")
            return

        repos_dir = config.get("OpenCheck", {}).get("repos_dir", "/tmp/repos")
        logger.info(f"Repository directory: {repos_dir}")

        if not os.path.exists(repos_dir):
            os.makedirs(repos_dir, exist_ok=True)
            logger.info(f"Created repository directory: {repos_dir}")

        original_cwd = os.getcwd()

        os.chdir(repos_dir)
        logger.info(f"Switched to working directory: {os.getcwd()}")

        res_payload = {
            "command_list": command_list,
            "project_url": project_url,
            "task_metadata": task_metadata,
            "scan_results": {}
        }

        if not _download_project_source(project_url, version_number):
            _handle_error_and_nack(ch, method, body, "Failed to download project source")
            return

        _generate_lock_files(project_url)

        _execute_commands(command_list, project_url, res_payload, commit_hash, access_token)

        _cleanup_project_source(project_url)

        os.chdir(original_cwd)
        logger.info(f"Restored working directory: {os.getcwd()}")

        _send_results(callback_url, res_payload)
        
        ch.basic_ack(delivery_tag=method.delivery_tag)

        logger.info(f"Project {project_url} processed successfully", 
                   extra={'extra_fields': {
                       'project_url': project_url,
                       'command_count': len(command_list),
                       'timestamp': datetime.now().isoformat()
                   }})
        
    except Exception as e:
        logger.error(f"Error occurred while processing message: {e}", exc_info=True)

        try:
            os.chdir(original_cwd)
            logger.info(f"Restored working directory after exception: {os.getcwd()}")
        except:
            pass

        _handle_error_and_nack(ch, method, body, str(e))


def _download_project_source(project_url: str, version_number: str) -> bool:
    """
    Download project source code
    
    Args:
        project_url: Project URL
        version_number: Version number
        
    Returns:
        bool: Whether successful
    """
    try:
        shell_script = shell_script_handlers["download-checkout"].format(
            project_url=project_url, 
            version_number=version_number
        )
        result, error = shell_exec(shell_script)
        
        if error is None:
            logger.info(f"Source code download completed: {project_url}")
            return True
        else:
            logger.error(f"Source code download failed: {project_url}, error: {error}")
            return False
            
    except Exception as e:
        logger.error(f"Source code download exception: {e}")
        return False


def _generate_lock_files(project_url: str) -> None:
    """
    Generate lock files
    
    Args:
        project_url: Project URL
    """
    try:
        shell_script = shell_script_handlers["generate-lock_files"].format(project_url=project_url)
        result, error = shell_exec(shell_script)
        
        if error is None:
            logger.info(f"Lock files generation completed: {project_url}")
        else:
            logger.error(f"Lock files generation failed: {project_url}, error: {error}")
            
    except Exception as e:
        logger.error(f"Lock files generation exception: {e}")


def _execute_commands(command_list: list, project_url: str, res_payload: dict, commit_hash: str, access_token: str) -> None:
    """
    Execute command list
    
    Args:
        command_list: Command list
        project_url: Project URL
        res_payload: Response payload
        commit_hash: Commit hash
    """

    command_handlers = {
            'criticality-score': run_criticality_score,
            'scorecard-score': run_scorecard_cli,
            'code-count': get_code_count,
            'package-info': get_package_info,
            'ohpm-info': get_ohpm_info
        }
    
    command_switch = {
        'binary-checker': lambda: _handle_binary_checker(project_url, res_payload),
        'release-checker': lambda: _handle_release_checker(project_url, res_payload),
        'url-checker': lambda: _handle_url_checker(project_url, res_payload),
        'sonar-scanner': lambda: _handle_sonar_scanner(project_url, res_payload),
        'osv-scanner': lambda: _handle_shell_script_command('osv-scanner', project_url, res_payload),
        'scancode': lambda: _handle_shell_script_command('scancode', project_url, res_payload),
        'dependency-checker': lambda: _handle_shell_script_command('dependency-checker', project_url, res_payload),
        'readme-checker': lambda: _handle_shell_script_command('readme-checker', project_url, res_payload),
        'maintainers-checker': lambda: _handle_shell_script_command('maintainers-checker', project_url, res_payload),
        'languages-detector': lambda: _handle_shell_script_command('languages-detector', project_url, res_payload),
        'oat-scanner': lambda: _handle_shell_script_command('oat-scanner', project_url, res_payload),
        'license-detector': lambda: _handle_shell_script_command('license-detector', project_url, res_payload),
        'api-doc-checker': lambda: _handle_general_doc_checker(project_url, res_payload, "api-doc"),
        'build-doc-checker': lambda: _handle_general_doc_checker(project_url, res_payload, "build-doc"),
        'readme-opensource-checker': lambda: _handle_readme_opensource_checker(project_url, res_payload),
        'bestpractices-checker': lambda: bestpractices_checker(project_url, res_payload),
        'dangerous-workflow-checker': lambda: dangerous_workflow_checker(project_url, res_payload),
        'fuzzing-checker': lambda: fuzzing_checker(project_url, res_payload),
        'packaging-checker': lambda: packaging_checker(project_url, res_payload),
        'pinned-dependencies-checker': lambda: pinned_dependencies_checker(project_url, res_payload),
        'sast-checker': lambda: sast_checker(project_url, res_payload),
        'security-policy-checker': lambda: security_policy_checker(project_url, res_payload),
        'token-permissions-checker': lambda: token_permissions_checker(project_url, res_payload),
        'webhooks-checker': lambda: webhooks_checker(project_url, res_payload, access_token),
        'changed-files-since-commit-detector': lambda: _handle_changed_files_detector(project_url, res_payload, commit_hash),
        'criticality-score': lambda: _handle_standard_command('criticality-score', project_url, res_payload, command_handlers),
        'scorecard-score': lambda: _handle_standard_command('scorecard-score', project_url, res_payload, command_handlers),
        'code-count': lambda: _handle_standard_command('code-count', project_url, res_payload, command_handlers),
        'package-info': lambda: _handle_standard_command('package-info', project_url, res_payload, command_handlers),
        'ohpm-info': lambda: _handle_standard_command('ohpm-info', project_url, res_payload, command_handlers),
    }
    
    for command in command_list:
        if command in command_switch:
            try:
                logger.info(f"{command} job done: {project_url}")
                command_switch[command]()
            except Exception as e:
                logger.error(f"Error executing command {command}: {e}")
                res_payload["scan_results"][command] = {"error": str(e)}
        else:
            logger.warning(f"Unknown command: {command}")
        


def _handle_shell_script_command(command: str, project_url: str, res_payload: dict) -> None:
    """
    Generic function to handle shell script commands
    
    Args:
        command: Command name
        project_url: Project URL
        res_payload: Response payload
    """
    try:
        if command not in shell_script_handlers:
            logger.error(f"No shell script handler found for command: {command}")
            return
        
        shell_script = shell_script_handlers[command].format(project_url=project_url)
        result, error = shell_exec(shell_script)
        
        if error is None:
            logger.info(f"{command} job done: {project_url}")
            
            processed_result = _process_command_result(command, result)
            res_payload["scan_results"][command] = processed_result
        else:
            logger.error(f"{command} job failed: {project_url}, error: {error}")
            res_payload["scan_results"][command] = {"error": error.decode("utf-8")}
            
    except Exception as e:
        logger.error(f"{command} job failed: {project_url}, error: {e}")
        res_payload["scan_results"][command] = {"error": str(e)}


def _process_command_result(command: str, result) -> Any:
    """
    Process results according to command type
    
    Args:
        command: Command name
        result: Original result
        
    Returns:
        Processed result
    """
    if not result:
        return {}
    
    result_str = result.decode('utf-8')
    
    json_commands = ['osv-scanner', 'scancode', 'languages-detector']
    if command in json_commands:
        try:
            return json.loads(result_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON for {command}: {e}")
            return {"raw_output": result_str}
    
    if command == 'dependency-checker':
        return dependency_checker_output_process(result)

    elif command == 'oat-scanner':
        return parse_oat_txt_to_json(result_str)
    
    return result_str


def _handle_binary_checker(project_url: str, res_payload: dict) -> None:
    """Handle binary checker"""
    # file_dir = os.path.dirname(os.path.abspath(__file__))
    # project_root = os.path.dirname(file_dir)
    binary_checker_script = os.path.join(project_root, "scripts", "binary_checker.sh")

    result, error = shell_exec(binary_checker_script, project_url)
    if error is None:
        logger.info(f"binary-checker job done: {project_url}")
        # Process special output format of binary checker
        result_str = result.decode('utf-8') if result else ""
        data_list = result_str.split('\n')
        binary_file_list = []
        binary_archive_list = []
        for data in data_list[:-1]:
            if "Binary file found:" in data:
                binary_file_list.append(data.split(": ")[1])
            elif "Binary archive found:" in data:
                binary_archive_list.append(data.split(": ")[1])
        binary_result = {"binary_file_list": binary_file_list, "binary_archive_list": binary_archive_list}
        res_payload["scan_results"]["binary-checker"] = binary_result
    else:
        logger.error(f"binary-checker job failed: {project_url}, error: {error}")
        res_payload["scan_results"]["binary-checker"] = {"error": error.decode("utf-8")}


def _handle_release_checker(project_url: str, res_payload: dict) -> None:
    """Handle release checker"""
    res_payload["scan_results"]["release-checker"] = {}
    
    # Check release contents (notes and sbom)
    for task in ["notes", "sbom"]:
        content_check_result, error = check_release_contents(project_url, task)
        if error is None:
            logger.info(f"release-checker {task} job done: {project_url}")
            res_payload["scan_results"]["release-checker"][task] = content_check_result
        else:
            logger.error(f"release-checker {task} job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["release-checker"][task] = {"error": error}

    # Check signed release
    signed_release_result, error = check_signed_release(project_url)
    if error is None:
        logger.info(f"signed-release-checker job done: {project_url}")
        res_payload["scan_results"]["release-checker"]["signed-release-checker"] = signed_release_result
    else:
        logger.error(f"signed-release-checker job failed: {project_url}, error: {error}")
        res_payload["scan_results"]["release-checker"]["signed-release-checker"] = {"error": error}


def _handle_url_checker(project_url: str, res_payload: dict) -> None:
    """Handle URL checker"""
    try:
        response = requests.get(project_url, timeout=10)
        res_payload["scan_results"]["url-checker"] = {
            "status_code": response.status_code,
            "is_accessible": response.status_code == 200
        }
        logger.info(f"url-checker job done: {project_url}")
    except Exception as e:
        logger.error(f"url-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["url-checker"] = {"error": str(e)}


def _handle_sonar_scanner(project_url: str, res_payload: dict) -> None:
    """Handle SonarQube scanner"""
    try:
        # Use platform adapter to parse project URL
        try:
            owner_name, repo_name = platform_manager.parse_project_url(project_url)
            adapter = platform_manager.get_adapter(project_url)
            platform = adapter.get_platform_name() if adapter else "other"
            organization = owner_name
            project = repo_name
        except ValueError:
            platform, organization, project = "other", "default", "default"
        
        sonar_project_name = f"{platform}_{organization}_{project}"
        sonar_config = config.get("SonarQube", {})
        
        if not _check_sonar_project_exists(sonar_project_name, sonar_config):
            _create_sonar_project(sonar_project_name, sonar_config)
        
        shell_script = shell_script_handlers["sonar-scanner"].format(
            project_url=project_url, 
            sonar_project_name=sonar_project_name, 
            sonar_host=sonar_config.get('host', 'localhost'),
            sonar_port=sonar_config.get('port', '9000'),
            sonar_token=sonar_config.get('token', '')
        )
        result, error = shell_exec(shell_script)
        
        if error is None:
            logger.info(f"sonar-scanner finish scanning project: {project_url}, report querying...")
            sonar_result = _query_sonar_measures(sonar_project_name, sonar_config)
            res_payload["scan_results"]["sonar-scanner"] = sonar_result
            
            logger.info(f"sonar-scanner job done: {project_url}")
        else:
            logger.error(f"sonar-scanner job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["sonar-scanner"] = {"error": error.decode("utf-8")}
            
    except Exception as e:
        logger.error(f"sonar-scanner job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["sonar-scanner"] = {"error": str(e)}


def _check_sonar_project_exists(project_name: str, sonar_config: dict) -> bool:
    """
    Check if SonarQube project already exists
    
    Args:
        project_name: Project name
        sonar_config: SonarQube configuration
        
    Returns:
        bool: Whether project exists
    """
    try:
        search_api_url = f"http://{sonar_config['host']}:{sonar_config['port']}/api/projects/search"
        auth = (sonar_config.get("username"), sonar_config.get("password"))
        
        response = requests.get(
            search_api_url, 
            auth=auth, 
            params={"projects": project_name},
            timeout=30
        )
        
        if response.status_code == 200:
            logger.info("Call sonarqube projects search api success: 200")
            result = json.loads(response.text)
            exists = result["paging"]["total"] > 0
            if exists:
                logger.info(f"SonarQube project {project_name} already exists")
            return exists
        else:
            logger.error(f"Call sonarqube projects search api failed with status code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Call sonarqube projects search api failed with error: {e}")
        return False
    except Exception as e:
        logger.error(f"Exception checking SonarQube project: {e}")
        return False


def _create_sonar_project(project_name: str, sonar_config: dict) -> None:
    """
    Create SonarQube project
    
    Args:
        project_name: Project name
        sonar_config: SonarQube configuration
    """
    try:
        create_api_url = f"http://{sonar_config['host']}:{sonar_config['port']}/api/projects/create"
        auth = (sonar_config.get("username"), sonar_config.get("password"))
        
        payload = {
            "project": project_name, 
            "name": project_name
        }
        
        response = requests.post(create_api_url, auth=auth, data=payload, timeout=60)
        
        if response.status_code == 200:
            logger.info("Call sonarqube projects create api success: 200")
            logger.info(f"SonarQube project {project_name} created successfully")
        else:
            logger.error(f"Call sonarqube projects create api failed with status code: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Call sonarqube projects create api failed with error: {e}")
    except Exception as e:
        logger.error(f"Exception creating SonarQube project: {e}")


def _query_sonar_measures(project_name: str, sonar_config: dict) -> dict:
    """
    Query SonarQube project metrics
    
    Args:
        project_name: Project name
        sonar_config: SonarQube configuration
        
    Returns:
        dict: Query result
    """
    try:
        logger.info("Waiting for SonarQube data processing...")
        time.sleep(30)
        
        measures_api_url = f"http://{sonar_config['host']}:{sonar_config['port']}/api/measures/component"
        auth = (sonar_config.get("username"), sonar_config.get("password"))
        
        params = {
            "component": project_name, 
            "metricKeys": "coverage,complexity,duplicated_lines_density,lines"
        }
        
        response = requests.get(measures_api_url, auth=auth, params=params, timeout=30)
        
        if response.status_code == 200:
            logger.info("Querying sonar-scanner report success: 200")
            return json.loads(response.text)
        else:
            logger.error(f"Querying sonar-scanner report failed with status code: {response.status_code}")
            return {"error": f"Query failed with status code: {response.status_code}"}
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Querying sonar-scanner report failed with error: {e}")
        return {"error": f"Query failed: {str(e)}"}
    except Exception as e:
        logger.error(f"Exception querying SonarQube measures: {e}")
        return {"error": f"Query exception: {str(e)}"}


def _handle_doc_checker(project_url: str, res_payload: dict, doc_type: str) -> None:
    """
    Generic document checker handler function
    
    Args:
        project_url: Project URL
        res_payload: Response payload
        doc_type: Document type ("api-doc" or "build-doc")
    """
    try:
        result, error = check_doc_content(project_url, doc_type)
        if error is None:
            logger.info(f"{doc_type}-checker job done: {project_url}")
            # Set different result formats based on document type
            if doc_type == "api-doc":
                res_payload["scan_results"]["api-doc-checker"] = result
            else:  # build-doc
                res_payload["scan_results"]["build-doc-checker"] = {"build-doc-checker": result} if result else {}
        else:
            logger.error(f"{doc_type}-checker job failed: {project_url}, error: {error}")
            checker_name = f"{doc_type}-checker"
            res_payload["scan_results"][checker_name] = {"error": error}
    except Exception as e:
        logger.error(f"{doc_type}-checker job failed: {project_url}, error: {e}")
        checker_name = f"{doc_type}-checker"
        res_payload["scan_results"][checker_name] = {"error": str(e)}


def _handle_general_doc_checker(project_url: str, res_payload: dict, doc_type: str) -> None:
    """Handle general document checker"""
    _handle_doc_checker(project_url, res_payload, doc_type)


def _handle_standard_command(command: str, project_url: str, res_payload: dict, command_handlers: dict) -> None:
    """Handle standard command"""
    handler = command_handlers[command]
    result, error = handler(project_url)
    if error is None:
        logger.info(f"{command} job done: {project_url}")
        res_payload["scan_results"][command] = result
    else:
        logger.error(f"{command} job failed: {project_url}, error: {error}")
        res_payload["scan_results"][command] = {"error": error}


def _cleanup_project_source(project_url: str) -> None:
    """Clean up project source code"""
    try:
        shell_script = shell_script_handlers["remove-source-code"].format(project_url=project_url)
        result, error = shell_exec(shell_script)
        
        if error is None:
            logger.info(f"Source code cleanup done: {project_url}")
        else:
            logger.warning(f"Source code cleanup failed: {project_url}, error: {error}")
            
    except Exception as e:
        logger.error(f"Exception during source cleanup: {e}")


def _send_results(callback_url: str, res_payload: dict) -> None:
    """Send results"""
    if callback_url:
        try:
            response, err = request_url(callback_url, res_payload)
            if err is None:
                logger.info("Results sent successfully")
            else:
                logger.error(f"Failed to send results: {err}")
        except Exception as e:
            logger.error(f"Exception sending results: {e}")


def _handle_error_and_nack(ch, method, body, error_msg: str) -> None:
    """Handle error and nack"""
    logger.error(f"Putting message to dead letters: {error_msg}")
    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def run_criticality_score(project_url):
    cmd = ["criticality_score", "--repo", project_url, "--format", "json"]
    github_token = config["Github"]["access_key"]
    os.environ['GITHUB_AUTH_TOKEN'] = github_token
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        json_str = result.stderr
        json_str = json_str.replace("\n", "")
        pattern = r'{.*?}'
        match = re.search(pattern, json_str)
        json_res = {}
        if match:
            json_score = match.group()
            try:
                json_res = json.loads(json_score)
                criticality_score = json_res['criticality_score']
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse criticality score JSON: {e}")
                return None, "Failed to parse criticality score JSON."
            return {"criticality_score": criticality_score}, None
    else:
        return None, "URL is not supported by criticality score."

def run_scorecard_cli(project_url):
    cmd = ["scorecard", "--repo", project_url, "--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        try:
            scorecard_json = json.loads(result.stdout)
            scorecard_json = simplify_scorecard(scorecard_json)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse scorecard JSON: {e}")
            return None, "Failed to parse scorecard JSON."
        return scorecard_json, None
    else:
        return None, "URL is not supported by scorecard CLI."

def simplify_scorecard(data):
    simplified = {
        "score": data["score"],
        "checks": []
    }
    if data["checks"] is not None:
        for check in data["checks"]:
            simplified_check = {
                "name": check["name"],
                "score": check["score"]
            }
            simplified["checks"].append(simplified_check)
    
    return simplified

def get_code_count(project_url):
    project_name = os.path.basename(project_url).replace('.git', '')

    if not os.path.exists(project_name):
        subprocess.run(["git", "clone", project_url, "--depth=1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cmd = ["cloc", project_name, "--json"] 
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        if result.stdout.strip() == "":
            return 0, None
        result_json = json.loads(result.stdout)
        code_count = result_json['SUM']['code']
        return {"code_count": code_count}, None
    else:
        return None, "Failed to get code count."

def get_package_info(project_url):
    urlList = project_url.split("/")
    package_name = urlList[len(urlList) - 1]
    url = f"https://registry.npmjs.org/{package_name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        description =  data['description']
        home_url = data['homepage']
        version_data = data["versions"]
        *_, last_version = version_data.items()
        dependency = last_version[1].get("dependencies", {})
        dependent_count = len(dependency)
        url_down = f"https://api.npmjs.org/downloads/range/last-month/{package_name}"
        response_down = requests.get(url_down)
        if response_down.status_code == 200:
            down_data = response_down.json()
            last_month = down_data['downloads']
            down_count = 0
            for ch in last_month:
                down_count += ch['downloads']
            day_enter = last_month[0]['day'] + " - " + last_month[len(last_month) - 1]['day']   
            return {
                "description": description, 
                "home_url": home_url, 
                "dependent_count": dependent_count, 
                "down_count": down_count, 
                "day_enter": day_enter
                }, None
        elif response.status_code == 404:
            logger.error("Failed to get down_count for package: {} \n Error: Not found".format(package_name))
            return {"description": False, "home_url": False, "dependent_count": False, "down_count": False, "day_enter": False}, "Not found"
    else:
        # Use platform adapter to get repo info
        try:
            repo_info, repo_error = platform_manager.get_repo_info(project_url)
            download_stats, download_error = platform_manager.get_download_stats(project_url)
            
            if repo_error:
                logger.error(f"Failed to get repo info for {project_url}: {repo_error}")
                return {"description": False, "home_url": False, "dependent_count": False, "down_count": False, "day_enter": False}, repo_error
                
            description = repo_info.get("description", "")
            home_url = repo_info.get("homepage", "")
            down_count = download_stats.get("download_count", 0)
            day_enter = download_stats.get("period", "")
            
            return {
                "description": description, 
                "home_url": home_url, 
                "dependent_count": False, 
                "down_count": down_count, 
                "day_enter": day_enter
            }, None
        except Exception as e:
            logger.error(f"Failed to get package info for {project_url}: {e}")
            return {"description": False, "home_url": False, "dependent_count": False, "down_count": False, "day_enter": False}, str(e)

def get_ohpm_info(project_url):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        abs_dir = os.path.dirname(script_dir)
        file_path = os.path.join(abs_dir, 'config', 'ohpm_repo.json')
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        project_url = project_url.replace('.git', '')
        for name, repo_address in data.items():
            if repo_address.lower() == project_url.lower():
                url = 'https://ohpm.openharmony.cn/ohpmweb/registry/oh-package/openapi/v1/detail/'+ name
                response = requests.get(url)
                if response.status_code == 200:
                    repo_body = json.loads(response.text)
                    repo_json = repo_body['body']
                    down_count = repo_json['downloads']
                    dependent =  repo_json['dependencies']['total']
                    bedependent = repo_json['dependent']['total']
                    return {"down_count": down_count, "dependent": dependent, "bedependent": bedependent}, None
                else:
                    logger.error("Failed to get dependent、bedependent、down_count for repo: {} \n Error: {}".format(project_url, "Not found"))
                    return {"down_count": False, "dependent": False, "bedependent": False}, "Not found"
        return {"down_count": "", "dependent": "", "bedependent": ""}, None
    except Exception as e:
        logger.error("parse_oat_txt error: {}".format(e))
        return {"down_count": "", "dependent": "", "bedependent": ""}, None

def parse_oat_txt_to_json(txt):
    """
    Parse OAT tool output text report to JSON format
    
    Args:
        txt (str): OAT tool output text content
        
    Returns:
        dict: Parsed JSON format data
    """
    try:
        de_str = txt.decode('unicode_escape') if isinstance(txt, bytes) else txt
        result = {}
        lines = de_str.splitlines()
        current_section = None
        pattern = r"Name:\s*(.+?)\s*Content:\s*(.+?)\s*Line:\s*(\d+)\s*Project:\s*(.+?)\s*File:\s*(.+)"

        for line in lines:
            line = line.strip()
            if not line:
                continue
            total_count_match = re.search(r"^(.*) Total Count:\s*(\d+)", line, re.MULTILINE)
            category_name = total_count_match.group(1).strip() if total_count_match else "Unknown"

            if 'Total Count' in line:
                current_section = category_name
                total_count = int(line.split(":")[1].strip())
                result[current_section] = {"total_count": total_count, "details": []}
            elif line.startswith("Name:"):
                matches = re.finditer(pattern, line)
                for match in matches:
                    entry = {
                        "name": match.group(1).strip(),
                        "content": match.group(2).strip(),
                        "line": int(match.group(3).strip()),
                        "project": match.group(4).strip(),
                        "file": match.group(5).strip(),
                    }
                if current_section and "details" in result[current_section]:
                    result[current_section]["details"].append(entry)
        return result
    except Exception as e:
        logger.error(f"parse_oat_txt error: {e}")
        return {"error": str(e)}

def _handle_readme_opensource_checker(project_url: str, res_payload: dict) -> None:
    """Handle README.OpenSource checker"""
    try:
        result, error = check_readme_opensource(project_url)
        if error is None:
            logger.info(f"readme-opensource-checker job done: {project_url}")
            res_payload["scan_results"]["readme-opensource-checker"] = {"readme-opensource-checker": result} if result else {}
        else:
            logger.error(f"readme-opensource-checker job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["readme-opensource-checker"] = {"error": error}
    except Exception as e:
        logger.error(f"readme-opensource-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["readme-opensource-checker"] = {"error": str(e)}

        

def _handle_build_doc_checker(project_url: str, res_payload: dict) -> None:
    """Handle build document checker"""
    _handle_doc_checker(project_url, res_payload, "build-doc")


def _handle_changed_files_detector(project_url: str, res_payload: dict, commit_hash: str) -> None:
    """Handle changed files detector"""
    
    if not commit_hash:
        logger.error("Fail to get commit hash!")
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": "No commit hash provided"}
        return
    
    context_path = os.getcwd()
    try:
        repository_path = os.path.join(context_path, os.path.splitext(os.path.basename(urlparse(project_url).path))[0])
        os.chdir(repository_path)
        logger.info(f"change os path to git repository directory: {repository_path}")
    except OSError as e:
        logger.error(f"failed to change os path to git repository directory: {e}")
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": str(e)}
        return

    # Get different types of changed files
    changed_files = _get_diff_files(commit_hash, "ACDMRTUXB")
    new_files = _get_diff_files(commit_hash, "A")
    rename_files = _get_diff_files(commit_hash, "R")
    deleted_files = _get_diff_files(commit_hash, "D")
    modified_files = _get_diff_files(commit_hash, "M")

    os.chdir(context_path)

    res_payload["scan_results"]["changed-files-since-commit-detector"] = {
        "changed_files": changed_files,
        "new_files": new_files,
        "rename_files": rename_files,
        "deleted_files": deleted_files,
        "modified_files": modified_files
    }
    
    logger.info(f"changed-files-since-commit-detector job done: {project_url}")

def _get_diff_files(commit_hash: str, type="ACDMRTUXB"):
    """
    Get changed files of specified type
    
    Args:
        commit_hash (str): Commit hash
        type (str): Change type, can be: [(A|C|D|M|R|T|U|X|B)…​[*]]
            Added (A), Copied (C), Deleted (D), Modified (M), Renamed (R),
            have their type changed (T), are Unmerged (U), are Unknown (X), 
            or have had their pairing Broken (B).
            
    Returns:
        list: Changed files list
    """
    try:
        result = subprocess.check_output(
            ["git", "diff", "--name-only", f"--diff-filter={type}", f"{commit_hash}..HEAD"],
            stderr=subprocess.STDOUT,
            text=True
        )
        return result.strip().split("\n") if result else []
    except subprocess.CalledProcessError as e:
        logger.error(f"failed to get {type} files: {e.output}")
        return []


if __name__ == "__main__":
    consumer(config["RabbitMQ"], "opencheck", callback_func)
    logger.info('Agents server ended.')

# TODO: Add an adapter for various code platforms, like github, gitee, gitcode, etc.