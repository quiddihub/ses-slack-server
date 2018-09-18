#importing external files
import sys
import logging
import logging.handlers
import os
from flask import request
from flask import Flask
from slackclient import SlackClient
import celery
import celery.result
import local_settings
from kombu import Queue, Exchange

config = local_settings.env
app = Flask(__name__)
__log_format = logging.Formatter(
    "%(name)s %(funcName)-20s:%(lineno)-4d %(relativeCreated)-8d %(levelname)s - %(message)s"
)

# Create the Celery component
celery = celery.Celery(
    config.get( 'APPLICATION_NAME' ),
    broker = config.get( 'CELERY_BROKER' ),
    backend = config.get( 'CELERY_BACKEND' ),
)

#Set the default celery queue
celery.conf.update(
    CELERY_DEFAULT_QUEUE = config.get('CELERY_DEFAULT_QUEUE'),
    CELERY_TASK_RESULT_EXPIRES = config.get('CELERY_TASK_RESULT_EXPIRES'),
    CELERY_MAX_CACHED_RESULTS = -1,
    CELERY_QUEUES = (
        Queue(
            config.get('CELERY_DEFAULT_QUEUE'),
            Exchange(config.get('CELERY_DEFAULT_QUEUE')),
            routing_key=config.get('CELERY_DEFAULT_QUEUE')),
    )
)

def add_logger_component( handler ):
    handler.setFormatter( __log_format )
    handler.setLevel( logging.DEBUG )
    app.logger.addHandler( handler )


@app.route('/')
def hello_world():
    return 'Hello, World!'

#keeps the server running
@app.route('/server_check')
def haproxy_keep_alive_check():
    return 'OK'

#funtion to receive the payload when an email comes in
@app.route('/slack', methods=['POST'])
def receive_payload() :
    expires_at = 1200
    app.logger.debug('About to send payload to celery task')
    resp = celery.send_task( 'tasks.slack.process_email', (), {'data':request.data.decode('utf-8')}, expires=expires_at )
    add_logger_component( logging.StreamHandler( ) )
    app.logger.debug('Celery task id: {}'.format(resp.id))
    return'OK'
    


if __name__ == '__main__':
    # create logging component, streaming to screen and syslog

    log = logging.getLogger( app.logger.name )
    log.setLevel( logging.DEBUG )
    add_logger_component( logging.handlers.SysLogHandler( address='/dev/log', facility=logging.handlers.SysLogHandler.LOG_USER ) )
    add_logger_component( logging.StreamHandler( ) )
    app.logger.info('server started')
    app.run( host=config['LISTEN_HOST'], port=config['LISTEN_PORT'] )
    
