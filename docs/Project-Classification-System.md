# Project Classification System

> **Relevant source files**
> * [openchecker/classify.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py)
> * [openchecker/clusters_util.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py)
> * [openchecker/llm.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py)
> * [openchecker/repo.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/repo.py)

## Purpose and Scope

The Project Classification System automatically categorizes software projects into predefined technology categories using Large Language Model (LLM) integration and machine learning techniques. This system processes project metadata including names, descriptions, topics, and languages to assign both first-level and second-level category classifications.

For information about project clustering and similarity analysis, see [Clustering and Embeddings](/Laniakea2012/openchecker/5.2-clustering-and-embeddings). For overall AI/ML system architecture, see [AI and Machine Learning Components](/Laniakea2012/openchecker/5-ai-and-machine-learning-components).

## Classification Architecture

The classification system operates through a pipeline that combines traditional NLP features with modern LLM-based categorization and embedding-based similarity analysis.

### System Components Overview

```mermaid
flowchart TD

ESClient["get_elasticsearch_client()"]
ProjectData["Project Metadata{name, description, topics, language}"]
YAMLCategories["collections.ymlCategory Definitions"]
TfIdfVectorizer["TfidfVectorizersklearn.feature_extraction.text"]
SentenceEmbeddingGenerator["SentenceEmbeddingGeneratorllm.py:51-81"]
EmbeddingCache[".embedding_cache.jsonCached Embeddings"]
ChatCompletionHandler["ChatCompletionHandlerllm.py:83-119"]
SystemMessage["system_messageCategory Instructions"]
FewShotExamples["few_shot_examplesClassification Examples"]
KMeansCustom["KMeansclusters_util.py:23-71"]
DistanceFunctions["euclidean_distance()manhattan_distance()"]
ClassificationResult["{project_name, assigned_first_level_category, assigned_second_level_category}"]
ClusterAssignment["cluster_idProject Groupings"]

    YAMLCategories --> SystemMessage
    ProjectData --> TfIdfVectorizer
    ProjectData --> SentenceEmbeddingGenerator
    TfIdfVectorizer --> KMeansCustom
    SentenceEmbeddingGenerator --> KMeansCustom
    ProjectData --> ChatCompletionHandler
    ChatCompletionHandler --> ClassificationResult
    KMeansCustom --> ClusterAssignment
subgraph Output ["Output"]
    ClassificationResult
    ClusterAssignment
end

subgraph ML_Processing ["ML Processing"]
    KMeansCustom
    DistanceFunctions
    KMeansCustom --> DistanceFunctions
end

subgraph Classification_Engine ["Classification Engine"]
    ChatCompletionHandler
    SystemMessage
    FewShotExamples
    SystemMessage --> ChatCompletionHandler
    FewShotExamples --> ChatCompletionHandler
end

subgraph Feature_Processing ["Feature Processing"]
    TfIdfVectorizer
    SentenceEmbeddingGenerator
    EmbeddingCache
    SentenceEmbeddingGenerator --> EmbeddingCache
end

subgraph Data_Input_Layer ["Data Input Layer"]
    ESClient
    ProjectData
    YAMLCategories
    ESClient --> ProjectData
end
```

**Sources:** [openchecker/classify.py L1-L112](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L1-L112)

 [openchecker/llm.py L1-L150](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L1-L150)

 [openchecker/clusters_util.py L1-L187](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L1-L187)

## LLM-Based Classification Workflow

The classification process uses structured prompts and few-shot learning to assign categories through LLM APIs.

### Classification Process Flow

[ERROR_PROCESSING_ELEMENT: PRE]

**Sources:** [openchecker/classify.py L23-L112](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L23-L112)

 [openchecker/llm.py L98-L104](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L98-L104)

### LLM Integration Components

| Component | Class/Function | Purpose |
| --- | --- | --- |
| Chat Handler | `ChatCompletionHandler` | Manages LLM API communication |
| Model Configuration | `model_name`, `base_url` | Configures Volcengine or OpenAI endpoints |
| Retry Logic | `@retry_with_exponential_backoff` | Handles API rate limits and failures |
| Response Parsing | `replace_single_quotes_with_regex()` | Sanitizes LLM JSON responses |

