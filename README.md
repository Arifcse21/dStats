# dStats

### Run in docker manually

```bash
docker build -t dstats:0.1.0 .
```

```bash
docker run -d --name docker-stats-web --privileged -v /var/run/docker.sock:/var/run/docker.sock -p 2743:2743 dstats:0.1.0
```

### Run in docker compose

```bash
docker compose up -d

docker compose down --remove-orphans --rmi all
```
