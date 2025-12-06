
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

# **Run with Docker**
## **Deploy Container Directly**
Pull and run the container from Docker Hub:

```bash
docker pull arifcse21/dstats:latest
```

Run the container:

```bash
docker run -d --name docker-stats-web --privileged \
-v /var/run/docker.sock:/var/run/docker.sock \
-p 2743:2743 arifcse21/dstats:latest
```

---

## **Clone the Repository**

If you’d like to explore or modify the project, start by cloning the repository:

```bash
git clone https://github.com/Arifcse21/dStats.git
cd dStats
```

---

## **Run with Docker Manually**

Build the Docker image locally:

```bash
docker build -t dstats:latest .
```

Run the container:

```bash
docker run -d --name docker-stats-web --privileged \
-v /var/run/docker.sock:/var/run/docker.sock \
-p 2743:2743 dstats:latest
```

---

## **Run with Docker Compose**

Use Docker Compose for easier setup and teardown:

1. Build and start the services:

   ```bash
   docker compose up -d
   ```

2. Stop and clean up the services:

   ```bash
   docker compose down --remove-orphans --rmi all
   ```

---

## **Access the Application**

- Open your browser and go to:  
  **http://localhost:2743**

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
