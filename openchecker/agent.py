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
import logging
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s : %(message)s')


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

        # 检查 declared_licenses 是否为空
        if not declared_licenses or len(declared_licenses)==0:
            # 优先检查 vcs_url 是否为 GitHub 地址
            if vcs_url.startswith(github_url_pattern):
                project_url = vcs_url
            elif homepage_url.startswith(github_url_pattern):
                project_url = homepage_url
            else:
                project_url = None
            # 如果找到了有效的 GitHub 地址，克隆仓库并调用 licensee
            if project_url:
                shell_script = shell_script_handlers["license-detector"].format(project_url=project_url)
                result, error = shell_exec(shell_script)
                if error == None:
                    try:
                        license_info = json.loads(result)
                        licenses_name = get_licenses_name(license_info)
                        item['declared_licenses'].append(licenses_name)
                    except json.JSONDecodeError as e:
                        logging.error(f"Failed to parse JSON from {project_url}: {e}")
                else:
                    logging.error("ruby_licenses job failed: {}, error: {}".format(project_url, error))
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
        logging.error(f"Error processing dependency-checker output: {e}")
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
        logging.info("Unsupported type: {}".format(type))
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
    获取所有release及其assets，支持github.com、gitee.com和gitcode.com。
    返回：
        list: 每个元素为release的dict，包含tag、name、assets等字段。
        str or None: 错误信息，无错为None。
    """
    return platform_manager.get_releases(project_url)

def check_release_contents(project_url, type="notes", check_repo=False):
    """
    检查指定项目所有 release 包中是否包含指定类型的内容文件。

    功能说明：
    - 支持 GitHub 和 Gitee 平台。
    - 遍历所有 release，下载每个 release 的归档包（zipball）。
    - 根据type参数检查不同类型的内容：
        - "notes": 检查 changelog、releasenotes、release_notes 等文件
        - "sbom": 检查 SBOM 文件（CDX、SPDX 格式）
    - 返回每个 release 是否包含指定内容及其文件名列表。

    参数：
        project_url (str): 项目的仓库地址，支持 GitHub 和 Gitee。
        type (str): 检查类型，"notes" 或 "sbom"，默认为 "notes"。
        check_repo (bool): 是否同时检查仓库源码，默认为 False。

    返回：
        tuple: (result_dict, error)
            result_dict: {
                "is_released": bool,  # 是否有 release
                "release_contents": [
                    {
                        "tag": 版本号,
                        "release_name": release名称,
                        "has_content": 是否有指定内容文件,
                        "content_files": 文件名列表,
                        "error": None或错误信息
                    }, ...
                ]
            }
            error: None 或错误信息字符串
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
        logging.error(f"Release contents check failed for {project_url}: {e}")
        return {"is_released": False, "release_contents": []}, f"Internal error: {str(e)}"


def _get_file_patterns(content_type):
    """
    根据内容类型获取文件匹配模式。
    
    Args:
        content_type (str): 内容类型，"notes" 或 "sbom"
        
    Returns:
        list: 文件匹配模式列表
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
    获取zipball下载URL。
    
    Args:
        project_url (str): 项目URL
        owner_name (str): 所有者名称
        repo_name (str): 仓库名称
        tag (str): 标签名称
        
    Returns:
        str: zipball URL，如果获取失败返回None
    """
    return platform_manager.get_zipball_url(project_url, tag)


