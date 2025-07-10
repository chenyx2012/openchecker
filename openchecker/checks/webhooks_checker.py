import logging
import re
import yaml
import requests
import json
import os
from ghapi.all import GhApi, paged
from pathlib import Path
from typing import Any, List, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s : %(message)s')

command = 'webhooks-checker'


def get_webhooks(project_url, access_token):
    """
    获取所有仓库webhooks, 支持github.com, gitee.com, gitcode.com。
    """

    owner_name = re.match(r"https://(?:github|gitee|gitcode).com/([^/]+)/", project_url).group(1)
    repo_name = re.sub(r'\.git$', '', os.path.basename(project_url))

    if "github.com" in project_url:
        # TODO
        pass

    elif "gitee.com" in project_url or "gitcode.com" in project_url:
        if "gitee.com" in project_url:
            # TODO
            pass
        else:
            url = f"https://api.gitcode.com/api/v5/repos/{owner_name}/{repo_name}/hooks?access_token={access_token}&page=1&per_page=100"

        headers = {
            'Accept': 'application/json'
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            hooks = response.json()
            return hooks, None
        else:
            logging.error(f"Failed to get hooks for repo: {project_url} \n Error: Not found")
            return [], "Not found"

    else:
        logging.info(f"Failed to do hooks check for repo: {project_url} \n Error: Not supported platform.")
        return [], "Not supported platform."


def webhooks_checker(project_url: str, res_payload: dict, access_token: str) -> None:
    """
    检查项目webhooks
    """
    logging.info(f"{command} processing projec: {project_url}")
    
    webhooks_hooks = []
    if access_token:
        hooks, msg = get_webhooks(project_url, access_token)
        if msg is None:
            webhooks_hooks = [
                {**hook, "password": "******"} 
                if hook.get("password") else hook for hook in hooks
            ]
    
    res_payload["scan_results"][command] = {
        "access_token": True if access_token else False,
        "webhooks_hooks": webhooks_hooks
    }
    logging.info(f"{command} processing completed projec: {project_url}")