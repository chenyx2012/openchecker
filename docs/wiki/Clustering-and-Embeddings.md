# Clustering and Embeddings

> **Relevant source files**
> * [openchecker/clusters_util.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py)
> * [openchecker/llm.py](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py)

This document covers the project clustering and embedding generation capabilities within OpenChecker. The system uses a combination of traditional NLP techniques (TF-IDF) and modern transformer-based embeddings to group similar projects together for analysis optimization and insight generation. For information about project classification into predefined categories, see [Project Classification System](/Laniakea2012/openchecker/5.1-project-classification-system).

## Clustering Pipeline Overview

The clustering system operates on project metadata to identify groups of similar projects using a dual-feature approach combining TF-IDF vectors and sentence embeddings.

```mermaid
flowchart TD

ProjectData["Project Metadataname, description, topics, language"]
TfIdf["TfidfVectorizersklearn.feature_extraction.text"]
EmbedGen["SentenceEmbeddingGeneratorllm.py:51-81"]
Cache["Embedding Cache.embedding_cache.json"]
EuclideanDist["euclidean_distance()clusters_util.py:10-14"]
ManhattanDist["manhattan_distance()clusters_util.py:17-21"]
CosineSim["cosine_similaritysklearn.metrics.pairwise"]
CustomKMeans["KMeansclusters_util.py:23-71"]
Centroids["centroids_x, centroids_yDual centroid tracking"]
Clusters["clusters_with_indexProject groupings by similarity"]
ClusterAssignment["cluster_id assignmentPer-project cluster membership"]

    ProjectData --> TfIdf
    ProjectData --> EmbedGen
    TfIdf --> CustomKMeans
    EmbedGen --> CustomKMeans
    EuclideanDist --> CustomKMeans
    ManhattanDist --> CustomKMeans
    CosineSim --> CustomKMeans
    CustomKMeans --> Clusters
subgraph Output ["Output"]
    Clusters
    ClusterAssignment
    Clusters --> ClusterAssignment
end

subgraph Clustering_Algorithm ["Clustering Algorithm"]
    CustomKMeans
    Centroids
    CustomKMeans --> Centroids
end

subgraph Distance_Calculation ["Distance Calculation"]
    EuclideanDist
    ManhattanDist
    CosineSim
end

subgraph Feature_Extraction ["Feature Extraction"]
    TfIdf
    EmbedGen
    Cache
    EmbedGen --> Cache
end

subgraph Input_Data ["Input Data"]
    ProjectData
end
```

**Sources:** [openchecker/clusters_util.py L1-L187](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L1-L187)

 [openchecker/llm.py L51-L81](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L51-L81)

## Feature Extraction Methods

The system employs two complementary feature extraction approaches to capture different aspects of project similarity.

### TF-IDF Vectorization

Traditional term frequency-inverse document frequency vectorization creates sparse feature vectors from project text data.

```mermaid
flowchart TD

ProjectText["project_to_feature_vector()clusters_util.py:109-111"]
ConcatText["Concatenated Textname + description + language + topics"]
TfIdfVect["TfidfVectorizersklearn.feature_extraction.text"]
SparseMatrix["X matrixfit_transform() output"]
Vocabulary["vocabulary_Word-to-index mapping"]
ToArray["X.toarray()Dense array conversion"]
DistanceCalc["Distance calculationFor clustering input"]

    ConcatText --> TfIdfVect
    SparseMatrix --> ToArray
subgraph Processing ["Processing"]
    ToArray
    DistanceCalc
    ToArray --> DistanceCalc
end

subgraph Vectorization ["Vectorization"]
    TfIdfVect
    SparseMatrix
    Vocabulary
    TfIdfVect --> SparseMatrix
    TfIdfVect --> Vocabulary
end

subgraph Text_Preparation ["Text Preparation"]
    ProjectText
    ConcatText
    ProjectText --> ConcatText
end
```

