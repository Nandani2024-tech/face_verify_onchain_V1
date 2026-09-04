"""
face_id.py
----------
Step 1 of the pipeline: detect a face in the input image and produce a
128-dimensional encoding for it using the `face_recognition` library
(built on dlib).

This encoding is NOT sent anywhere in this consent-based demo — it is
only used locally to prove a face was genuinely detected. The actual
web lookup in this project is done by reverse-image-searching a public
URL you already own (see search_module/reverse_search.py), not by
matching this encoding against any third-party database.
"""

import sys
import hashlib
import face_recognition


def encode_face(image_path: str):
    """
    Load an image from disk, detect the first face, and return:
      - the face location (top, right, bottom, left)
      - the 128-d face encoding (as a list of floats)
      - a short SHA-256 fingerprint of the encoding (for display/logging,
        NOT a cryptographic proof of anything by itself)
    """
    image = face_recognition.load_image_file(image_path)

    face_locations = face_recognition.face_locations(image)
    if not face_locations:
        raise ValueError(f"No face detected in {image_path}")

    face_encodings = face_recognition.face_encodings(image, known_face_locations=face_locations)
    if not face_encodings:
        raise ValueError(f"Face detected but could not be encoded in {image_path}")

    encoding = face_encodings[0]
    location = face_locations[0]

    encoding_bytes = encoding.tobytes()
    fingerprint = hashlib.sha256(encoding_bytes).hexdigest()

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
    print(f"Face detected at (top, right, bottom, left): {result['location']}")
    print(f"Encoding length: {len(result['encoding'])} floats")
    print(f"Encoding fingerprint (SHA-256): {result['fingerprint']}")
