import logging

logger = logging.getLogger(__name__)

def process_request(request):
    logger.info(request.token)