The `project_to_feature_vector()` function [openchecker/clusters_util.py L109-L111](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L109-L111)

 combines all textual project metadata into a single string for vectorization.

**Sources:** [openchecker/clusters_util.py L108-L124](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L108-L124)

### LLM Embeddings Generation

Modern transformer-based embeddings provide dense semantic representations using the BGE (BAAI General Embedding) model.

```mermaid
flowchart TD

ModelPath["/home/guoqiang/models/bge-large-en-v1.5Local transformer model"]
Tokenizer["AutoTokenizertransformers.AutoTokenizer"]
Model["AutoModeltransformers.AutoModel"]
SentEmbed["SentenceEmbeddingGeneratorllm.py:51-81"]
Encoding["tokenizer encodingpadding, truncation, tensor conversion"]
ModelOutput["model(**encoded_input)Forward pass through transformer"]
Normalize["torch.nn.functional.normalizeL2 normalization"]
HashCheck["hash(project['description'])Cache key generation"]
CacheFile[".embedding_cache.jsonPersistent embedding storage"]
CacheLoad["Cache loading/savingJSON serialization"]

    Tokenizer --> SentEmbed
    Model --> SentEmbed
    SentEmbed --> CacheLoad
subgraph Caching_System ["Caching System"]
    HashCheck
    CacheFile
    CacheLoad
    HashCheck --> CacheFile
    CacheFile --> CacheLoad
end

subgraph Embedding_Generation ["Embedding Generation"]
    SentEmbed
    Encoding
    ModelOutput
    Normalize
    SentEmbed --> Encoding
    Encoding --> ModelOutput
    ModelOutput --> Normalize
end

subgraph Model_Loading ["Model Loading"]
    ModelPath
    Tokenizer
    Model
    ModelPath --> Tokenizer
    ModelPath --> Model
end
```

The `SentenceEmbeddingGenerator` class [openchecker/llm.py L51-L81](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L51-L81)

 handles the complete embedding pipeline from tokenization to normalized vector output.

