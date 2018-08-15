import uuid
import sys
import os
import json
import boto3
import botocore
from io import BytesIO
import email
import mimetypes
from email.policy import default
from slackclient import SlackClient
import base64
import quopri
import types
import logging
import logging.handlers

slack_token = os.environ['SLACK_API_BOT_TOKEN']
sc = SlackClient(slack_token)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
log = logging.getLogger(__name__)

class PseudoLogger():
    def __init__( self ):
        pass
    def __getattr__(self, name):
        def myfunc(self, *args ):
            return
        return types.MethodType( myfunc, self, PseudoLogger )

    
#defining class to hold the raw data when email comes through    
class SesLambdaPayload (object):

    def __init__ (self, payload=None, logger=PseudoLogger()):
        self._payload = None
        self.log = logger
        if payload:
            self.payload = payload
            
    #property to make sure payload has a value
    @property
    def payload( self):
        if not self._payload:
            raise Exception ('payload not populated')
        return self._payload
            
    #converts the payload into json format
    @payload.setter
    def payload (self, payload):
        self._payload = json.loads( payload )
        self.log.info('Payload received from AWS Lambda and converted to JSON format')
        
    #properties to get important data values like subject, sender and virus checks
    @property
    def spam_verdict(self):
        return self.payload['ses']['receipt']['spamVerdict']
    
    @property
    def virus_verdict(self):
        return self.payload['ses']['receipt']['virusVerdict']
    
    @property
    def spf_verdict(self):
        return self.payload['ses']['receipt']['spfVerdict']
    
    @property
    def sender(self):
        return self.payload['ses']['mail']['commonHeaders']['from'][0]
    
    @property
    def recipient(self):
        return self.payload['ses']['mail']['commonHeaders']['to'][0]

    @property
    def subject(self):
         return self.payload['ses']['mail']['commonHeaders']['subject']
     
    @property
    def message_id(self):
         return self.payload['ses']['mail']['messageId']

    @property
    def channel(self) :
        destination = self.recipient.split('@')[1]
        channel = destination.split('.')[0].lower().replace('-', '_')
        return channel
     
#declaring a class to get the content of the email
class SesEmailPayload (object):
    #giving the class properties to set and call on
    def __init__ (self, download_bucket, logger = PseudoLogger()):
        self.download_bucket = download_bucket
        self.output = BytesIO()
        self.msg = None
        self._parts = []
        self.log = logger

    #getting the message id
    @property
    def message_id( self):
        return self.message_id

    #class function using the message id
    @message_id.setter
    def message_id (self, message_id):
        s3 = boto3.client('s3') #Linking boto3 to Amazon S3 buckets
        self.log.info('Attepmting to download payload content from S3 bucket: {}'.format(self.download_bucket))
        s3.download_fileobj( self.download_bucket, message_id, self.output ) #get the email content using the key
        self.log.info('Payload content accquired from S3 bucket, now attempting to decode contents and any attachments')
        self.msg = email.message_from_string( self.output.getvalue().decode( 'utf-8' ) ) #decode the content
        for part in self.msg.walk(): #loop to check over the email and keep track of the number of parts
            #once a part is found, it is processed, decoded and returned to our array
            self.append_part( part.get_content_type(), part.get_payload(),  part['Content-Transfer-Encoding'], part.get_filename())
        self.log.info('All parts of the content received and processed, now attempting to send parts to slack')
        if isinstance (message_id, dict):
            self._message_id = message_id
            return
                                                                                                     
    @property
    def parts( self ):
        return self._parts
    
    def append_part( self, mime_type, content, encoding, filename ):
        if encoding:
            self._parts.append( OurAttachment( mime_type, content, encoding, filename, logger = log ) )
                 
#defining the class which all of our content/attachments will be                                             
class OurAttachment( object ):
    
    def __init__( self, mime_type, content, encoding, filename, logger = PseudoLogger() ):
        self._mime_type = mime_type
        self.content = content
        self.encoding = encoding
        self.filename = filename
        self.log = logger
        if not self.encoding:
            return
        #logic to determine what encoding is being used for each attachment and use the corresponding function
        function_name = "process_content_{}".format( self.encoding.lower().replace( '-', '_' ) )
        function = None
        try:
            function = getattr( self, function_name )
        except Exception as e:
            self.log.error( e )
            
        if function:
            function( content, mime_type )
        else:
            self.log.warn( "no function to deal with encoding type {}".format( self.encoding ) )
                        
    @property
    def mime_type( self ):
        return self._mime_type
    
    #decodes anything with base64 encoding
    def process_content_base64( self, content, mime_type ):
        self.log.info('Part with base64 encoding found, attemptiing to decode.')
        self.content = base64.b64decode(self.content)
        self.log.info('Base64 part decoded, returning to parts array')
        
    #decodes anything which has QP encoding and if its html, uses the function below to upload it to S3 and return the link to the upload
    def process_content_quoted_printable( self, content, mime_type ):
        self.log.info('Part with QP encoding found, attempting to decode')
        self.content = quopri.decodestring(content)
        self.log.info('QP part decoded')
        if self.mime_type == 'text/plain':
            self.content = bytes(content.encode('utf-8'))
            self.log.info('Part with text/plain mime type found, returning to parts array')
            return
        self.log.info('HTML content found, attempting to upload to S3 bucket: ses.sqs.htmlcontent')
        url = self.upload_html_s3('ses.sqs.htmlcontent', self.content)
        self.log.info('HTML content uploaded to S3 bucket successfully, returning link to parts array. Link: {}'.format(url))
        self.content = url
        
    #function to upload html content to an S3 bucket
    def upload_html_s3 (self, bucket, content):
        key = '{}.html'.format(uuid.uuid4())
        temp_file =  BytesIO( bytes(self.content ))
        s3 = boto3.client('s3')
        s3.upload_fileobj(temp_file, bucket, key, ExtraArgs={'ContentType': "text/html"} ) #make sure to set content type  to text/html or it will download
        url = 'http://{}.s3-website-eu-west-1.amazonaws.com/{}'.format(bucket, key)
        return url

#defining our slack properties and the functions that will send the info to slack
class SlackInfo (object):

    def __init__ (self, channel, logger = PseudoLogger()):
        self._channel = channel
        self._ts = None
        self.log = logger
        
    @property
    def text(self):
        return self._text
    
    @property
    def channel(self):
        return self._channel
    
    @property
    def ts(self):
        return self._ts
    
    @channel.setter
    def channel (self, channel) :
        self._channel = channel

    #method to send the email info and the html link to slack
    def send( self, message ):
        response = sc.api_call(
            "chat.postMessage",
            channel = self.channel,
            text = message,
            icon_emoji = ':email:',
            as_user = False,
            thread_ts = self.ts
        )
        if not self.ts:
            self._ts = response['ts']
        self.log.info('Content successsfully processed and a message has been sent to the slack channel: {}'.format(self.channel))
            
    #Method to upload the content and the attachment files
    def upload_file (self, title, att ):
        temp_file =  BytesIO( att.content )
        response = sc.api_call(
            'files.upload',
            filename = att.filename,
            channels = self.channel,
            title = title,
            file=temp_file,
            as_user = False,
            thread_ts = self._ts,
        )
        self.log.info('File successfully processed and has been uploaded to the slack channel: {}'.format(self.channel))
