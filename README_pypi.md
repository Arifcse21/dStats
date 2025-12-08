
# **dStats**

**dStats** is a real-time web-based monitoring tool that provides performance stats for Docker containers and visualizes their network connectivity graph.

---
## Run the Python pip package
```bash
pip install dStats
```

## Run the server:
```bash
dStats.server
```

## With Basic Authentication(Good for security)
```bash
USE_AUTH=true AUTH_USERNAME=<your_username> AUTH_PASSWORD=<your_password> dStats.server
```
## **Access the Application(Running on port 2743)**
- Open your browser and go to:  
  **http://localhost:2743**

---
## Example UI
![Alt docker stats and network graph](https://github.com/Arifcse21/dStats/blob/main/examples/stats-and-network-graph.png)
![Alt docker network graph](https://github.com/Arifcse21/dStats/blob/main/examples/network-visualizer-graph.png)
![Alt docker network graph](https://github.com/Arifcse21/dStats/blob/main/examples/stats-chart.png)

Here, you’ll find:
1. **Container Stats:** Real-time CPU, memory, and network I/O usage.
2. **Network Graph:** Visualization of container interconnections.

---
Note: To run continuously you can create a systemd service or use the [docker image](https://hub.docker.com/r/arifcse21/dstats)

---
## **Contribute to dStats Project**

Thank you for considering contributing to dStats! We appreciate all efforts, big or small, to help improve the [project](https://github.com/Arifcse21/dStats)
