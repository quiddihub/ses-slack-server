from __future__ import absolute_import
from kombu import Queue, Exchange
import sys, os
import local_settings
sys.path.insert( 1, os.path.dirname( os.path.realpath( __file__ ) ) )
config = local_settings.env

from celery import Celery
import logging
from celery.signals import after_setup_logger, after_setup_task_logger

def after_setup_logger_handler(sender=None, logger=None, loglevel=logging.DEBUG, logfile=None, format=None, colorize=None, **kwds):
    handler = logging.handlers.SysLogHandler( address='/dev/log', facility=logging.handlers.SysLogHandler.LOG_LOCAL7 )
    handler.setFormatter( logging.Formatter( format ) )
    handler.setLevel( loglevel )
    logger.addHandler( handler )

after_setup_logger.connect(after_setup_logger_handler)
after_setup_task_logger.connect(after_setup_logger_handler)

app = Celery(
    config.get( 'APPLICATION_NAME' ),
    broker = config.get( 'CELERY_BROKER' ),
    backend = config.get( 'CELERY_BACKEND' ),
    include = [
        'tasks.slack',
    ]
)

app.conf.update(
    CELERY_DEFAULT_QUEUE = config.get('CELERY_DEFAULT_QUEUE'),
    CELERY_TASK_RESULT_EXPIRES = config.get('CELERY_TASK_RESULT_EXPIRES'),
    CELERY_TRACK_STARTED = True,
    CELERY_QUEUES = (
        Queue(
            config.get('CELERY_DEFAULT_QUEUE'),
            Exchange(config.get('CELERY_DEFAULT_QUEUE')),
            routing_key=config.get('CELERY_DEFAULT_QUEUE')),
    )
)


if __name__ == '__main__':
    app.control.time_limit( 'tasks.request.application', soft=60*10, hard=60*15 )
    app.start()
    
