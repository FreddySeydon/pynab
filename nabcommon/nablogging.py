import logging
import logging.handlers
import os
import queue
from logging.handlers import QueueHandler, QueueListener


def setup_logging(daemon):
    logdir = os.environ.get("LOGDIR", "/var/log/")
    loglevel = os.environ.get("LOGLEVEL", "INFO")
    
    # Target handler for the SD card
    log_file = f"{logdir}/{daemon}.log"
    file_handler = logging.handlers.WatchedFileHandler(log_file)
    formatter = logging.Formatter(
        f"%(asctime)s [%(levelname)s] {daemon}: %(message)s"
    )
    file_handler.setFormatter(formatter)
    
    # Queue for asynchronous logging
    log_queue = queue.Queue(-1)  # Unlimited size
    queue_handler = QueueHandler(log_queue)
    
    # Listener runs in a separate thread to handle the file I/O
    listener = QueueListener(log_queue, file_handler)
    listener.start()
    
    logger = logging.getLogger()
    # Remove existing handlers if any
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        
    logger.addHandler(queue_handler)
    
    try:
        logger.setLevel(loglevel)
    except ValueError:
        loglevel = "DEBUG"
        logger.setLevel(loglevel)
        
    logging.info(f"started with asynchronous logging (log level {loglevel})")
    return listener # Return to prevent GC if needed
