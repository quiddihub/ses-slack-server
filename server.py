#importing external files
import uuid
import sys
import os
from flask import request
from flask import Flask
import json
import boto3
import botocore
from io import BytesIO
import email
import mimetypes
from email.policy import default
from slackclient import SlackClient
import base64

slack_token = os.environ['SLACK_API_BOT_TOKEN']
sc = SlackClient(slack_token)

app = Flask(__name__)

#declaring a class to get the content of the email
class SesEmailPayload (object):
    #giving the class properties to set and call on
    def __init__ (self, download_bucket):
        self.download_bucket = download_bucket
        self.output = BytesIO()
        self.msg = None
        self._parts = []

    #getting the message id
    @property
    def message_id( self):
        return self.message_id

    #class function using the message id
    @message_id.setter
    def message_id (self, message_id):
        s3 = boto3.client('s3') #Linking boto3 to Amazon S3 buckets
        s3.download_fileobj( self.download_bucket, message_id, self.output ) #get the email content using the key
        self.msg = email.message_from_string( self.output.getvalue().decode( 'utf-8' ) ) #decode the content
        for part in self.msg.walk(): #loop to check over the email and keep track of the number of parts
            
            self.append_part( part.get_content_type(), part.get_payload(),  part['Content-Transfer-Encoding'], part.get_filename() )
        if isinstance (message_id, dict):
            self._message_id = message_id
            return
        #raise Exception ()
        
    @property
    def parts( self ):
        return self._parts

    def append_part( self, mime_type, content, encoding, filename ):
        if encoding:
            self._parts.append( OurAttachment( mime_type, content, encoding, filename ) )
            
class OurAttachment( object ):

    def __init__( self, mime_type, content, encoding, filename ):
        self._mime_type = mime_type
        self.content = content
        self.encoding = encoding
        self.filename = filename
        if not self.encoding:
            return
        
        function_name = "process_content_{}".format( self.encoding.lower().replace( '-', '_' ) )
        function = None
        try:
            function = getattr( self, function_name )
        except Exception as e:
            print( e )

        if function:
            function( content, mime_type )
        else:
            print( "no function to deal with encoding type {}".format( self.encoding ) )

    @property
    def mime_type( self ):
        return self._mime_type

    def process_content_base64( self, content, mime_type ):
        self.content = base64.b64decode(self.content)
        
    
    def process_content_quoted_printable( self, content, mime_type ):
        if self.mime_type == 'text/plain':
            self.content = bytes(content.encode('utf-8'))
            return
        url = self.upload_html_s3('ses.sqs.htmlcontent', self.content)
        self.content = url        
        
    def upload_html_s3 (self, bucket, content):
        key = '{}.html'.format(uuid.uuid4())
        temp_file =  BytesIO( bytes(self.content.encode('utf-8') ))
        s3 = boto3.client('s3')
        s3.upload_fileobj(temp_file, bucket, key)
        url = 'http://{}.s3-website-eu-west-1.amazonaws.com/{}'.format(bucket, key)
        return url
    
#defining class to hold the raw data when email comes through
class SesLambdaPayload (object):

    def __init__ (self, payload=None):
        self._payload = None

        if payload:
            self.payload = payload

    #property to make sure payload has a value
    @property
    def payload( self):
        if not self._payload:
            raise Exception ('payload not populated')
        return self._payload

    #decodes the data
    @payload.setter
    def payload (self, payload):
        self._payload = json.loads( payload.decode( 'utf-8' ) )

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

class SlackInfo (object):

    def __init__ (self, channel):
        self._channel = channel
                                            
    @property
    def text(self):
        return self._text
                                
    @property
    def channel(self):
        return self._channel

    @channel.setter
    def channel (self, channel) :
        self._channel = channel

    def send( self, message ):
        response = sc.api_call(
            "chat.postMessage",
            channel = self.channel,
            text = message,
            icon_emoji = ':email:',
            as_user = False
        )
        self._ts = response['ts']

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
    #virus/spam check to see if incoming email is safe to process
    email_body = SesEmailPayload('ses.sqs.content') #takes our payload class and sets it to a new class for content process
    email_body.message_id = ses.message_id #sets the message ID value of the new class
    slack = SlackInfo(channel='#forkredit')
    slack.send( "You received an emal about *{}* from '{}' to '{}'".format( ses.subject, ses.sender, ses.recipient) )
    for attachment in email_body.parts:
        if attachment.mime_type == 'text/html':
            slack.send('HTML content link: {}'.format(attachment.content))
        else:
            slack.upload_file('title', attachment ) 
    return'OK'