**Sources:** [openchecker/llm.py L83-L119](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L83-L119)

 [openchecker/classify.py L8-L10](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L8-L10)

## Embedding-Based Feature Extraction

The system generates semantic embeddings for project descriptions to enable similarity-based clustering and classification.

### Embedding Generation Pipeline

```mermaid
flowchart TD

ProjectDesc["project['description']"]
CacheCheck["hash(description)in embedding_cache_data"]
AutoTokenizer["AutoTokenizer.from_pretrained()"]
AutoModel["AutoModel.from_pretrained()"]
TokenizeStep["tokenizer(sentences,padding=True, truncation=True)"]
ModelForward["model(**encoded_input)"]
Normalize["torch.nn.functional.normalize()"]
EmbeddingCache[".embedding_cache.json"]
CacheWrite["json.dump()"]

    CacheCheck -->|Cache Miss| AutoTokenizer
    CacheCheck -->|Cache Miss| EmbeddingCache
    Normalize --> EmbeddingCache
subgraph Caching_Layer ["Caching Layer"]
    EmbeddingCache
    CacheWrite
    EmbeddingCache --> CacheWrite
end

subgraph Model_Processing ["Model Processing"]
    AutoTokenizer
    AutoModel
    TokenizeStep
    ModelForward
    Normalize
    AutoTokenizer --> TokenizeStep
    TokenizeStep -->|Cache Hit| AutoModel
    AutoModel -->|Cache Hit| ModelForward
    ModelForward --> Normalize
end

subgraph Input_Processing ["Input Processing"]
    ProjectDesc
    CacheCheck
    ProjectDesc --> CacheCheck
end
```

**Sources:** [openchecker/llm.py L51-L81](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L51-L81)

 [openchecker/clusters_util.py L130-L152](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L130-L152)

### SentenceEmbeddingGenerator Implementation

The `SentenceEmbeddingGenerator` class provides the core embedding functionality:

```
# Key methods from llm.py:51-81
def __init__(self, model_path):
    self.tokenizer = AutoTokenizer.from_pretrained(model_path)
    self.model = AutoModel.from_pretrained(model_path)

def generate_embeddings(self, sentences):
    encoded_input = self.tokenizer(sentences, padding=True, truncation=True, return_tensors='pt')
    with torch.no_grad():
        model_output = self.model(**encoded_input)
        sentence_embeddings = model_output[0][:, 0]
    return torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)
```

**Sources:** [openchecker/llm.py L51-L81](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L51-L81)

## Category Management System

Categories are defined in YAML configuration files and parsed into structured dictionaries for LLM prompt construction.

### Category Structure and Processing

```mermaid
flowchart TD

YAMLFile["collections.yml"]
YAMLStructure["{name: 'Category Name',items: ['subcategory1', 'subcategory2']}"]
ExtractFunction["extract_second_level_categories()"]
CategoryDict["categories = {'Operation System': [...],'Database': [...]}"]
SystemMessage["system_message['content']"]
CategoryInstructions["给定的一级分类及二级分类信息及对应关系如下:{categories}"]
ProjectSchema["{'project_name': '具体项目名称','assigned_first_level_category': '划分到的一级类别名称','assigned_second_level_category': '划分到的二级类别名称'}"]

    YAMLStructure --> ExtractFunction
    CategoryDict --> SystemMessage
subgraph LLM_Prompt_Construction ["LLM Prompt Construction"]
    SystemMessage
    CategoryInstructions
    ProjectSchema
    SystemMessage --> CategoryInstructions
    CategoryInstructions --> ProjectSchema
end

subgraph Processing_Functions ["Processing Functions"]
    ExtractFunction
    CategoryDict
    ExtractFunction --> CategoryDict
end

subgraph Category_Definition ["Category Definition"]
    YAMLFile
    YAMLStructure
    YAMLFile --> YAMLStructure
end
```

**Sources:** [openchecker/classify.py L11-L21](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L11-L21)

 [openchecker/classify.py L59-L67](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L59-L67)

### Example Classification Response Format

The system expects LLM responses in a specific JSON schema:

