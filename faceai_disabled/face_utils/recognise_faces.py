import os
from collections import Counter

import face_recognition

from .handle_embeddings import load_embeddings  # Import from handle_embeddings


def recognise_faces(image_path, embeddings_file=None):
    # Construct the embeddings file path relative to this script
    if embeddings_file is None:
        script_dir = os.path.dirname(__file__)  # Directory of this script
        embeddings_file = os.path.join(script_dir, "../embeddings/encodings.pkl")

    """Recognize faces in an image."""
    encodings_data = load_embeddings(embeddings_file)
    known_names, known_encodings = encodings_data["names"], encodings_data["encodings"]

    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, model="hog")
    face_encodings = face_recognition.face_encodings(image, face_locations)

    results = []
    for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_encodings, face_encoding)
        votes = Counter(name for match, name in zip(matches, known_names) if match)
        if votes:
            results.append(votes.most_common(1)[0][0])
        else:
            results.append("Unknown")

    return results