**Sources:** [openchecker/llm.py L51-L81](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/llm.py#L51-L81)

 [openchecker/clusters_util.py L126-L152](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L126-L152)

## Custom KMeans Implementation

The system implements a custom KMeans algorithm that operates on dual feature spaces simultaneously.

### KMeans Class Architecture

| Component | Type | Purpose |
| --- | --- | --- |
| `n_clusters` | int | Number of clusters to generate |
| `max_iter` | int | Maximum iterations for convergence |
| `distance_func_x` | function | Distance function for TF-IDF features |
| `distance_func_y` | function | Distance function for embeddings |
| `centroids_x` | numpy.ndarray | TF-IDF centroids |
| `centroids_y` | numpy.ndarray | Embedding centroids |
| `clusters_with_index` | list | Index mapping of points to clusters |

### Clustering Algorithm Flow

```mermaid
flowchart TD

RandomCentroids["np.random.choice()Initial centroid selectionclusters_util.py:36-38"]
SetCentroids["centroids_x, centroids_yDual centroid initialization"]
DistCalc["Distance Calculationdistance_func_x + distance_func_yclusters_util.py:45"]
Assignment["Cluster Assignmentnp.argmin(distances)clusters_util.py:46"]
Update["Centroid Updatenp.mean(cluster, axis=0)clusters_util.py:56,59"]
Convergence["Convergence Checknp.allclose()clusters_util.py:62"]
FinalClusters["clusters_with_indexFinal cluster assignments"]
IndexMapping["Project index to cluster mapping"]

    SetCentroids --> DistCalc
    Convergence -->|Converged| FinalClusters
subgraph Output ["Output"]
    FinalClusters
    IndexMapping
    FinalClusters -->|Converged| IndexMapping
end

subgraph Iteration_Loop ["Iteration Loop"]
    DistCalc
    Assignment
    Update
    Convergence
    DistCalc -->|Not converged| Assignment
    Assignment -->|Not converged| Update
    Update -->|Converged| Convergence
    Convergence -->|Not converged| DistCalc
end

subgraph Initialization ["Initialization"]
    RandomCentroids
    SetCentroids
    RandomCentroids --> SetCentroids
end
```

The `fit()` method [openchecker/clusters_util.py L35-L63](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L35-L63)

 implements the core clustering algorithm with dual-space centroid tracking.

**Sources:** [openchecker/clusters_util.py L23-L71](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L23-L71)

## Distance Functions

The clustering system supports multiple distance metrics for different feature types:

| Function | Use Case | Implementation |
| --- | --- | --- |
| `euclidean_distance()` | TF-IDF vectors | [openchecker/clusters_util.py L10-L14](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L10-L14) |
| `manhattan_distance()` | TF-IDF vectors | [openchecker/clusters_util.py L17-L21](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L17-L21) |
| `cosine_similarity` | Embedding vectors | sklearn.metrics.pairwise |

## Embedding Caching System

To optimize performance, the system implements a persistent caching mechanism for expensive embedding calculations.

```mermaid
flowchart TD

CacheCheck["os.path.exists(cache_file_path)clusters_util.py:133"]
LoadCache["json.load(cache_file)Load existing embeddings"]
FilterNew["need_vectorized_dataFilter uncached descriptions"]
Generate["embedding_model.generate_embeddings()Process new descriptions"]
MergeCache["Merge new + cached embeddingsclusters_util.py:141-148"]
SaveCache["json.dump(embedding_cache_data)Persist updated cache"]
HashKey["hash(project['description'])Description-based cache key"]
UniqueId["project_id mappingHash to embedding lookup"]

    UniqueId --> MergeCache
subgraph Cache_Key_Strategy ["Cache Key Strategy"]
    HashKey
    UniqueId
    HashKey --> UniqueId
end

subgraph Cache_Operations ["Cache Operations"]
    CacheCheck
    LoadCache
    FilterNew
    Generate
    MergeCache
    SaveCache
    CacheCheck --> LoadCache
    LoadCache --> FilterNew
    FilterNew --> Generate
    Generate --> MergeCache
    MergeCache --> SaveCache
end
```

The caching system uses description hashes as keys [openchecker/clusters_util.py L137-L142](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L137-L142)

 to avoid regenerating embeddings for projects with identical descriptions.

**Sources:** [openchecker/clusters_util.py L130-L152](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L130-L152)

## Integration with Analysis Workflow

The clustering results integrate with the broader OpenChecker analysis pipeline to optimize processing and provide insights.

### Cluster Assignment Output

```mermaid
flowchart TD

ClusterLoop["for i, cluster_index in enumerate(clusters_index)clusters_util.py:163"]
ProjectUpdate["all_projects[index]['cluster_id'] = iAssign cluster ID"]
ClusterInfo["Cluster information loggingProject name + description per cluster"]
SimilarProjects["Similar project groupingShared analysis patterns"]
ResourceOptim["Resource optimizationBatch processing similar projects"]
InsightGen["Insight generationCross-project analysis within clusters"]

    ClusterInfo --> SimilarProjects
subgraph Analysis_Optimization ["Analysis Optimization"]
    SimilarProjects
    ResourceOptim
    InsightGen
    SimilarProjects --> ResourceOptim
    SimilarProjects --> InsightGen
end

subgraph Cluster_Processing ["Cluster Processing"]
    ClusterLoop
    ProjectUpdate
    ClusterInfo
    ClusterLoop --> ProjectUpdate
    ProjectUpdate --> ClusterInfo
end
```

The final cluster assignments [openchecker/clusters_util.py L163-L169](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L163-L169)

 are stored as `cluster_id` attributes on project objects for downstream processing optimization.

**Sources:** [openchecker/clusters_util.py L155-L170](https://github.com/Laniakea2012/openchecker/blob/00a9732e/openchecker/clusters_util.py#L155-L170)