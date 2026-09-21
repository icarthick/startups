# Azure Pricing Cache

**Last updated:** 2026-09-21
**Source:** https://azure.microsoft.com/en-us/pricing/details/app-service/linux/,
https://azure.microsoft.com/en-us/pricing/details/azure-database-for-postgresql/,
https://azure.microsoft.com/en-us/pricing/details/storage/blobs/,
https://azure.microsoft.com/en-us/pricing/details/key-vault/,
https://azure.microsoft.com/en-us/pricing/details/cache/,
https://azure.microsoft.com/en-us/pricing/details/functions/
**Currency:** USD, East US region
**Accuracy:** ±10% (published list prices; actual may vary by reservation, region, and usage)

> Use this cache to derive an approximate current Azure monthly cost for comparison with the AWS
> estimate. Look up each discovered resource's plan in the tables below. If a plan is not found,
> set `azure_cost_source: "unavailable"` for that resource and exclude from total.
> These rates are approximate — do not use for contractual or billing purposes.

---

## App Service Plans (Linux, East US)

Source: https://azure.microsoft.com/en-us/pricing/details/app-service/linux/

| SKU               | vCPU | RAM (GB) | $/month (approx.) | Notes             |
| ----------------- | ---- | -------- | ----------------- | ----------------- |
| B1 (Basic)        | 1    | 1.75     | 13                | Dev/test          |
| B2 (Basic)        | 2    | 3.5      | 26                | Dev/test          |
| B3 (Basic)        | 4    | 7        | 52                | Dev/test          |
| S1 (Standard)     | 1    | 1.75     | 73                | Standard          |
| S2 (Standard)     | 2    | 3.5      | 146               | Standard          |
| S3 (Standard)     | 4    | 7        | 292               | Standard          |
| P1v2 (Premium v2) | 1    | 3.5      | 81                | Premium           |
| P2v2 (Premium v2) | 2    | 7        | 162               | Premium           |
| P3v2 (Premium v2) | 4    | 14       | 324               | Premium           |
| P1v3 (Premium v3) | 2    | 8        | 123               | Premium v3        |
| P2v3 (Premium v3) | 4    | 16       | 246               | Premium v3        |
| P3v3 (Premium v3) | 8    | 32       | 492               | Premium v3        |
| Y1 (Consumption)  | -    | -        | 0                 | Pay-per-execution |

---

## Azure Database for PostgreSQL — Flexible Server (East US)

Source: https://azure.microsoft.com/en-us/pricing/details/azure-database-for-postgresql/

| SKU                | vCPU | RAM (GB) | $/month (approx.) | Notes            |
| ------------------ | ---- | -------- | ----------------- | ---------------- |
| B_Standard_B1ms    | 1    | 2        | 14                | Burstable        |
| B_Standard_B2s     | 2    | 4        | 28                | Burstable        |
| GP_Standard_D2s_v3 | 2    | 8        | 93                | General purpose  |
| GP_Standard_D4s_v3 | 4    | 16       | 185               | General purpose  |
| GP_Standard_D8s_v3 | 8    | 32       | 370               | General purpose  |
| MO_Standard_E2s_v3 | 2    | 16       | 155               | Memory optimized |
| MO_Standard_E4s_v3 | 4    | 32       | 310               | Memory optimized |

Storage: ~$0.115/GB/month (General Purpose SSD).
Backup: first 100% of provisioned storage free; additional $0.095/GB/month.

---

## Azure Blob Storage (East US, LRS)

Source: https://azure.microsoft.com/en-us/pricing/details/storage/blobs/

| Tier              | $/GB/month (approx.) | Notes             |
| ----------------- | -------------------- | ----------------- |
| Hot (first 50 TB) | 0.018                | Standard tier     |
| Cool              | 0.01                 | Infrequent access |
| Archive           | 0.00099              | Rarely accessed   |

Operations: Hot PUT ~$0.0065/10K, GET ~$0.0052/10K.

---

## Azure Key Vault

Source: https://azure.microsoft.com/en-us/pricing/details/key-vault/

| Operation type                       | Rate                                |
| ------------------------------------ | ----------------------------------- |
| Secrets operations (first 10K/month) | $0.03/10K                           |
| Keys (RSA 2048) operations           | $0.03/10K                           |
| Per vault/month                      | ~$0 (no vault fee at standard tier) |

Estimate: ~$1-5/month per vault at moderate usage.

---

## Azure Cache for Redis (East US)

Source: https://azure.microsoft.com/en-us/pricing/details/cache/

| Tier        | Size   | $/month (approx.) | Notes           |
| ----------- | ------ | ----------------- | --------------- |
| Basic C0    | 250 MB | 16                | No SLA          |
| Basic C1    | 1 GB   | 55                | No SLA          |
| Standard C1 | 1 GB   | 110               | Replicated      |
| Standard C2 | 6 GB   | 218               | Replicated      |
| Premium P1  | 6 GB   | 405               | Cluster-capable |
| Premium P2  | 13 GB  | 810               | Cluster-capable |

---

## Azure Functions (Consumption Plan, East US)

Source: https://azure.microsoft.com/en-us/pricing/details/functions/

First 1M executions/month free; first 400K GB-seconds free.
After free tier: $0.20/million executions; $0.000016/GB-second.

Estimate for dev-scale: $0-5/month.
