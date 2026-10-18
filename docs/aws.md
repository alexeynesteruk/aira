# AWS service research and future options

> Superseded for the initial MVP on October 18, 2026. The user selected OpenAI instead of Bedrock. Follow the [current model provider decision](model-provider.md) for implementation and reviewer setup. AWS credentials and Textract are not MVP prerequisites.

The sections below preserve the October 17 AWS proposal and the service documentation verified that day. Their provider-specific instructions describe the superseded proposal and possible future options, not the current implementation requirements. The proposal used Bedrock inference with a local application runtime and considered pagewise Textract for scans. No AWS resources were provisioned, account access checked, inference run, or model performance measured during that research.

## Service boundary

| Capability | Earlier proposed direction | Reason and later trigger |
| --- | --- | --- |
| Language interpretation | Bedrock Runtime through a thin Boto3 adapter. | Structured policy and chart interpretation with configurable model/profile and region. |
| PDF processing | Native text/layout parser; trial synchronous Textract for suspect pages. | Avoid OCR work on usable text; add verified scan support within the tested input envelope. |
| Application runtime | Local FastAPI/React container. | Reviewers must run it on their own machines. |
| Metadata and artifacts | SQLite and local files. | A single local application needs persistence without infrastructure setup. |
| Cloud hosting | Later ECS Fargate, S3, shared database, and CloudWatch. | Useful when a hosted service is needed; not required by this assessment. |
| Durable background execution | Later SQS worker or, when justified, Step Functions. | Add when multiple workers, restart recovery, or long cross-service waits exceed the local executor. |
| Policy retrieval | Defer Knowledge Bases, OpenSearch, and embeddings. | The user supplies the relevant policy; retrieval must demonstrate a quality or scale benefit. |

