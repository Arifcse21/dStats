
# **dStats**

**dStats** is a real-time web-based monitoring tool that provides performance stats for Docker containers and visualizes their network connectivity graph.

---
## **Run with Docker**
Pull and run the container from Docker Hub:

```bash
docker pull arifcse21/dstats:latest
```

Run the container with **NO** authentication:

```bash
docker run -d --name docker-stats-web --privileged \
-v /var/run/docker.sock:/var/run/docker.sock \
-p 2743:2743 arifcse21/dstats:latest
```

Run the container with authentication:

```bash
docker run -d --name docker-stats-web --privileged \
-v /var/run/docker.sock:/var/run/docker.sock \
-p 2743:2743 \
-e USE_AUTH=true \
-e AUTH_USERNAME=<your_username> \
-e AUTH_PASSWORD=<your_password> \
arifcse21/dstats:latest
```

---

## Or You can run the Python pip package(requires Python 3.12+):
```bash
pip install dStats
```

Run the server:
```bash
dStats.server
```

With Basic Authentication
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

## **Contribute to dStats Project**

Thank you for considering contributing to dStats! We appreciate all efforts, big or small, to help improve the project.

### **How to Contribute**

We believe collaboration is key to building great software. Here’s how you can get involved:

1. **Report Issues**  
   Found a bug? Have a feature request? Open an issue [here](https://github.com/Arifcse21/dStats/issues).

2. **Suggest Enhancements**  
   Have an idea for improvement? Share it by opening a discussion or issue.

3. **Contribute Code**  
   Whether it’s fixing bugs, adding features, or enhancing documentation, here’s how to start:
   - Fork this repository.
   - Clone your fork:  
     ```bash
     git clone https://github.com/Arifcse21/dStats.git
     cd dStats
     ```
   - Create a branch:  
     ```bash
     git checkout -b my-feature
     ```
   - Commit your changes:  
     ```bash
     git commit -m "Add my feature"
     ```
   - Push your branch:  
     ```bash
     git push origin my-feature
     ```
   - Open a pull request on GitHub.

4. **Improve Documentation**  
   Good documentation helps everyone. Spot typos? Want to clarify something? Update the `README.md` or other docs and send us a PR.

---

### **Need Help?**

Feel free to reach out by opening a discussion on the repository. We’re here to help!  

Thank you for being part of this project. Together, we can make dStats even better. 🎉

--- 
