import io
import logging
import unittest

from shared.logging_utils import repair_closed_streams


class LoggingStabilizationTests(unittest.TestCase):
    def test_closed_handler_is_replaced_by_visible_stream(self):
        logger = logging.getLogger("test.closed-handler")
        logger.handlers.clear()
        closed_stream = io.StringIO()
        closed_stream.close()
        handler = logging.StreamHandler(closed_stream)
        logger.addHandler(handler)
        try:
            repair_closed_streams()
            self.assertTrue(all(getattr(item.stream, "closed", False) is False for item in logger.handlers))
        finally:
            logger.handlers.clear()
            handler.close()


if __name__ == "__main__":
    unittest.main()
