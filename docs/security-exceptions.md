# Checkov exceptions

CI fails on unhandled Checkov findings. The small allowlist in `.checkov.yml`
documents controls that are inapplicable or intentionally deferred for this
cost-aware, single-account training environment.

| Policy | Reason | Production treatment |
|---|---|---|
| CKV_AWS_260 | ALB port 80 performs a redirect only | Keep redirect or disable port 80 entirely |
| CKV_AWS_338 | Lab logs expire after 30 days | Retain according to the organization's evidence policy |
| CKV_AWS_117 | Responders call AWS APIs and require no VPC path | Keep outside VPC unless private endpoints are required |
| CKV_AWS_272 | No artifact-signing pipeline exists in the lab | Add Signer profile and signed release workflow |
| CKV_AWS_109/111/356 | KMS key policies use `Resource = "*"` to refer to the key itself | Preserve constrained principals and SourceAccount conditions |
| CKV_AWS_18 | Audit and access-log buckets are terminal log sinks | Send data events to CloudTrail; do not create recursive access logs |
| CKV2_AWS_3 | The lab is not a GuardDuty organization administrator | Delegate an organization admin in a multi-account landing zone |
| CKV_AWS_145 | ALB access-log delivery uses SSE-S3 | Follow current ELB encryption support and organizational requirements |
| CKV_AWS_144 | Cross-Region replication adds recurring lab cost | Enable replication for production disaster recovery |
| CKV2_AWS_5 | Scanner cannot resolve the app SG attachment across the module boundary | Validate attachment in the Terraform plan |

Changing this list requires security review. `soft_fail` is disabled, so any
new, non-allowlisted failure blocks the pull request.
