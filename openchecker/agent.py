import subprocess
from message_queue import consumer
from helper import read_config
from datetime import datetime
from exponential_backoff import post_with_backoff
import json
import requests
import re
import time
import os
import zipfile
import io
from urllib.parse import urlparse
from constans import shell_script_handlers
from typing import Any, List, Dict
from pathlib import Path
from platform_adapter import platform_manager
from common import shell_exec
from checkers.fuzzing_checker import fuzzing_checker
from checkers.dangerous_workflow_checker import dangerous_workflow_checker
from checkers.bestpractices_checker import bestpractices_checker
from checkers.packaging_checker import packaging_checker
from checkers.pinned_dependencies_checker import pinned_dependencies_checker
from checkers.sast_checker import sast_checker
from checkers.security_policy_checker import security_policy_checker
from checkers.token_permissions_checker import token_permissions_checker
from checkers.webhooks_checker import webhooks_checker
from checkers.document_checker import api_doc_checker, build_doc_checker, readme_opensource_checker
from checkers.release_checker import release_checker
from checkers.binary_checker import binary_checker
from checkers.url_checker import url_checker
from checkers.sonar_checker import sonar_checker
from checkers.standard_command_checker import (
    criticality_score_checker, scorecard_score_checker, code_count_checker,
    package_info_checker, ohpm_info_checker
)
from checkers.changed_files_checker import changed_files_detector
from logger import get_logger, log_performance, setup_logging

setup_logging(
    log_level=os.getenv('LOG_LEVEL', 'INFO'),
    log_format=os.getenv('LOG_FORMAT', 'structured'),
    enable_console=True,
    enable_file=False,
    log_dir='logs'
)
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


    
    command_switch = {
        'binary-checker': lambda: binary_checker(project_url, res_payload),
        'release-checker': lambda: release_checker(project_url, res_payload),
        'url-checker': lambda: url_checker(project_url, res_payload),
        'sonar-scanner': lambda: sonar_checker(project_url, res_payload, config),
        'osv-scanner': lambda: _handle_shell_script_command('osv-scanner', project_url, res_payload),
        'scancode': lambda: _handle_shell_script_command('scancode', project_url, res_payload),
        'dependency-checker': lambda: _handle_shell_script_command('dependency-checker', project_url, res_payload),
        'readme-checker': lambda: _handle_shell_script_command('readme-checker', project_url, res_payload),
        'maintainers-checker': lambda: _handle_shell_script_command('maintainers-checker', project_url, res_payload),
        'languages-detector': lambda: _handle_shell_script_command('languages-detector', project_url, res_payload),
        'oat-scanner': lambda: _handle_shell_script_command('oat-scanner', project_url, res_payload),
        'license-detector': lambda: _handle_shell_script_command('license-detector', project_url, res_payload),
        'api-doc-checker': lambda: api_doc_checker(project_url, res_payload),
        'build-doc-checker': lambda: build_doc_checker(project_url, res_payload),
        'readme-opensource-checker': lambda: readme_opensource_checker(project_url, res_payload),
        'bestpractices-checker': lambda: bestpractices_checker(project_url, res_payload),
        'dangerous-workflow-checker': lambda: dangerous_workflow_checker(project_url, res_payload),
        'fuzzing-checker': lambda: fuzzing_checker(project_url, res_payload),
        'packaging-checker': lambda: packaging_checker(project_url, res_payload),
        'pinned-dependencies-checker': lambda: pinned_dependencies_checker(project_url, res_payload),
        'sast-checker': lambda: sast_checker(project_url, res_payload),
        'security-policy-checker': lambda: security_policy_checker(project_url, res_payload),
        'token-permissions-checker': lambda: token_permissions_checker(project_url, res_payload),
        'webhooks-checker': lambda: webhooks_checker(project_url, res_payload, access_token),
        'changed-files-since-commit-detector': lambda: changed_files_detector(project_url, res_payload, commit_hash),
        'criticality-score': lambda: criticality_score_checker(project_url, res_payload, config),
        'scorecard-score': lambda: scorecard_score_checker(project_url, res_payload),
        'code-count': lambda: code_count_checker(project_url, res_payload),
        'package-info': lambda: package_info_checker(project_url, res_payload),
        'ohpm-info': lambda: ohpm_info_checker(project_url, res_payload),
    }
    
    for command in command_list:
        if command in command_switch:
            try:
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




if __name__ == "__main__":
    consumer(config["RabbitMQ"], "opencheck", callback_func)
    logger.info('Agents server ended.')

# TODO: Add an adapter for various code platforms, like github, gitee, gitcode, etc.