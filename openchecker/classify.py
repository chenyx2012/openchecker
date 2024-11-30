from llm import ChatCompletionHandler
import yaml
import json
from repo import get_generator, get_elasticsearch_client

def extract_second_level_categories(yaml_file_path):
    categories = {}

    with open(yaml_file_path, 'r') as file:
        data = yaml.safe_load(file)

    for category in data:
        categories[category["name"]] = category['items']

    return categories


if __name__ == "__main__":
    yaml_file_path = "/home/guoqiang/opencheck/test/collections.yml"
    categories = extract_second_level_categories(yaml_file_path)
    result_projects_file_path = "/home/guoqiang/opencheck/test/result_projects.json"

    few_shot_examples = """例如有如下项目信息：
        name：DataVisTool
        description：这是一个用于快速创建各种数据可视化图表的工具，支持多种数据源接入，能够方便地进行数据探索和展示。
        language：Python
        topics：[Data visualization, Chart drawing, Data analysis]
        按照要求，模型的输出应该如下：
        [{
            "project_name": "[DataVisTool]",
            "assigned_first_level_category": "Frontend",
            "assigned_second_level_category": "data-visualization",
        }]
        """

    project_schema = """[{
            "project_name": "具体开源项目名称",
            "assigned_first_level_category": "划分到的一级类别名称，如果是新建类别则在此处明确写出新建的类别名称",
            "assigned_second_level_category": "划分到的二级类别名称，如果是新建类别则在此处明确写出新建的类别名称",
            }]"""

    system_message = {
        "role": "system",
        "content": f"""你是一个专业的项目分类助手，能够根据输入的开源项目的各项信息和给定的类别列表，准确地将项目划分到合适的二级分类类别中。一个项目可以被划分到多个分类中，且只能划分到给定的类别中，你要尽可能保证分类准确性。请严格按照以下格式输出结果，以方便后续的解析处理：
            {project_schema}

            给定的一级分类及二级分类信息及对应关系如下：
            {categories}

            {few_shot_examples}
            """
    }

    opensearch_url = ""
    repo_index = "github_event_repository"
    client = get_elasticsearch_client(opensearch_url)
    body = {
        "_source": ["name", "html_url", "description", "topics", "language"],
        "query": {
            "bool": {
                "must": [
                    {
                        "exists": {
                            "field": "topics"
                        }
                    },
                    {
                        "exists": {
                            "field": "language"
                        }
                    },
                    {
                        "exists": {
                            "field": "description"
                        }
                    }
                ]
            }
        },
        "size": 100
    }
    
    repo_generator = get_generator(client, body, repo_index)
    result_projects = []
    
    count = 0
    all_count = 0
    for repo_item in repo_generator:
        count += 1
        all_count += 1
        project = {
                "name": repo_item["_source"]["name"], 
                "description": repo_item["_source"]["description"],
                "topics": repo_item["_source"]["topics"],
                "language": repo_item["_source"]["language"]
                }

        user_message = {
            "role": "user", 
            "content": """以下是需要进行分类的开源项目的详细信息：
            {}
            """.format(project)
        }
        
        messages = [system_message, user_message]
        
        llm = ChatCompletionHandler(model_name="ep-20241129094859-p47sh", base_url=f"https://ark.cn-beijing.volces.com/api/v3/")
        
        try:
            llm_result = json.loads(llm.non_streaming_chat(messages))
            first_category, second_category = [res['assigned_first_level_category']  for res in llm_result], [res['assigned_second_level_category'] for res in llm_result]
        except Exception as e:
            print("Failed to category: ", project['name'], e)
            print(llm_result)
            first_category, second_category = '', ''
            
        project["assigned_first_level_category"] = first_category
        project['assigned_second_level_category'] = second_category
        
        result_projects.append(project)

        if count == 20:
            with open(result_projects_file_path, 'w', encoding='utf-8') as f:
                json.dump(result_projects, f, ensure_ascii=True)
            
            count = 0

        if all_count == 5000:
            exit()