| Field | Description | Example |
| --- | --- | --- |
| `project_name` | Exact project name | "PostgreSQL" |
| `assigned_first_level_category` | Primary category | "Database" |
| `assigned_second_level_category` | Subcategory | "sql-database" |

**Sources:** [openchecker/classify.py L40-L51](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L40-L51)

 [openchecker/classify.py L53-L57](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L53-L57)

## Data Flow and Storage

The classification system processes projects in batches and maintains results in JSON files with intermediate checkpointing.

### Batch Processing Architecture

```mermaid
flowchart TD

ESGenerator["get_generator()Elasticsearch Pagination"]
ProjectFiles["all_projects_part_{input_param}.json"]
BatchCounter["count += 1"]
ProjectProcessing["project_m = {name, description}"]
LLMCall["llm.non_streaming_chat(messages)"]
ResultParsing["json.loads(llm_result)"]
ErrorHandling["try/except Exception"]
ResultAccumulation["result_projects.append(project)"]
BatchCheckpoint["if count == 100: write to file"]
FinalOutput["all_projects_part_{input_param}.json"]

    ProjectFiles --> BatchCounter
    ErrorHandling --> ResultAccumulation
subgraph Output_Management ["Output Management"]
    ResultAccumulation
    BatchCheckpoint
    FinalOutput
    ResultAccumulation --> BatchCheckpoint
    BatchCheckpoint --> FinalOutput
end

subgraph Processing_Loop ["Processing Loop"]
    BatchCounter
    ProjectProcessing
    LLMCall
    ResultParsing
    ErrorHandling
    BatchCounter --> ProjectProcessing
    ProjectProcessing --> LLMCall
    LLMCall --> ResultParsing
    ResultParsing --> ErrorHandling
end

subgraph Input_Sources ["Input Sources"]
    ESGenerator
    ProjectFiles
    ESGenerator --> ProjectFiles
end
```

**Sources:** [openchecker/classify.py L69-L112](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L69-L112)

 [openchecker/repo.py L74-L114](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/repo.py#L74-L114)

### Configuration and Environment Variables

The system requires specific environment configuration for LLM API access:

| Environment Variable | Purpose | API Provider |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI API authentication | openai.com |
| `ARK_API_KEY` | Volcengine API authentication | ark.cn-beijing.volces.com |

**Sources:** [openchecker/llm.py L84-L95](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L84-L95)

## Error Handling and Reliability

The classification system implements robust error handling and retry mechanisms to ensure reliable operation with external LLM APIs.

### Retry and Recovery Mechanisms

```mermaid
flowchart TD

FunctionCall["llm.non_streaming_chat()"]
RetryDecorator["@retry_with_exponential_backoff"]
APICall["client.chat.completions.create()"]
RateLimitError["openai.RateLimitError"]
APIError["openai.APIError"]
TimeoutError["openai.Timeout"]
ConnectionError["openai.APIConnectionError"]
InternalError["openai.InternalServerError"]
DelayCalculation["delay *= exponential_base"]
SleepPeriod["time.sleep(delay)"]
RetryCounter["num_retries += 1"]
MaxRetryCheck["if num_retries > max_retries"]

    APICall --> RateLimitError
    APICall --> APIError
    APICall --> TimeoutError
    APICall --> ConnectionError
    APICall --> InternalError
    RateLimitError --> DelayCalculation
    APIError --> DelayCalculation
    TimeoutError --> DelayCalculation
    ConnectionError --> DelayCalculation
    InternalError --> DelayCalculation
subgraph Recovery_Strategy ["Recovery Strategy"]
    DelayCalculation
    SleepPeriod
    RetryCounter
    MaxRetryCheck
    DelayCalculation --> SleepPeriod
    SleepPeriod --> RetryCounter
    RetryCounter --> MaxRetryCheck
end

subgraph Error_Types ["Error Types"]
    RateLimitError
    APIError
    TimeoutError
    ConnectionError
    InternalError
end

subgraph API_Call_Flow ["API Call Flow"]
    FunctionCall
    RetryDecorator
    APICall
    FunctionCall --> RetryDecorator
    RetryDecorator --> APICall
end
```

**Sources:** [openchecker/llm.py L7-L49](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L7-L49)

 [openchecker/classify.py L92-L99](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/classify.py#L92-L99)