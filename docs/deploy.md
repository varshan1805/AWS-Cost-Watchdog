# Deploying the watchdog to your own AWS account

Written for Windows, from a fresh AWS account to the first email in your inbox.
Plan on about an hour the first time.

## 0. Before you start

Install these:

- **AWS CLI v2**: https://aws.amazon.com/cli/ (Windows installer)
- **Terraform 1.10 or newer**: in PowerShell, `winget install Hashicorp.Terraform`
- **Git**: https://git-scm.com/download/win
- **Python 3.12**, only if you want to run the tests locally

Then, in the AWS console, open **Billing and Cost Management > Budgets** and set a small monthly budget
alert on your account if you haven't already. The stack adds its own budget later, but do this first so
you're protected while you experiment.

## 1. Credentials for the one-time setup

The bootstrap step needs admin rights, once. Simplest way for a personal account:

1. IAM > Users > Create user, for example `bootstrap-admin`. Attach `AdministratorAccess`.
2. Open the user > Security credentials > Create access key > "Command Line Interface".
3. In PowerShell:
   ```powershell
   aws configure
   # paste the key and secret, region: ap-south-1, output: json
   aws sts get-caller-identity   # should print your account id
   ```

After step 2 below you won't need these keys again. Delete the access key once bootstrap is done.
GitHub never sees them.

## 2. Bootstrap: state bucket and GitHub deploy role

```powershell
cd terraform\bootstrap
terraform init
terraform apply -var="github_repo=varshan1805/aws-cost-watchdog"
```

Type `yes`. Note the two outputs:

```
deploy_role_arn = "arn:aws:iam::123456789012:role/cost-watchdog-github-deploy"
state_bucket    = "cost-watchdog-tfstate-123456789012"
```

If your repo has a different name, use that in `github_repo`. It has to match exactly, including case,
or GitHub won't be allowed to assume the role.

## 3. Repo settings on GitHub

Repo > **Settings > Secrets and variables > Actions**.

On the **Variables** tab, add:

| Name | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | the `deploy_role_arn` output |
| `TF_STATE_BUCKET` | the `state_bucket` output |

On the **Secrets** tab, add:

| Name | Value |
|---|---|
| `ALERT_EMAIL` | the email address that should get reports |

Optional variables (these defaults are used if you leave them out):

| Name | Default | For a quick demo |
|---|---|---|
| `AWS_REGION` | `ap-south-1` | |
| `SCHEDULER_DRY_RUN` | `true` | `false` once you've checked the logs |
| `LOOKBACK_DAYS` | `7` | `1` |
| `SNAPSHOT_MAX_AGE_DAYS` | `90` | `0` |
| `MONTHLY_BUDGET_USD` | `10` | |

## 4. Deploy

Repo > **Actions > Deploy > Run workflow**. Tests run first, then Terraform plans and applies.
It takes about two minutes.

If the apply fails with `AccessDenied` for some action, the error names it. Add that action to the
matching statement in `terraform/bootstrap/main.tf`, run `terraform apply` in the bootstrap folder again,
and re-run the workflow. The deploy role is deliberately tight, so this can happen on the first run.

## 5. Confirm the email subscription

AWS sends an "AWS Notification - Subscription Confirmation" email. Click **Confirm subscription**.
Check spam. Until you click it, no reports arrive.

## 6. Watch it catch something

Open **AWS CloudShell** (the `>_` icon at the top of the AWS console). It's a browser terminal with the
AWS CLI already set up.

```bash
git clone https://github.com/varshan1805/aws-cost-watchdog.git
cd aws-cost-watchdog
bash scripts/create_test_waste.sh
```

Run a scan straight away instead of waiting for 08:00:

```bash
aws lambda invoke --function-name cost-watchdog-scanner --region ap-south-1 out.json && cat out.json
```

You should get an email within a minute listing the volume, the Elastic IP, and (with
`SNAPSHOT_MAX_AGE_DAYS=0`) the snapshot. The instance shows up as idle after `LOOKBACK_DAYS` of doing nothing.

Look at the history in **DynamoDB > Tables > cost-watchdog-findings > Explore table items**.

## 7. Try the scheduler

It starts in dry-run mode, so it only logs what it would do:

```bash
aws lambda invoke --function-name cost-watchdog-scheduler --region ap-south-1 \
  --cli-binary-format raw-in-base64-out --payload '{"action": "stop"}' out.json && cat out.json
```

`out.json` lists the demo instance. Check **CloudWatch > Log groups > /aws/lambda/cost-watchdog-scheduler**
to see the "DRY RUN: would stop" line. When you're happy, set the `SCHEDULER_DRY_RUN` variable to `false`
and run the Deploy workflow again. Now it really stops tagged instances at 20:00 and starts them at 09:00 IST.

## 8. Screenshots worth taking for the README

- the report email
- a green Deploy run in the Actions tab
- the two Lambda functions and the three schedules in the console
- DynamoDB items showing the same resource flagged on several days
- the scheduler log line stopping the demo instance

## 9. Cleaning up

Delete the demo waste (do this, the Elastic IP costs money every hour):

```bash
bash scripts/cleanup_test_waste.sh
```

The watchdog itself can keep running; it costs a few cents a month. To remove it completely, run
`terraform destroy` from `terraform/` with your admin credentials (copy `backend.hcl.example` to
`backend.hcl` and fill in your bucket first, then `terraform init -backend-config=backend.hcl`).
Then destroy the bootstrap stack last. Its S3 bucket has versioning on, so empty it in the S3 console
(including old versions) before `terraform destroy` in `terraform/bootstrap`.
