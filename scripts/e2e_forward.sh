#!/usr/bin/env bash
# Opens the backend to the browser tests on 127.0.0.1:8090 (only this machine), for a throwaway site named in the
# X-Frappe-Site-Name header; static files still come from the development nginx on 127.0.0.1:8080.
# Stop it with: docker rm -f imed-e2e-forward
set -euo pipefail
NET=$(docker inspect frappe_docker-backend-1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')
IMAGE=$(docker inspect frappe_docker-backend-1 --format '{{.Config.Image}}')
docker rm -f imed-e2e-forward >/dev/null 2>&1 || true
docker run -d --rm --name imed-e2e-forward --network "$NET" -p 127.0.0.1:8090:8090 --entrypoint python3 "$IMAGE" -c '
import socket, threading
def pipe(a, b, done):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except OSError:
        pass
    try:
        b.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    done.append(1)
    if len(done) == 2:
        a.close(); b.close()
def serve(c):
    try:
        u = socket.create_connection(("backend", 8000))
    except OSError:
        c.close(); return
    done = []
    threading.Thread(target=pipe, args=(c, u, done), daemon=True).start()
    threading.Thread(target=pipe, args=(u, c, done), daemon=True).start()
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", 8090)); s.listen(128)
while True:
    c, _ = s.accept()
    threading.Thread(target=serve, args=(c,), daemon=True).start()
'
echo "forwarding 127.0.0.1:8090 -> backend:8000"
