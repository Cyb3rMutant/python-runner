from pydantic import BaseModel, model_validator


class JobFile:
    """What a job's run() returns: the file content to send back, in memory."""

    def __init__(
        self,
        content: bytes,
        filename: str,
        media_type: str = "application/octet-stream",
    ):
        self.content = content
        self.filename = filename
        self.media_type = media_type
