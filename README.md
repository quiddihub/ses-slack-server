# SES-Slack-Server

1. Create AWS account and generate AWS Access and Secret Keys (make sure to save the scret key in a safe place as you won't be able to see it again)

2. Run `aws configure` on the machine you will be running this app on and fill in the prompts with your keys, region and the output format(json)

3. Clone the `ses-slack` repo

4. Replace the example_url with your the url you want any incoming emails to be delivered to

5. Navigate into the repo and run `pip install requests -t` to install requests in the current directory.

6. Navigate back out of the repo dir and run `zip -r {name_of_zip_file}.zip {name_of_file_to_zip}` to make the lambda deployment package

7. Deploy the lambda package by running:
```
aws lambda create-function \
--function-name YOUR-FUNCTION-NAME (example: ses-slack)\
--region YOUR REGION (example: eu-west-1)\
--zip-file fileb://PATH/FILENAME.zip \
--runtime python3.6 \
--handler ses_lambda_slack.email_handler \
--role ROLE-ARN (found under IAM/roles in the aws console)\
```

9. Clone the `ses-slack-server` repo 

10. Fill in `local_settings.py` with the following:
  * SPAM_SLACK_CHANNEL = the name of the slack channel any emails that do not pass the spam/virus verdict will be sent to
  * DEFAULT_SLACK_CHANNEL = the name of the slack channel any emails that do pass the spam/virus verdict will be sent to
  * SLACK_TOKEN = the slack api token for the slack app that will be posting the emails
  * EMAIL_S3_BUCKET = the name of the bucket where you want to store the emails
  * HTML_S3_BUCKET = the name of the bucket where yoou want to store the html content of the emails
  * LAMBDA_FUNCTION_NAME = the name you gave to the lambda function when you created it
  (Note: bucket names are shared across all users so using a unique identfier is ideal (eg. name, company, etc.))
  
12. Create a new hosted zone for this domain on AWS route53 and add any DNS records you need

12. Change the domain nameservers on the registrar to point to the AWS nameservers on the route53 hosted zone

13. Run `python3 ses.py $DOMAIN_NAME` which will verify your domain and create a rule on ses for it and create the s3 buckets

14. Start up flask app and celery workers  
