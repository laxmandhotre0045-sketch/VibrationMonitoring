"""Env-derived constants, grouped by topic and re-exported flat.

Every `from app.config import X` keeps working regardless of which submodule X
lives in, and - critically - the consumer still gets a *module-level binding* of
X. That is what lets tests do:

    monkeypatch.setattr(vision_enrichment, "VISION_MAX_ELEMENTS", 3)

which rebinds the name in the consuming module's namespace. This is deliberately
NOT a settings object: `settings.VISION_MAX_ELEMENTS` would break ~40 tests and
force every call site to change.

`paths` MUST be imported first. It calls load_dotenv(override=True), and every
other submodule reads os.getenv at its own import time - so anything imported
ahead of it would silently take its hardcoded default instead of the .env value.
"""

from app.config.paths import *  # noqa: F401,F403  MUST BE FIRST - loads .env
from app.config.chat import *  # noqa: F401,F403
from app.config.ingestion import *  # noqa: F401,F403
from app.config.llm import *  # noqa: F401,F403
from app.config.retrieval import *  # noqa: F401,F403
from app.config.vision import *  # noqa: F401,F403
