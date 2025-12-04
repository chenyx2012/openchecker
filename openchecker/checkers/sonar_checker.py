import os
import json
import time
import requests
from typing import Dict, Tuple
from constans import shell_script_handlers
from common import shell_exec
from platform_adapter import platform_manager
from logger import get_logger

logger = get_logger('openchecker.checkers.sonar_checker')


def sonar_checker(project_url: str, res_payload: dict, config: dict) -> None:
    """
    SonarQube scanner checker
    
    Args:
        project_url: Project URL
        res_payload: Response payload
        config: Configuration dictionary
    """
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
            sonar_token=sonar_config.get('token', ''),
            scan_timeout=sonar_config.get('scan_timeout', '1800')
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