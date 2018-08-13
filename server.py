#importing external files
import sys
import os
from flask import request
from flask import Flask
from slackclient import SlackClient
from classes import *

app = Flask(__name__)
        
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
    ses = SesLambdaPayload( request.data ) #takes the incoming email and stores in the our class
    email_body = SesEmailPayload('ses.sqs.content') #takes our payload class and sets it to a new class for content process
    email_body.message_id = ses.message_id #sets the message ID value of the new class
    slack = SlackInfo(channel='#forkredit') #sets the slack channel our bot will post too
    slack.send( "You received an emal about *{}* from '{}' to '{}'".format( ses.subject, ses.sender, ses.recipient) ) #formats the message to be sent
    for attachment in email_body.parts: #filters attachments to upload images and post links to html content
        if attachment.mime_type == 'text/html':
            slack.send('HTML content link: {}'.format(attachment.content))
        else:
            slack.upload_file('title', attachment ) 
    return'OK'
    
