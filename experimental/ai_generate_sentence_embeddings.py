from sentence_transformers import SentenceTransformer
sentences = ["This is my example sentence", "Each sentence is converted by me"]

model = SentenceTransformer('sentence-transformers/all-MiniLM-L12-v2')
embeddings = model.encode(sentences)
print(embeddings)