def _check_zip_contents(zip_url, file_patterns):
    """
    检查zip文件中的内容。
    
    Args:
        zip_url (str): zip文件下载URL
        file_patterns (list): 文件匹配模式列表
        
    Returns:
        tuple: (found_files, error_msg)
            found_files: 找到的文件列表
            error_msg: 错误信息，无错误为None
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
    创建结果条目。
    
    Args:
        tag (str): 标签名称
        release_name (str): 发布名称
        has_content (bool): 是否有内容
        content_files (list): 内容文件列表
        error_msg (str): 错误信息
        
    Returns:
        dict: 结果条目
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
    检查所有release的assets中是否包含签名文件，支持github.com和gitee.com。
    返回：{
        'is_released': bool,  # 是否有release
        'signed_files': [
            {
                'tag': tag,
                'release_name': release_name,
                'signature_files': [文件名列表],
                'error': None或错误信息
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

def callback_func(ch, method, properties, body):
    """
    消息队列回调函数，处理项目检查任务
    
    Args:
        ch: 消息通道
        method: 消息方法
        properties: 消息属性
        body: 消息体
    """
    logging.info(f"callback func called at {datetime.now()}")

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
        logging.info(f"Processing project: {project_url}")

        if not project_url:
            logging.error("Project URL is required")
            return

        repos_dir = config.get("OpenCheck", {}).get("repos_dir", "/tmp/repos")
        logging.info(f"Repos directory: {repos_dir}")

        if not os.path.exists(repos_dir):
            os.makedirs(repos_dir, exist_ok=True)
            logging.info(f"Created repos directory: {repos_dir}")

        original_cwd = os.getcwd()

        os.chdir(repos_dir)
        logging.info(f"Changed working directory to: {os.getcwd()}")

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
        logging.info(f"Restored working directory to: {os.getcwd()}")

        _send_results(callback_url, res_payload)
        

        ch.basic_ack(delivery_tag=method.delivery_tag)

        logging.info(f"Project {project_url} processed successfully at {datetime.now()}")
        
    except Exception as e:
        logging.error(f"Error processing message: {e}")

        try:
            os.chdir(original_cwd)
            logging.info(f"Restored working directory to: {os.getcwd()} after exception")
        except:
            pass

        _handle_error_and_nack(ch, method, body, str(e))


def _download_project_source(project_url: str, version_number: str) -> bool:
    """
    下载项目源码
    
    Args:
        project_url: 项目URL
        version_number: 版本号
        
    Returns:
        bool: 是否成功
    """
    try:
        shell_script = shell_script_handlers["download-checkout"].format(
            project_url=project_url, 
            version_number=version_number
        )
        result, error = shell_exec(shell_script)
        
        if error is None:
            logging.info(f"Download source code done: {project_url}")
            return True
        else:
            logging.error(f"Download source code failed: {project_url}, error: {error}")
            return False
            
    except Exception as e:
        logging.error(f"Exception during source download: {e}")
        return False


def _generate_lock_files(project_url: str) -> None:
    """
    生成锁文件
    
    Args:
        project_url: 项目URL
    """
    try:
        shell_script = shell_script_handlers["generate-lock_files"].format(project_url=project_url)
        result, error = shell_exec(shell_script)
        
        if error is None:
            logging.info(f"Lock files generation done: {project_url}")
        else:
            logging.error(f"Lock files generation failed: {project_url}, error: {error}")
            
    except Exception as e:
        logging.error(f"Exception during lock files generation: {e}")


def _execute_commands(command_list: list, project_url: str, res_payload: dict, commit_hash: str, access_token: str) -> None:
    """
    执行命令列表
    
    Args:
        command_list: 命令列表
        project_url: 项目URL
        res_payload: 响应载荷
        commit_hash: 提交哈希
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
                logging.info(f"{command} job done: {project_url}")
                command_switch[command]()
            except Exception as e:
                logging.error(f"Error executing command {command}: {e}")
                res_payload["scan_results"][command] = {"error": str(e)}
        else:
            logging.warning(f"Unknown command: {command}")
        


def _handle_shell_script_command(command: str, project_url: str, res_payload: dict) -> None:
    """
    处理shell脚本命令的通用函数
    
    Args:
        command: 命令名称
        project_url: 项目URL
        res_payload: 响应载荷
    """
    try:
        if command not in shell_script_handlers:
            logging.error(f"No shell script handler found for command: {command}")
            return
        
        shell_script = shell_script_handlers[command].format(project_url=project_url)
        result, error = shell_exec(shell_script)
        
        if error is None:
            logging.info(f"{command} job done: {project_url}")
            
            processed_result = _process_command_result(command, result)
            res_payload["scan_results"][command] = processed_result
        else:
            logging.error(f"{command} job failed: {project_url}, error: {error}")
            res_payload["scan_results"][command] = {"error": error.decode("utf-8")}
            
    except Exception as e:
        logging.error(f"{command} job failed: {project_url}, error: {e}")
        res_payload["scan_results"][command] = {"error": str(e)}


def _process_command_result(command: str, result) -> Any:
    """
    根据命令类型处理结果
    
    Args:
        command: 命令名称
        result: 原始结果
        
    Returns:
        处理后的结果
    """
    if not result:
        return {}
    
    result_str = result.decode('utf-8')
    
    json_commands = ['osv-scanner', 'scancode', 'languages-detector']
    if command in json_commands:
        try:
            return json.loads(result_str)
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to parse JSON for {command}: {e}")
            return {"raw_output": result_str}
    
    if command == 'dependency-checker':
        return dependency_checker_output_process(result)

    elif command == 'oat-scanner':
        return parse_oat_txt_to_json(result_str)
    
    return result_str


