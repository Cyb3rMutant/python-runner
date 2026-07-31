from pydantic import BaseModel, model_validator


class GithubOptions(BaseModel):
    push: bool = False
    message: str | None = None

    @model_validator(mode="after")
    def require_message_when_pushing(self):
        if self.push and not self.message:
            raise ValueError("github.message is required when github.push is true")
        return self


class RunRequest(BaseModel):
    github: GithubOptions = GithubOptions()


class GithubResult(BaseModel):
    pushed: bool
    commit: str | None = None
    detail: str | None = None


class JobFile:
    """What a job's run() returns: the file content to send back, in memory."""

    def __init__(self, content: bytes, filename: str, media_type: str = "application/octet-stream"):
        self.content = content
        self.filename = filename
        self.media_type = media_type
