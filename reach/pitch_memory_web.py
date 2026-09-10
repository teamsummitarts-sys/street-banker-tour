"""Template seam for Pitch Memory.

Pitch Memory remains a read model. The helper is evaluated only by screens that
ask for it, so ordinary Reach pages do not incur the history query.
"""

from . import pitch_memory
from .web import bp


@bp.app_context_processor
def _pitch_memory_helpers():
    return {"pitch_memory_summary": pitch_memory.summary}
