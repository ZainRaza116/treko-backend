import pickle as pkl


# Save embeddings
def save_embeddings(encodings, file_path="./embeddings/encodings.pkl"):
    with open(file_path, "wb") as file:
        pkl.dump(encodings, file)


# Load embeddings
def load_embeddings(file_path="./embeddings/encodings.pkl"):
    with open(file_path, "rb") as file:
        return pkl.load(file)
