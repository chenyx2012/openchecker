from transformers import AutoTokenizer, AutoModel
import torch


class SentenceEmbeddingGenerator:
    def __init__(self, model_path):
        """
        初始化函数，用于加载模型和分词器。

        Args:
            model_path (str): 预训练模型的路径。
        """
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModel.from_pretrained(model_path)
        self.model.eval()

    def generate_embeddings(self, sentences):
        """
        生成句子嵌入的函数。

        Args:
            sentences (list): 要生成嵌入的句子列表。

        Returns:
            torch.Tensor: 句子嵌入的张量。
        """
        encoded_input = self.tokenizer(sentences, padding=True, truncation=True, return_tensors='pt')

        with torch.no_grad():
            model_output = self.model(**encoded_input)
            sentence_embeddings = model_output[0][:, 0]

        sentence_embeddings = torch.nn.functional.normalize(sentence_embeddings, p=2, dim=1)

        return sentence_embeddings
    
if __name__ == "__main__":
    model_path = '/home/guoqiang/models/bge-large-en-v1.5'
    sentences = ["样例数据-1", "样例数据-2"]

    embedding_generator = SentenceEmbeddingGenerator(model_path)
    embeddings = embedding_generator.generate_embeddings(sentences)

    print(embeddings.shape)
    print("Sentence embeddings:", embeddings)