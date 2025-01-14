# dStats


### Deploy container directly
```bash
docker pull arifcse21/dstats:latest
```

```bash
docker run -d --name docker-stats-web --privileged -v /var/run/docker.sock:/var/run/docker.sock -p 2743:2743 arifcse21/dstats:latest
```


### Run in docker manually

```bash
docker build -t dstats:latest .
```

```bash
docker run -d --name docker-stats-web --privileged -v /var/run/docker.sock:/var/run/docker.sock -p 2743:2743 dstats:latest
```

### Run in docker compose

```bash
docker compose up -d

docker compose down --remove-orphans --rmi all
```
