`export SENTRY_DSN="http://34db819263f34c28809da045f841f045@devops-sentry-public-lb-1114947433.us-east-1.elb.amazonaws.com/2";

export SENTRY_PUBLIC_DSN="http://<>@devops-sentry-public-lb-718357739.us-east-1.elb.amazonaws.com/3"`

If you’re deploying to AWS, SENTRY_DSN should have `devops-sentry-public-lb-718357739.us-east-1.elb.amazonaws.com` replaced with `sentry-internal.devops.cloud.` so it stays on the private network.
