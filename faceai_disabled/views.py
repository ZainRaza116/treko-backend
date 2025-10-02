from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from faceai.face_utils.recognise_and_match import recognise_and_match


def process_face_recognition(image_bytes, ground_truth_names):
    """
    Process face recognition with image bytes and match against ground truth names.
    Args:
        image_bytes: Raw image bytes from S3 or any source
        ground_truth_names: List of names or semicolon-separated string of names
    Returns:
        dict: Recognition results
    """
    # Convert string of names to list if needed
    if isinstance(ground_truth_names, str):
        ground_truth_names = [name.strip() for name in ground_truth_names.split(";")]

    try:
        # Save bytes to temporary file
        image_path = default_storage.save('temp/temp_image.jpg', ContentFile(image_bytes))

        # Perform face recognition and matching
        results = recognise_and_match(image_path, ground_truth_names)

        # Clean up the temporary file
        default_storage.delete(image_path)

        # Determine the overall match status
        all_results = results['results']
        all_matched = all(result['match'] for result in all_results)

        return {
            "status": "success" if all_matched else "error",
            "message": "All detected faces match the provided names." if all_matched else "Mismatch detected for some faces.",
            "results": results
        }

    except Exception as e:
        # Clean up on error if file exists
        if 'image_path' in locals() and default_storage.exists(image_path):
            default_storage.delete(image_path)
        return {
            "status": "error",
            "message": str(e)
        }