The public [AWS prior authorization sample](https://github.com/aws-samples/sample-prior-authorization-assistant) is useful for its stage separation. Its deployed service set and decision aggregation are not requirements for Aira; the [implementation research](research.md#what-to-avoid-copying-from-reference-code) records the differences.

## Bedrock output contracts

Converse supports native structured output through `outputConfig.textFormat` on supported models. Strict tool definitions are another mechanism. Unsupported schema features are rejected before inference. Keep schemas stable across documents: first-use compilation can take minutes, and AWS documents a 24-hour compiled-grammar cache. Measure both cold and warm behavior before setting timeouts. [AWS structured outputs](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html).

The schema subset excludes recursion, numerical bounds, and string-length bounds; object schemas require `additionalProperties: false`. Therefore policy output uses flat node records with child IDs. Application validation enforces bounds, unique IDs, one root, valid references, acyclicity, reachability, and meaningful operator arity. A provider-compatible schema and the richer application contract are separate concerns. [AWS structured outputs](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html).

For Anthropic models, native citations cannot be combined with structured outputs. Use ordinary fields for document identity, page/span references, and excerpts, then resolve them against the preserved extraction. This validates provenance; semantic support and completeness still require the [evaluation cases](evaluation.md). [AWS structured outputs](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html).

The October 17 proposal identified Claude Sonnet 4.6 as a candidate using `us.anthropic.claude-sonnet-4-6`, a US geographic inference profile, from a supported source region such as `us-east-1`. The model card read then listed Converse and structured-output support. This was a candidate to evaluate, not a selected model or a claim that it is best. A geographic profile can route beyond the source region; it is not a promise of single-region execution. Reverify model lifecycle, regional availability, profile behavior, access, and output support before any future adoption. [AWS model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html).

The feasibility experiment must select and pin a tested default, a compatible Boto3/Botocore version, inference settings, and schema/prompt versions. Never assume every Bedrock model supports the same contract, or that every bare model ID supports on-demand inference in the chosen region.

## Reviewer credentials and configuration

Bedrock readiness involves model access as well as credentials. AWS documents first-use activation through Marketplace and provider-specific prerequisites; Anthropic through Bedrock Runtime requires its first-use form. Activation or account permissions may block invocation. Resolve onboarding before submission; application startup should not attempt subscription or permission changes. [AWS model access](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).

Use the SDK credential provider chain. For the container launch, the simplest initial path is temporary credentials supplied by the reviewer's environment: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_SESSION_TOKEN`, explicitly forwarded by Compose. Do not commit them. An AWS profile is an alternate route, but profile files and any necessary login cache must be mounted and refresh behavior tested; setting `AWS_PROFILE` alone does not expose host files inside Docker. [Boto3 credentials](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html).

Document `AWS_DEFAULT_REGION` or an explicit application-to-SDK region mapping, `BEDROCK_MODEL_ID`, input/output budgets, timeouts, and extraction mode. Pin dependencies whose service definitions recognize the chosen structured-output fields. Preflight should distinguish missing/expired credentials, unsupported region/model/schema, access denial, and transient service failure. `docker compose up --build` is the planned launch after prerequisite setup, and remains unverified until M6. [Boto3 configuration](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html).

Do not require the author's local gateway, MCP services, browser sessions, or private container registry. Deterministic fixture mode is for tests and must remain visibly separate from real assessment of new uploads.

## Textract scan experiment

For short documents, try synchronous `AnalyzeDocument` with `TABLES` and `LAYOUT` on rendered suspect pages. The SDK accepts document bytes, allowing this path without S3. Preserve raw blocks, relationships, geometry, and extraction-model version. Remap each call's page identity to the original PDF page. Pagewise processing is our design choice; cross-page sections and table continuity still require reconstruction and evaluation. [AnalyzeDocument API](https://docs.aws.amazon.com/textract/latest/APIReference/API_AnalyzeDocument.html).

Synchronous limits verified on October 17 were 10 MB per input and one page for PDF/TIFF. Asynchronous PDF/TIFF limits were 500 MB and 3,000 pages. Password-protected and XFA PDFs were unsupported. These are service ceilings, not application targets: reverify them and choose smaller measured limits if Textract is later adopted. Do not send an original multi-page chart to a synchronous operation. [Textract document limits](https://docs.aws.amazon.com/textract/latest/dg/limits-document.html).

M2 must validate native, full-scan, and mixed-page inputs, including tables, two columns, and page-spanning passages. Every original page must be represented. A low-quality or failed page cannot silently disappear from an otherwise completed assessment. OCR confidence concerns extraction quality; it is not a medical necessity score. If this path does not fit the delivery scope, explicitly mark scanned inputs unsupported rather than pretending the text-only path handles them.

For longer scanned documents, asynchronous analysis adds S3 input, `StartDocumentAnalysis`, a persisted job ID, and retrieval through `GetDocumentAnalysis`. AWS recommends completion notifications through SNS/SQS instead of repeated Get calls to discover completion. Consume all `NextToken` result pages. Matching Start requests can be deduplicated with `ClientRequestToken` for seven days; changed parameters under the same token fail. Default results last seven days, so persist artifacts needed for later source inspection. This is a later option, not a required infrastructure stack for the small pagewise experiment. [Textract asynchronous operations](https://docs.aws.amazon.com/textract/latest/dg/api-async.html).

## Reliability and measurement

Use standard SDK retries with an explicit finite attempt budget and an application stage deadline. `AWS_MAX_ATTEMPTS` counts the initial request in its total; similarly named SDK settings may use different conventions. Set connect/read timeouts deliberately, allowing for structured-output cold compilation. Avoid multiplying SDK retries by an unbounded application retry loop. [Boto3 configuration](https://docs.aws.amazon.com/boto3/latest/guide/configuration.html).

Retry transient failures with backoff and jitter; configuration and invalid-input failures need corrective action. Record service error codes rather than assuming all throttling looks like HTTP 429. A timeout may follow work already performed by a provider, so do not promise exactly-once inference charges. These design rules follow the failure and retry principles in the [AWS Builders' Library](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/).

Persist input hashes and configuration versions alongside stage state, AWS request IDs when available, elapsed time, attempts, and usage. Reuse only completed validated artifacts with matching fingerprints. A failed provider or parser stage produces an operational failure, never a clinical `missing` or `not_met` finding. Measure actual tokens, OCR pages, cold/warm latency, and failed/retried work before estimating spend. No price or performance estimate is established yet.

## Hosted extension

ECS Fargate is a reasonable later target for the same application container. It removes host management but still requires networking, IAM, resource sizing, and deployment configuration. Use task-role credentials for application API calls; move documents/artifacts to S3 and shared metadata to Postgres before running multiple instances. Add an HTTP entry point and service monitoring as part of that deployment. This is a proposed extension based on [AWS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html), not current infrastructure.

Add a durable queue and worker when concurrency or restart recovery requires them. Consider Step Functions when coordinating long-running services becomes harder to operate than its setup cost. None of those changes replaces the assessment's local launch contract or demonstrates better evidence quality by itself.
