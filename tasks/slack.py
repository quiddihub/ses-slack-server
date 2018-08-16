from __future__ import absolute_import
import sys, json, logging, pprint
from tasks.celery import app
from celery import group, subtask
from celery.utils.log import get_task_logger
from ses_slack_utils import *


log = get_task_logger(__name__)
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
@app.task
def process_email( **kwargs ):

    log.info( "{}".format( pprint.pformat( kwargs ) ) ) # log the payload
    ses = SesLambdaPayload( kwargs['data'], logger = log ) #takes the incoming email and stores in the our class
    email_body = SesEmailPayload('ses.sqs.content', logger = log) #takes our payload class and sets it to a new class for content process
    email_body.message_id = ses.message_id #sets the message ID value of the new class
    slack = SlackInfo(channel=ses.channel, default_channel=config['DEFAULT_SLACK_CHANNEL'], logger = log)#sets the slack channel our bot will post too
    slack.send( "You received an email about *{}* from '{}' to '{}'".format( ses.subject, ses.sender, ses.recipient) ) #formats the message to be sent
    for attachment in email_body.parts: #filters attachments to upload images and post links to html content
        if attachment.mime_type == 'text/html':
            slack.send('HTML content link: {}'.format(attachment.content))
        else:
            slack.upload_file('title', attachment )

    return { }

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
