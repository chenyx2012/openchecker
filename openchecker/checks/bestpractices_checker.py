import logging
import re
import yaml
import requests
import json
from pathlib import Path
from typing import Any, List, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s : %(message)s')

command = 'bestpractices-checker'

def bestpractices_checker(project_url: str, res_payload: dict) -> None:
    """
    获取项目的OpenSSF Best Pactices
    """
    logging.info(f"{command} processing projec: {project_url}")
    api_url = f"https://www.bestpractices.dev/projects.json?url={project_url}"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        logging.info(f"{command} processing completed projec: {project_url}")
        if data and len(data) > 0:
            res_payload["scan_results"][command] = data[0]
        else:
            res_payload["scan_results"][command] = {}
            
    except requests.exceptions.RequestException as e:
        logging.info(f"{command} request api fail projec: {project_url}, error: {e}")
        res_payload["scan_results"][command] = {}
    except json.JSONDecodeError as e:
        logging.info(f"{command} parse json fail projec: {project_url}, error: {e}")
        res_payload["scan_results"][command] = {}