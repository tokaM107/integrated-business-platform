# Local development stack

`pwd.yml` is the compose file that runs ERPNext locally with the `imed_erp` app mounted from this repository
(README, *Setup from scratch*). It started from upstream frappe/frappe_docker's `pwd.yml` and is kept here on its
own: the rest of that repository is not needed (removed on 1 Nov 2026; fetch it from
https://github.com/frappe/frappe_docker when upgrading the images).

```bash
cd frappe_docker && docker compose -p frappe_docker -f pwd.yml up -d
```
