# Distributed Vital Signs Monitoring System

## Overview

This project was developed by Lucas Braun and Cem Koca as part of the Digital Business Engineering M.Sc. curriculum at the [Herman Hollerith Center](https://www.hhz.de/en/), taught and supervised by Prof. Dr. Marco Aiello and Dr. Ilche Georgievski from the Department of Service Computing at Stuttgart University's [Institute of Architecture of Application Systems (IAAS)](https://www.iaas.uni-stuttgart.de/en/). One goal of this course is to learn how to design distributed algorithms by implementing a stand-alone distributed system. It is achieved through lectures and developing and demonstrating a self-built distributed system.

Our system implements a robust distributed system for continuous monitoring of vital signs (such as heart rate and body temperature) in care facilities. For demonstration purposes, vital sign data is simulated in this system. Our system connects multiple sensor nodes, each capable of generating and transmitting vital sign data, to ensure patient safety through real-time monitoring and immediate alerting when critical thresholds are exceeded.

Key features include:
- **Dynamic node discovery** via UDP multicast
- **Decentralized leader election** (Bully algorithm) for fault tolerance
- **Reliable alerting** using TCP for critical events
- **Automatic recovery** from node and leader failures
- **Scalable, self-organizing architecture** suitable for real-world environments

---

## Features

- **Automatic Node Discovery:**  
  Nodes announce themselves via UDP multicast and are dynamically integrated into the system.

- **Leader Election:**  
  The system uses the Bully algorithm to elect a leader node, which coordinates data collection and alerting. If the leader fails, a new leader is automatically elected.

- **Heartbeat Mechanism:**  
  All nodes send periodic heartbeats via UDP multicast. If a node (including the leader) fails to send heartbeats, it is detected as dead and recovery is initiated.

- **Sensor Data Monitoring:**  
  Nodes generate (simulated) sensor data and send it to the leader. The leader checks for threshold violations.

- **Reliable Critical Alerts:**  
  Critical alerts are sent from non-leader nodes to the leader via TCP for reliability. The leader then broadcasts alerts to all nodes via UDP multicast.

- **Fault Tolerance:**  
  The system is robust to node crashes, network partitions, and dynamic changes (nodes joining/leaving).

- **Clear Logging:**  
  All major events (discovery, leader election, alerts, failures) are clearly logged to the console.

---

## Architecture

- **Decentralized, leader-based distributed system**
- **Hybrid communication:**  
  - UDP multicast for discovery, heartbeats, and regular sensor data  
  - TCP unicast for critical alerts to the leader
- **Nodes identified by UUIDs** for global uniqueness

---

## How It Works

1. **Node Startup & Discovery:**  
   Each node generates a UUID and announces itself (with its IP) via UDP multicast. All nodes maintain a list of known nodes and their IPs.

2. **Leader Election:**  
   The Bully algorithm is used to elect a leader based on the highest UUID. If the leader fails (missed heartbeats), a new election is triggered.

3. **Sensor Data & Heartbeats:**  
   Nodes periodically generate and send sensor data and heartbeats via UDP multicast.

4. **Critical Alerts:**  
   If a node detects a threshold violation, it sends a critical alert to the leader via TCP. The leader then broadcasts the alert to all nodes.

5. **Failure Recovery:**  
   If a node or leader crashes, the system detects the failure and automatically recovers by electing a new leader and reintegrating recovered nodes.

---

## Requirements

- Python 3.7+
- Runs on Linux, macOS, or Windows (tested on Debian, Windows and macOS)
- Network must support UDP multicast for full functionality

---

## Usage

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/vital-signs-distributed-system.git
   cd vital-signs-distributed-system
   ```

2. **Run the system on each node:**
   ```bash
   python3 ds-project.py
   ```

3. **Monitor the console output** for status updates, leader election, sensor data, and alerts.

---

## Configuration

- **Thresholds, intervals, and ports** can be adjusted at the top of `ds-project.py`.
- **UUIDs** are generated at startup; for persistent identity, modify the code to save/load UUIDs from disk.

---

## Limitations & Future Improvements

- **Security:**  
  All communication is currently unencrypted. For production, add TLS/DTLS and authentication.
- **UUID Persistence:**  
  UUIDs are regenerated on each restart. Persist them for stable node identity.
- **Scalability:**  
  Suitable for small to medium deployments. For large-scale use, consider hierarchical leaders or sharding.
- **No Byzantine Fault Tolerance:**  
  The system handles crash and omission faults, but not arbitrary (malicious) faults.
