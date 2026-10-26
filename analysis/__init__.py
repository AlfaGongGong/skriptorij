import logging
logger = logging.getLogger(__name__)
try:
    from analysis.book_context import BookContext
except ImportError:
    logger.debug("[C3_fallback] __init__.py:4 ImportError")
else:
    __all__ = ["BookContext"]