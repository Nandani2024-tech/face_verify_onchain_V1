"""
face_id.py
----------
Step 1 of the pipeline: detect a face in the input image and produce a
128-dimensional encoding for it using the `face_recognition` library
(built on dlib).
"""

import os
import sys
import hashlib
import logging
import face_recognition

# Configure logger
logger = logging.getLogger("face_id")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [face_id] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False



def encode_face(image_path: str):
    """
    Load an image from disk, detect the first face, and return:
      - the face location (top, right, bottom, left)
      - the 128-d face encoding (as a list of floats)
      - a short SHA-256 fingerprint of the encoding
    """
    logger.info(f"Loading image from path: '{image_path}'")
    if not os.path.isfile(image_path):
        logger.error(f"Image file does not exist at path: '{image_path}'")
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        image = face_recognition.load_image_file(image_path)
    except Exception as e:
        logger.error(f"Failed to read/parse image file '{image_path}': {e}")
        raise

    height, width = image.shape[:2]
    channels = image.shape[2] if len(image.shape) > 2 else 1
    logger.info(f"Image loaded successfully (Dimensions: {width}x{height}px, Channels: {channels})")

    logger.info("Scanning image for human faces using dlib HOG face detector...")
    face_locations = face_recognition.face_locations(image)

    if not face_locations:
        logger.error(f"NO FACE DETECTED in image '{image_path}'. Ensure the photo has a clear, unobstructed human face.")
        raise ValueError(f"No face detected in {image_path}")

    logger.info(f"Detected {len(face_locations)} face(s) in image.")
    location = face_locations[0]
    top, right, bottom, left = location
    logger.info(f"Primary face bounding box: top={top}, right={right}, bottom={bottom}, left={left} (width={right-left}px, height={bottom-top}px)")

    logger.info("Extracting 128-dimensional facial feature vector (encoding)...")
    face_encodings = face_recognition.face_encodings(image, known_face_locations=face_locations)
    if not face_encodings:
        logger.error(f"Face bounding box found, but failed to generate 128-d feature encoding for '{image_path}'")
        raise ValueError(f"Face detected but could not be encoded in {image_path}")

    encoding = face_encodings[0]
    logger.info(f"Successfully generated face encoding vector (length: {len(encoding)} floats)")

    encoding_bytes = encoding.tobytes()
    fingerprint = hashlib.sha256(encoding_bytes).hexdigest()
    logger.info(f"Local Face SHA-256 Fingerprint: {fingerprint}")

    return {
        "location": location,       # (top, right, bottom, left)
        "encoding": encoding.tolist(),
        "fingerprint": fingerprint,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python face_id.py <path_to_image>")
        sys.exit(1)

    result = encode_face(sys.argv[1])
    print(f"\nSummary Result:")
    print(f"  Face Location: {result['location']}")
    print(f"  Encoding Size: {len(result['encoding'])} floats")
    print(f"  Fingerprint:   {result['fingerprint']}")

