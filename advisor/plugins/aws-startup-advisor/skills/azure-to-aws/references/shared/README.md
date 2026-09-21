# azure-to-aws shared references

Skill-specific reference files for `azure-to-aws`. These are NOT vendored from
`skills/shared/` — they are authored specifically for this skill.

| File                       | Purpose                                                                  |
| -------------------------- | ------------------------------------------------------------------------ |
| `azure-pricing-cache.md`   | Azure resource pricing cache (source-side baseline for cost comparisons) |
| `schema-discover-azure.md` | Schema for `azure-resource-inventory.json`                               |

Do not confuse these with `references/vendored/` — those are synced copies of the
plugin-level canonical shared files and must not be hand-edited.
