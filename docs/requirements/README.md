# Requirements: the authoritative specification

The specification is the client's Business Requirements Document, in Arabic:

| | |
|---|---|
| Title | وثيقة متطلبات نظام ERP — ERP System Business Requirements Document |
| Version | v1.2, draft for review and approval (the cover's status: بانتظار المراجعة والاعتماد) |
| File | `وثيقة_متطلبات_نظام_ERP_v1.2.docx`, 64,403 bytes |
| SHA-256 | `4c5632e14c9a85683c35977a4cb88ddc37f46296453fc900815a54e695526e32` |
| Where it is kept | Outside git, with the project's shared documents. A copy may sit in `docs/` on a developer's machine; `.gitignore` keeps any `.docx` there out of the repository. |
| Requirement IDs | 183 (CORE, LIB, PRN, DOC, HAL, STU, APP, ACC, EXP, CRM, HR, TSK, RPT, AI, SEC, INT) |

Why it is not committed: it names the client and the authors and sets out the business's structure, prices and
rules. It holds no passwords, phone numbers, e-mail addresses or salaries (checked 21 Oct 2026), but it is the
client's document, and the repository may be shared with people who should not receive it. Commit it only if the
owner agrees.

To check a copy is the registered one:

```bash
shasum -a 256 "docs/وثيقة_متطلبات_نظام_ERP_v1.2.docx"
```

## Changes approved since v1.2

[v1.3-amendments.md](v1.3-amendments.md) lists, by requirement ID, every rule the owner has approved that changes
or adds to v1.2, with its date. Until the Word document is reissued as v1.3, **v1.2 plus those amendments** is
the specification; where they differ, the amendment wins.

Where each requirement stands in the system: docs/production-readiness-2026-10-21.md (section *Requirements*) and
docs/known-issues.md.
