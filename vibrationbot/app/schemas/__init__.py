"""Pydantic DTOs, split by feature and re-exported flat.

Every `from app.schemas import X` works regardless of which submodule X lives in.
"""

from app.schemas.chat import *  # noqa: F401,F403
from app.schemas.documents import *  # noqa: F401,F403
