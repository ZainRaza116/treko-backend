import os

import face_recognition

from .handle_embeddings import load_embeddings, save_embeddings  # Import from handle_embeddings


def retrain_model(image_path, person_name, embeddings_file=None):
    # Construct the embeddings file path relative to this script
    if embeddings_file is None:
        script_dir = os.path.dirname(__file__)  # Directory of this script
        embeddings_file = os.path.join(script_dir, "../embeddings/encodings.pkl")

    """Retrain the model with a new image and ground truth name."""
    encodings_data = load_embeddings(embeddings_file)
    names, encodings = encodings_data["names"], encodings_data["encodings"]

    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, model="hog")
    face_encodings = face_recognition.face_encodings(image, face_locations)

    for encoding in face_encodings:
        names.append(person_name)
        encodings.append(encoding)

    save_embeddings({"names": names, "encodings": encodings}, embeddings_file)
    return len(face_encodings)
