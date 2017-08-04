#
# Copyright 2015 Ryan Holland
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License.
#
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and limitations under the License.
#
# https://github.com/ryanholland/rdslogs_to_s3
#


import boto3, botocore, pprint

## Set the values below if using Lambda Scheduled Event as an Event Source, otherwise leave empty and send data through the Lambda event payload.
#S3BUCKET='aws-logs-omg'
#S3PREFIX='onelife-staging-db/'
#RDSINSTANCE='onemedical-staging-encrypted-1481384393'
#LOGNAME='general/mysql-general'
#LASTRECIEVED='lastWrittenMarker'
#REGION='us-east-1'

## pprint example: pprint.pprint(myVar)


def lambda_handler(event, context):

	firstRun = False
	logFileData = ""
	
	if {'BucketName','S3BucketPrefix','RDSInstanceName','LogNamePrefix','lastRecievedFile','Region'}.issubset(event):
		S3BucketName = event['BucketName']
		S3BucketPrefix = event['S3BucketPrefix']
		RDSInstanceName = event['RDSInstanceName']
		logNamePrefix = event['LogNamePrefix']
		lastRecievedFile = S3BucketPrefix + event['lastRecievedFile']
		region = event['Region']
	else:
		S3BucketName = S3BUCKET
		S3BucketPrefix = S3PREFIX
		RDSInstanceName = RDSINSTANCE
		logNamePrefix = LOGNAME
		lastRecievedFile = S3BucketPrefix + LASTRECIEVED
		region = REGION

	RDSclient = boto3.client('rds',region_name=region)
	S3client = boto3.client('s3',region_name=region)
	dbLogs = RDSclient.describe_db_log_files( DBInstanceIdentifier=RDSInstanceName, FilenameContains=logNamePrefix)
	lastWrittenTime = 0
	lastWrittenThisRun = None

	
	try:
		S3client.head_bucket(Bucket=S3BucketName)
	except botocore.exceptions.ClientError as e:
		error_code = int(e.response['ResponseMetadata']['HTTPStatusCode'])
		if error_code == 404:
			raise Exception("Error: Bucket name provided not found")
		else:
			raise Exception("Error: Unable to access bucket name, error: " + e.response['Error']['Message'])
	try:
		lrfHandle = S3client.get_object(Bucket=S3BucketName, Key=lastRecievedFile)
	except botocore.exceptions.ClientError as e:
		error_code = int(e.response['ResponseMetadata']['HTTPStatusCode'])
		if error_code == 404:
			print("It appears this is the first log import, so all files will be retrieved from RDS.")
			firstRun = True
		else:
			raise Exception("Error: Unable to access lastRecievedFile name, error: " + e.response['Error']['Message'])

	if firstRun == False:
		lastWrittenTime = int(lrfHandle['Body'].read())
		if lastWrittenTime == 0 or lastWrittenTime == None:
			raise Exception("Error: Existing lastWrittenTime is " + lastWrittenTime)
		print("Found marker from last log download, retrieving log files with lastWritten time after %s" % str(lastWrittenTime))
	
	writes = 0;
	hasRun = False;

	for dbLog in dbLogs['DescribeDBLogFiles']:

		# We're only doing one log file
		## You could modify the script to accept an argument as to which log file to process,
		## and create 25 lambdas: general/mysql-general.log.{0-23}, plus general/mysql-general.log
		## You would also need to modify the script to create/read the lastWritten marker for each file.
		# if dbLog['LogFileName'] != 'general/mysql-general.log':
		# 	print("Ignoring log file", dbLog['LogFileName'])
		# 	continue
		# else:
		# 	print("Processing log file", dbLog['LogFileName'])

		if ( int(dbLog['LastWritten']) > lastWrittenTime ) or firstRun:
			print("Downloading DB log file: %s found with LastWritten value of: %s " % (dbLog['LogFileName'], dbLog['LastWritten']))
			
			if int(dbLog['LastWritten']) > lastWrittenThisRun:
				lastWrittenThisRun = int(dbLog['LastWritten'])

			logFile = RDSclient.download_db_log_file_portion(DBInstanceIdentifier=RDSInstanceName, LogFileName=dbLog['LogFileName'], Marker='0')
			logFileData = logFile['LogFileData']
			
			while logFile['AdditionalDataPending']:
				logFile = RDSclient.download_db_log_file_portion(DBInstanceIdentifier=RDSInstanceName, LogFileName=dbLog['LogFileName'], Marker=logFile['Marker'])
				logFileData += logFile['LogFileData']
			byteData = str.encode(logFileData)
			
			try:
				objectName = S3BucketPrefix + dbLog['LogFileName']
				print("Attempting to write log file %s to S3 bucket %s" % (objectName, S3BucketName))
				S3client.put_object(Bucket=S3BucketName, Key=objectName, Body=byteData)
			except botocore.exceptions.ClientError as e:
				raise Exception("Error writing log file to S3 bucket, S3 ClientError: " + e.response['Error']['Message'])
			
			hasRun = True;
			writes+=1;
			print("Successfully wrote log file %s to S3 bucket %s" % (objectName, S3BucketName))
		
	# Otherwise, leave it alone
	if hasRun == True:	
		try:
			S3client.put_object(Bucket=S3BucketName, Key=lastRecievedFile, Body=str.encode(str(lastWrittenThisRun)))
		except botocore.exceptions.ClientError as e:
			raise Exception("Error writing marker to S3 bucket, S3 ClientError: " + e.response['Error']['Message'])
	else:
		print("No new log files were written during this execution.")

	print("------------ Writing of files to S3 complete:")
	print("Successfully wrote %s log files." % (writes))
	print("Successfully wrote new Last Written Marker to %s in Bucket %s" % (lastRecievedFile, S3BucketName))
	
	return "Log file export complete."