def _handle_binary_checker(project_url: str, res_payload: dict) -> None:
    """处理二进制检查器"""
    # file_dir = os.path.dirname(os.path.abspath(__file__))
    # project_root = os.path.dirname(file_dir)
    binary_checker_script = os.path.join(project_root, "scripts", "binary_checker.sh")

    result, error = shell_exec(binary_checker_script, project_url)
    if error is None:
        logging.info(f"binary-checker job done: {project_url}")
        # 处理二进制检查器的特殊输出格式
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
        logging.error(f"binary-checker job failed: {project_url}, error: {error}")
        res_payload["scan_results"]["binary-checker"] = {"error": error.decode("utf-8")}


def _handle_release_checker(project_url: str, res_payload: dict) -> None:
    """处理发布检查器"""
    res_payload["scan_results"]["release-checker"] = {}
    
    # 检查发布内容（notes和sbom）
    for task in ["notes", "sbom"]:
        content_check_result, error = check_release_contents(project_url, task)
        if error is None:
            logging.info(f"release-checker {task} job done: {project_url}")
            res_payload["scan_results"]["release-checker"][task] = content_check_result
        else:
            logging.error(f"release-checker {task} job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["release-checker"][task] = {"error": error}

    # 检查签名发布
    signed_release_result, error = check_signed_release(project_url)
    if error is None:
        logging.info(f"signed-release-checker job done: {project_url}")
        res_payload["scan_results"]["release-checker"]["signed-release-checker"] = signed_release_result
    else:
        logging.error(f"signed-release-checker job failed: {project_url}, error: {error}")
        res_payload["scan_results"]["release-checker"]["signed-release-checker"] = {"error": error}


def _handle_url_checker(project_url: str, res_payload: dict) -> None:
    """处理URL检查器"""
    try:
        response = requests.get(project_url, timeout=10)
        res_payload["scan_results"]["url-checker"] = {
            "status_code": response.status_code,
            "is_accessible": response.status_code == 200
        }
        logging.info(f"url-checker job done: {project_url}")
    except Exception as e:
        logging.error(f"url-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["url-checker"] = {"error": str(e)}


def _handle_sonar_scanner(project_url: str, res_payload: dict) -> None:
    """处理SonarQube扫描器"""
    try:
        # 使用平台适配器解析项目URL
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
            logging.info(f"sonar-scanner finish scanning project: {project_url}, report querying...")
            sonar_result = _query_sonar_measures(sonar_project_name, sonar_config)
            res_payload["scan_results"]["sonar-scanner"] = sonar_result
            
            logging.info(f"sonar-scanner job done: {project_url}")
        else:
            logging.error(f"sonar-scanner job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["sonar-scanner"] = {"error": error.decode("utf-8")}
            
    except Exception as e:
        logging.error(f"sonar-scanner job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["sonar-scanner"] = {"error": str(e)}


def _check_sonar_project_exists(project_name: str, sonar_config: dict) -> bool:
    """
    检查SonarQube项目是否已存在
    
    Args:
        project_name: 项目名称
        sonar_config: SonarQube配置
        
    Returns:
        bool: 项目是否存在
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
            logging.info("Call sonarqube projects search api success: 200")
            result = json.loads(response.text)
            exists = result["paging"]["total"] > 0
            if exists:
                logging.info(f"SonarQube project {project_name} already exists")
            return exists
        else:
            logging.error(f"Call sonarqube projects search api failed with status code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Call sonarqube projects search api failed with error: {e}")
        return False
    except Exception as e:
        logging.error(f"Exception checking SonarQube project: {e}")
        return False


def _create_sonar_project(project_name: str, sonar_config: dict) -> None:
    """
    创建SonarQube项目
    
    Args:
        project_name: 项目名称
        sonar_config: SonarQube配置
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
            logging.info("Call sonarqube projects create api success: 200")
            logging.info(f"SonarQube project {project_name} created successfully")
        else:
            logging.error(f"Call sonarqube projects create api failed with status code: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Call sonarqube projects create api failed with error: {e}")
    except Exception as e:
        logging.error(f"Exception creating SonarQube project: {e}")


def _query_sonar_measures(project_name: str, sonar_config: dict) -> dict:
    """
    查询SonarQube项目的度量指标
    
    Args:
        project_name: 项目名称
        sonar_config: SonarQube配置
        
    Returns:
        dict: 查询结果
    """
    try:
        logging.info("Waiting for SonarQube data processing...")
        time.sleep(30)
        
        measures_api_url = f"http://{sonar_config['host']}:{sonar_config['port']}/api/measures/component"
        auth = (sonar_config.get("username"), sonar_config.get("password"))
        
        params = {
            "component": project_name, 
            "metricKeys": "coverage,complexity,duplicated_lines_density,lines"
        }
        
        response = requests.get(measures_api_url, auth=auth, params=params, timeout=30)
        
        if response.status_code == 200:
            logging.info("Querying sonar-scanner report success: 200")
            return json.loads(response.text)
        else:
            logging.error(f"Querying sonar-scanner report failed with status code: {response.status_code}")
            return {"error": f"Query failed with status code: {response.status_code}"}
            
    except requests.exceptions.RequestException as e:
        logging.error(f"Querying sonar-scanner report failed with error: {e}")
        return {"error": f"Query failed: {str(e)}"}
    except Exception as e:
        logging.error(f"Exception querying SonarQube measures: {e}")
        return {"error": f"Query exception: {str(e)}"}


def _handle_doc_checker(project_url: str, res_payload: dict, doc_type: str) -> None:
    """
    通用的文档检查器处理函数
    
    Args:
        project_url: 项目URL
        res_payload: 响应载荷
        doc_type: 文档类型 ("api-doc" 或 "build-doc")
    """
    try:
        result, error = check_doc_content(project_url, doc_type)
        if error is None:
            logging.info(f"{doc_type}-checker job done: {project_url}")
            # 根据文档类型设置不同的结果格式
            if doc_type == "api-doc":
                res_payload["scan_results"]["api-doc-checker"] = result
            else:  # build-doc
                res_payload["scan_results"]["build-doc-checker"] = {"build-doc-checker": result} if result else {}
        else:
            logging.error(f"{doc_type}-checker job failed: {project_url}, error: {error}")
            checker_name = f"{doc_type}-checker"
            res_payload["scan_results"][checker_name] = {"error": error}
    except Exception as e:
        logging.error(f"{doc_type}-checker job failed: {project_url}, error: {e}")
        checker_name = f"{doc_type}-checker"
        res_payload["scan_results"][checker_name] = {"error": str(e)}


def _handle_general_doc_checker(project_url: str, res_payload: dict, doc_type: str) -> None:
    """处理通用文档检查器"""
    _handle_doc_checker(project_url, res_payload, doc_type)


def _handle_standard_command(command: str, project_url: str, res_payload: dict, command_handlers: dict) -> None:
    """处理标准命令"""
    handler = command_handlers[command]
    result, error = handler(project_url)
    if error is None:
        logging.info(f"{command} job done: {project_url}")
        res_payload["scan_results"][command] = result
    else:
        logging.error(f"{command} job failed: {project_url}, error: {error}")
        res_payload["scan_results"][command] = {"error": error}


def _cleanup_project_source(project_url: str) -> None:
    """清理项目源码"""
    try:
        shell_script = shell_script_handlers["remove-source-code"].format(project_url=project_url)
        result, error = shell_exec(shell_script)
        
        if error is None:
            logging.info(f"Source code cleanup done: {project_url}")
        else:
            logging.warning(f"Source code cleanup failed: {project_url}, error: {error}")
            
    except Exception as e:
        logging.error(f"Exception during source cleanup: {e}")


def _send_results(callback_url: str, res_payload: dict) -> None:
    """发送结果"""
    if callback_url:
        try:
            response, err = request_url(callback_url, res_payload)
            if err is None:
                logging.info("Results sent successfully")
            else:
                logging.error(f"Failed to send results: {err}")
        except Exception as e:
            logging.error(f"Exception sending results: {e}")


def _handle_error_and_nack(ch, method, body, error_msg: str) -> None:
    """处理错误并拒绝消息"""
    logging.error(f"Putting message to dead letters: {error_msg}")
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
                logging.error(f"Failed to parse criticality score JSON: {e}")
                return None, "Failed to parse criticality score JSON."
            return criticality_score, None
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
            logging.error(f"Failed to parse scorecard JSON: {e}")
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
        return code_count, None
    else:
        return None, "Failed to get code count."

def get_package_info(project_url):
    urlList = project_url.split("/")
    package_name = urlList[len(urlList) - 1]
    url = f"https://registry.npmjs.org/{package_name}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        ##功能描述
        description =  data['description']
        ##官网地址
        home_url = data['homepage']
        ##依赖
        version_data = data["versions"]
        *_, last_version = version_data.items()
        dependency = last_version[1].get("dependencies", {})
        dependent_count = len(dependency)
        ##下载量
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
            logging.error("Failed to get down_count for package: {} \n Error: Not found".format(package_name))
            return {"description": False, "home_url": False, "dependent_count": False, "down_count": False, "day_enter": False}, "Not found"
    else:
        # 使用平台适配器获取仓库信息
        try:
            repo_info, repo_error = platform_manager.get_repo_info(project_url)
            download_stats, download_error = platform_manager.get_download_stats(project_url)
            
            if repo_error:
                logging.error(f"Failed to get repo info for {project_url}: {repo_error}")
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
            logging.error(f"Failed to get package info for {project_url}: {e}")
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
                    logging.error("Failed to get dependent、bedependent、down_count for repo: {} \n Error: {}".format(project_url, "Not found"))
                    return {"down_count": False, "dependent": False, "bedependent": False}, "Not found"
        return {"down_count": "", "dependent": "", "bedependent": ""}, None
    except Exception as e:
        logging.error("parse_oat_txt error: {}".format(e))
        return {"down_count": "", "dependent": "", "bedependent": ""}, None

def parse_oat_txt_to_json(txt):
    """
    解析OAT工具输出的文本报告为JSON格式
    
    Args:
        txt (str): OAT工具输出的文本内容
        
    Returns:
        dict: 解析后的JSON格式数据
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
        logging.error(f"parse_oat_txt error: {e}")
        return {"error": str(e)}

def _handle_readme_opensource_checker(project_url: str, res_payload: dict) -> None:
    """处理README.OpenSource检查器"""
    try:
        result, error = check_readme_opensource(project_url)
        if error is None:
            logging.info(f"readme-opensource-checker job done: {project_url}")
            res_payload["scan_results"]["readme-opensource-checker"] = {"readme-opensource-checker": result} if result else {}
        else:
            logging.error(f"readme-opensource-checker job failed: {project_url}, error: {error}")
            res_payload["scan_results"]["readme-opensource-checker"] = {"error": error}
    except Exception as e:
        logging.error(f"readme-opensource-checker job failed: {project_url}, error: {e}")
        res_payload["scan_results"]["readme-opensource-checker"] = {"error": str(e)}

        

def _handle_build_doc_checker(project_url: str, res_payload: dict) -> None:
    """处理构建文档检查器"""
    _handle_doc_checker(project_url, res_payload, "build-doc")


def _handle_changed_files_detector(project_url: str, res_payload: dict, commit_hash: str) -> None:
    """处理变更文件检测器"""
    
    if not commit_hash:
        logging.error("Fail to get commit hash!")
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": "No commit hash provided"}
        return
    
    context_path = os.getcwd()
    try:
        repository_path = os.path.join(context_path, os.path.splitext(os.path.basename(urlparse(project_url).path))[0])
        os.chdir(repository_path)
        logging.info(f"change os path to git repository directory: {repository_path}")
    except OSError as e:
        logging.error(f"failed to change os path to git repository directory: {e}")
        res_payload["scan_results"]["changed-files-since-commit-detector"] = {"error": str(e)}
        return

    # 获取不同类型的变更文件
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
    
    logging.info(f"changed-files-since-commit-detector job done: {project_url}")

def _get_diff_files(commit_hash: str, type="ACDMRTUXB"):
    """
    获取指定类型的变更文件
    
    Args:
        commit_hash (str): 提交哈希
        type (str): 变更类型，可以是: [(A|C|D|M|R|T|U|X|B)…​[*]]
            Added (A), Copied (C), Deleted (D), Modified (M), Renamed (R),
            have their type changed (T), are Unmerged (U), are Unknown (X), 
            or have had their pairing Broken (B).
            
    Returns:
        list: 变更文件列表
    """
    try:
        result = subprocess.check_output(
            ["git", "diff", "--name-only", f"--diff-filter={type}", f"{commit_hash}..HEAD"],
            stderr=subprocess.STDOUT,
            text=True
        )
        return result.strip().split("\n") if result else []
    except subprocess.CalledProcessError as e:
        logging.error(f"failed to get {type} files: {e.output}")
        return []


if __name__ == "__main__":
    consumer(config["RabbitMQ"], "opencheck", callback_func)
    logging.info('Agents server ended.')

# TODO: Add an adapter for various code platforms, like github, gitee, gitcode, etc.