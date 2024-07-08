#!/bin/bash

set -eu -o pipefail

STACK_NAME=$1
if [[ -z "${STACK_NAME}" ]]; then
    echo "STACK_NAME must be set prior to running this script."
    exit 1
fi

TODAY=$(date +%Y%m%d)
# job log and json output file names
LOG_FILE="stack-drift-${STACK_NAME}-${TODAY}.log"
echo $STACK_NAME | tee ${LOG_FILE}

OUTPUT_FILE="stack-drift-${STACK_NAME}-${TODAY}.json"
echo $OUTPUT_FILE | tee ${LOG_FILE}

# to get a list of nested stack names for concordia's crowd environment based stack use the aws cli to
#   to fetch the arns and extract the name needed for the drift results command
#
NESTED_STACK_ARNS="$(aws cloudformation list-stack-resources \
    --stack-name ${STACK_NAME} \
    --query "StackResourceSummaries[*].PhysicalResourceId")"
echo "NESTED_STACK_ARNS: $NESTED_STACK_ARNS" | tee -a ${LOG_FILE}


COUNT=1;

for ARN in $NESTED_STACK_ARNS; do
    # Extract logical nested stack name from the arn
    NESTED_STACK_NAME="$(echo ${ARN} | awk -F'/' '{ print $2}')"

    # the list brackets in the result set will be blank - skip them
    if [[ $NESTED_STACK_NAME == "" ]]; then
        NESTED_STACK_NAME=None
        echo "skip not a valid value: $NESTED_STACK_NAME" | tee -a ${LOG_FILE};
    else
        echo "Nested stack name: $NESTED_STACK_NAME" | tee -a ${LOG_FILE};
        echo $COUNT;

        # fetch logical resources names where drift exists to report out the details
        # list of MODIFIED
        LOGICAL_RESOURCE_IDS_MODIFIED="$(aws cloudformation describe-stack-resources \
            --stack-name ${NESTED_STACK_NAME} \
            --query 'StackResources[?DriftInformation.StackResourceDriftStatus==`MODIFIED`].LogicalResourceId' --output text)"
        echo "LOGICAL_RESOURCE_IDS_MODIFIED: $LOGICAL_RESOURCE_IDS_MODIFIED" | tee -a ${LOG_FILE}

        for id in $LOGICAL_RESOURCE_IDS_MODIFIED; do
            echo "modified resource id: $id";
            aws cloudformation detect-stack-resource-drift --stack-name "$NESTED_STACK_NAME" --logical-resource-id "$id" >> "$OUTPUT_FILE" | tee -a ${LOG_FILE};
        done;

        # list of DELETED
        LOGICAL_RESOURCE_IDS_DELETED="$(aws cloudformation describe-stack-resources \
            --stack-name ${NESTED_STACK_NAME} \
            --query 'StackResources[?DriftInformation.StackResourceDriftStatus==`DELETED`].LogicalResourceId' --output text)"
        echo "LOGICAL_RESOURCE_IDS_DELETED: $LOGICAL_RESOURCE_IDS_DELETED" | tee -a ${LOG_FILE}

        for id in $LOGICAL_RESOURCE_IDS_DELETED; do
            echo "deleted resource id: $id";
            aws cloudformation detect-stack-resource-drift --stack-name "$NESTED_STACK_NAME" --logical-resource-id "$id" >> "$OUTPUT_FILE" | tee -a ${LOG_FILE};
        done;
        ((COUNT++));
    fi;
done;
RETURNCODE=$?

echo $RETURNCODE | tee -a ${LOG_FILE}

echo "Drift results saved to $OUTPUT_FILE" | tee -a ${LOG_FILE}
exit $RETURNCODE
EOF
