# AWS Lambda function to export Amazon RDS MySQL Query Logs to S3

Forked from: https://github.com/ryanholland/rdslogs_to_s3

### Forked Writings

#### Limitations & Scalability
As of this writing, Lambda functions are limited to 5 minutes of run time, ~1.5GB of memory, and ~500MB of disk space. Obviously, these are intended to be for quick execution of small programs. If you have a low-volume database, this solution will probably work.

However, for large databases, you will quickly hit either the memory or run time limits of Lambda--the log files become too large. If the function fails without a clear error, this may be the case. Check your CloudWatch logs for the function (there's a link in the Lambda, on the Monitoring tab, "View logs in CloudWatch"), and you'll see on the final "REPORT" line that indicates either the memory or run time maxed out.

I experimented with the possibility of creating 25 lambda functions--one each of `general/mysql-general.log.{0-23}`, plus `general/mysql-general.log`--but even the `general/mysql-general.log` alone hit Lambda's memory limit in my use case--the volume was simply too high at peak.

Since the disk space is less than max memory possible in Lambda, writing to a file and streaming the file into S3, isn't an option either. Also, since files cannot be appended to in S3, the entirety of the log file must be built first and held in Lambda's memory before being sent to S3, thus eliminating the possibility of streaming a given log file's chunks onto a single file in S3. You could potentially just write the individual chunks into S3 (instead of trying to construct a file from them), but this isn't an option I explored, and doesn't seem scalable; if one chunk again becomes so large that it exceed's Lambda's limits, you will now need to re-visit the solution. The smallest unit I attempted was a single log file.

So, if you have low volume, this solution might work for you. If you have medium volume, it might still work for you if you modify the script to only operate on one file, and create 25 Lambda's; I've left some comments in the code for a suggestion on how to modify the script for this. Otherwise, a more scalable ETL-style solution will be the right choice for you.

---

### Requirments
In order to enable query logging in RDS you must enable the general_log in the RDS Parameter Group with the output format to FILE
Details on how to do this are available from the Amazon RDS documentation 
http://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_LogAccess.Concepts.MySQL.html 

### Creating the IAM Execution Role

The AWS Lambda service uses an IAM role to execute the function, below is the IAM policy needed by the function to run.  
*Replace [BucketName] below with the name of the bucket in your account where you want the log files to be written to*
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": [
                "arn:aws:s3:::[BucketName]/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket"
            ],
            "Resource": [
                "arn:aws:s3:::[BucketName]"
            ]
        },
        {
            
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBLogFiles",
                "rds:DownloadDBLogFilePortion"
            ],
            "Resource": [
                "*"
            ]
        }
    ]
}
```

### Configuring the AWS Lambda fucntion
To create the new AWS Lambda function create a zip file that contains only the rds_mysql_to_s3.py and upload the zip file to a new AWS Lambda function.

The Lambda Handler needs to be set to: rds_mysql_to_s3.lambda_handler
The Runtime Environment is Python 2.7
Role needs to be set to a role that has the policy above.
Modify the Timeout value (under Advanced) from the default of 3 seconds to at least 1 minute, if you have very large log files you may need to increase the timeout even further.

### Creating a Test Event
The event input for the function is a JSON package that contains the information about the RDS instance and S3 bucket and has the following values:
```
{
  "BucketName": "[BucketName]",
  "S3BucketPrefix": "[Prefix to use within the specified bucket]/",
  "RDSInstanceName": "[RDS DB Instance Name]",
  "LogNamePrefix" : "general/mysql-general",
  "lastRecievedFile" : "lastWrittenMarker",
  "Region"  :"[RegionName]"
}
```

### Scheduling the AWS Lambda Function
Since RDS only maintains log files for a maximum of 24 hours or until the log data exceeds 2% of the storage allocated to the DB Instance its adviseable to have the function run at least once per day.  By setting up an Event Source in Lambda you can have the function run on a scheduled basis.  As new log files are retrieved from the RDS service they will overwrite older log files of the same name in the S3 bucket/prefix so you should retrieve the log files from S3 prior to subsequent runs of the function.  If you are going to leverage the Scheduled Event to call the function the event there is no way to pass a payload to the function so set the values at the top of the file with those the same values as the in the Test Event:
```
S3BCUKET='[BucketName]'
S3PREFIX='[Prefix to use within the specified bucket]/'
RDSINSANCE='[RDS DB Instance Name]'
LOGNAME='general/mysql-general'
LASTRECIEVED='lastWrittenMarker'
REGION='[RegionName]'
```

