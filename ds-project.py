import socket
import threading
import time
import random
import struct
import sys
import uuid
import signal
 
# --- Utility Functions ---
def get_local_ip():
    """Get the local IP address of the current machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP
 
# Configuration
MULTICAST_GROUP = '224.1.1.1'
MULTICAST_PORT = 5007
HEARTBEAT_INTERVAL = 2  # seconds
LEADER_TIMEOUT = 5      # seconds
SENSOR_DATA_INTERVAL = 3  # seconds
NODE_ID = str(uuid.uuid4())  # Unique ID for this node (UUID)
NODE_IP = get_local_ip()  # For logging/debugging only
ALERT_TCP_PORT = 6000  # TCP port for critical alerts
 
# Thresholds for vital signs
HEART_RATE_THRESHOLD = (50, 120)  # (min, max)
TEMP_THRESHOLD = (36.0, 38.0)     # (min, max)
 
# Node state
is_leader = False  # True if this node is the leader
leader_id = None   # Node ID of the current leader
last_leader_heartbeat = 0  # Timestamp of last heartbeat received from leader
node_list = set()  # Track known nodes (for demo)
node_ip_map = {}  # Maps node UUID to IP address
 
# For leader: store latest sensor data from each node
sensor_data_store = {}
 
# Election state
election_in_progress = False  # True if this node is currently running an election
received_ok = False           # True if this node received ELECTION_OK from a higher node
leader_elected_event = threading.Event()  # Event to signal when a leader is elected
 
# --- UDP Multicast Communication ---
def multicast_send(message: str):
    """Send a message to the multicast group."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Set TTL to 1 so the multicast doesn't leave the local network
    ttl = struct.pack('b', 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    try:
        sock.sendto(message.encode('utf-8'), (MULTICAST_GROUP, MULTICAST_PORT))
    finally:
        sock.close()
 
# --- Multicast Listener ---
def multicast_listener():
    """
    Listen for multicast messages (discovery, leader announcements, sensor data, etc.).
    Handles all distributed system communication and state updates.
    """
    global last_leader_heartbeat, leader_id, is_leader, node_list, sensor_data_store
    global election_in_progress, received_ok, leader_elected_event
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('', MULTICAST_PORT))
    except OSError:
        sock.bind((get_local_ip(), MULTICAST_PORT))
    mreq = struct.pack('4sl', socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    print_status(f"Listening for multicast messages on {MULTICAST_GROUP}:{MULTICAST_PORT}")
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8')
            # Ignore own messages (by IP and node ID)
            if addr[0] == get_local_ip() and msg.endswith(str(NODE_ID)):
                continue
            # --- Message type handling ---
            if msg.startswith("HEARTBEAT:"):
                # Heartbeat from a node (could be leader or sensor)
                sender_id = msg.split(":")[1]
                if leader_id is None or sender_id > leader_id:
                    leader_id = sender_id
                    last_leader_heartbeat = time.time()
                    is_leader = (leader_id == NODE_ID)
                    print_status(f"Updated leader to {leader_id}")
                elif sender_id == leader_id:
                    last_leader_heartbeat = time.time()
            elif msg.startswith("NODE_ANNOUNCE:"):
                parts = msg.split(":")
                sender_id = parts[1]
                sender_ip = parts[2] if len(parts) > 2 else addr[0]
                node_list.add(sender_id)
                node_ip_map[sender_id] = sender_ip
                print_status(f"Node discovered: {sender_id} with IP {sender_ip}")
            elif msg.startswith("SENSOR_DATA:"):
                # SENSOR_DATA:<node_id>:<heart_rate>:<temperature>
                parts = msg.split(":")
                if len(parts) == 4:
                    sender_id = parts[1]
                    hr = int(parts[2])
                    temp = float(parts[3])
                    if is_leader:
                        sensor_data_store[sender_id] = {'heart_rate': hr, 'temperature': temp}
                        check_thresholds({'heart_rate': hr, 'temperature': temp}, sender_id)
            elif msg.startswith("ALERT:"):
                # ALERT:<node_id>:<msg>
                parts = msg.split(":", 2)
                if len(parts) == 3:
                    alert_node = parts[1]
                    alert_msg = parts[2]
                    print_alert(f"Node {alert_node}: {alert_msg}")
            elif msg.startswith("ELECTION:"):
                candidate_id = msg.split(":")[1]
                print_status(f"Received ELECTION message from {candidate_id}")
                if NODE_ID > candidate_id:
                    print_status(f"Responding to ELECTION from {candidate_id} (my ID {NODE_ID} is higher)")
                    multicast_send(f"ELECTION_OK:{NODE_ID}")
                    if not election_in_progress:
                        print_status("Starting my own leader election after ELECTION message.")
                        threading.Thread(target=start_leader_election, daemon=True).start()
            elif msg.startswith("ELECTION_OK:"):
                print_status("Received ELECTION_OK from higher node.")
                received_ok = True
                leader_elected_event.set()
            elif msg.startswith("LEADER:"):
                new_leader = msg.split(":")[1]
                if new_leader > NODE_ID:
                    print_status(f"Received LEADER announcement: {new_leader}")
                    leader_id = new_leader
                    is_leader = (leader_id == NODE_ID)
                    last_leader_heartbeat = time.time()
                    print_status(f"New leader announced: {leader_id}")
                    election_in_progress = False
                    leader_elected_event.set()
                else:
                    print_status(f"Ignored LEADER announcement from {new_leader} (lower UUID than self)")
            elif msg.startswith("LEADER_ANNOUNCE:"):
                parts = msg.split(":")
                if len(parts) == 3:
                    leader_uuid = parts[1]
                    leader_ip = parts[2]
                    node_ip_map[leader_uuid] = leader_ip
                    print_status(f"Updated leader IP: {leader_uuid} -> {leader_ip}")
            print_status(f"Received multicast from {addr}: {msg}" + (" (self)" if addr[0] == NODE_IP or msg.endswith(str(NODE_ID)) else ""))
        except Exception as e:
            print_status(f"Multicast listener error: {e}")
            break
 
# --- Heartbeat Mechanism ---
running = True

def graceful_shutdown(signum, frame):
    global running
    print_status("Shutting down gracefully...")
    running = False
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

def send_heartbeat():
    """Send heartbeat messages to indicate this node is alive (leader or sensor)."""
    while running:
        heartbeat_msg = f"HEARTBEAT:{NODE_ID}"
        multicast_send(heartbeat_msg)
        time.sleep(HEARTBEAT_INTERVAL)
 
def monitor_heartbeats():
    """
    Monitor heartbeats from the leader. If the leader is unresponsive, start an election.
    """
    global last_leader_heartbeat, leader_id, is_leader
    while running:
        if leader_id is not None and leader_id != NODE_ID:
            elapsed = time.time() - last_leader_heartbeat
            if elapsed > LEADER_TIMEOUT:
                print_status("==============================")
                print_status(f"[ALERT] Leader {leader_id} is suspected dead! No heartbeat received for {elapsed:.1f} seconds.")
                print_status("==============================")
                if not election_in_progress:
                    threading.Thread(target=start_leader_election, daemon=True).start()
        time.sleep(1)
 
# --- Leader Election (Robust Bully Algorithm) ---
def start_leader_election():
    """
    Start the Bully leader election algorithm:
    - Send ELECTION to all nodes with higher IDs
    - Wait for ELECTION_OK responses
    - If none, announce self as leader
    - If a leader is announced, stop election
    """
    global leader_id, is_leader, election_in_progress, received_ok, leader_elected_event
    if election_in_progress:
        print_status("Election already in progress, not starting another.")
        return
    election_in_progress = True
    received_ok = False
    leader_elected_event.clear()
    print_status(f"Starting leader election as node {NODE_ID}...")
    multicast_send(f"ELECTION:{NODE_ID}")
    # Wait for ELECTION_OK from higher nodes
    election_timeout = 2
    start = time.time()
    while time.time() - start < election_timeout:
        if received_ok:
            print_status("Received ELECTION_OK, waiting for leader announcement.")
            break
        if leader_elected_event.is_set():
            # Someone else became leader
            print_status("Leader announcement received during election. Stopping election.")
            election_in_progress = False
            return
        time.sleep(0.1)
    if not received_ok:
        print_status("No higher node responded. Announcing self as leader.")
        announce_leader()
    else:
        print_status("Higher node responded, waiting for leader announcement.")
        # Wait for leader announcement
        wait_leader_timeout = 3
        start2 = time.time()
        while time.time() - start2 < wait_leader_timeout:
            if leader_elected_event.is_set():
                print_status("Leader announcement received after waiting.")
                break
            time.sleep(0.1)
    election_in_progress = False
 
def announce_leader():
    """Announce self as leader to the network."""
    global leader_id, is_leader
    leader_id = NODE_ID
    is_leader = True
    node_ip_map[NODE_ID] = NODE_IP  # Ensure leader knows its own IP
    print_status(f"Announcing self as leader: {NODE_ID}")
    multicast_send(f"LEADER:{NODE_ID}")
    multicast_send(f"LEADER_ANNOUNCE:{NODE_ID}:{NODE_IP}")
    print_status(f"Announced self as leader: {NODE_ID}")
 
# --- Sensor Data Generation & Threshold Checking ---
def generate_sensor_data():
    """Simulate sensor data (heart rate, temperature)."""
    return {
        'heart_rate': random.randint(40, 130),
        'temperature': round(random.uniform(35.0, 39.0), 1)
    }
 
def check_thresholds(data, node_id=None):
    """
    Check if sensor data exceeds thresholds and trigger alert if needed.
    If this node is the leader, broadcast the alert. Otherwise, send alert to leader via TCP.
    """
    hr = data['heart_rate']
    temp = data['temperature']
    alert_msgs = []
    if not (HEART_RATE_THRESHOLD[0] <= hr <= HEART_RATE_THRESHOLD[1]):
        alert_msgs.append(f"Heart rate out of range: {hr}")
    if not (TEMP_THRESHOLD[0] <= temp <= TEMP_THRESHOLD[1]):
        alert_msgs.append(f"Temperature out of range: {temp}")
    if alert_msgs:
        alert_msg = "; ".join(alert_msgs)
        if is_leader:
            broadcast_alert(f"{NODE_ID}:{alert_msg}")
        else:
            send_critical_alert_to_leader(f"{NODE_ID}:{alert_msg}")
        print_alert(f"{'(self)' if node_id is None else f'(node {node_id})'} {alert_msg}")
 
# --- Sensor Data Sending (for non-leader nodes) ---
def send_sensor_data():
    """
    Non-leader nodes periodically generate and send their sensor data to the leader.
    Also check their own data for threshold violations.
    """
    while running:
        if not is_leader and leader_id is not None:
            data = generate_sensor_data()
            msg = f"SENSOR_DATA:{NODE_ID}:{data['heart_rate']}:{data['temperature']}"
            multicast_send(msg)
            check_thresholds(data)  # Check own data and send alert if needed
        time.sleep(SENSOR_DATA_INTERVAL)
 
# --- Leader Responsibilities ---
def collect_sensor_data():
    """
    If this node is the leader, periodically generate its own data and check thresholds.
    Also stores latest data from all nodes (handled in listener).
    """
    while running:
        if is_leader:
            data = generate_sensor_data()
            sensor_data_store[NODE_ID] = data
            # Leader also sends its own sensor data
            msg = f"SENSOR_DATA:{NODE_ID}:{data['heart_rate']}:{data['temperature']}"
            multicast_send(msg)
            check_thresholds(data, NODE_ID)
        time.sleep(SENSOR_DATA_INTERVAL)
 
def broadcast_alert(alert_msg):
    """
    Broadcast alert messages to all nodes (used by leader).
    """
    multicast_send(f"ALERT:{alert_msg}")
    print_alert(f"Broadcasted alert: {alert_msg}")
 
# --- TCP Server for Critical Alerts (Leader Only) ---
def tcp_alert_server():
    """TCP server to receive critical alerts from other nodes."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((get_local_ip(), ALERT_TCP_PORT))
    server_sock.listen()
    print_status(f"Leader TCP alert server listening on port {ALERT_TCP_PORT}")
    while running:
        conn, addr = server_sock.accept()
        with conn:
            alert_msg = conn.recv(1024).decode('utf-8')
            if alert_msg:
                print_alert(f"Received critical alert via TCP from {addr[0]}: {alert_msg}")
                # Broadcast to all nodes via UDP multicast for awareness
                broadcast_alert(alert_msg)

def send_critical_alert_to_leader(alert_msg):
    """Send a critical alert to the leader via TCP."""
    if is_leader:
        print_status("Leader handling its own critical alert directly.")
        broadcast_alert(f"{NODE_ID}:{alert_msg}")
        return
    if leader_id and leader_id in node_ip_map:
        leader_ip = node_ip_map[leader_id]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect((leader_ip, ALERT_TCP_PORT))
                s.sendall(alert_msg.encode('utf-8'))
                print_status(f"Sent critical alert to leader {leader_id} ({leader_ip}) via TCP: {alert_msg}")
        except Exception as e:
            print_status(f"Failed to send critical alert to leader {leader_id} ({leader_ip}) via TCP: {e}")
    else:
        print_status(f"Leader IP address unknown for leader {leader_id}, cannot send critical alert.")
 
# --- Console Output ---
def print_status(msg):
    print(f"[STATUS] {msg}")
 
def print_alert(msg):
    print(f"[ALERT] {msg}")
 
# --- Main Loop ---
def main():
    """
    Main entry point: starts all threads for communication, heartbeats, data, and leader logic.
    """
    global is_leader, leader_id, last_leader_heartbeat
    print_status("==============================")
    print_status("Distributed System Node Starting Up")
    print_status(f"Node started with UUID {NODE_ID} and IP {NODE_IP}")
    # Announce self to the network with both UUID and IP
    announce_msg = f"NODE_ANNOUNCE:{NODE_ID}:{NODE_IP}"
    multicast_send(announce_msg)
    print_status(f"Sent announcement: {announce_msg}")
    # Start multicast listener thread
    listener_thread = threading.Thread(target=multicast_listener, daemon=True)
    listener_thread.start()
    # Start heartbeat sender thread
    heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
    heartbeat_thread.start()
    # Start heartbeat monitor thread
    monitor_thread = threading.Thread(target=monitor_heartbeats, daemon=True)
    monitor_thread.start()
    # Start sensor data sender thread (for non-leader nodes)
    sensor_sender_thread = threading.Thread(target=send_sensor_data, daemon=True)
    sensor_sender_thread.start()
    # Start leader's data collection thread
    leader_collector_thread = threading.Thread(target=collect_sensor_data, daemon=True)
    leader_collector_thread.start()
    # Start TCP alert server thread (for leader only)
    tcp_server_thread = threading.Thread(target=tcp_alert_server, daemon=True)
    tcp_server_thread.start()
    # Allow some time for messages to be received/printed
    time.sleep(2)
    # Main thread can be used for future extensions or just sleep
    while running:
        time.sleep(1)
 
if __name__ == "__main__":
    main()