if __name__ == '__main__':



    #test email
    a= {   'eventSource': 'aws:ses',
        'eventVersion': '1.0',
    'ses': {   'mail': {   'commonHeaders': {   'date': 'Fri, 3 Aug 2018 16:59:28 +0100',
                                                'from': [   'Charlie Tatham <charlie.tatham@dojono.com>'],
                                                'messageId': '<5b647be0.1c69fb81.8707e.c2e9@mx.google.com>',
                                                'returnPath': 'charlie.tatham@dojono.com',
                                                'subject': 'sanmdbsa',
                                                'to': [   '"info@forkredit.com" <info@forkredit.com>']},
                           'destination': ['info@forkredit.com'],
                           'headers': [   {   'name': 'Return-Path',
                                              'value': '<charlie.tatham@dojono.com>'},
                                          {   'name': 'Received',
                                              'value': 'from mail-ed1-f49.google.com (mail-ed1-f49.google.com [209.85.208.49]) by inbound-smtp.eu-west-1.amazonaws.com with SMTP id 9sqe7v8ke7al44hob5s8fsoi5n69a6iilq7hu881 for info@forkredit.com; Fri, 03 Aug 2018 15:59:30 +0000 (UTC)'},
                                          {   'name': 'X-SES-Spam-Verdict',
                                              'value': 'PASS'},
                                          {   'name': 'X-SES-Virus-Verdict',
                                              'value': 'PASS'},
                                          {   'name': 'Received-SPF',
                                              'value': 'pass (spfCheck: domain of dojono.com designates 209.85.208.49 as permitted sender) client-ip=209.85.208.49; envelope-from=charlie.tatham@dojono.com; helo=mail-ed1-f49.google.com;'},
                                          {   'name': 'Authentication-Results',
                                              'value': 'amazonses.com; spf=pass (spfCheck: domain of dojono.com designates 209.85.208.49 as permitted sender) client-ip=209.85.208.49; envelope-from=charlie.tatham@dojono.com; helo=mail-ed1-f49.google.com; dkim=pass header.i=@dojono-com.20150623.gappssmtp.com;'},
                                          {   'name': 'X-SES-RECEIPT',
                                              'value': 'AEFBQUFBQUFBQUFFKzUxeWMvWEF0dXVKWUVmSUV3cml5N0dMdG85ZFQwMDk4d3lIcFZvR1NmcDRmMjVHRy9SSGtpdmt3SlljWHRVN1hHRHRlaGhGNUs2MWRLRU9saHhZRENOT1JySU9yQ3U0ZXZrcFlwdFFkRkJUYnhVeEJ5dDZVcWxHK3czM3ZHWjQxWWl5ZW92OVZielpFLzIrcmt3eDRZbEVMTHZYSXNjZTdFUEtPaW9UcmU1ek0yUjlzMHhEMlhMV0VDeGtLOHlqZ0RyREdncHlybmhncndpUWNpaGRCSmtkRUlnR3hLSmJYZDZmblEzdFZJSUFFTFUxenRQVW1FZFUzdnJKT1NjWXBYK0xpR1JrT3dLY3U4Z0psRGoxbFJ3cmVqait1TVdrZnBIbDJxaTBvcnc9PQ=='},
                                          {   'name': 'X-SES-DKIM-SIGNATURE',
                                              'value': 'a=rsa-sha256; q=dns/txt; b=WFWMdedweIZi56BHmEmojLJyf8R3aJP2fkX7WrdUh9qgR5mqnIRASHLfOo9NdCaag1mop1apvUai/ZMQmhV9nFM5Ix1G4FXdm7BLR4AUNJHO1z51A7o7UjIvB+nXRYR9n1PFtQfXkb/2W0N8qj1cegSCW9o+zlJWhpQEUZD8WPk=; c=relaxed/simple; s=uku4taia5b5tsbglxyj6zym32efj7xqv; d=amazonses.com; t=1533311970; v=1; bh=MF6WZ599LHkV4PNolsA7k9fudHv8Dj9fysx4nLH0wvE=; h=From:To:Cc:Bcc:Subject:Date:Message-ID:MIME-Version:Content-Type:X-SES-RECEIPT;'},
                                          {   'name': 'Received',
                                              'value': 'by mail-ed1-f49.google.com with SMTP id s24-v6so2338776edr.8 for <info@forkredit.com>; Fri, 03 Aug 2018 08:59:30 -0700 (PDT)'},
                                          {   'name': 'DKIM-Signature',
                                              'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=dojono-com.20150623.gappssmtp.com; s=20150623; h=message-id:mime-version:to:from:subject:date:importance; bh=FSk14ZRr80eBCRaZO4D2KYkNmEVroWXKZN1Q6+TzDmk=; b=mH03WrSSX/Eub4/hacqtN39H9VPOD2C8BAg2b2y/Zg6+EkoNcMcq/Qlqa/XyRNqKKxiiPqHEcHV5tnHq5t6bk+KjoKBKW1FAMbPbygMr4q5cfyxESHhUadl72fjjd28epVOTENokRvS7dxpsxuqNjiwWdIHrU9INOuFvsnioSPST4mYJA77VgI487ys4RMXz2vQobCYEOVutDpBqukEFs1H2fBLz1YnCX++Zv3BqZ5YUdQyfYpgBXHLL/ry+WyQVyKs3QaCOdSsmi+9WLbz+lUQwWS9z/bXtBMu/5qL1sSTYYP/Ese+WLHYUVjw/4xd/vlcAvZx3k8DXeWJYm670rw=='},
                                          {   'name': 'X-Google-DKIM-Signature',
                                              'value': 'v=1; a=rsa-sha256; c=relaxed/relaxed; d=1e100.net; s=20161025; h=x-gm-message-state:message-id:mime-version:to:from:subject:date :importance; bh=FSk14ZRr80eBCRaZO4D2KYkNmEVroWXKZN1Q6+TzDmk=; b=Hn4WHWuYMfHeBBQ+Aa7ZIAmRthWk0/m7e4yPkjjutcRs3ZCJtOINAAfQPgaISd9D74 GhqSax5dYCLO7A9w2sXYSd/sF6CSH4esGVxawZxfAVrxv0JaL7yjFZtSRl9kOHnYE8g8 94hXZPo2AbywUVatRC2GPbD48AmgYbbcK+ImXq3qmqV6jWOTyfKF9hJkAKehrk94spYq gfsgcwUjK3K1gJhlsXtjglAVvaRMgiWtThP/c+UhVHLVtkLUu9BH252GVPNtigknuIyn LybhiTsRQ2lE83WoPRhnZPIkCFaeGuJ2x0GGKLRPDyDjIDnuoLb0Xo3W0pSNSRUy0LCW Q5Kg=='},
                                          {   'name': 'X-Gm-Message-State',
                                              'value': 'AOUpUlEFP0MWIuBNXt1AGM08nBzt0WYcwX3YhXtlPFyFhmqFUrtFX+GM e+rE77dLQIW8pbl1zztTO3pIi51Ij1w='},
                                          {   'name': 'X-Google-Smtp-Source',
                                              'value': 'AAOMgpfDNcgKWHai/V7VF6AWU3vIVGRhjOVzbcNSb1j6xJSsET5wVzSXn8RmRZQjQ2wt+Y6YDg3vrQ=='},
                                          {   'name': 'X-Received',
                                              'value': 'by 2002:a50:b56e:: with SMTP id z43-v6mr8214470edd.223.1533311969648; Fri, 03 Aug 2018 08:59:29 -0700 (PDT)'},
                                           {   'name': 'Return-Path',
                                              'value': '<charlie.tatham@dojono.com>'},
                                          {   'name': 'Received',
                                              'value': 'from ?IPv6:::ffff:172.16.1.53? ([185.53.225.2]) by smtp.gmail.com with ESMTPSA id p3-v6sm2192261edp.47.2018.08.03.08.59.28 for <info@forkredit.com> (version=TLS1_2 cipher=ECDHE-RSA-AES128-GCM-SHA256 bits=128/128); Fri, 03 Aug 2018 08:59:28 -0700 (PDT)'},
                                          {   'name': 'Message-ID',
                                              'value': '<5b647be0.1c69fb81.8707e.c2e9@mx.google.com>'},
                                          {   'name': 'MIME-Version',
                                              'value': '1.0'},
                                          {   'name': 'To',
                                              'value': '"info@forkredit.com" <info@forkredit.com>'},
                                          {   'name': 'From',
                                              'value': 'Charlie Tatham <charlie.tatham@dojono.com>'},
                                          {   'name': 'Subject',
                                              'value': 'sanmdbsa'},
                                          {   'name': 'Date',
                                              'value': 'Fri, 3 Aug 2018 16:59:28 +0100'},
                                          {   'name': 'Importance',
                                              'value': 'normal'},
                                          {   'name': 'X-Priority',
                                              'value': '3'},
                                          {   'name': 'Content-Type',
                                              'value': 'multipart/alternative; boundary="_49DF6724-352A-49C7-97D5-09ED5D5412C0_"'}],
                           'headersTruncated': False,
                           'messageId': '6l0lb0ua7m0070c04c4r72nb4v39u2185cjbd201',
                           'source': 'charlie.tatham@dojono.com',
                           'timestamp': '2018-08-03T15:59:30.404Z'},
               'receipt': {   'action': {   'functionArn': 'arn:aws:lambda:eu-west-1:650836110062:function:ses-slack',
                                            'invocationType': 'Event',
                                            'type': 'Lambda'},
                              'dkimVerdict': {   'status': 'GRAY'},
                              'dmarcVerdict': {   'status': 'GRAY'},
                              'processingTimeMillis': 368,
                              'recipients': ['info@forkredit.com'],
                              'spamVerdict': {   'status': 'PASS'},
                              'spfVerdict': {   'status': 'PASS'},
                              'timestamp': '2018-08-03T15:59:30.404Z',
                              'virusVerdict': {   'status': 'PASS'}}}}
    
    #stores 'imcoming' email as class
    ses = SesLambdaPayload()
    ses.payload = bytes( json.dumps( a ).encode( 'utf-8' ) ) #encodes the data

    #sets new class with correct directory parameters
    #potential virus/spamverdict check 
    email_body = SesEmailPayload( bucket='ses.sqs.content')
    email_body.message_id = ses.message_id #sets message ID
    sys.exit(1)
    
