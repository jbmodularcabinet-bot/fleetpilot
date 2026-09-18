"""One explicit baseline evidence policy for both API and UI."""

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_ATTEMPT_FILES = 12  # Includes superseded versions; limits retained storage per attempt.
DELIVERY_STAGES = {"ARRIVED_DELIVERY", "UNLOADING_STARTED", "UNLOADING_COMPLETED"}
POLICY = {
    "recipient_name_required": True,
    "driver_confirmation_required": True,
    "minimum_delivery_photos": 1,
    "signature_required": False,
    "max_file_bytes": MAX_FILE_BYTES,
    "max_image_pixels": MAX_IMAGE_PIXELS,
    "max_attempt_files": MAX_ATTEMPT_FILES,
    "allowed_content_types": ["image/jpeg", "image/png", "image/webp"],
}
