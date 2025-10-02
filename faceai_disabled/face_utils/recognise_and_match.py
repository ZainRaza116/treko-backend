import os
import re
from collections import Counter

import face_recognition

from .handle_embeddings import load_embeddings, save_embeddings  # Import from handle_embeddings


def normalize_name(name):
    """
    Normalize the name by removing spaces, underscores, and making it lowercase.
    """
    return re.sub(r"[\s_]+", "", name.strip().lower())


def recognise_and_match(image_path, ground_truth_names, embeddings_file=None):
    """
    Recognize faces in an image, compare with the ground truth names, and retrain embeddings.

    Args:
        image_path (str): Path to the image file.
        ground_truth_names (list): List of ground truth names for the image.
        embeddings_file (str): Path to the embeddings file.

    Returns:
        dict: A dictionary containing match status, retraining details, and predictions.
    """
    if embeddings_file is None:
        script_dir = os.path.dirname(__file__)
        embeddings_file = os.path.join(script_dir, "../embeddings/encodings.pkl")

    # Normalize the ground truth names
    normalized_truth_names = [normalize_name(name) for name in ground_truth_names]

    # Load embeddings
    encodings_data = load_embeddings(embeddings_file)
    known_names = [normalize_name(n) for n in encodings_data["names"]]
    known_encodings = encodings_data["encodings"]

    # Process the input image
    image = face_recognition.load_image_file(image_path)
    face_locations = face_recognition.face_locations(image, model="hog")
    face_encodings = face_recognition.face_encodings(image, face_locations)

    retrain_count = 0
    results = []

    for face_encoding in face_encodings:
        # Predict the closest match for the face
        matches = face_recognition.compare_faces(known_encodings, face_encoding)
        votes = Counter(name for match, name in zip(matches, known_names) if match)
        predicted_name = votes.most_common(1)[0][0] if votes else "Unknown"

        # Check if the predicted name matches any of the ground truth names
        match = predicted_name in normalized_truth_names

        # Update embeddings for unmatched faces
        if not match:
            for truth_name in normalized_truth_names:
                if truth_name not in known_names:
                    # Add new name and encoding
                    encodings_data["names"].append(truth_name)
                    encodings_data["encodings"].append(face_encoding)
                    retrain_count += 1
                    break  # Add only once per mismatch
        else:
            # Reinforce the matching ground truth name
            matching_truth_name = normalized_truth_names[normalized_truth_names.index(predicted_name)]
            encodings_data["names"].append(matching_truth_name)
            encodings_data["encodings"].append(face_encoding)
            retrain_count += 1

        # Append the result for this face
        results.append({
            "predicted_name": predicted_name,
            "ground_truth_names": ground_truth_names,
            "match": match
        })

    # Save the updated embeddings
    save_embeddings(encodings_data, embeddings_file)

    return {
        "status": "success",
        "message": f"Processed {len(face_encodings)} face(s). Retrained {retrain_count} embedding(s).",
        "results": results
    }
